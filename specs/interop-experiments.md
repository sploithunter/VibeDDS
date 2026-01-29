# Interop Experiments Log

## 2026-01-29 (RTI Connext 7.3.0.5, macOS, domain 0)

### Tooling setup
- NDDSHOME: `/Applications/rti_connext_dds-7.3.0`
- RTI Python API installed into local venv: `.venv-rti` using
  `rti.connext.activated-7.3.0-cp312-cp312-macosx_11_0_arm64.whl`
- Test harness: single-process RTI DataWriter + VibeDDS DataReader
  (topic `HelloWorld`, type `HelloWorld`, BEST_EFFORT)

### Script used (summary)
- Create RTI DomainParticipant + DataWriter (topic `HelloWorld`)
- Create VibeDDS DomainParticipant + DataReader (topic `HelloWorld`)
- Publish 5 samples from RTI
- Spin VibeDDS event loop and count received payloads
- Success condition: VibeDDS receives >=1 sample

### Matrix results
All cases below received **0** samples on VibeDDS:

| Case | Env Overrides |
|------|---------------|
| full_default | (none; default full profile) |
| full_no_xtypes | `VIBEDDS_SEDP_XTYPES=off` |
| full_no_datarep | `VIBEDDS_SEDP_DATA_REP=none` |
| full_allow_type | `VIBEDDS_SEDP_TYPE_CONSISTENCY=allow` |
| full_loc_both | `VIBEDDS_SEDP_LOCATOR_PID=both` |
| minimal | `VIBEDDS_SEDP_PROFILE=minimal` |
| minimal_with_guid | `VIBEDDS_SEDP_PROFILE=minimal`, `VIBEDDS_SEDP_INCLUDE_PARTICIPANT_GUID=1`, `VIBEDDS_SEDP_INCLUDE_PROTOCOL_VENDOR=1` |
| xcdr2_only | `VIBEDDS_SEDP_DATA_REP=xcdr2` |

### Interpretation (preliminary)
- SEDP discovery occurs, but RTI still does not match the VibeDDS reader
  for user data flow.
- Likely missing requirement is **TypeInformation / TypeObject** (PID 0x0075 or 0x8021)
  or an RTI-specific vendor PID needed for matching, rather than the basic
  QoS or locator formatting.
- DataRepresentation and TypeConsistency alone are insufficient to make
  RTI publish to VibeDDS.

### Next experiments to run
- Add `PID_XTYPES_TYPE_INFORMATION (0x0075)` with minimal TypeIdentifier for HelloWorld.
- Try `PID_TYPE_OBJECT (0x8021)` with RTI-compatible TypeObject bytes.
- Compare RTI SEDP subscription payload (via Wireshark) and mirror extra PIDs.
- Test whether RTI requires `PID_BUILTIN_ENDPOINT_QOS` or vendor-specific PIDs.

### Update: TypeInformation blobs captured (OpenDDS)
Using OpenDDS 3.34 `TypeSupportImpl::to_type_info` + `XTypes::serialize_type_info`,
we extracted XTypes TypeInformation blobs for common interop types:

| Type | Bytes | Hex (prefix) |
|------|-------|--------------|
| HelloWorld | 88 | `54000000011000402800000024000000...` |
| ShapeType | 88 | `54000000011000402800000024000000...` |
| PingType | 88 | `54000000011000402800000024000000...` |

These are now embedded in:
- `python/vibedds/type_support.py`
- `rust/vibedds/src/type_support.rs`

Next step: rerun RTI→VibeDDS with `PID_TYPE_INFORMATION` enabled and validate
whether RTI matches the reader once this parameter is present.

### 2026-01-29: RTI→VibeDDS with TypeInformation (HelloWorld)
- Env: `VIBEDDS_SEDP_INCLUDE_TYPE_INFORMATION=1` (plus default full profile)
- Result: **0 samples received** (RTI still shows 0 matched readers).
- Interpretation: TypeInformation alone is not sufficient; likely need either
  RTI-specific PID(s) or TypeObject in SEDP, or a strict assignability mismatch.

### 2026-01-29: RTI↔RTI vs VibeDDS↔RTI SEDP captures (pcap)
Captures were taken with `tshark` on `lo0` to see unicast SEDP traffic.

RTI↔RTI SEDP (see `logs/rti_rti3.sedp.txt`):
- **PID 0x8021 (TYPE_OBJECT)** present, len=200, payload begins with `78da` (zlib).
- **Vendor PIDs** present in endpoint DATA: `0x8000`, `0x8002`, `0x8009`, `0x8015`.
- **PID 0x0053** present with 4-byte value (likely Group Entity ID).
- **DATA_REPRESENTATION** len=12 (value `010000000000000007000000`).
- **TYPE_CONSISTENCY_ENFORCEMENT** len=8 (value `0100010100000000`).

VibeDDS→RTI SEDP (see `logs/vibedds_rti_lo.sedp.txt`):
- **No PID 0x8021**, **no vendor PIDs**, **no PID 0x0053**.
- **DATA_REPRESENTATION** len=8 (value `0100000000000000`).
- **TYPE_CONSISTENCY_ENFORCEMENT** len=12 (full XTypes struct).
- **TYPE_INFORMATION** len=88 present (OpenDDS-derived).

Conclusion: RTI expects additional TypeObject/vendor metadata and appears to use
shorter TypeConsistency/DataRepresentation encodings than VibeDDS currently sends.

### 2026-01-29: RTI ShapesDemo → VibeDDS (ShapeType)
- RTI side verified with `rtiddsspy -printSample` showing ShapeType samples on topic `Square`.
- VibeDDS subscriber initially discovered the writer but received no samples.
- Fix: include Partition QoS with `*` and serialize it in SEDP.
  - VibeDDS run: `VIBEDDS_SEDP_PROFILE=rti python examples/shape_sub.py --topic Square --partition "*"`.
- Result: **samples received** by VibeDDS (ShapeType blue square updates).
- Capture `logs/rti_shape.pcapng` shows RTI participants advertising
  `PID_PARTITION` with value `*` (sequence length 1, string "*").

Interpretation: RTI ShapesDemo uses partition `*`, and explicit partition
advertisement appears required for matching; missing `PID_PARTITION` can
block interop even when topics/types match.

### 2026-01-29: RTI ShapesDemo SEDP capture (rtiddsspy active subscriber)
- Capture: `logs/rti_shape2.pcapng` → `logs/rti_shape2.sedp.txt`
- Endpoint for topic `Square` (type `ShapeType`) includes:
  - `PID_PARTITION` with `*` (value `01000000020000002a000000`)
  - `PID_DATA_REPRESENTATION` value `020000000000020007000000`
  - `PID_TYPE_CONSISTENCY_ENFORCEMENT` value `0000010100000000`
  - Vendor PIDs: `0x8000`, `0x8002`, `0x8009`, `0x8015`, `0x8004`
  - `PID_TYPE_OBJECT (0x8021)` length 416 (ShapeType blob)
- ShapeType TypeObject bytes captured and embedded into:
  - `python/vibedds/type_support.py`
  - `rust/vibedds/src/type_support.rs`

### 2026-01-29: RTI HelloWorld SEDP refresh + timing
- RTI HelloWorld TypeObject (0x8021) observed in `logs/rtps_sniff_hello.log` differs
  from earlier capture (length 192, header `78 01 ... b1 00 00 00`).
  Updated `HELLOWORLD_TYPE_OBJECT` in both Python and Rust to match.
- Using participant_id=7 avoids port conflicts and allows SEDP discovery with RTI
  (remote HelloWorld writer appears after ~30s).
- Even after discovery, RTI does not send user data to VibeDDS yet.
  Remaining hypothesis: RTI still rejects our SEDP subscription or requires
  additional vendor PIDs/TypeInformation or a different TypeObject encoding.
