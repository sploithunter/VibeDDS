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

### RTI → VibeDDS (WORKING)
- RTI writer sends data to VibeDDS reader ✓
- Verified with rti_test/test_rti_to_vibedds.py (12 samples received)
- RTI BEST_EFFORT writer matches VibeDDS BEST_EFFORT reader ✓
- RTI matched_subscriptions reports 1 matched subscription ✓

### Bugs Fixed for RTI Interop
1. **Transport binding** (transport.py): Metatraffic socket was bound to specific IP
   instead of INADDR_ANY. RTI sends same-host metatraffic via 127.0.0.1, which
   couldn't reach a socket bound to 192.168.1.12. Fixed by binding to "".
2. **Entity kind constants swapped** (constants.py): ENTITY_KIND_USER_READER_NO_KEY
   was 0x07 (which is actually WITH_KEY per RTPS spec 9.3.1.2) and vice versa.
   RTI rejected VibeDDS's reader because entity kind didn't match expectations.
3. **Reliability wire values** (qos.py): ReliabilityKind used 0/1 (DDS API values)
   instead of 1/2 (RTPS wire values per spec 9.4.2.13). RTI couldn't parse the
   reliability QoS back from matched subscription data.

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
