/// RTPS protocol constants: magic, IDs, PIDs, ports, entity IDs.

pub const RTPS_MAGIC: [u8; 4] = *b"RTPS";
pub const RTPS_VERSION_MAJOR: u8 = 2;
pub const RTPS_VERSION_MINOR: u8 = 5;
pub const VENDOR_ID: [u8; 2] = [0xFF, 0x01];

// Submessage IDs
pub const SUBMSG_PAD: u8 = 0x01;
pub const SUBMSG_ACKNACK: u8 = 0x06;
pub const SUBMSG_HEARTBEAT: u8 = 0x07;
pub const SUBMSG_GAP: u8 = 0x08;
pub const SUBMSG_INFO_TS: u8 = 0x09;
pub const SUBMSG_INFO_SRC: u8 = 0x0C;
pub const SUBMSG_INFO_DST: u8 = 0x0E;
pub const SUBMSG_DATA: u8 = 0x15;

// Submessage flag bits
pub const FLAG_ENDIAN: u8 = 0x01;
pub const FLAG_DATA_Q: u8 = 0x02;
pub const FLAG_DATA_D: u8 = 0x04;
pub const FLAG_DATA_K: u8 = 0x08;

// Well-known EntityIds
pub const ENTITYID_UNKNOWN: [u8; 4] = [0x00, 0x00, 0x00, 0x00];
pub const ENTITYID_PARTICIPANT: [u8; 4] = [0x00, 0x00, 0x01, 0xC1];
pub const ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER: [u8; 4] = [0x00, 0x01, 0x00, 0xC2];
pub const ENTITYID_SPDP_BUILTIN_PARTICIPANT_READER: [u8; 4] = [0x00, 0x01, 0x00, 0xC7];
pub const ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER: [u8; 4] = [0x00, 0x00, 0x03, 0xC2];
pub const ENTITYID_SEDP_BUILTIN_PUBLICATIONS_READER: [u8; 4] = [0x00, 0x00, 0x03, 0xC7];
pub const ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER: [u8; 4] = [0x00, 0x00, 0x04, 0xC2];
pub const ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_READER: [u8; 4] = [0x00, 0x00, 0x04, 0xC7];

// User entity kinds
pub const ENTITY_KIND_USER_WRITER_WITH_KEY: u8 = 0x02;
pub const ENTITY_KIND_USER_WRITER_NO_KEY: u8 = 0x03;
pub const ENTITY_KIND_USER_READER_WITH_KEY: u8 = 0x04;
pub const ENTITY_KIND_USER_READER_NO_KEY: u8 = 0x07;

// Parameter IDs (PIDs)
pub const PID_PAD: u16 = 0x0000;
pub const PID_SENTINEL: u16 = 0x0001;
pub const PID_PARTICIPANT_LEASE_DURATION: u16 = 0x0002;
pub const PID_TOPIC_NAME: u16 = 0x0005;
pub const PID_TYPE_NAME: u16 = 0x0007;
pub const PID_PROTOCOL_VERSION: u16 = 0x0015;
pub const PID_VENDORID: u16 = 0x0016;
pub const PID_RELIABILITY: u16 = 0x001A;
pub const PID_DURABILITY: u16 = 0x001D;
pub const PID_OWNERSHIP: u16 = 0x001F;
pub const PID_LIVELINESS: u16 = 0x001B;
pub const PID_DESTINATION_ORDER: u16 = 0x0025;
pub const PID_DEADLINE: u16 = 0x0023;
pub const PID_HISTORY: u16 = 0x0040;
pub const PID_PARTITION: u16 = 0x0029;
pub const PID_UNICAST_LOCATOR: u16 = 0x002F;
pub const PID_DEFAULT_UNICAST_LOCATOR: u16 = 0x0031;
pub const PID_METATRAFFIC_UNICAST_LOCATOR: u16 = 0x0032;
pub const PID_PARTICIPANT_GUID: u16 = 0x0050;
pub const PID_GROUP_ENTITY_ID: u16 = 0x0053;
pub const PID_BUILTIN_ENDPOINT_SET: u16 = 0x0058;
pub const PID_ENDPOINT_GUID: u16 = 0x005A;
pub const PID_DATA_REPRESENTATION: u16 = 0x0073;
pub const PID_TYPE_CONSISTENCY_ENFORCEMENT: u16 = 0x0074;
pub const PID_TYPE_INFORMATION: u16 = 0x0075;
pub const PID_TYPE_OBJECT: u16 = 0x8021;
pub const PID_RTI_VENDOR_0013: u16 = 0x0013;
pub const PID_RTI_VENDOR_0018: u16 = 0x0018;
pub const PID_RTI_VENDOR_0060: u16 = 0x0060;
pub const PID_RTI_VENDOR_8000: u16 = 0x8000;
pub const PID_RTI_VENDOR_8002: u16 = 0x8002;
pub const PID_RTI_VENDOR_8004: u16 = 0x8004;
pub const PID_RTI_VENDOR_8009: u16 = 0x8009;
pub const PID_RTI_VENDOR_8015: u16 = 0x8015;

// BuiltinEndpointSet flags
pub const DISC_BUILTIN_ENDPOINT_PARTICIPANT_ANNOUNCER: u32 = 1 << 0;
pub const DISC_BUILTIN_ENDPOINT_PARTICIPANT_DETECTOR: u32 = 1 << 1;
pub const DISC_BUILTIN_ENDPOINT_PUBLICATIONS_ANNOUNCER: u32 = 1 << 2;
pub const DISC_BUILTIN_ENDPOINT_PUBLICATIONS_DETECTOR: u32 = 1 << 3;
pub const DISC_BUILTIN_ENDPOINT_SUBSCRIPTIONS_ANNOUNCER: u32 = 1 << 4;
pub const DISC_BUILTIN_ENDPOINT_SUBSCRIPTIONS_DETECTOR: u32 = 1 << 5;
pub const DISC_BUILTIN_ENDPOINT_PARTICIPANT_MESSAGE_DATA_ANNOUNCER: u32 = 1 << 10;
pub const DISC_BUILTIN_ENDPOINT_PARTICIPANT_MESSAGE_DATA_DETECTOR: u32 = 1 << 11;

pub const BUILTIN_ENDPOINT_SET_DEFAULT: u32 = DISC_BUILTIN_ENDPOINT_PARTICIPANT_ANNOUNCER
    | DISC_BUILTIN_ENDPOINT_PARTICIPANT_DETECTOR
    | DISC_BUILTIN_ENDPOINT_PUBLICATIONS_ANNOUNCER
    | DISC_BUILTIN_ENDPOINT_PUBLICATIONS_DETECTOR
    | DISC_BUILTIN_ENDPOINT_SUBSCRIPTIONS_ANNOUNCER
    | DISC_BUILTIN_ENDPOINT_SUBSCRIPTIONS_DETECTOR
    | DISC_BUILTIN_ENDPOINT_PARTICIPANT_MESSAGE_DATA_ANNOUNCER
    | DISC_BUILTIN_ENDPOINT_PARTICIPANT_MESSAGE_DATA_DETECTOR;

// Locator kinds
pub const LOCATOR_KIND_INVALID: i32 = -1;
pub const LOCATOR_KIND_UDPV4: i32 = 1;

// Multicast
pub const SPDP_MULTICAST_ADDRESS: &str = "239.255.0.1";

// Port calculations
const PB: u16 = 7400;
const DG: u16 = 250;
const PG: u16 = 2;
const D0: u16 = 0;
const D1: u16 = 10;
const D2: u16 = 1;

pub fn spdp_multicast_port(domain_id: u16) -> u16 {
    PB + DG * domain_id + D0
}

pub fn spdp_unicast_port(domain_id: u16, participant_id: u16) -> u16 {
    PB + DG * domain_id + D1 + PG * participant_id
}

pub fn user_unicast_port(domain_id: u16, participant_id: u16) -> u16 {
    PB + DG * domain_id + D2 + PG * participant_id
}

// Encapsulation schemes
pub const CDR_BE: u16 = 0x0000;
pub const CDR_LE: u16 = 0x0001;
pub const PL_CDR_BE: u16 = 0x0002;
pub const PL_CDR_LE: u16 = 0x0003;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_spdp_multicast_port_domain0() {
        assert_eq!(spdp_multicast_port(0), 7400);
    }

    #[test]
    fn test_spdp_multicast_port_domain1() {
        assert_eq!(spdp_multicast_port(1), 7650);
    }

    #[test]
    fn test_spdp_unicast_port() {
        assert_eq!(spdp_unicast_port(0, 0), 7410);
        assert_eq!(spdp_unicast_port(0, 1), 7412);
    }

    #[test]
    fn test_user_unicast_port() {
        assert_eq!(user_unicast_port(0, 0), 7401);
        assert_eq!(user_unicast_port(0, 1), 7403);
    }
}
