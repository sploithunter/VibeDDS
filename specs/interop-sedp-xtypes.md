# SEDP XTypes QoS Encoding (Interop Expectations)

## Scope
This document defines the expected RTPS ParameterList encoding for the XTypes QoS
fields used in SEDP endpoint announcements. It exists to keep VibeDDS interop
bytes aligned with the DDS-XTypes and DDSI-RTPS specifications.

## References
- specs/DDS-XTypes-1.3-spec.md (Annex D: DDS Built-in Topic Data Types; XCDR1 encoding)
- specs/DDSI-RTPS-2.5-spec.md (ParameterList rules and PID assignments)

Note: PID 0x0053 is PID_GROUP_ENTITY_ID per DDSI-RTPS 2.5. TypeConsistency
Enforcement is identified by PID 0x0074 per DDS-XTypes Annex D.

## ParameterList and Encoding Rules
- SEDP endpoint data is encoded as a RTPS ParameterList with PL_CDR_LE encapsulation.
- Parameter values are serialized with XCDR1 (CDR) per DDS-XTypes Annex D.
- Each parameter is padded to a 4-byte boundary by the ParameterList builder.

## PID_DATA_REPRESENTATION (0x0073)
Value type: DDS::DataRepresentationQosPolicy

IDL summary:
- typedef short DataRepresentationId_t;
- const XCDR_DATA_REPRESENTATION = 0
- const XML_DATA_REPRESENTATION  = 1
- const XCDR2_DATA_REPRESENTATION = 2
- typedef sequence<DataRepresentationId_t> DataRepresentationIdSeq;
- struct DataRepresentationQosPolicy { DataRepresentationIdSeq value; }

VibeDDS default:
- Advertise only XCDR1 (value = [0]) because VibeDDS currently serializes user data
  with XCDR1 only.

Expected bytes (little-endian, value only, before PID header):
- count (u32): 01 00 00 00
- element (short): 00 00
- padding: 00 00
Total value length: 8 bytes (padded to 4-byte alignment).

## PID_TYPE_CONSISTENCY_ENFORCEMENT (0x0074)
Value type: DDS::TypeConsistencyEnforcementQosPolicy

IDL summary:
- enum TypeConsistencyKind { DISALLOW_TYPE_COERCION=0, ALLOW_TYPE_COERCION=1 }
- struct TypeConsistencyEnforcementQosPolicy {
    TypeConsistencyKind kind;
    boolean ignore_sequence_bounds;
    boolean ignore_string_bounds;
    boolean ignore_member_names;
    boolean prevent_type_widening;
    boolean force_type_validation;
  }

VibeDDS default:
- kind = DISALLOW_TYPE_COERCION
- all flags = false

Expected bytes (little-endian, value only, before PID header):
- kind (i32): 00 00 00 00
- 5 booleans: 00 00 00 00 00
- padding: 00 00 00
Total value length: 12 bytes (padded to 4-byte alignment).

## Applicability
- PID_DATA_REPRESENTATION is included for both readers and writers.
- PID_TYPE_CONSISTENCY_ENFORCEMENT is included only for readers (per DDS-XTypes).

## PID_TYPE_INFORMATION (0x0075)
Value type: DDS::XTypes::TypeInformation (XCDR2 encoding).

Notes:
- TypeInformation is encoded using the XTypes TypeObject encoding (XCDR2), not
  the regular CDR1 ParameterList encoding.
- OpenDDS serializes this via `XTypes::serialize_type_info`, which is the
  reference we used to capture baseline bytes for common interop types.

VibeDDS default:
- Includes TypeInformation when available and `VIBEDDS_SEDP_INCLUDE_TYPE_INFORMATION=1`.
- Built-in blobs are provided for `HelloWorld`, `ShapeType`, and `PingType`.

Known-good TypeInformation blobs (hex, OpenDDS 3.34):
- HelloWorld (88 bytes):
  `5400000001100040280000002400000014000000f1b171dd17cc21f1d56aa6e08ff86a0028000000ffffffff0400000000000000021000401c00000018000000080000000000000000000000000000000400000000000000`
- ShapeType (88 bytes):
  `5400000001100040280000002400000014000000f139b4f2ccabb48bad086c66d05df10057000000ffffffff0400000000000000021000401c00000018000000080000000000000000000000000000000400000000000000`
- PingType (88 bytes):
  `5400000001100040280000002400000014000000f1ebfe38b8cbf57ed81be0408006740027000000ffffffff0400000000000000021000401c00000018000000080000000000000000000000000000000400000000000000`

If you need additional types, regenerate via OpenDDS `TypeSupportImpl::to_type_info`
and `XTypes::serialize_type_info`, then register the bytes in
`python/vibedds/type_support.py` and `rust/vibedds/src/type_support.rs`.
