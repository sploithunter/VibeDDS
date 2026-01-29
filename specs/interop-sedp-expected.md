# SEDP Interop Data Expectations (RTI focus)

This spec documents the expected SEDP ParameterList data for interop with
RTI Connext, based on packet captures taken on 2026-01-29. It is intentionally
explicit about *bytes on the wire* to survive context compression and
experimentation.

## Scope
- Applies to SEDP Publications (writers) and Subscriptions (readers).
- Focus is the RTI Connext behavior observed in captures.
- Uses DDSI-RTPS ParameterList with PL_CDR_LE encapsulation (XCDR1).
 - `VIBEDDS_SEDP_PROFILE=rti` enables RTI-oriented defaults in VibeDDS.

## Required baseline PIDs (VibeDDS side)
These are the minimum PIDs VibeDDS must emit for endpoint discovery:
- PID_ENDPOINT_GUID (0x005A)
- PID_TOPIC_NAME (0x0005)
- PID_TYPE_NAME (0x0007)
- PID_RELIABILITY (0x001A)
- PID_DURABILITY (0x001D)
- One locator PID:
  - PID_UNICAST_LOCATOR (0x002F) or
  - PID_DEFAULT_UNICAST_LOCATOR (0x0031)

Recommended (RTI usually sends these):
- PID_PROTOCOL_VERSION (0x0015)
- PID_VENDORID (0x0016)
- PID_PARTICIPANT_GUID (0x0050)
- PID_PARTITION (0x0029)
  - Default partition: empty sequence
  - ShapesDemo: explicit `*` (sequence length 1, string "*")
- Extended QoS: OWNERSHIP, LIVELINESS, DESTINATION_ORDER, DEADLINE, HISTORY

## EntityId kinds for keyed topics
RTPS EntityId kinds must reflect whether a topic is keyed:
- Writer WITH_KEY: kind 0x02
- Writer NO_KEY: kind 0x03
- Reader WITH_KEY: kind 0x04
- Reader NO_KEY: kind 0x07

ShapeType (keyed by `color`) must use WITH_KEY entity kinds. Using NO_KEY can
prevent OpenDDS/RTI from matching endpoints even when topic/type names align.

## XTypes PID expectations
### PID_DATA_REPRESENTATION (0x0073)
Standard XTypes encoding (sequence<short> in XCDR1):
- For [XCDR1] only, value bytes are 8 bytes:
  - `01 00 00 00 00 00 00 00`
  - (count=1, element=0, padding)

RTI observed encoding (2026-01-29, HelloWorld):
- Value length = 12 bytes
- Value bytes:
  - `01 00 00 00 00 00 00 00 07 00 00 00`
- Interpretation is not fully known; treat as raw bytes when interoping
  with RTI to match observed behavior.

### PID_TYPE_CONSISTENCY_ENFORCEMENT (0x0074)
Standard XTypes encoding (XCDR1 struct):
- Value length = 12 bytes
- Fields: kind (i32) + 5 booleans + padding
- Default DISALLOW with all flags false -> all zero bytes.

RTI observed encoding (2026-01-29, HelloWorld):
- Value length = 8 bytes
- Value bytes:
  - `01 00 01 01 00 00 00 00`
- Interpretation is not fully known; treat as raw bytes for RTI interop.

### PID_TYPE_INFORMATION (0x0075)
- Value is XTypes TypeInformation encoded with XCDR2 (not CDR1).
- VibeDDS uses OpenDDS-captured TypeInformation for known types:
  - HelloWorld (88 bytes)
  - ShapeType (88 bytes)
  - PingType (88 bytes)
- See `python/vibedds/type_support.py` and `rust/vibedds/src/type_support.rs`.

### PID_TYPE_OBJECT (0x8021)
RTI includes a compressed TypeObject in endpoint DATA (len=192, zlib header
`78 da` in payload). Observed HelloWorld bytes:
```
01 00 00 00 78 01 00 00 b1 00 00 00 78 da 63 ac e7 60 00 01 1f 46 06 06 26
30 8b 85 41 0c 48 32 02 c5 39 81 f4 12 28 1b 04 14 c0 a4 18 98 fc a5 ff f4
0a 77 55 f6 3f 6e 20 db 23 35 27 27 3f 3c bf 28 27 05 a2 96 11 6c 0a 04 80
f8 29 68 fc 54 90 1e 10 1b c9 6c 15 06 04 10 86 d2 15 57 7d d2 2c 99 b6 54
82 54 e4 a6 16 17 27 a6 a7 62 98 cf 54 8f c0 20 51 61 a8 99 20 3d 25 48 e6 eb
80 d4 42 4d 86 99 2b 0a 64 17 97 14 65 e6 a5 c7 1b 99 9a c6 27 67 24 16 25 26 97
a4 16 c1 dc 89 cb 1f 3c 40 98 0a 95 01 89 9f 80 8a ff 47 72 0f 4c bf 00 3c c4 10 61
06 92 07 00 a6 e8 2f e3 00 00 00
```
This payload is added as a raw blob for HelloWorld interop experiments.

ShapeType TypeObject (len=416) was captured from RTI ShapesDemo and is stored
in:
- `python/vibedds/type_support.py` (`SHAPETYPE_TYPE_OBJECT`)
- `rust/vibedds/src/type_support.rs` (`SHAPETYPE_TYPE_OBJECT`)

RTI 0x8021 format (observed):
- 12-byte little-endian header: `{u32 kind, u32 uncompressed_len, u32 compressed_len}`
- zlib stream (XCDR2-serialized TypeObject)
- EquivalenceHash per spec: first 14 bytes of MD5(serialized TypeObject)

## RTI vendor-specific PIDs observed (endpoint DATA)
- 0x8000, 0x8002, 0x8004, 0x8009, 0x8015
Their semantics are unknown; VibeDDS does not emit them by default.
Observed RTI HelloWorld values (2026-01-29):
- 0x8000 = `07 03 00 05`
- 0x8002 = endpoint GUID (16 bytes)
- 0x8009 = `00 00 00 00`
- 0x8015 = `01 00 00 00 00 00 00 00`
- 0x0013 (writer) = `ff ff ff ff`
- 0x0018 (reader) = `ff ff ff ff`
- 0x0060 (writer) = `08 01 00 00`

## PID_GROUP_ENTITY_ID (0x0053)
RTI includes PID 0x0053 in endpoint data with 4-byte values:
- Writer example: `00 00 01 09`
- Reader example: `00 00 01 08`
VibeDDS can emit PID 0x0053 via an explicit override for experimentation.

## Configuration knobs (VibeDDS)
The following env vars allow precise control during interop testing:
- `VIBEDDS_SEDP_PROFILE=full|minimal|rti|rti_strict`
- `VIBEDDS_VENDOR_ID=<hex>` (override 2-byte vendor ID, e.g. `0101`)
- `VIBEDDS_KEYED_TYPES=<TypeName[,TypeName...]>` (mark types as keyed)
- `VIBEDDS_SEDP_XTYPES_FORMAT=standard|rti|raw`
- `VIBEDDS_SEDP_DATA_REP_RAW=<hex>`
- `VIBEDDS_SEDP_DATA_REP_TAIL=<u32>` (used with RTI layout)
- `VIBEDDS_SEDP_TYPE_CONSISTENCY_RAW=<hex>`
- `VIBEDDS_SEDP_TYPE_CONSISTENCY_MASK=<u32>` (used with compact layout)
- `VIBEDDS_SEDP_INCLUDE_TYPE_OBJECT=0|1`
- `VIBEDDS_SEDP_TYPE_OBJECT_HEX=<hex>` (global override)
- `VIBEDDS_SEDP_TYPE_OBJECT_HEX_<TypeName>=<hex>` (type-specific override)
- `VIBEDDS_SEDP_GROUP_ENTITY_ID=<u32>`
- `VIBEDDS_SEDP_INCLUDE_RTI_VENDOR_PIDS=0|1`
- `VIBEDDS_SEDP_INCLUDE_RTI_PID_8002_GUID=0|1`
- `VIBEDDS_SEDP_RTI_PID_8000=<hex>`
- `VIBEDDS_SEDP_RTI_PID_8004=<hex>`
- `VIBEDDS_SEDP_RTI_PID_8009=<hex>`
- `VIBEDDS_SEDP_RTI_PID_8015=<hex>`
- `VIBEDDS_SEDP_RTI_PID_0013=<hex>`
- `VIBEDDS_SEDP_RTI_PID_0018=<hex>`
- `VIBEDDS_SEDP_RTI_PID_0060=<hex>`
- `VIBEDDS_SEDP_INCLUDE_RELIABILITY=0|1`
- `VIBEDDS_SEDP_INCLUDE_DURABILITY=0|1`
- `VIBEDDS_SEDP_DATA_REP_WRITERS=0|1`
- `VIBEDDS_SEDP_DATA_REP_READERS=0|1`

Use raw overrides when matching RTI byte-for-byte. Start from minimal fields,
then add one PID at a time to identify which field unlocks matching.
- `VIBEDDS_SEDP_RTI_PID_8004=<hex>`
