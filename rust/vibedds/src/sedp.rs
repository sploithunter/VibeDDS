/// Simple Endpoint Discovery Protocol (SEDP).
///
/// After SPDP discovers a remote participant, SEDP exchanges endpoint
/// information (topic, type, QoS) over reliable unicast. This enables
/// matching of DataWriters and DataReaders across participants.

use std::collections::HashMap;

use crate::cdr::{encapsulation_header, parse_encapsulation_header, CdrDeserializer, CdrSerializer, Endian, ParameterListBuilder, ParameterListParser};
use crate::constants::*;
use crate::messages::{DataSubmessage, HeartbeatSubmessage};
use crate::qos::{deserialize_durability_qos, deserialize_reliability_qos, qos_compatible, serialize_durability_qos, serialize_reliability_qos, DurabilityKind, QosPolicy, ReliabilityKind};
use crate::reliability::{ReliableReader, ReliableWriter};
use crate::spdp::DiscoveredParticipant;
use crate::types::*;
use crate::wire::RtpsMessageBuilder;

/// Information about a discovered remote endpoint (writer or reader).
#[derive(Debug, Clone)]
pub struct DiscoveredEndpoint {
    pub endpoint_guid: Guid,
    pub topic_name: String,
    pub type_name: String,
    pub reliability: ReliabilityKind,
    pub durability: DurabilityKind,
    pub unicast_locators: Vec<Locator>,
    pub qos: QosPolicy,
}

impl DiscoveredEndpoint {
    pub fn new(endpoint_guid: Guid) -> Self {
        Self {
            endpoint_guid,
            topic_name: String::new(),
            type_name: String::new(),
            reliability: ReliabilityKind::BestEffort,
            durability: DurabilityKind::Volatile,
            unicast_locators: Vec::new(),
            qos: QosPolicy::default(),
        }
    }
}

/// Information about a local endpoint to be announced via SEDP.
#[derive(Debug, Clone)]
pub struct LocalEndpoint {
    pub guid: Guid,
    pub topic_name: String,
    pub type_name: String,
    pub qos: QosPolicy,
    pub is_writer: bool,
    pub unicast_locators: Vec<Locator>,
}

impl LocalEndpoint {
    pub fn new_writer(guid: Guid, topic_name: &str, type_name: &str, qos: QosPolicy) -> Self {
        Self {
            guid,
            topic_name: topic_name.to_string(),
            type_name: type_name.to_string(),
            qos,
            is_writer: true,
            unicast_locators: Vec::new(),
        }
    }

    pub fn new_reader(guid: Guid, topic_name: &str, type_name: &str, qos: QosPolicy) -> Self {
        Self {
            guid,
            topic_name: topic_name.to_string(),
            type_name: type_name.to_string(),
            qos,
            is_writer: false,
            unicast_locators: Vec::new(),
        }
    }
}

/// Match event type.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MatchEvent {
    WriterMatched,
    ReaderMatched,
}

/// Stores local and discovered remote endpoints, finds matches.
pub struct EndpointDatabase {
    local_writers: HashMap<[u8; 16], LocalEndpoint>,
    local_readers: HashMap<[u8; 16], LocalEndpoint>,
    remote_writers: HashMap<[u8; 16], DiscoveredEndpoint>,
    remote_readers: HashMap<[u8; 16], DiscoveredEndpoint>,
    on_match_callbacks: Vec<Box<dyn Fn(MatchEvent, &Guid, &Guid) + Send>>,
}

impl EndpointDatabase {
    pub fn new() -> Self {
        Self {
            local_writers: HashMap::new(),
            local_readers: HashMap::new(),
            remote_writers: HashMap::new(),
            remote_readers: HashMap::new(),
            on_match_callbacks: Vec::new(),
        }
    }

    pub fn on_match<F>(&mut self, callback: F)
    where
        F: Fn(MatchEvent, &Guid, &Guid) + Send + 'static,
    {
        self.on_match_callbacks.push(Box::new(callback));
    }

    pub fn add_local_writer(&mut self, endpoint: LocalEndpoint) {
        let key = endpoint.guid.to_bytes();
        self.local_writers.insert(key, endpoint.clone());
        self.check_matches_for_local_writer(&endpoint);
    }

    pub fn add_local_reader(&mut self, endpoint: LocalEndpoint) {
        let key = endpoint.guid.to_bytes();
        self.local_readers.insert(key, endpoint.clone());
        self.check_matches_for_local_reader(&endpoint);
    }

    pub fn add_remote_writer(&mut self, endpoint: DiscoveredEndpoint) {
        let key = endpoint.endpoint_guid.to_bytes();
        self.remote_writers.insert(key, endpoint.clone());
        self.check_matches_for_remote_writer(&endpoint);
    }

    pub fn add_remote_reader(&mut self, endpoint: DiscoveredEndpoint) {
        let key = endpoint.endpoint_guid.to_bytes();
        self.remote_readers.insert(key, endpoint.clone());
        self.check_matches_for_remote_reader(&endpoint);
    }

    pub fn find_matching_remote_readers(&self, local_writer: &LocalEndpoint) -> Vec<&DiscoveredEndpoint> {
        self.remote_readers
            .values()
            .filter(|rr| Self::endpoints_match(local_writer, rr))
            .collect()
    }

    pub fn find_matching_remote_writers(&self, local_reader: &LocalEndpoint) -> Vec<&DiscoveredEndpoint> {
        self.remote_writers
            .values()
            .filter(|rw| Self::endpoints_match_wr(rw, local_reader))
            .collect()
    }

    pub fn local_writers(&self) -> impl Iterator<Item = &LocalEndpoint> {
        self.local_writers.values()
    }

    pub fn local_readers(&self) -> impl Iterator<Item = &LocalEndpoint> {
        self.local_readers.values()
    }

    pub fn remote_writers(&self) -> impl Iterator<Item = &DiscoveredEndpoint> {
        self.remote_writers.values()
    }

    pub fn remote_readers(&self) -> impl Iterator<Item = &DiscoveredEndpoint> {
        self.remote_readers.values()
    }

    /// Get a remote writer by GUID.
    pub fn get_remote_writer(&self, guid: &Guid) -> Option<&DiscoveredEndpoint> {
        self.remote_writers.get(&guid.to_bytes())
    }

    /// Get a remote reader by GUID.
    pub fn get_remote_reader(&self, guid: &Guid) -> Option<&DiscoveredEndpoint> {
        self.remote_readers.get(&guid.to_bytes())
    }

    /// Find remote readers matching by topic name and type name.
    pub fn find_readers_by_topic(&self, topic_name: &str, type_name: &str) -> Vec<&DiscoveredEndpoint> {
        self.remote_readers
            .values()
            .filter(|r| r.topic_name == topic_name && r.type_name == type_name)
            .collect()
    }

    fn endpoints_match(local_writer: &LocalEndpoint, remote_reader: &DiscoveredEndpoint) -> bool {
        if local_writer.topic_name != remote_reader.topic_name {
            return false;
        }
        if local_writer.type_name != remote_reader.type_name {
            return false;
        }
        qos_compatible(&local_writer.qos, &remote_reader.qos)
    }

    fn endpoints_match_wr(remote_writer: &DiscoveredEndpoint, local_reader: &LocalEndpoint) -> bool {
        if remote_writer.topic_name != local_reader.topic_name {
            return false;
        }
        if remote_writer.type_name != local_reader.type_name {
            return false;
        }
        qos_compatible(&remote_writer.qos, &local_reader.qos)
    }

    fn check_matches_for_local_writer(&self, writer: &LocalEndpoint) {
        for reader in self.remote_readers.values() {
            if Self::endpoints_match(writer, reader) {
                for cb in &self.on_match_callbacks {
                    cb(MatchEvent::WriterMatched, &writer.guid, &reader.endpoint_guid);
                }
            }
        }
    }

    fn check_matches_for_local_reader(&self, reader: &LocalEndpoint) {
        for writer in self.remote_writers.values() {
            if Self::endpoints_match_wr(writer, reader) {
                for cb in &self.on_match_callbacks {
                    cb(MatchEvent::ReaderMatched, &reader.guid, &writer.endpoint_guid);
                }
            }
        }
    }

    fn check_matches_for_remote_writer(&self, remote_writer: &DiscoveredEndpoint) {
        for local_reader in self.local_readers.values() {
            if Self::endpoints_match_wr(remote_writer, local_reader) {
                for cb in &self.on_match_callbacks {
                    cb(MatchEvent::ReaderMatched, &local_reader.guid, &remote_writer.endpoint_guid);
                }
            }
        }
    }

    fn check_matches_for_remote_reader(&self, remote_reader: &DiscoveredEndpoint) {
        for local_writer in self.local_writers.values() {
            if Self::endpoints_match(local_writer, remote_reader) {
                for cb in &self.on_match_callbacks {
                    cb(MatchEvent::WriterMatched, &local_writer.guid, &remote_reader.endpoint_guid);
                }
            }
        }
    }
}

impl Default for EndpointDatabase {
    fn default() -> Self {
        Self::new()
    }
}

/// Build SEDP endpoint data as PL_CDR for announcement.
fn build_endpoint_data(endpoint: &LocalEndpoint) -> Vec<u8> {
    let mut pl = ParameterListBuilder::new(Endian::Little);

    // PID_ENDPOINT_GUID
    pl.add_parameter(PID_ENDPOINT_GUID, &endpoint.guid.to_bytes());

    // PID_TOPIC_NAME (CDR string)
    let mut ser = CdrSerializer::new(Endian::Little);
    ser.write_string(&endpoint.topic_name);
    pl.add_parameter(PID_TOPIC_NAME, ser.buffer());

    // PID_TYPE_NAME (CDR string)
    let mut ser = CdrSerializer::new(Endian::Little);
    ser.write_string(&endpoint.type_name);
    pl.add_parameter(PID_TYPE_NAME, ser.buffer());

    // PID_RELIABILITY
    pl.add_parameter(PID_RELIABILITY, &serialize_reliability_qos(&endpoint.qos));

    // PID_DURABILITY
    pl.add_parameter(PID_DURABILITY, &serialize_durability_qos(&endpoint.qos));

    // PID_DEFAULT_UNICAST_LOCATOR (for each locator)
    for loc in &endpoint.unicast_locators {
        pl.add_parameter(PID_DEFAULT_UNICAST_LOCATOR, &loc.to_bytes());
    }

    pl.finalize()
}

/// Parse SEDP endpoint data from encapsulated parameter list.
fn parse_endpoint_data(payload: &[u8]) -> Option<DiscoveredEndpoint> {
    let (scheme, offset) = parse_encapsulation_header(payload).ok()?;
    let endian = if scheme == PL_CDR_LE || scheme == CDR_LE {
        Endian::Little
    } else {
        Endian::Big
    };

    let pl_data = &payload[offset..];
    let mut endpoint = DiscoveredEndpoint::new(Guid::new(GuidPrefix::UNKNOWN, EntityId::UNKNOWN));

    for (pid, value) in ParameterListParser::new(pl_data, endian) {
        match pid {
            PID_ENDPOINT_GUID => {
                if value.len() >= 16 {
                    endpoint.endpoint_guid = Guid::from_bytes(value);
                }
            }
            PID_TOPIC_NAME => {
                let mut de = CdrDeserializer::new(value, endian);
                if let Ok(s) = de.read_string() {
                    endpoint.topic_name = s;
                }
            }
            PID_TYPE_NAME => {
                let mut de = CdrDeserializer::new(value, endian);
                if let Ok(s) = de.read_string() {
                    endpoint.type_name = s;
                }
            }
            PID_RELIABILITY => {
                if let Some((kind, _duration)) = deserialize_reliability_qos(value) {
                    endpoint.reliability = kind;
                    endpoint.qos.reliability = kind;
                }
            }
            PID_DURABILITY => {
                if let Some(kind) = deserialize_durability_qos(value) {
                    endpoint.durability = kind;
                    endpoint.qos.durability = kind;
                }
            }
            PID_DEFAULT_UNICAST_LOCATOR => {
                if value.len() >= 24 {
                    endpoint.unicast_locators.push(Locator::from_bytes(value));
                }
            }
            _ => {}
        }
    }

    Some(endpoint)
}

/// Manages SEDP builtin endpoints for endpoint discovery.
///
/// Creates 4 builtin endpoints:
/// - publications writer/reader (announce/discover DataWriters)
/// - subscriptions writer/reader (announce/discover DataReaders)
pub struct SEDPProtocol {
    guid_prefix: GuidPrefix,
    pub_writer: ReliableWriter,
    pub_reader: ReliableReader,
    sub_writer: ReliableWriter,
    sub_reader: ReliableReader,
}

impl SEDPProtocol {
    pub fn new(guid_prefix: GuidPrefix) -> Self {
        Self {
            guid_prefix,
            pub_writer: ReliableWriter::new(
                Guid::new(guid_prefix, EntityId(ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER)),
                2.0,
                100,
            ),
            pub_reader: ReliableReader::new(
                Guid::new(guid_prefix, EntityId(ENTITYID_SEDP_BUILTIN_PUBLICATIONS_READER)),
            ),
            sub_writer: ReliableWriter::new(
                Guid::new(guid_prefix, EntityId(ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER)),
                2.0,
                100,
            ),
            sub_reader: ReliableReader::new(
                Guid::new(guid_prefix, EntityId(ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_READER)),
            ),
        }
    }

    /// Called when SPDP discovers a new participant.
    ///
    /// Sets up reader/writer proxies based on the participant's
    /// builtin_endpoints bitmap.
    pub fn on_participant_discovered(&mut self, pd: &DiscoveredParticipant) {
        let endpoints = pd.builtin_endpoints;

        if endpoints & DISC_BUILTIN_ENDPOINT_PUBLICATIONS_DETECTOR != 0 {
            // Remote has publications reader → our publications writer needs a proxy
            let reader_guid = Guid::new(
                pd.guid_prefix,
                EntityId(ENTITYID_SEDP_BUILTIN_PUBLICATIONS_READER),
            );
            self.pub_writer.add_reader_proxy(reader_guid);
        }

        if endpoints & DISC_BUILTIN_ENDPOINT_PUBLICATIONS_ANNOUNCER != 0 {
            // Remote has publications writer → our publications reader needs a proxy
            let writer_guid = Guid::new(
                pd.guid_prefix,
                EntityId(ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER),
            );
            self.pub_reader.add_writer_proxy(writer_guid);
        }

        if endpoints & DISC_BUILTIN_ENDPOINT_SUBSCRIPTIONS_DETECTOR != 0 {
            let reader_guid = Guid::new(
                pd.guid_prefix,
                EntityId(ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_READER),
            );
            self.sub_writer.add_reader_proxy(reader_guid);
        }

        if endpoints & DISC_BUILTIN_ENDPOINT_SUBSCRIPTIONS_ANNOUNCER != 0 {
            let writer_guid = Guid::new(
                pd.guid_prefix,
                EntityId(ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER),
            );
            self.sub_reader.add_writer_proxy(writer_guid);
        }
    }

    /// Queue a local endpoint for SEDP announcement.
    pub fn announce_endpoint(&mut self, endpoint: &LocalEndpoint) {
        let pl_data = build_endpoint_data(endpoint);
        let mut payload = encapsulation_header(PL_CDR_LE).to_vec();
        payload.extend_from_slice(&pl_data);

        if endpoint.is_writer {
            self.pub_writer.new_change(payload);
        } else {
            self.sub_writer.new_change(payload);
        }
    }

    /// Build SEDP DATA messages for a specific remote participant.
    ///
    /// Returns list of (message_bytes, dest_addr, dest_port).
    pub fn build_announcement_messages(
        &mut self,
        dest_prefix: GuidPrefix,
        dest_meta_locators: &[Locator],
    ) -> Vec<(Vec<u8>, String, u32)> {
        let mut messages = Vec::new();

        if dest_meta_locators.is_empty() {
            return messages;
        }

        let dest_addr = dest_meta_locators[0]
            .ipv4_str()
            .unwrap_or_else(|| "127.0.0.1".to_string());
        let dest_port = dest_meta_locators[0].port;

        // Send publications (our DataWriters)
        for change in self.pub_writer.history() {
            let mut builder = RtpsMessageBuilder::new(self.guid_prefix);
            let now = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default();
            builder.add_info_ts(Some(Timestamp::from_seconds(now.as_secs_f64())));
            builder.add_info_dst(dest_prefix);
            builder.add_data(
                EntityId(ENTITYID_SEDP_BUILTIN_PUBLICATIONS_READER),
                EntityId(ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER),
                change.sequence_number,
                Some(&change.serialized_data),
                None,
                false,
            );
            messages.push((builder.build(), dest_addr.clone(), dest_port));
        }

        // Send subscriptions (our DataReaders)
        for change in self.sub_writer.history() {
            let mut builder = RtpsMessageBuilder::new(self.guid_prefix);
            let now = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default();
            builder.add_info_ts(Some(Timestamp::from_seconds(now.as_secs_f64())));
            builder.add_info_dst(dest_prefix);
            builder.add_data(
                EntityId(ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_READER),
                EntityId(ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER),
                change.sequence_number,
                Some(&change.serialized_data),
                None,
                false,
            );
            messages.push((builder.build(), dest_addr.clone(), dest_port));
        }

        // Send heartbeats
        if !self.pub_writer.history().is_empty() {
            let mut builder = RtpsMessageBuilder::new(self.guid_prefix);
            builder.add_info_dst(dest_prefix);
            builder.add_heartbeat(
                EntityId(ENTITYID_SEDP_BUILTIN_PUBLICATIONS_READER),
                EntityId(ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER),
                self.pub_writer.first_available_sn(),
                self.pub_writer.last_available_sn(),
                self.pub_writer.next_heartbeat_count(),
                false,
                false,
            );
            messages.push((builder.build(), dest_addr.clone(), dest_port));
        }

        if !self.sub_writer.history().is_empty() {
            let mut builder = RtpsMessageBuilder::new(self.guid_prefix);
            builder.add_info_dst(dest_prefix);
            builder.add_heartbeat(
                EntityId(ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_READER),
                EntityId(ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER),
                self.sub_writer.first_available_sn(),
                self.sub_writer.last_available_sn(),
                self.sub_writer.next_heartbeat_count(),
                false,
                false,
            );
            messages.push((builder.build(), dest_addr.clone(), dest_port));
        }

        messages
    }

    /// Handle incoming SEDP publications DATA (remote DataWriter info).
    pub fn handle_publications_data(
        &mut self,
        sm: &DataSubmessage,
        source_prefix: GuidPrefix,
        endpoint_db: &mut EndpointDatabase,
    ) {
        let payload = match &sm.serialized_payload {
            Some(p) => p,
            None => return,
        };

        let endpoint = match parse_endpoint_data(payload) {
            Some(e) => e,
            None => return,
        };

        let writer_guid = Guid::new(source_prefix, sm.writer_id);
        self.pub_reader.record_received(&writer_guid, sm.writer_sn);

        log::info!(
            "Discovered remote writer: {:?} topic={} type={}",
            endpoint.endpoint_guid,
            endpoint.topic_name,
            endpoint.type_name
        );
        endpoint_db.add_remote_writer(endpoint);
    }

    /// Handle incoming SEDP subscriptions DATA (remote DataReader info).
    pub fn handle_subscriptions_data(
        &mut self,
        sm: &DataSubmessage,
        source_prefix: GuidPrefix,
        endpoint_db: &mut EndpointDatabase,
    ) {
        let payload = match &sm.serialized_payload {
            Some(p) => p,
            None => return,
        };

        let endpoint = match parse_endpoint_data(payload) {
            Some(e) => e,
            None => return,
        };

        let writer_guid = Guid::new(source_prefix, sm.writer_id);
        self.sub_reader.record_received(&writer_guid, sm.writer_sn);

        log::info!(
            "Discovered remote reader: {:?} topic={} type={}",
            endpoint.endpoint_guid,
            endpoint.topic_name,
            endpoint.type_name
        );
        endpoint_db.add_remote_reader(endpoint);
    }

    /// Handle incoming HEARTBEAT, return ACKNACK message if needed.
    pub fn handle_heartbeat(
        &mut self,
        sm: &HeartbeatSubmessage,
        source_prefix: GuidPrefix,
    ) -> Option<Vec<u8>> {
        let writer_entity = sm.writer_id.0;

        let (reader, reader_entity) = if writer_entity == ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER {
            (&mut self.pub_reader, ENTITYID_SEDP_BUILTIN_PUBLICATIONS_READER)
        } else if writer_entity == ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER {
            (&mut self.sub_reader, ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_READER)
        } else {
            return None;
        };

        let writer_guid = Guid::new(source_prefix, sm.writer_id);
        let sn_set = reader.process_heartbeat(sm, &writer_guid);

        // Build ACKNACK
        let mut builder = RtpsMessageBuilder::new(self.guid_prefix);
        builder.add_info_dst(source_prefix);
        builder.add_acknack(
            EntityId(reader_entity),
            sm.writer_id,
            &sn_set,
            reader.next_acknack_count(),
            true,
        );
        Some(builder.build())
    }

    pub fn pub_writer(&self) -> &ReliableWriter {
        &self.pub_writer
    }

    pub fn sub_writer(&self) -> &ReliableWriter {
        &self.sub_writer
    }

    pub fn pub_reader(&self) -> &ReliableReader {
        &self.pub_reader
    }

    pub fn sub_reader(&self) -> &ReliableReader {
        &self.sub_reader
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::spdp::DiscoveredParticipant;

    fn test_guid_prefix() -> GuidPrefix {
        GuidPrefix([0xAA; 12])
    }

    fn other_guid_prefix() -> GuidPrefix {
        GuidPrefix([0xBB; 12])
    }

    #[test]
    fn test_endpoint_database_new() {
        let db = EndpointDatabase::new();
        assert_eq!(db.local_writers.len(), 0);
        assert_eq!(db.local_readers.len(), 0);
        assert_eq!(db.remote_writers.len(), 0);
        assert_eq!(db.remote_readers.len(), 0);
    }

    #[test]
    fn test_local_endpoint_new_writer() {
        let guid = Guid::new(test_guid_prefix(), EntityId([0x00, 0x00, 0x01, 0x02]));
        let ep = LocalEndpoint::new_writer(guid, "TestTopic", "TestType", QosPolicy::default());
        assert!(ep.is_writer);
        assert_eq!(ep.topic_name, "TestTopic");
        assert_eq!(ep.type_name, "TestType");
    }

    #[test]
    fn test_local_endpoint_new_reader() {
        let guid = Guid::new(test_guid_prefix(), EntityId([0x00, 0x00, 0x01, 0x07]));
        let ep = LocalEndpoint::new_reader(guid, "TestTopic", "TestType", QosPolicy::default());
        assert!(!ep.is_writer);
    }

    #[test]
    fn test_endpoint_database_add_local_writer() {
        let mut db = EndpointDatabase::new();
        let guid = Guid::new(test_guid_prefix(), EntityId([0x00, 0x00, 0x01, 0x02]));
        let ep = LocalEndpoint::new_writer(guid, "TestTopic", "TestType", QosPolicy::default());
        db.add_local_writer(ep);
        assert_eq!(db.local_writers.len(), 1);
    }

    #[test]
    fn test_endpoint_database_add_remote_reader() {
        let mut db = EndpointDatabase::new();
        let guid = Guid::new(other_guid_prefix(), EntityId([0x00, 0x00, 0x01, 0x07]));
        let mut ep = DiscoveredEndpoint::new(guid);
        ep.topic_name = "TestTopic".to_string();
        ep.type_name = "TestType".to_string();
        db.add_remote_reader(ep);
        assert_eq!(db.remote_readers.len(), 1);
    }

    #[test]
    fn test_endpoint_matching_same_topic_type() {
        let local_guid = Guid::new(test_guid_prefix(), EntityId([0x00, 0x00, 0x01, 0x02]));
        let local_writer = LocalEndpoint::new_writer(local_guid, "HelloWorld", "HelloWorldType", QosPolicy::best_effort());

        let remote_guid = Guid::new(other_guid_prefix(), EntityId([0x00, 0x00, 0x01, 0x07]));
        let mut remote_reader = DiscoveredEndpoint::new(remote_guid);
        remote_reader.topic_name = "HelloWorld".to_string();
        remote_reader.type_name = "HelloWorldType".to_string();
        remote_reader.qos = QosPolicy::best_effort();

        assert!(EndpointDatabase::endpoints_match(&local_writer, &remote_reader));
    }

    #[test]
    fn test_endpoint_matching_different_topic() {
        let local_guid = Guid::new(test_guid_prefix(), EntityId([0x00, 0x00, 0x01, 0x02]));
        let local_writer = LocalEndpoint::new_writer(local_guid, "TopicA", "TestType", QosPolicy::default());

        let remote_guid = Guid::new(other_guid_prefix(), EntityId([0x00, 0x00, 0x01, 0x07]));
        let mut remote_reader = DiscoveredEndpoint::new(remote_guid);
        remote_reader.topic_name = "TopicB".to_string();
        remote_reader.type_name = "TestType".to_string();

        assert!(!EndpointDatabase::endpoints_match(&local_writer, &remote_reader));
    }

    #[test]
    fn test_endpoint_matching_qos_compatible() {
        let local_guid = Guid::new(test_guid_prefix(), EntityId([0x00, 0x00, 0x01, 0x02]));
        let local_writer = LocalEndpoint::new_writer(local_guid, "Test", "TestType", QosPolicy::reliable());

        let remote_guid = Guid::new(other_guid_prefix(), EntityId([0x00, 0x00, 0x01, 0x07]));
        let mut remote_reader = DiscoveredEndpoint::new(remote_guid);
        remote_reader.topic_name = "Test".to_string();
        remote_reader.type_name = "TestType".to_string();
        remote_reader.qos = QosPolicy::best_effort();

        // Reliable writer can satisfy best-effort reader
        assert!(EndpointDatabase::endpoints_match(&local_writer, &remote_reader));
    }

    #[test]
    fn test_endpoint_matching_qos_incompatible() {
        let local_guid = Guid::new(test_guid_prefix(), EntityId([0x00, 0x00, 0x01, 0x02]));
        let local_writer = LocalEndpoint::new_writer(local_guid, "Test", "TestType", QosPolicy::best_effort());

        let remote_guid = Guid::new(other_guid_prefix(), EntityId([0x00, 0x00, 0x01, 0x07]));
        let mut remote_reader = DiscoveredEndpoint::new(remote_guid);
        remote_reader.topic_name = "Test".to_string();
        remote_reader.type_name = "TestType".to_string();
        remote_reader.qos = QosPolicy::reliable();

        // Best-effort writer cannot satisfy reliable reader
        assert!(!EndpointDatabase::endpoints_match(&local_writer, &remote_reader));
    }

    #[test]
    fn test_sedp_protocol_new() {
        let prefix = test_guid_prefix();
        let sedp = SEDPProtocol::new(prefix);
        assert_eq!(sedp.guid_prefix, prefix);
    }

    #[test]
    fn test_sedp_on_participant_discovered() {
        let prefix = test_guid_prefix();
        let mut sedp = SEDPProtocol::new(prefix);

        let mut pd = DiscoveredParticipant::new(other_guid_prefix());
        pd.builtin_endpoints = BUILTIN_ENDPOINT_SET_DEFAULT;

        sedp.on_participant_discovered(&pd);

        // Should have added proxies
        assert!(sedp.pub_writer.has_reader_proxies());
        assert!(sedp.sub_writer.has_reader_proxies());
    }

    #[test]
    fn test_sedp_announce_endpoint() {
        let prefix = test_guid_prefix();
        let mut sedp = SEDPProtocol::new(prefix);

        let writer_guid = Guid::new(prefix, EntityId([0x00, 0x00, 0x01, 0x02]));
        let endpoint = LocalEndpoint::new_writer(writer_guid, "TestTopic", "TestType", QosPolicy::default());

        sedp.announce_endpoint(&endpoint);
        assert_eq!(sedp.pub_writer.history().len(), 1);
    }

    #[test]
    fn test_build_endpoint_data_roundtrip() {
        let prefix = test_guid_prefix();
        let guid = Guid::new(prefix, EntityId([0x00, 0x00, 0x01, 0x02]));
        let mut endpoint = LocalEndpoint::new_writer(guid, "HelloWorld", "HelloWorldType", QosPolicy::reliable());
        endpoint.unicast_locators.push(Locator::from_ipv4("192.168.1.100", 7401));

        let pl_data = build_endpoint_data(&endpoint);
        let mut payload = encapsulation_header(PL_CDR_LE).to_vec();
        payload.extend_from_slice(&pl_data);

        let parsed = parse_endpoint_data(&payload).unwrap();
        assert_eq!(parsed.endpoint_guid, guid);
        assert_eq!(parsed.topic_name, "HelloWorld");
        assert_eq!(parsed.type_name, "HelloWorldType");
        assert_eq!(parsed.reliability, ReliabilityKind::Reliable);
        assert!(!parsed.unicast_locators.is_empty());
        assert_eq!(parsed.unicast_locators[0].port, 7401);
    }

    #[test]
    fn test_sedp_build_announcement_messages_empty() {
        let prefix = test_guid_prefix();
        let mut sedp = SEDPProtocol::new(prefix);

        let messages = sedp.build_announcement_messages(other_guid_prefix(), &[]);
        assert!(messages.is_empty());
    }

    #[test]
    fn test_sedp_build_announcement_messages_with_endpoints() {
        let prefix = test_guid_prefix();
        let mut sedp = SEDPProtocol::new(prefix);

        // Add an endpoint
        let writer_guid = Guid::new(prefix, EntityId([0x00, 0x00, 0x01, 0x02]));
        let endpoint = LocalEndpoint::new_writer(writer_guid, "TestTopic", "TestType", QosPolicy::default());
        sedp.announce_endpoint(&endpoint);

        let dest_locator = Locator::from_ipv4("192.168.1.50", 7410);
        let messages = sedp.build_announcement_messages(other_guid_prefix(), &[dest_locator]);

        // Should have DATA + HEARTBEAT
        assert!(messages.len() >= 2);
    }

    #[test]
    fn test_discovered_endpoint_new() {
        let guid = Guid::new(test_guid_prefix(), EntityId([0x00, 0x00, 0x01, 0x02]));
        let ep = DiscoveredEndpoint::new(guid);
        assert_eq!(ep.endpoint_guid, guid);
        assert!(ep.topic_name.is_empty());
        assert!(ep.type_name.is_empty());
        assert_eq!(ep.reliability, ReliabilityKind::BestEffort);
        assert_eq!(ep.durability, DurabilityKind::Volatile);
    }

    #[test]
    fn test_find_matching_remote_readers() {
        let mut db = EndpointDatabase::new();

        // Add local writer
        let local_guid = Guid::new(test_guid_prefix(), EntityId([0x00, 0x00, 0x01, 0x02]));
        let local_writer = LocalEndpoint::new_writer(local_guid, "TestTopic", "TestType", QosPolicy::default());
        db.add_local_writer(local_writer.clone());

        // Add matching remote reader
        let remote_guid = Guid::new(other_guid_prefix(), EntityId([0x00, 0x00, 0x01, 0x07]));
        let mut remote_reader = DiscoveredEndpoint::new(remote_guid);
        remote_reader.topic_name = "TestTopic".to_string();
        remote_reader.type_name = "TestType".to_string();
        db.add_remote_reader(remote_reader);

        // Add non-matching remote reader
        let remote_guid2 = Guid::new(other_guid_prefix(), EntityId([0x00, 0x00, 0x02, 0x07]));
        let mut remote_reader2 = DiscoveredEndpoint::new(remote_guid2);
        remote_reader2.topic_name = "OtherTopic".to_string();
        remote_reader2.type_name = "OtherType".to_string();
        db.add_remote_reader(remote_reader2);

        let matches = db.find_matching_remote_readers(&local_writer);
        assert_eq!(matches.len(), 1);
        assert_eq!(matches[0].endpoint_guid, remote_guid);
    }

    #[test]
    fn test_match_event() {
        assert_eq!(MatchEvent::WriterMatched, MatchEvent::WriterMatched);
        assert_ne!(MatchEvent::WriterMatched, MatchEvent::ReaderMatched);
    }
}
