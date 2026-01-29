# VibeDDS Development Notes

## DDS Protocol Behavior

### DataWriter Message Sending
The default behavior of a DDS DataWriter is to NOT send any data messages unless there is a fully matched subscriber. This means:
- The writer must discover a reader via SEDP
- The reader's QoS must be compatible with the writer's QoS
- Only after the match is established will the writer send DATA messages to that reader

This is important for testing - if the writer hasn't matched any readers, calling `write()` will not result in any network traffic to user data ports.

### SEDP Discovery Flow
1. SPDP discovers remote participant via multicast
2. SEDP exchanges endpoint information (publications/subscriptions)
3. Writer/reader matching happens based on topic, type, and QoS compatibility
4. Only after matching does user data flow

## RTI Interop Notes

### Known Observations
- RTI uses XTypes PIDs (DATA_REPRESENTATION, TYPE_CONSISTENCY_ENFORCEMENT) in SEDP
- RTI entity IDs often have high bit set (e.g., 0x80000003 for user writers)
- RTI includes TYPE_OBJECT (PID 0x8021) with compressed type information
- RTI BUILTIN_ENDPOINT_SET is typically 0x0C3F (more flags than VibeDDS's 0x3F)

### VibeDDS → RTI (WORKING)
- VibeDDS writer can send data to RTI reader ✓
- Verified with rtiddsspy reading HelloWorld topic

### RTI → VibeDDS (IN PROGRESS)
Investigation status:
- SPDP discovery works bidirectionally ✓
- VibeDDS receives RTI's SEDP publications (discovers remote writer) ✓
- RTI receives and ACKs VibeDDS's SEDP subscription ✓
- Topic/type names match exactly ✓
- QoS is compatible (both BEST_EFFORT/VOLATILE) ✓
- RTI reports no incompatible QoS ✓
- BUT: RTI writer shows 0 matched subscriptions

Possible causes still being investigated:
1. TYPE_OBJECT (PID 0x8021) may be required for XTypes type checking
2. RTI vendor-specific PIDs (0x8000, 0x800f, 0x8010, etc.)
3. DATA_REPRESENTATION / TYPE_CONSISTENCY / TYPE_INFORMATION mismatches

### SEDP Subscription PIDs Included
VibeDDS includes these PIDs in SEDP subscription announcements:
- ENDPOINT_GUID, PARTICIPANT_GUID
- PROTOCOL_VERSION, VENDORID
- TOPIC_NAME, TYPE_NAME
- RELIABILITY (kind + max_blocking_time)
- DURABILITY, OWNERSHIP, LIVELINESS (with INFINITE lease)
- DESTINATION_ORDER, DEADLINE (INFINITE), HISTORY (KEEP_LAST, depth=1)
- DATA_REPRESENTATION (XCDR1 sequence<short>, XCDR1 only by default)
- TYPE_CONSISTENCY_ENFORCEMENT (XCDR1 struct, DISALLOW + all flags false)
- TYPE_INFORMATION (XTypes TypeInformation blob when known)
- PARTITION (empty = default partition)
- UNICAST_LOCATOR

### Interop Experiment Knobs
SEDP interop can be tuned via env vars (see `specs/interop-sedp-matrix.md`).
Key toggles: `VIBEDDS_SEDP_PROFILE`, `VIBEDDS_SEDP_XTYPES`,
`VIBEDDS_SEDP_DATA_REP`, `VIBEDDS_SEDP_TYPE_CONSISTENCY`,
`VIBEDDS_SEDP_LOCATOR_PID`, `VIBEDDS_SEDP_INCLUDE_TYPE_INFORMATION`.

Latest experiment outcomes are logged in `specs/interop-experiments.md`.

### Testing RTI Interop
```bash
# Start RTI publisher in one terminal
$NDDSHOME/bin/rtipublisher -domainId 0 -topic HelloWorld

# Start VibeDDS subscriber in another terminal
cd python && python examples/hello_sub.py
```
