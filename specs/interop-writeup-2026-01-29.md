# Interop Write-up (2026-01-29)

This is a detailed status report of the interop work executed so far for VibeDDS,
with emphasis on RTI Connext and OpenDDS. It records the experiments, pcap captures,
code changes, and the current "works vs doesn't" state so future context compression
has minimal impact.

## Scope and environment
- Platform: macOS (local machine)
- Date: 2026-01-29
- RTI Connext: 7.3.0.5 (`NDDSHOME=/Applications/rti_connext_dds-7.3.0`)
- OpenDDS: built from `third_party/OpenDDS`
- VibeDDS: Python + Rust implementations in this repo
- Domain: 0

## What changed (code + tooling)
### VibeDDS (Python)
- Added keyed-entity detection and selection (defaulting `ShapeType` to keyed).
  This affects entityId kind (`*_WITH_KEY`) for DataWriters/DataReaders.
  - `python/vibedds/type_support.py`
  - `python/vibedds/topic.py`
  - `python/vibedds/participant.py`
- SEDP changes:
  - Send announcements to all discovered locators, not just the first.
  - Optionally include `INFO_DST` in SEDP for interop (`VIBEDDS_SEDP_INCLUDE_INFO_DST`).
  - Added extra logging for locator resolution, user traffic, and spdp source addr/port.
  - `python/vibedds/sedp.py`
  - `python/vibedds/participant.py`
- Transport changes:
  - Added user multicast socket and handler path.
  - Accept SEDP that arrives on multicast (fallback if SPDP socket sees non-SPDP).
  - `python/vibedds/transport.py`
  - `python/vibedds/participant.py`
- DataSubmessage parsing robustness:
  - Added fallback parsing when payload offset seems to match
    `octetsToInlineQos` rather than the assumed header offset.
  - `python/vibedds/wire.py`
- SPDP: store source addr/port for correct unicast replies.
  - `python/vibedds/spdp.py`

### VibeDDS (Rust)
- Added keyed-entity detection (`ShapeType` default) and correct entityId kind.
  - `rust/vibedds/src/type_support.rs`
  - `rust/vibedds/src/constants.rs`
  - `rust/vibedds/src/participant.rs`

### Tooling / docs
- Captured multiple RTI/VibeDDS/VibeDDS loopback SEDP pcaps and dumped
  decoded parameter lists.
- Added interop docs for RTI SEDP expected payloads and XTypes notes:
  - `specs/interop-sedp-expected.md`
  - `specs/interop-sedp-matrix.md`
  - `specs/interop-sedp-xtypes.md`
  - `specs/interop-experiments.md`
- Added OpenDDS sample app in `opendds_shape/` (ShapeType publisher/subscriber)
  for interop testing (RTPS transport). This is a convenience test harness.

## Captures and analysis (pcapng + decoded SEDP)
All captures are in `logs/` with decoded parameter lists in matching
`*.sedp.txt` files. These are the main ones used:

### RTI <-> RTI baseline
- `logs/rti_rti2.pcapng` / `logs/rti_rti2.sedp.txt`
- `logs/rti_rti3.pcapng` / `logs/rti_rti3.sedp.txt`

Observations:
- RTI includes vendor PIDs in endpoint DATA:
  `0x8000`, `0x8002`, `0x8009`, `0x8015`, and sometimes `0x8004`.
- `PID_TYPE_OBJECT (0x8021)` is present and zlib-compressed.
- `PID_DATA_REPRESENTATION` is encoded with a shorter 12-byte format
  (as observed in the capture) vs VibeDDS's 8-byte format in some cases.
- `PID_TYPE_CONSISTENCY_ENFORCEMENT` appears in a compact 8-byte format
  (not the full XTypes struct VibeDDS currently emits).

### RTI ShapesDemo SEDP (with active rtiddsspy subscriber)
- `logs/rti_shape.pcapng` / `logs/rti_shape.sedp.txt`
- `logs/rti_shape2.pcapng` / `logs/rti_shape2.sedp.txt`

Observations:
- `PID_PARTITION` is set to `*` for `ShapeType` endpoints.
  This appears required for matching (if missing, interop fails).
- RTI endpoint payload includes `PID_TYPE_OBJECT (0x8021)` len 416 for ShapeType.
- Vendor PIDs are present.
- `PID_DATA_REPRESENTATION` value observed for ShapesDemo:
  `020000000000020007000000`.
- `PID_TYPE_CONSISTENCY_ENFORCEMENT` value observed:
  `0000010100000000`.

### VibeDDS <-> RTI on loopback (unicast SEDP)
- `logs/vibedds_rti_lo.pcapng` / `logs/vibedds_rti_lo.sedp.txt`

Observations:
- VibeDDS sends `PID_TYPE_INFORMATION` (OpenDDS-derived 88-byte blobs).
- VibeDDS **does not** send vendor PIDs or `PID_TYPE_OBJECT (0x8021)`.
- VibeDDS sends `PID_TYPE_CONSISTENCY_ENFORCEMENT` in full XTypes struct format
  (length 12) rather than the shorter RTI format.
- `PID_DATA_REPRESENTATION` length/value differs from RTI's observed format.

### VibeDDS <-> VibeDDS baseline
- `logs/vibedds_vibedds_lo.pcapng` / `logs/vibedds_vibedds_lo.sedp.txt`

Observations:
- Baseline SEDP is consistent and decodes cleanly (useful for regression checks
  when changing SEDP serialization).

### Additional captures
- `logs/rtps_sniff_hello.log`, `logs/rtps_sniff_rti_sub.log`,
  `logs/rtps_sniff_bidir*.log` capture broader RTI/VibeDDS activity and were
  used to identify TypeObject payload variants and GUIDs.

## What was tested
### RTI
- **RTI ShapesDemo -> VibeDDS (ShapeType)**
  - VibeDDS subscriber with `partition="*"` receives samples after sending
    `PID_PARTITION` in SEDP.
  - Confirmed with `rtiddsspy -printSample` and VibeDDS logs.
  - Captures: `logs/rti_shape*.pcapng`, `logs/rti_shape*.sedp.txt`.
- **VibeDDS -> RTI Spy (ShapeType)**
  - RTI Spy sees VibeDDS writer and data for `Square` when partition matches.
  - Evidence in `logs/rtiddsspy_vibe*.log`.
- **RTI HelloWorld -> VibeDDS**
  - No samples delivered to VibeDDS despite discovery.
  - Multiple SEDP profiles tested (minimal, no xtypes, no data rep,
    type consistency allow, include participant guid, etc.).
  - VibeDDS still shows 0 matched reader in RTI.
  - See `specs/interop-experiments.md` for full matrix.

### OpenDDS
- **OpenDDS ShapeType pub/sub (OpenDDS -> OpenDDS)**
  - Local OpenDDS publisher/subscriber works and shows matching.
- **OpenDDS -> VibeDDS / VibeDDS -> OpenDDS**
  - VibeDDS can parse OpenDDS SEDP after multicast fallback changes.
  - VibeDDS logs show discovered OpenDDS endpoints (topic/type parsed).
  - OpenDDS reports *no matched subscriptions* when VibeDDS reader is present.
  - No user data observed in either direction (OpenDDS <-> VibeDDS).

## What works
- VibeDDS discovery of RTI participants (SPDP) and endpoint announcements (SEDP)
  is functional.
- VibeDDS can receive **RTI ShapesDemo samples** for `ShapeType` when the
  `PID_PARTITION` is explicitly provided (`*`).
- RTI Spy can receive **VibeDDS ShapeType samples** when topic and partition
  match (confirmed by rtiddsspy logs).
- VibeDDS can parse and decode OpenDDS SEDP announcements (topic/type are
  extracted), indicating the basic SEDP parser supports OpenDDS payloads.

## What doesn't work
- **RTI HelloWorld -> VibeDDS** still does not deliver user samples.
  Discovery succeeds but RTI does not match the VibeDDS reader.
- **OpenDDS <-> VibeDDS user data** does not flow in either direction yet.
  OpenDDS sees zero matched subscriptions with VibeDDS.

## Progress toward RTI interoperability (verbose)
### What is working
- SPDP discovery (bidirectional) is stable.
- SEDP parsing works and VibeDDS can interpret RTI endpoint announcements.
- ShapesDemo succeeds when partition is set to `*`.

### What is missing
- RTI expects additional SEDP metadata to match readers for at least
  HelloWorld and other non-Shape types.
- Evidence from RTI<->RTI captures shows RTI emits:
  - `PID_TYPE_OBJECT (0x8021)` with zlib-compressed blobs.
  - Vendor PIDs (`0x8000`, `0x8002`, `0x8009`, `0x8015`, `0x8004`).
  - Shorter encodings for DataRepresentation and TypeConsistency.
- VibeDDS currently does not emit these RTI-specific fields, and uses
  the full XTypes structure for TypeConsistency which does not match the
  compact RTI encoding.

### What likely blocks matching
- Missing RTI vendor PIDs and/or `PID_TYPE_OBJECT (0x8021)`.
- TypeConsistency and DataRepresentation formatting mismatch.
- Possible mismatch in TypeObject for HelloWorld (even when provided)
  based on varying capture payloads.

## Progress toward OpenDDS interoperability (verbose)
### What is working
- OpenDDS and VibeDDS discover each other (participant + endpoint discovery).
- VibeDDS can parse OpenDDS SEDP and discover OpenDDS endpoints.

### What is missing
- OpenDDS does not match VibeDDS subscriptions (pub side reports 0 matched).
- No user data flows in either direction.

### Likely causes
- Type compatibility mismatch (OpenDDS may require a different type
  representation or assignability flags).
- Locator mismatch: OpenDDS advertises unusual locators for user traffic
  (e.g., `127.0.0.1:12345` observed in logs), which may not be reachable
  for VibeDDS.
- VibeDDS may still lack some endpoint QoS parameter expected by OpenDDS
  or may be providing different representations for type info.

## Common issues vs. unique issues
### Common across RTI and OpenDDS
- **Endpoint matching is the gate**: discovery is visible but user data
  does not flow unless the remote implementation accepts VibeDDS's SEDP
  endpoint data.
- **Type metadata is critical**: missing or mismatched type information
  (TypeInformation / TypeObject / TypeConsistency) prevents matching even
  when topics and types are nominally the same.
- **QoS parameter formatting** matters as much as presence; different
  binary representations can cause silent non-matching.

### Unique to RTI
- RTI emits and appears to require **vendor-specific PIDs** and
  `PID_TYPE_OBJECT (0x8021)` with zlib-compressed payloads.
- RTI ShapesDemo requires explicit `PID_PARTITION` with `*` to match.
- RTI seems to use **compact encodings** for DataRepresentation and
  TypeConsistency that differ from VibeDDS's current format.

### Unique to OpenDDS
- OpenDDS locators can include **loopback-only user locators** (observed
  `127.0.0.1:12345`), which can prevent cross-process interop even on the
  same host if VibeDDS does not align with those endpoints.
- OpenDDS XTypes expectations may differ from RTI's compact encoding;
  OpenDDS often uses `PID_TYPE_INFORMATION` without RTI vendor PIDs.

## Where to look next (actionable)
- Implement RTI `PID_TYPE_OBJECT (0x8021)` emission for known types and
  add vendor PID stubs to mirror RTI's endpoint payloads.
- Align TypeConsistency and DataRepresentation encoding to RTI's compact
  formats for RTI-specific interop profiles.
- For OpenDDS, confirm locator usage (override or prefer unicast locators
  that are reachable), and validate OpenDDS's exact type metadata with
  its `XTypes::serialize_type_info` output.

## References
- Detailed experiment log: `specs/interop-experiments.md`
- RTI expected payloads: `specs/interop-sedp-expected.md`
- SEDP parameter matrix: `specs/interop-sedp-matrix.md`
- XTypes notes: `specs/interop-sedp-xtypes.md`
- Captures and decoded payloads: `logs/*.pcapng`, `logs/*.sedp.txt`
