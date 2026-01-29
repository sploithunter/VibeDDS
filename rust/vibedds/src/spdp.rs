/// Simple Participant Discovery Protocol (SPDP).
///
/// Handles announcing our participant via multicast and discovering
/// remote participants from their SPDP announcements.

use std::collections::HashMap;
use std::net::Ipv4Addr;
use std::time::Instant;

use crate::cdr::{encapsulation_header, parse_encapsulation_header, Endian, ParameterListBuilder, ParameterListParser};
use crate::constants::*;
use crate::types::*;
use crate::wire::{parse_rtps_message, RtpsMessageBuilder};

/// Information about a discovered remote participant.
#[derive(Debug, Clone)]
pub struct DiscoveredParticipant {
    pub guid_prefix: GuidPrefix,
    pub protocol_version: Option<ProtocolVersion>,
    pub vendor_id: Option<VendorId>,
    pub participant_guid: Option<Guid>,
    pub lease_duration: Option<Duration>,
    pub default_unicast_locators: Vec<Locator>,
    pub default_multicast_locators: Vec<Locator>,
    pub metatraffic_unicast_locators: Vec<Locator>,
    pub metatraffic_multicast_locators: Vec<Locator>,
    pub builtin_endpoints: u32,
    pub last_seen: Instant,
}

impl DiscoveredParticipant {
    pub fn new(guid_prefix: GuidPrefix) -> Self {
        Self {
            guid_prefix,
            protocol_version: None,
            vendor_id: None,
            participant_guid: None,
            lease_duration: None,
            default_unicast_locators: Vec::new(),
            default_multicast_locators: Vec::new(),
            metatraffic_unicast_locators: Vec::new(),
            metatraffic_multicast_locators: Vec::new(),
            builtin_endpoints: 0,
            last_seen: Instant::now(),
        }
    }

    pub fn is_expired(&self) -> bool {
        if let Some(lease) = &self.lease_duration {
            let lease_secs = lease.seconds as f64 + lease.fraction as f64 / (1u64 << 32) as f64;
            let elapsed = self.last_seen.elapsed().as_secs_f64();
            elapsed > lease_secs
        } else {
            false
        }
    }
}

/// Writes SPDP participant announcements to multicast.
pub struct SpdpWriter {
    guid_prefix: GuidPrefix,
    local_ip: Ipv4Addr,
    metatraffic_unicast_port: u16,
    user_unicast_port: u16,
    builtin_endpoints: u32,
    lease_duration: Duration,
    sequence_number: SequenceNumber,
}

impl SpdpWriter {
    pub fn new(
        guid_prefix: GuidPrefix,
        local_ip: Ipv4Addr,
        metatraffic_unicast_port: u16,
        user_unicast_port: u16,
    ) -> Self {
        Self {
            guid_prefix,
            local_ip,
            metatraffic_unicast_port,
            user_unicast_port,
            builtin_endpoints: BUILTIN_ENDPOINT_SET_DEFAULT,
            lease_duration: Duration {
                seconds: 100,
                fraction: 0,
            },
            sequence_number: SequenceNumber::ZERO,
        }
    }

    /// Build an SPDP announcement RTPS message.
    pub fn build_announcement(&mut self) -> Vec<u8> {
        self.sequence_number = self.sequence_number.increment();

        // Build parameter list payload
        let mut pl = ParameterListBuilder::new(Endian::Little);

        // PID_PROTOCOL_VERSION
        pl.add_parameter(PID_PROTOCOL_VERSION, &[RTPS_VERSION_MAJOR, RTPS_VERSION_MINOR]);

        // PID_VENDORID
        pl.add_parameter(PID_VENDORID, &VENDOR_ID);

        // PID_PARTICIPANT_GUID (16 bytes: guidPrefix + participantEntityId)
        let mut participant_guid = [0u8; 16];
        participant_guid[..12].copy_from_slice(&self.guid_prefix.0);
        participant_guid[12..16].copy_from_slice(&ENTITYID_PARTICIPANT);
        pl.add_parameter(PID_PARTICIPANT_GUID, &participant_guid);

        // PID_PARTICIPANT_LEASE_DURATION
        pl.add_parameter(
            PID_PARTICIPANT_LEASE_DURATION,
            &self.lease_duration.to_bytes_le(),
        );

        // PID_DEFAULT_UNICAST_LOCATOR
        let user_loc = Locator::from_ipv4(
            &self.local_ip.to_string(),
            self.user_unicast_port as u32,
        );
        pl.add_parameter(PID_DEFAULT_UNICAST_LOCATOR, &user_loc.to_bytes());

        // PID_METATRAFFIC_UNICAST_LOCATOR
        let meta_loc = Locator::from_ipv4(
            &self.local_ip.to_string(),
            self.metatraffic_unicast_port as u32,
        );
        pl.add_parameter(PID_METATRAFFIC_UNICAST_LOCATOR, &meta_loc.to_bytes());

        // PID_BUILTIN_ENDPOINT_SET
        pl.add_parameter(
            PID_BUILTIN_ENDPOINT_SET,
            &self.builtin_endpoints.to_le_bytes(),
        );

        let payload_bytes = pl.finalize();

        // Wrap in PL_CDR_LE encapsulation
        let encap = encapsulation_header(PL_CDR_LE);
        let mut serialized_payload = encap.to_vec();
        serialized_payload.extend_from_slice(&payload_bytes);

        // Build RTPS message: Header + INFO_TS + DATA
        let mut builder = RtpsMessageBuilder::new(self.guid_prefix);

        // Get current time as timestamp
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default();
        let ts = Timestamp::from_seconds(now.as_secs_f64());
        builder.add_info_ts(Some(ts));

        builder.add_data(
            EntityId(ENTITYID_UNKNOWN),
            EntityId(ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER),
            self.sequence_number,
            Some(&serialized_payload),
            None,
            false,
        );

        builder.build()
    }
}

/// Reads and parses SPDP participant announcements.
pub struct SpdpReader;

impl SpdpReader {
    /// Parse an RTPS message and extract SPDP participant data.
    pub fn parse_announcement(data: &[u8]) -> Option<DiscoveredParticipant> {
        let msg = parse_rtps_message(data).ok()?;

        // Look for DATA submessage from SPDP writer
        for sm in &msg.submessages {
            if let crate::messages::Submessage::Data(data_sm) = sm {
                if data_sm.writer_id.0 != ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER {
                    continue;
                }
                if let Some(payload) = &data_sm.serialized_payload {
                    return Self::parse_spdp_data(payload, msg.header.guid_prefix);
                }
            }
        }

        None
    }

    fn parse_spdp_data(payload: &[u8], source_prefix: GuidPrefix) -> Option<DiscoveredParticipant> {
        let (scheme, offset) = parse_encapsulation_header(payload).ok()?;
        let endian = if scheme == PL_CDR_LE || scheme == CDR_LE {
            Endian::Little
        } else {
            Endian::Big
        };

        let pl_data = &payload[offset..];
        let mut participant = DiscoveredParticipant::new(source_prefix);

        for (pid, value) in ParameterListParser::new(pl_data, endian) {
            match pid {
                PID_PROTOCOL_VERSION => {
                    if value.len() >= 2 {
                        participant.protocol_version =
                            Some(ProtocolVersion::new(value[0], value[1]));
                    }
                }
                PID_VENDORID => {
                    if value.len() >= 2 {
                        participant.vendor_id = Some(VendorId([value[0], value[1]]));
                    }
                }
                PID_PARTICIPANT_GUID => {
                    if value.len() >= 16 {
                        participant.participant_guid = Some(Guid::from_bytes(value));
                        // Update guid_prefix from the GUID parameter
                        let mut prefix = [0u8; 12];
                        prefix.copy_from_slice(&value[..12]);
                        participant.guid_prefix = GuidPrefix(prefix);
                    }
                }
                PID_PARTICIPANT_LEASE_DURATION => {
                    if value.len() >= 8 {
                        let seconds = match endian {
                            Endian::Little => {
                                i32::from_le_bytes([value[0], value[1], value[2], value[3]])
                            }
                            Endian::Big => {
                                i32::from_be_bytes([value[0], value[1], value[2], value[3]])
                            }
                        };
                        let fraction = match endian {
                            Endian::Little => {
                                u32::from_le_bytes([value[4], value[5], value[6], value[7]])
                            }
                            Endian::Big => {
                                u32::from_be_bytes([value[4], value[5], value[6], value[7]])
                            }
                        };
                        participant.lease_duration = Some(Duration { seconds, fraction });
                    }
                }
                PID_DEFAULT_UNICAST_LOCATOR => {
                    if value.len() >= 24 {
                        participant
                            .default_unicast_locators
                            .push(Locator::from_bytes(value));
                    }
                }
                PID_METATRAFFIC_UNICAST_LOCATOR => {
                    if value.len() >= 24 {
                        participant
                            .metatraffic_unicast_locators
                            .push(Locator::from_bytes(value));
                    }
                }
                PID_BUILTIN_ENDPOINT_SET => {
                    if value.len() >= 4 {
                        participant.builtin_endpoints = match endian {
                            Endian::Little => {
                                u32::from_le_bytes([value[0], value[1], value[2], value[3]])
                            }
                            Endian::Big => {
                                u32::from_be_bytes([value[0], value[1], value[2], value[3]])
                            }
                        };
                    }
                }
                _ => {}
            }
        }

        Some(participant)
    }
}

/// Tracks discovered participants, handles lease expiry.
pub struct ParticipantDatabase {
    participants: HashMap<[u8; 12], DiscoveredParticipant>,
}

impl ParticipantDatabase {
    pub fn new() -> Self {
        Self {
            participants: HashMap::new(),
        }
    }

    /// Add or update a participant. Returns true if new.
    pub fn update(&mut self, mut participant: DiscoveredParticipant) -> bool {
        participant.last_seen = Instant::now();
        let key = participant.guid_prefix.0;
        let is_new = !self.participants.contains_key(&key);
        self.participants.insert(key, participant);
        is_new
    }

    /// Get a participant by GUID prefix.
    pub fn get(&self, guid_prefix: &GuidPrefix) -> Option<&DiscoveredParticipant> {
        self.participants.get(&guid_prefix.0)
    }

    /// Remove and return expired participants.
    pub fn remove_expired(&mut self) -> Vec<DiscoveredParticipant> {
        let expired_keys: Vec<_> = self
            .participants
            .iter()
            .filter(|(_, p)| p.is_expired())
            .map(|(k, _)| *k)
            .collect();

        let mut expired = Vec::new();
        for key in expired_keys {
            if let Some(p) = self.participants.remove(&key) {
                expired.push(p);
            }
        }
        expired
    }

    pub fn len(&self) -> usize {
        self.participants.len()
    }

    pub fn is_empty(&self) -> bool {
        self.participants.is_empty()
    }

    pub fn iter(&self) -> impl Iterator<Item = &DiscoveredParticipant> {
        self.participants.values()
    }
}

impl Default for ParticipantDatabase {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_guid_prefix() -> GuidPrefix {
        GuidPrefix([0xFF, 0x01, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A])
    }

    #[test]
    fn test_spdp_writer_build_announcement() {
        let prefix = test_guid_prefix();
        let mut writer = SpdpWriter::new(prefix, Ipv4Addr::new(192, 168, 1, 100), 7410, 7401);
        let data = writer.build_announcement();

        // Verify RTPS header
        assert_eq!(&data[0..4], b"RTPS");
        assert_eq!(data[4], RTPS_VERSION_MAJOR);
        assert_eq!(data[5], RTPS_VERSION_MINOR);
        assert_eq!(&data[6..8], &VENDOR_ID);
        assert_eq!(&data[8..20], &prefix.0);

        // Verify it's parseable
        let msg = parse_rtps_message(&data).unwrap();
        assert_eq!(msg.header.guid_prefix, prefix);
        assert!(msg.submessages.len() >= 2); // INFO_TS + DATA
    }

    #[test]
    fn test_spdp_roundtrip() {
        let prefix = test_guid_prefix();
        let mut writer = SpdpWriter::new(prefix, Ipv4Addr::new(192, 168, 1, 100), 7410, 7401);
        let data = writer.build_announcement();

        let participant = SpdpReader::parse_announcement(&data).unwrap();
        assert_eq!(participant.guid_prefix, prefix);
        assert_eq!(
            participant.protocol_version,
            Some(ProtocolVersion::new(2, 5))
        );
        assert_eq!(participant.vendor_id, Some(VendorId([0xFF, 0x01])));
        assert!(participant.lease_duration.is_some());
        assert_eq!(participant.lease_duration.unwrap().seconds, 100);
        assert!(!participant.default_unicast_locators.is_empty());
        assert!(!participant.metatraffic_unicast_locators.is_empty());
        assert_eq!(participant.builtin_endpoints, BUILTIN_ENDPOINT_SET_DEFAULT);
    }

    #[test]
    fn test_participant_database_update() {
        let mut db = ParticipantDatabase::new();
        let participant = DiscoveredParticipant::new(test_guid_prefix());

        let is_new = db.update(participant.clone());
        assert!(is_new);
        assert_eq!(db.len(), 1);

        let is_new = db.update(participant);
        assert!(!is_new);
        assert_eq!(db.len(), 1);
    }

    #[test]
    fn test_participant_database_get() {
        let mut db = ParticipantDatabase::new();
        let prefix = test_guid_prefix();
        let participant = DiscoveredParticipant::new(prefix);
        db.update(participant);

        let found = db.get(&prefix);
        assert!(found.is_some());
        assert_eq!(found.unwrap().guid_prefix, prefix);
    }

    #[test]
    fn test_spdp_sequence_increments() {
        let prefix = test_guid_prefix();
        let mut writer = SpdpWriter::new(prefix, Ipv4Addr::new(192, 168, 1, 100), 7410, 7401);

        writer.build_announcement();
        assert_eq!(writer.sequence_number.value(), 1);

        writer.build_announcement();
        assert_eq!(writer.sequence_number.value(), 2);
    }

    #[test]
    fn test_participant_expiry_with_short_lease() {
        let prefix = test_guid_prefix();
        let mut participant = DiscoveredParticipant::new(prefix);

        // Set a very short lease (effectively already expired)
        participant.lease_duration = Some(Duration { seconds: 0, fraction: 0 });
        participant.last_seen = Instant::now() - std::time::Duration::from_secs(1);

        assert!(participant.is_expired());
    }

    #[test]
    fn test_participant_not_expired_with_long_lease() {
        let prefix = test_guid_prefix();
        let mut participant = DiscoveredParticipant::new(prefix);

        // Set a long lease
        participant.lease_duration = Some(Duration { seconds: 100, fraction: 0 });
        participant.last_seen = Instant::now();

        assert!(!participant.is_expired());
    }

    #[test]
    fn test_participant_not_expired_without_lease() {
        let prefix = test_guid_prefix();
        let participant = DiscoveredParticipant::new(prefix);

        // No lease set - should not expire
        assert!(!participant.is_expired());
    }

    #[test]
    fn test_participant_database_remove_expired() {
        let mut db = ParticipantDatabase::new();

        // Add a participant with expired lease
        let prefix1 = GuidPrefix([0x01; 12]);
        let mut p1 = DiscoveredParticipant::new(prefix1);
        p1.lease_duration = Some(Duration { seconds: 0, fraction: 0 });
        p1.last_seen = Instant::now() - std::time::Duration::from_secs(1);
        db.update(p1);

        // Add a participant with valid lease
        let prefix2 = GuidPrefix([0x02; 12]);
        let mut p2 = DiscoveredParticipant::new(prefix2);
        p2.lease_duration = Some(Duration { seconds: 100, fraction: 0 });
        p2.last_seen = Instant::now();
        db.update(p2);

        assert_eq!(db.len(), 2);

        let expired = db.remove_expired();
        assert_eq!(expired.len(), 1);
        assert_eq!(expired[0].guid_prefix, prefix1);
        assert_eq!(db.len(), 1);
        assert!(db.get(&prefix2).is_some());
    }

    #[test]
    fn test_spdp_announcement_contains_required_fields() {
        let prefix = test_guid_prefix();
        let mut writer = SpdpWriter::new(prefix, Ipv4Addr::new(192, 168, 1, 100), 7410, 7401);
        let data = writer.build_announcement();

        // Parse and verify all required SPDP fields are present
        let participant = SpdpReader::parse_announcement(&data).unwrap();

        assert!(participant.protocol_version.is_some());
        assert!(participant.vendor_id.is_some());
        assert!(participant.participant_guid.is_some());
        assert!(participant.lease_duration.is_some());
        assert!(!participant.default_unicast_locators.is_empty());
        assert!(!participant.metatraffic_unicast_locators.is_empty());
        assert!(participant.builtin_endpoints != 0);
    }

    #[test]
    fn test_spdp_locator_contains_correct_ports() {
        let prefix = test_guid_prefix();
        let mut writer = SpdpWriter::new(prefix, Ipv4Addr::new(192, 168, 1, 100), 7410, 7401);
        let data = writer.build_announcement();

        let participant = SpdpReader::parse_announcement(&data).unwrap();

        // Verify ports in locators
        let meta_loc = &participant.metatraffic_unicast_locators[0];
        assert_eq!(meta_loc.port, 7410);

        let user_loc = &participant.default_unicast_locators[0];
        assert_eq!(user_loc.port, 7401);
    }

    #[test]
    fn test_parse_python_generated_spdp() {
        // Python-generated SPDP announcement (176 bytes)
        // GuidPrefix: aabbccdd01020304050607008, IP: 192.168.1.100, ports: 7410/7401
        const PYTHON_SPDP_BYTES: &[u8] = &[
            0x52, 0x54, 0x50, 0x53, 0x02, 0x05, 0xff, 0x01, 0xaa, 0xbb, 0xcc, 0xdd, 0x01, 0x02, 0x03, 0x04,
            0x05, 0x06, 0x07, 0x08, 0x09, 0x01, 0x08, 0x00, 0x92, 0xc9, 0x7a, 0x69, 0x00, 0xfc, 0x9d, 0x82,
            0x15, 0x05, 0x8c, 0x00, 0x00, 0x00, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0xc2,
            0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x03, 0x00, 0x00, 0x15, 0x00, 0x04, 0x00,
            0x02, 0x05, 0x00, 0x00, 0x16, 0x00, 0x04, 0x00, 0xff, 0x01, 0x00, 0x00, 0x50, 0x00, 0x10, 0x00,
            0xaa, 0xbb, 0xcc, 0xdd, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x00, 0x00, 0x01, 0xc1,
            0x02, 0x00, 0x08, 0x00, 0x64, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x31, 0x00, 0x18, 0x00,
            0x01, 0x00, 0x00, 0x00, 0xe9, 0x1c, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0xc0, 0xa8, 0x01, 0x64, 0x32, 0x00, 0x18, 0x00, 0x01, 0x00, 0x00, 0x00,
            0xf2, 0x1c, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0xc0, 0xa8, 0x01, 0x64, 0x58, 0x00, 0x04, 0x00, 0x3f, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,
        ];

        let participant = SpdpReader::parse_announcement(PYTHON_SPDP_BYTES)
            .expect("Failed to parse Python-generated SPDP");

        // Verify GUID prefix
        let expected_prefix = GuidPrefix([0xaa, 0xbb, 0xcc, 0xdd, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]);
        assert_eq!(participant.guid_prefix, expected_prefix);

        // Verify protocol version
        assert_eq!(participant.protocol_version, Some(ProtocolVersion::new(2, 5)));

        // Verify vendor ID (VibeDDS = 0xFF01)
        assert_eq!(participant.vendor_id, Some(VendorId([0xFF, 0x01])));

        // Verify lease duration (100 seconds)
        assert!(participant.lease_duration.is_some());
        assert_eq!(participant.lease_duration.unwrap().seconds, 100);

        // Verify locators have correct ports
        assert!(!participant.default_unicast_locators.is_empty());
        assert_eq!(participant.default_unicast_locators[0].port, 7401);

        assert!(!participant.metatraffic_unicast_locators.is_empty());
        assert_eq!(participant.metatraffic_unicast_locators[0].port, 7410);

        // Verify IP address (192.168.1.100) - IPv4 is in bytes [12..16]
        let loc = &participant.default_unicast_locators[0];
        assert_eq!(loc.address[12], 192);
        assert_eq!(loc.address[13], 168);
        assert_eq!(loc.address[14], 1);
        assert_eq!(loc.address[15], 100);
    }
}
