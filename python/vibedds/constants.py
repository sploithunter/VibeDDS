"""RTPS protocol constants: magic, IDs, PIDs, ports, entity IDs."""

import os
import struct

# --- RTPS Header ---
RTPS_MAGIC = b'RTPS'
RTPS_VERSION_MAJOR = 2
RTPS_VERSION_MINOR = 5


def _parse_vendor_id(value: str) -> tuple[int, int] | None:
    cleaned = "".join(ch for ch in value if ch in "0123456789abcdefABCDEF")
    if len(cleaned) < 4:
        return None
    cleaned = cleaned[:4]
    try:
        b0 = int(cleaned[0:2], 16)
        b1 = int(cleaned[2:4], 16)
    except ValueError:
        return None
    return (b0, b1)


_vendor_env = os.getenv("VIBEDDS_VENDOR_ID")
VENDOR_ID = _parse_vendor_id(_vendor_env) if _vendor_env else None
if VENDOR_ID is None:
    VENDOR_ID = (0xFF, 0x01)  # Experimental / unregistered

# --- Submessage IDs ---
SUBMSG_PAD = 0x01
SUBMSG_ACKNACK = 0x06
SUBMSG_HEARTBEAT = 0x07
SUBMSG_GAP = 0x08
SUBMSG_INFO_TS = 0x09
SUBMSG_INFO_SRC = 0x0C
SUBMSG_INFO_DST = 0x0E
SUBMSG_INFO_REPLY = 0x0F
SUBMSG_DATA = 0x15
SUBMSG_DATA_FRAG = 0x16
SUBMSG_NACK_FRAG = 0x12
SUBMSG_HEARTBEAT_FRAG = 0x13

# --- Submessage flag bits ---
FLAG_ENDIAN = 0x01       # E: 1=little-endian, 0=big-endian
FLAG_DATA_Q = 0x02       # Q: inline QoS present
FLAG_DATA_D = 0x04       # D: serialized data present
FLAG_DATA_K = 0x08       # K: serialized key present
FLAG_HB_FINAL = 0x02     # F: final heartbeat
FLAG_HB_LIVELINESS = 0x04  # L: liveliness heartbeat
FLAG_ACKNACK_FINAL = 0x02  # F: final acknack

# --- Well-known EntityIds (4 bytes: entityKey[3] + entityKind[1]) ---
ENTITYID_UNKNOWN = bytes([0x00, 0x00, 0x00, 0x00])
ENTITYID_PARTICIPANT = bytes([0x00, 0x00, 0x01, 0xC1])

# SPDP
ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER = bytes([0x00, 0x01, 0x00, 0xC2])
ENTITYID_SPDP_BUILTIN_PARTICIPANT_READER = bytes([0x00, 0x01, 0x00, 0xC7])

# SEDP Publications
ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER = bytes([0x00, 0x00, 0x03, 0xC2])
ENTITYID_SEDP_BUILTIN_PUBLICATIONS_READER = bytes([0x00, 0x00, 0x03, 0xC7])

# SEDP Subscriptions
ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER = bytes([0x00, 0x00, 0x04, 0xC2])
ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_READER = bytes([0x00, 0x00, 0x04, 0xC7])

# SEDP Topics (not always used)
ENTITYID_SEDP_BUILTIN_TOPIC_WRITER = bytes([0x00, 0x00, 0x02, 0xC2])
ENTITYID_SEDP_BUILTIN_TOPIC_READER = bytes([0x00, 0x00, 0x02, 0xC7])

# Entity kind values
ENTITY_KIND_USER_WRITER_WITH_KEY = 0x02
ENTITY_KIND_USER_WRITER_NO_KEY = 0x03
ENTITY_KIND_USER_READER_WITH_KEY = 0x04
ENTITY_KIND_USER_READER_NO_KEY = 0x07
ENTITY_KIND_BUILTIN_WRITER_WITH_KEY = 0xC2
ENTITY_KIND_BUILTIN_WRITER_NO_KEY = 0xC3
ENTITY_KIND_BUILTIN_READER_WITH_KEY = 0xC7
ENTITY_KIND_BUILTIN_READER_NO_KEY = 0xC4
ENTITY_KIND_PARTICIPANT = 0xC1

# --- Parameter IDs (PIDs) ---
PID_PAD = 0x0000
PID_SENTINEL = 0x0001
PID_PARTICIPANT_LEASE_DURATION = 0x0002
PID_DOMAIN_ID = 0x000F  # Optional: indicates domain
PID_TOPIC_NAME = 0x0005
PID_TYPE_NAME = 0x0007
PID_DURABILITY = 0x001D
PID_DEADLINE = 0x0023
PID_LIVELINESS = 0x001B
PID_RELIABILITY = 0x001A
PID_OWNERSHIP = 0x001F
PID_DESTINATION_ORDER = 0x0025
PID_HISTORY = 0x0040
PID_RESOURCE_LIMITS = 0x0041
PID_PARTITION = 0x0029
PID_PROTOCOL_VERSION = 0x0015
PID_VENDORID = 0x0016
PID_UNICAST_LOCATOR = 0x002f  # Endpoint-level unicast locator
PID_MULTICAST_LOCATOR = 0x0030  # Endpoint-level multicast locator
PID_DEFAULT_UNICAST_LOCATOR = 0x0031  # Participant-level default
PID_DEFAULT_MULTICAST_LOCATOR = 0x0048
PID_METATRAFFIC_UNICAST_LOCATOR = 0x0032
PID_METATRAFFIC_MULTICAST_LOCATOR = 0x0033
PID_PARTICIPANT_GUID = 0x0050
PID_GROUP_ENTITY_ID = 0x0053
PID_ENDPOINT_GUID = 0x005A
PID_BUILTIN_ENDPOINT_SET = 0x0058
PID_PROPERTY_LIST = 0x0059
PID_KEY_HASH = 0x0070
PID_STATUS_INFO = 0x0071
PID_PARTICIPANT_BUILTIN_ENDPOINTS = 0x0044

# --- XTypes-related PIDs (DDS-XTYPES spec) ---
PID_DATA_REPRESENTATION = 0x0073
PID_TYPE_CONSISTENCY_ENFORCEMENT = 0x0074
PID_TYPE_INFORMATION = 0x0075

# --- Additional PIDs for SEDP ---
PID_EXPECTS_INLINE_QOS = 0x0043
PID_TYPE_OBJECT = 0x8021  # XTypes: serialized TypeObject (vendor extension)

# RTI vendor-specific PIDs observed in SEDP
PID_RTI_VENDOR_0013 = 0x0013
PID_RTI_VENDOR_0018 = 0x0018
PID_RTI_VENDOR_0060 = 0x0060
PID_RTI_VENDOR_8000 = 0x8000
PID_RTI_VENDOR_8002 = 0x8002
PID_RTI_VENDOR_8004 = 0x8004
PID_RTI_VENDOR_8009 = 0x8009
PID_RTI_VENDOR_8015 = 0x8015

# --- BuiltinEndpointSet flags ---
DISC_BUILTIN_ENDPOINT_PARTICIPANT_ANNOUNCER = 1 << 0
DISC_BUILTIN_ENDPOINT_PARTICIPANT_DETECTOR = 1 << 1
DISC_BUILTIN_ENDPOINT_PUBLICATIONS_ANNOUNCER = 1 << 2
DISC_BUILTIN_ENDPOINT_PUBLICATIONS_DETECTOR = 1 << 3
DISC_BUILTIN_ENDPOINT_SUBSCRIPTIONS_ANNOUNCER = 1 << 4
DISC_BUILTIN_ENDPOINT_SUBSCRIPTIONS_DETECTOR = 1 << 5
DISC_BUILTIN_ENDPOINT_TOPICS_ANNOUNCER = 1 << 6
DISC_BUILTIN_ENDPOINT_TOPICS_DETECTOR = 1 << 7
DISC_BUILTIN_ENDPOINT_PARTICIPANT_MESSAGE_DATA_ANNOUNCER = 1 << 10
DISC_BUILTIN_ENDPOINT_PARTICIPANT_MESSAGE_DATA_DETECTOR = 1 << 11

# Standard set: SPDP + SEDP publications + SEDP subscriptions
BUILTIN_ENDPOINT_SET_DEFAULT = (
    DISC_BUILTIN_ENDPOINT_PARTICIPANT_ANNOUNCER
    | DISC_BUILTIN_ENDPOINT_PARTICIPANT_DETECTOR
    | DISC_BUILTIN_ENDPOINT_PUBLICATIONS_ANNOUNCER
    | DISC_BUILTIN_ENDPOINT_PUBLICATIONS_DETECTOR
    | DISC_BUILTIN_ENDPOINT_SUBSCRIPTIONS_ANNOUNCER
    | DISC_BUILTIN_ENDPOINT_SUBSCRIPTIONS_DETECTOR
    | DISC_BUILTIN_ENDPOINT_PARTICIPANT_MESSAGE_DATA_ANNOUNCER
    | DISC_BUILTIN_ENDPOINT_PARTICIPANT_MESSAGE_DATA_DETECTOR
)

# --- Locator kinds ---
LOCATOR_KIND_INVALID = -1
LOCATOR_KIND_UDPv4 = 1
LOCATOR_KIND_UDPv6 = 2

LOCATOR_PORT_INVALID = 0
LOCATOR_ADDRESS_INVALID = b'\x00' * 16

# --- Multicast addresses ---
SPDP_MULTICAST_ADDRESS = "239.255.0.1"

# --- Port calculations (Section 9.6.1.1, Table 9-15) ---
PB = 7400  # port base
DG = 250   # domain gain
PG = 2     # participant gain
D0 = 0     # additional offset for discovery multicast
D1 = 10    # additional offset for discovery unicast (metatraffic)
D2 = 1     # additional offset for user traffic multicast
D3 = 11    # additional offset for user traffic unicast


def spdp_multicast_port(domain_id: int) -> int:
    """Port for SPDP multicast: PB + DG * domainId + d0."""
    return PB + DG * domain_id + D0


def spdp_unicast_port(domain_id: int, participant_id: int) -> int:
    """Port for SPDP unicast: PB + DG * domainId + d1 + PG * participantId."""
    return PB + DG * domain_id + D1 + PG * participant_id


def user_unicast_port(domain_id: int, participant_id: int) -> int:
    """Port for user unicast traffic: PB + DG * domainId + d3 + PG * participantId."""
    return PB + DG * domain_id + D3 + PG * participant_id


def user_multicast_port(domain_id: int) -> int:
    """Port for user multicast traffic: PB + DG * domainId + d2."""
    return PB + DG * domain_id + D2
