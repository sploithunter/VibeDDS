# SEDP Interop Matrix + Experiment Knobs

This doc captures the *observed* SEDP discovery payload differences across
OpenDDS, RustDDS, and VibeDDS (Python/Rust), plus the knobs you can toggle
when experimenting with RTI interop. The goal is to survive context
compression by keeping the critical bytes/choices documented.

## Key PID assignments (sanity checks)
- `0x0053` is **PID_GROUP_ENTITY_ID** (DDSI-RTPS). It is **not** TypeConsistency.
- `0x0073` is **PID_DATA_REPRESENTATION** (DDS-XTypes).
- `0x0074` is **PID_XTYPES_TYPE_CONSISTENCY** (DDS-XTypes).
- `0x0075` is **PID_XTYPES_TYPE_INFORMATION** (DDS-XTypes).

## Observations from external repos
### OpenDDS (reference: `dds/DCPS/RTPS/RtpsCore.idl`, `dds/DCPS/RTPS/ParameterListConverter.cpp`)
- Defines:
  - `PID_DATA_REPRESENTATION = 0x0073`
  - `PID_XTYPES_TYPE_CONSISTENCY = 0x0074`
  - `PID_XTYPES_TYPE_INFORMATION = 0x0075`
- **DataRepresentation is omitted** if it is the default `XCDR1`.
  - `add_DataRepresentationQos()` only pushes PID 0x0073 when the list is not exactly `[XCDR1]`.
  - Default for discovered readers/writers is set to `XCDR1` when absent.
- TypeConsistencyEnforcement is parsed via PID 0x0074 and defaults are applied when missing.

### RTI Connext (observed via pcap on 2026-01-29)
- Endpoint SEDP includes **PID 0x8021 (TYPE_OBJECT)** with a compressed payload (zlib header `78da`).
- Includes vendor-specific PIDs: `0x8000`, `0x8002`, `0x8009`, `0x8015` in endpoint DATA.
- Includes **PID 0x0053** (likely Group Entity ID) for both writers/readers.
- Uses **DATA_REPRESENTATION len=12** and **TYPE_CONSISTENCY len=8**, differing from
  the standard XTypes encodings VibeDDS currently sends.

### RustDDS (reference: `src/structure/parameter_id.rs`)
- Defines **PID_GROUP_ENTITYID = 0x0053** (Group Entity ID), matching DDSI-RTPS.
- Does **not** define PIDs 0x0073/0x0074/0x0075, so it appears to omit XTypes
  QoS from SEDP discovery.

## VibeDDS current behavior (post-fix)
### Python (default “full” profile)
- Always emits:
  - `PID_ENDPOINT_GUID`
  - `PID_TOPIC_NAME`, `PID_TYPE_NAME`
  - `PID_RELIABILITY`, `PID_DURABILITY`
- Emits (by default):
  - `PID_PARTICIPANT_GUID`, `PID_PROTOCOL_VERSION`, `PID_VENDORID`
  - Extended QoS: `OWNERSHIP`, `LIVELINESS`, `DESTINATION_ORDER`,
    `DEADLINE`, `HISTORY`
  - `PID_PARTITION` (empty, default)
  - `PID_DATA_REPRESENTATION` (XCDR1 only)
  - `PID_TYPE_CONSISTENCY_ENFORCEMENT` (readers only)
  - `PID_TYPE_INFORMATION` (when known for the type)
  - `PID_UNICAST_LOCATOR` (endpoint-level locators)

### Rust (default “minimal” profile)
- Emits only:
  - `PID_ENDPOINT_GUID`
  - `PID_TOPIC_NAME`, `PID_TYPE_NAME`
  - `PID_RELIABILITY`, `PID_DURABILITY`
  - `PID_DEFAULT_UNICAST_LOCATOR`
- No participant GUID, protocol/vendor, XTypes, partition, or extended QoS
  unless enabled via env toggles (see below).

## Experiment knobs (Python + Rust)
These environment variables are now supported in both implementations.

### Profiles
- `VIBEDDS_SEDP_PROFILE=full|minimal`
  - `full`: add protocol/vendor/participant GUID, extended QoS, partition,
    XTypes (DataRepresentation + TypeConsistency), endpoint locators.
  - `minimal`: keep only core fields (Rust-style).

### XTypes toggles
- `VIBEDDS_SEDP_XTYPES=on|off`
  - Enables/disables DATA_REPRESENTATION + TYPE_CONSISTENCY + TYPE_INFORMATION.
- `VIBEDDS_SEDP_DATA_REP=xcdr1|xcdr2|xcdr1,xcdr2|none`
  - Controls the DataRepresentation sequence values.
- `VIBEDDS_SEDP_TYPE_CONSISTENCY=disallow|allow|off`
  - Controls the TypeConsistency kind for readers.

### Granular includes
- `VIBEDDS_SEDP_INCLUDE_PARTICIPANT_GUID=0|1`
- `VIBEDDS_SEDP_INCLUDE_PROTOCOL_VENDOR=0|1`
- `VIBEDDS_SEDP_INCLUDE_EXTENDED_QOS=0|1`
- `VIBEDDS_SEDP_INCLUDE_PARTITION=0|1`
- `VIBEDDS_SEDP_INCLUDE_UNICAST_LOCATOR=0|1`
- `VIBEDDS_SEDP_INCLUDE_TYPE_INFORMATION=0|1`

### Locator PID selection
- `VIBEDDS_SEDP_LOCATOR_PID=endpoint|default|both`
  - `endpoint` -> `PID_UNICAST_LOCATOR` (Python default)
  - `default`  -> `PID_DEFAULT_UNICAST_LOCATOR` (Rust default)
  - `both`     -> include both PIDs

## Suggested experimental matrix (RTI interop)
Start from **minimal**, then add features one at a time:
1. `minimal` profile (no XTypes, no participant GUID, no protocol/vendor).
2. Add participant GUID + protocol/vendor.
3. Add DataRepresentation only (`xcdr1`).
4. Add TypeConsistency (disallow).
5. Add extended QoS + partition.
6. Try endpoint locators vs default locators.

Record which step makes RTI start matching so we can lock in the minimum
required fields and avoid over-specifying.

## RTI expectations
See `specs/interop-sedp-expected.md` for the observed RTI byte layouts and
raw payloads (DATA_REPRESENTATION, TYPE_CONSISTENCY, TYPE_OBJECT) captured
on 2026-01-29.

## Experiment Log
See `specs/interop-experiments.md` for dated results and outcomes.
