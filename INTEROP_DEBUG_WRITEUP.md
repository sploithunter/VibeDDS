# VibeDDS RTI Connext DDS Interoperability: A Debugging Story

## The Goal

VibeDDS is a DDS (Data Distribution Service) implementation built from scratch in Python and Rust. The goal was full bidirectional interoperability with RTI Connext DDS 7.3.0, the industry-leading commercial DDS implementation. This document chronicles the debugging process that achieved that goal.

## Starting Point

VibeDDS had working SPDP (Simple Participant Discovery Protocol) — RTI and VibeDDS could discover each other's existence on the network. VibeDDS could also publish data that RTI's `rtiddsspy` tool could receive (VibeDDS → RTI direction). But the reverse direction — RTI publishing data that VibeDDS could receive — was completely broken.

The symptom was clear: RTI's writer reported **0 matched subscriptions** when VibeDDS had a reader on the same topic. RTI simply refused to acknowledge VibeDDS's reader existed.

## Phase 1: The SEDP Configuration Matrix (Dead End)

### The Hypothesis
DDS endpoint discovery (SEDP) uses Parameter List CDR encoding to exchange endpoint metadata. Different implementations include different PIDs (Parameter IDs) in their SEDP announcements. The initial hypothesis was that RTI was rejecting VibeDDS's SEDP subscription announcement because it was missing required PIDs or had them in the wrong format.

### What We Tried
Six different SEDP configurations were tested via environment variables:
- `VIBEDDS_SEDP_PROFILE=minimal` — bare minimum PIDs
- `VIBEDDS_SEDP_PROFILE=default` — standard DDS PIDs
- `VIBEDDS_SEDP_PROFILE=rti` — RTI-specific PIDs (DATA_REPRESENTATION, TYPE_CONSISTENCY_ENFORCEMENT)
- Various combinations of XTypes PIDs, TYPE_INFORMATION blobs, different locator formats

### The Result
**All six configurations failed identically.** RTI consistently showed 0 matched subscriptions. This was a strong signal that the problem was not in the SEDP payload content at all — it was somewhere more fundamental.

## Phase 2: Transport-Level Investigation (Root Cause #1)

### The Breakthrough Insight
If all SEDP configurations fail, the packets probably aren't arriving at all. The problem shifted from "what are we saying" to "can they even hear us."

### Discovery: Socket Binding
VibeDDS's metatraffic unicast socket was bound to the machine's specific IP address:

```python
# transport.py (BEFORE)
sock.bind((self.local_ip, self._metatraffic_unicast_port))
# Binds to e.g., 192.168.1.12:7416
```

On macOS, when two DDS participants run on the same host, they communicate via `127.0.0.1` (localhost). RTI was sending SEDP traffic to VibeDDS's metatraffic port — but via `127.0.0.1`, not via `192.168.1.12`. A socket bound to `192.168.1.12` cannot receive packets sent to `127.0.0.1`, even on the same machine.

### The Fix
```python
# transport.py (AFTER)
sock.bind(("", self._metatraffic_unicast_port))
# Binds to INADDR_ANY — accepts packets on any interface
```

### How It Was Found
A raw UDP sniffer script (`scripts/udp_sniffer.py`) was used to monitor all traffic on VibeDDS's metatraffic port. It showed:
- RTI was sending SEDP packets to `127.0.0.1:7416`
- VibeDDS's socket bound to `192.168.1.12:7416` was receiving **zero** of them

### macOS SO_REUSEPORT Complication
During debugging, we also discovered that macOS's `SO_REUSEPORT` behavior can cause stale processes to steal unicast packets. If a previous VibeDDS process died without closing its socket, the OS kernel could route incoming unicast packets to the dead socket instead of the new one. This caused intermittent failures that were extremely confusing. The fix was to always `pkill` stale processes before testing.

### Result After Fix
After binding to `INADDR_ANY`, VibeDDS's metatraffic socket started receiving RTI's SEDP packets. But RTI still reported 0 matched subscriptions. The packets were arriving, but something in their content was wrong.

## Phase 3: Entity Kind Constants (Root Cause #2)

### Discovery: Swapped Reader Entity Kinds
The RTPS specification (Section 9.3.1.2) defines entity kind bytes for identifying the type of each endpoint:

| Entity Kind | Value | Description |
|-------------|-------|-------------|
| USER_WRITER_WITH_KEY | 0x02 | Keyed writer |
| USER_WRITER_NO_KEY | 0x03 | Non-keyed writer |
| USER_READER_NO_KEY | 0x04 | Non-keyed reader |
| USER_READER_WITH_KEY | 0x07 | Keyed reader |

VibeDDS had these **swapped**:
```python
# constants.py (BEFORE - WRONG)
ENTITY_KIND_USER_READER_WITH_KEY = 0x04  # Should be 0x07!
ENTITY_KIND_USER_READER_NO_KEY = 0x07    # Should be 0x04!
```

### Why This Mattered
When VibeDDS created a non-keyed reader (e.g., for `HelloWorld` with no key fields), it assigned entity kind `0x07` — which RTI interpreted as a **keyed** reader. RTI's writer was publishing non-keyed data, so it refused to match with what it believed was a keyed reader. The entity ID embedded in the SEDP subscription data told RTI "I'm a keyed reader" when VibeDDS meant "I'm a non-keyed reader."

### The Fix
```python
# constants.py (AFTER - CORRECT per RTPS spec 9.3.1.2)
ENTITY_KIND_USER_READER_NO_KEY = 0x04
ENTITY_KIND_USER_READER_WITH_KEY = 0x07
```

The same fix was applied to the Rust implementation (`rust/vibedds/src/constants.rs`).

### How It Was Found
After the transport fix enabled VibeDDS to receive RTI's SEDP data (and thus discover RTI's writer), the E2E test (`rti_test/test_rti_to_vibedds.py`) showed:
- SPDP discovery: PASS
- SEDP remote writer found: PASS
- RTI matched_subscriptions: **FAIL (0)**
- Data received: FAIL

RTI could see VibeDDS's subscription in SEDP, but rejected the match. Comparing VibeDDS's entity ID (`00000107`) with the RTPS spec revealed the entity kind byte `0x07` should mean "reader with key," not "reader no key." A simple swap.

### Result After Fix
After fixing the entity kinds, RTI's writer reported **1 matched subscription** for the first time. Data started flowing from RTI to VibeDDS.

## Phase 4: Reliability Wire Values (Root Cause #3)

### Discovery: Wrong Enum Values on Wire
With RTI now matching VibeDDS's reader, data flowed successfully — but RTI logged a warning:
```
DDS_ReliabilityQosPolicy_from_presentation_reliability_kind:ERROR: Bad parameter: src
```

This error appeared when RTI tried to read back the reliability QoS from VibeDDS's matched subscription data. The RTPS wire protocol uses different values for reliability than the DDS API:

| Reliability | DDS API | RTPS Wire (Spec 9.4.2.13) |
|-------------|---------|---------------------------|
| BEST_EFFORT | 0 | **1** |
| RELIABLE | 1 | **2** |

VibeDDS was sending the DDS API values (0 and 1) on the wire, but RTI expected the RTPS wire values (1 and 2).

```python
# qos.py (BEFORE - DDS API values)
class ReliabilityKind(enum.IntEnum):
    BEST_EFFORT = 0
    RELIABLE = 1

# qos.py (AFTER - RTPS wire values per spec 9.4.2.13)
class ReliabilityKind(enum.IntEnum):
    BEST_EFFORT = 1
    RELIABLE = 2
```

### How It Was Found
The RTI error message `Bad parameter: src` in RTI's logs pointed directly at the reliability QoS deserialization. Cross-referencing RTPS spec Section 9.4.2.13 ("Mapping of the ReliabilityQosPolicy") confirmed the wire values differ from API values.

### Result After Fix
The RTI error disappeared. RTI could now fully parse VibeDDS's QoS data.

## Phase 5: Periodic SEDP Heartbeats

### The Problem
SEDP uses the RTPS reliable protocol: the writer sends DATA + HEARTBEAT, the reader responds with ACKNACK, and the writer retransmits if needed. If the initial SEDP exchange happened before both sides were fully ready, the SEDP data could be lost with no retry mechanism.

### The Fix
Added periodic SEDP heartbeat resending in `participant.py`:
```python
# In spin_once(), every 5 seconds:
if now - self._last_sedp_heartbeat >= self._sedp_heartbeat_interval:
    self._last_sedp_heartbeat = now
    self._resend_sedp_heartbeats()
```

This ensures that even if the initial SEDP exchange is lost due to timing, the reliable protocol eventually completes.

## Phase 6: Loopback Detection (Root Cause #4)

### Discovery
The comprehensive bidirectional test (`rti_test/test_bidirectional.py`) used distinct message prefixes — "Hello from RTI #N" and "Hello from VibeDDS #N" — to verify that each side received only the other's messages.

The test revealed that VibeDDS's reader was receiving **its own writer's messages** (loopback). VibeDDS's `DataWriter.write()` sends data both to matched remote readers via unicast AND to user multicast. The multicast packets bounced back to VibeDDS's own user multicast socket.

Additionally, VibeDDS was discovering **its own endpoints** as "remote" — because SEDP announcements sent to the SPDP multicast address would arrive back on VibeDDS's own multicast socket, get parsed as metatraffic (not SPDP), and cause self-discovery.

### The Fix
Added GUID prefix filtering in both metatraffic and user data packet handlers:
```python
def _handle_metatraffic_packet(self, data, addr, port):
    msg = RtpsMessageParser.parse(data)
    if msg.header.guid_prefix == self.guid_prefix:
        return  # Skip our own messages

def _handle_user_packet(self, data, addr, port):
    msg = RtpsMessageParser.parse(data)
    if msg.header.guid_prefix == self.guid_prefix:
        return  # Skip our own messages
```

This is the standard DDS approach — every RTPS message carries the sender's GUID prefix in the header, so receivers can trivially identify and drop their own messages.

### Result
After the fix, the bidirectional test confirmed:
- VibeDDS reader received **0 loopback messages** (its own)
- VibeDDS reader received **14 messages from RTI** (correct)
- RTI reader received **13 messages from VibeDDS** (correct)

## Final Verification

### Bidirectional Test Results
```
======================================================================
BIDIRECTIONAL TEST: RTI <-> VibeDDS with loopback detection
======================================================================

  [PASS] spdp_discovered
  [PASS] sedp_rti_writer_found
  [PASS] sedp_rti_reader_found
  [PASS] rti_matched_vibe_reader
  [PASS] rti_matched_vibe_writer
  [PASS] rti_to_vibe_data
  [PASS] vibe_to_rti_data

--- Direction 1: RTI -> VibeDDS ---
  RTI published: 15 samples
  VibeDDS received from RTI: 14 samples
  First: 'Hello from RTI #1'
  Last:  'Hello from RTI #14'

--- Direction 2: VibeDDS -> RTI ---
  VibeDDS published: 14 samples
  RTI received from VibeDDS: 13 samples
  First: 'Hello from VibeDDS #2'
  Last:  'Hello from VibeDDS #14'

--- Loopback Check ---
  OK: VibeDDS reader received 0 loopback messages

ALL TESTS PASSED - Bidirectional interop confirmed, no loopback
======================================================================
```

The slight difference in counts (14 received out of 15 published) is expected with BEST_EFFORT reliability — UDP packets can be lost, and the first few are sent before SEDP matching completes.

### RTI Note
RTI's own reader also receives RTI's own writer's messages (15 RTI loopback). This is expected behavior — RTI handles loopback at a higher layer in its middleware, where the application can choose to filter it. VibeDDS now filters at the RTPS transport layer.

## Summary of All Bugs Found

| # | Bug | File | Root Cause | Impact |
|---|-----|------|------------|--------|
| 1 | Metatraffic socket binding | `transport.py` | Bound to specific IP, not INADDR_ANY | RTI's localhost packets never arrived |
| 2 | Entity kind constants swapped | `constants.py` | READER_NO_KEY=0x07, should be 0x04 | RTI saw keyed reader, rejected match |
| 3 | Reliability wire values | `qos.py` | Used 0/1 (API), spec requires 1/2 | RTI couldn't parse reliability QoS |
| 4 | No loopback filtering | `participant.py` | No GUID prefix check on received packets | Reader received its own writer's data |

## Key Debugging Lessons

1. **Check transport first.** When all content variations fail identically, the problem is below the content layer. Six SEDP configurations all failing was a strong signal that packets weren't arriving at all.

2. **Same-host testing has hidden gotchas.** On macOS, same-host DDS participants communicate via `127.0.0.1`, not via the external IP. Binding to `INADDR_ANY` is essential.

3. **Kill stale processes.** macOS `SO_REUSEPORT` distributes unicast packets between all sockets bound to the same port. A stale process can silently steal packets from the active one.

4. **Wire values differ from API values.** The RTPS wire protocol often uses different numeric values than the DDS API for the same concepts. Always check the RTPS spec for wire encoding.

5. **Use distinct message content.** When testing bidirectional communication, each direction must use unique message prefixes to detect loopback and confirm which path data traveled.

6. **The spec is the ground truth.** Both the entity kind swap and the reliability wire values were caught by carefully reading the RTPS specification sections 9.3.1.2 and 9.4.2.13.

---

## Part 2: Porting to Rust and Full Cross-Compatibility

With Python↔RTI interop fully working, the next step was porting the same fixes to the Rust implementation and verifying full 6-way cross-compatibility: Python↔RTI, Rust↔RTI, and Rust↔Python.

## Phase 7: Porting Interop Fixes to Rust

### What Was Already Correct

Not all Python bugs existed in Rust. Two of the four root causes were already handled:

- **Transport binding** (`transport.rs`): Rust already bound to `Ipv4Addr::UNSPECIFIED` (INADDR_ANY). The Python-specific bug never existed in Rust because the Rust transport was written after learning from the Python debugging.
- **Loopback filtering** (`participant.rs`): Rust already checked `msg.header.guid_prefix == self.guid_prefix` in both `handle_metatraffic_packet` and `handle_user_packet`.

### What Needed Fixing

**ReliabilityKind wire values** (`qos.rs`): The Rust enum had the same DDS API values as Python:

```rust
// qos.rs (BEFORE - DDS API values, wrong on wire)
pub enum ReliabilityKind {
    BestEffort = 0,
    Reliable = 1,
}
```

Fixed to match RTPS wire protocol:

```rust
// qos.rs (AFTER - RTPS wire values per spec 9.4.2.13)
pub enum ReliabilityKind {
    BestEffort = 1,
    Reliable = 2,
}
```

The `from_u32()` parser was also updated to accept 0 as a backward-compatibility alias for BestEffort, since VibeDDS's own older serialized data might contain it.

**Entity kind constants** (`constants.rs`): Already fixed during the Python debugging phase. The swap was applied to both languages simultaneously.

### Unit Test Updates

Fixing `ReliabilityKind` values cascaded into test assertions:
- Reliability serialization test: expected wire byte changed from `1u32` to `2u32` for RELIABLE
- `from_u32` test: updated to reflect 1=BestEffort, 2=Reliable
- `test_create_reader`: entity kind assertion updated from `0x07` to `0x04` (matching the earlier constant fix)

All 154 unit tests + 17 wire compatibility tests passed after the fixes.

## Phase 8: The User Unicast Port Bug (Root Cause #5)

### Discovery During Interop Testing

The first Rust→RTI interop test (`test3_rust_pub_rti_sub.py`) initially failed with `Address already in use`. Rust's `hello_pub` example used `participant_id=0`, which collides with RTI's participant when both run on domain 0.

After changing Rust examples to use distinct participant IDs (hello_pub=5, hello_sub=4), a subtler bug appeared: Rust's `hello_pub` with participant_id=5 still had a port conflict with RTI's participant_id=0.

### Root Cause: D3 vs D2 in Port Formula

The RTPS specification defines four port offset constants:

| Constant | Value | Purpose |
|----------|-------|---------|
| D0 | 0 | SPDP multicast offset |
| D1 | 10 | Metatraffic unicast offset |
| D2 | 1 | User multicast offset |
| D3 | 11 | User unicast offset |

The port formula for user unicast is: `PB + DG * domain_id + D3 + PG * participant_id`

Rust's `constants.rs` was using **D2 (=1)** instead of **D3 (=11)**:

```rust
// constants.rs (BEFORE - wrong offset)
pub fn user_unicast_port(domain_id: u16, participant_id: u16) -> u16 {
    PB + DG * domain_id + D2 + PG * participant_id  // D2=1, WRONG!
}
```

This made Rust's user unicast port for participant_id=5 equal to `7400 + 0 + 1 + 10 = 7411`. But with the correct D3=11, RTI's participant_id=0 uses port `7400 + 0 + 11 + 0 = 7411`. Same port — collision.

Python already had this correct with `d3 = 11`.

### The Fix

```rust
// constants.rs (AFTER)
const D3: u16 = 11;

pub fn user_unicast_port(domain_id: u16, participant_id: u16) -> u16 {
    PB + DG * domain_id + D3 + PG * participant_id  // D3=11, correct
}
```

This changed port values:
- participant_id=0: 7401 → 7411
- participant_id=1: 7403 → 7413
- Domain 1, participant_id=0: 7651 → 7661

Four transport and participant tests needed their expected values updated accordingly.

### Why It Wasn't Caught Earlier

VibeDDS-only unit tests passed because they tested internal consistency — all ports were wrong by the same amount, so they didn't conflict with each other. The bug only manifested when sharing a network with an implementation using the correct D3 value.

This is a classic interop bug: internally consistent but externally wrong.

## Phase 9: Subprocess and Stdout Buffering (Test Infrastructure)

### The Problem

The Python→Rust interop test (`test6_python_pub_rust_sub.py`) required running the Rust `hello_sub` binary as a subprocess and parsing its stdout for "Received:" lines. The test consistently showed **0 messages received** even though manual testing confirmed data was flowing.

### Root Cause: C Runtime Block Buffering

When a process's stdout is connected to a pipe (via `subprocess.PIPE`), the C runtime switches from line buffering to **block buffering** with a 4KB or 8KB buffer. The Rust `hello_sub` binary uses `println!()`, which goes through the C runtime's stdout. With block buffering:

1. The Rust process receives DDS messages and prints "Received: ..." lines
2. These lines sit in an internal 8KB buffer, never flushed to the pipe
3. When the Python test sends SIGTERM, the Rust process exits
4. The unflushed buffer is **lost** — the data never reaches the pipe

### The Fix

The solution was structural:

1. **Run the binary directly** instead of via `cargo run` (which adds an intermediate process that complicates signal handling)
2. **Read stdout synchronously** after the process terminates using `rust_proc.stdout.read()`, not during execution
3. **Wait long enough** for enough messages to accumulate past the buffer boundary
4. **Send SIGTERM and wait** for graceful shutdown, which gives the Rust runtime a chance to flush

The working pattern:
```python
# Start Rust binary directly
rust_proc = subprocess.Popen([rust_binary], stdout=subprocess.PIPE, ...)

# Spin Python publisher continuously (discovery + data in same loop)
while time.time() - start < 30:
    dp.spin_once(timeout=0.1)
    if should_publish:
        writer.write(payload)

# Terminate and read all output
rust_proc.send_signal(signal.SIGTERM)
rust_proc.wait(timeout=5)
stdout_data = rust_proc.stdout.read()  # Read after termination
```

### Lesson

When testing DDS implementations via subprocess stdout, block buffering is a significant obstacle. Alternatives include:
- Writing received messages to a file and checking the file
- Using a network-based verification channel
- Accumulating enough output to trigger buffer flushes
- Using `stdbuf -oL` to force line buffering (Linux only)

## Phase 10: Full 6-Way Cross-Compatibility Verification

### Test Matrix

Six interop tests were run sequentially, with all DDS processes killed between tests to avoid port conflicts:

| Test | Direction | Result |
|------|-----------|--------|
| test1 | Python VibeDDS → RTI Connext | PASS |
| test2 | RTI Connext → Python VibeDDS | PASS |
| test3 | Rust VibeDDS → RTI Connext | PASS |
| test4 | RTI Connext → Rust VibeDDS | PASS |
| test5 | Rust VibeDDS → Python VibeDDS | PASS |
| test6 | Python VibeDDS → Rust VibeDDS | PASS |

All six tests verify:
- SPDP participant discovery
- SEDP endpoint discovery and matching
- User data delivery (correct content)
- No loopback (receiver doesn't see its own messages)

### Sample Output (Test 3: Rust → RTI)

```
============================================================
TEST 3: Rust VibeDDS Publisher -> RTI Connext DDS Subscriber
============================================================

[SETUP] Building Rust hello_pub example... Build successful
[SETUP] Rust hello_pub started (pid=38219)
[SETUP] RTI DDS BEST_EFFORT reader created on topic 'HelloWorld'

  [Rust TX] (message published by Rust example)
  [RTI  RX] Hello World from Rust VibeDDS! #2
  [RTI  RX] Hello World from Rust VibeDDS! #3
  [RTI  RX] Hello World from Rust VibeDDS! #4
  [RTI  RX] Hello World from Rust VibeDDS! #5
  [RTI  RX] Hello World from Rust VibeDDS! #6

RESULTS
  RTI received: 5 messages
  Correct messages: 5
  Wrong/loopback messages: 0

PASS - RTI received Rust VibeDDS messages, no loopback
```

### Three Implementations, Full Mesh

The complete verification covers every directed pair in the three-implementation triangle:

```
     Python VibeDDS
        ↕
RTI Connext ↔ Rust VibeDDS
```

Each arrow represents a verified, tested data path with content validation and loopback detection.

## Updated Summary of All Bugs Found

| # | Bug | File(s) | Root Cause | Impact |
|---|-----|---------|------------|--------|
| 1 | Metatraffic socket binding | `transport.py` | Bound to specific IP, not INADDR_ANY | RTI's localhost packets never arrived |
| 2 | Entity kind constants swapped | `constants.py`, `constants.rs` | READER_NO_KEY=0x07, should be 0x04 | RTI saw keyed reader, rejected match |
| 3 | Reliability wire values | `qos.py`, `qos.rs` | Used 0/1 (API), spec requires 1/2 | RTI couldn't parse reliability QoS |
| 4 | No loopback filtering | `participant.py` | No GUID prefix check on received packets | Reader received its own writer's data |
| 5 | User unicast port formula | `constants.rs` | Used D2=1 instead of D3=11 | Port collision with RTI on same host |

Bug #5 is notable because it only existed in Rust and was only discoverable through interop testing with another implementation. The Python code had D3=11 from the start.

## Files Modified

### Python (all bugs fixed)
- `python/vibedds/transport.py` — INADDR_ANY binding
- `python/vibedds/constants.py` — Entity kind swap
- `python/vibedds/qos.py` — Reliability wire values
- `python/vibedds/participant.py` — Loopback filtering + periodic SEDP heartbeats

### Rust (all bugs fixed)
- `rust/vibedds/src/constants.rs` — Entity kind swap + D3 port formula fix
- `rust/vibedds/src/qos.rs` — Reliability wire values
- `rust/vibedds/src/transport.rs` — Already correct (INADDR_ANY)
- `rust/vibedds/src/participant.rs` — Already correct (loopback filtering)
- `rust/vibedds/examples/hello_pub.rs` — BEST_EFFORT QoS, participant_id=5
- `rust/vibedds/examples/hello_sub.rs` — participant_id=4

### Tests and Tools
- `rti_test/test_rti_to_vibedds.py` — RTI→Python VibeDDS (test 2)
- `rti_test/test_bidirectional.py` — Python bidirectional test with loopback detection
- `rti_test/test3_rust_pub_rti_sub.py` — Rust→RTI (test 3)
- `rti_test/test4_rti_pub_rust_sub.py` — RTI→Rust (test 4)
- `rti_test/test5_rust_pub_python_sub.py` — Rust→Python (test 5)
- `rti_test/test6_python_pub_rust_sub.py` — Python→Rust (test 6)
- `rti_test/rti_hello_pub.py` — RTI publisher helper
- `scripts/udp_sniffer.py` — Raw UDP traffic monitor

## Tools That Were Useful

1. **RTI `rtiddsspy`** — Shows discovered endpoints and sample data
2. **RTI Python API (`rti.connextdds`)** — Programmatic access to RTI's DDS, essential for automated E2E tests
3. **Custom UDP sniffer** — Raw socket monitoring to verify packet delivery at the transport layer
4. **RTI `matched_subscriptions` / `matched_publications`** — Direct API to check if RTI has matched a remote endpoint, providing binary pass/fail for matching
5. **RTI `offered_incompatible_qos_status`** — Reports QoS mismatches, helped identify reliability issues
6. **`cargo build --example`** — Building Rust examples separately for subprocess testing
7. **`RUST_LOG=info`** — Rust's `env_logger` for debugging discovery and data flow in Rust examples

## Key Debugging Lessons (Updated)

1. **Check transport first.** When all content variations fail identically, the problem is below the content layer. Six SEDP configurations all failing was a strong signal that packets weren't arriving at all.

2. **Same-host testing has hidden gotchas.** On macOS, same-host DDS participants communicate via `127.0.0.1`, not via the external IP. Binding to `INADDR_ANY` is essential.

3. **Kill stale processes.** macOS `SO_REUSEPORT` distributes unicast packets between all sockets bound to the same port. A stale process can silently steal packets from the active one.

4. **Wire values differ from API values.** The RTPS wire protocol often uses different numeric values than the DDS API for the same concepts. Always check the RTPS spec for wire encoding.

5. **Use distinct message content.** When testing bidirectional communication, each direction must use unique message prefixes to detect loopback and confirm which path data traveled.

6. **The spec is the ground truth.** The entity kind swap, reliability wire values, and D3 port constant were all caught by carefully reading the RTPS specification.

7. **Interop testing catches what unit tests miss.** The D3 vs D2 port formula bug passed all unit tests because the error was internally consistent. Only when sharing ports with RTI did the collision reveal itself. Unit tests verify self-consistency; interop tests verify correctness.

8. **Prototype in Python, port to Rust.** Debugging protocol issues is dramatically faster in Python (no compile step, easy introspection, quick iteration). Once the protocol is correct in Python, porting to Rust is mechanical. Two of four Python bugs didn't even exist in Rust because the Rust code was written after learning from the Python debugging.

9. **Subprocess stdout buffering is treacherous.** When piping a Rust (or C) process's stdout through `subprocess.PIPE`, the C runtime switches to block buffering. Short-lived processes may never flush their output. Read stdout after process termination, not during execution.

10. **Use distinct participant IDs.** When running multiple DDS implementations on the same host, each needs a unique participant_id to avoid port collisions. This is especially important for testing where you control both endpoints.
