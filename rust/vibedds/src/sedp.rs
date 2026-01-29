/// Simple Endpoint Discovery Protocol (SEDP).
///
/// After SPDP discovers a remote participant, SEDP exchanges endpoint
/// information (topic, type, QoS) over reliable unicast. This enables
/// matching of DataWriters and DataReaders across participants.

use std::collections::HashMap;
use std::env;

use crate::cdr::{
    encapsulation_header, parse_encapsulation_header, CdrDeserializer, CdrSerializer, Endian,
    ParameterListBuilder, ParameterListParser,
};
use crate::constants::*;
use crate::messages::{DataSubmessage, HeartbeatSubmessage};
use crate::qos::{
    deserialize_durability_qos, deserialize_reliability_qos, qos_compatible,
    serialize_data_representation_qos, serialize_data_representation_qos_rti, serialize_deadline_qos,
    serialize_destination_order_qos, serialize_durability_qos, serialize_history_qos,
    serialize_liveliness_qos, serialize_ownership_qos, serialize_partition_qos,
    serialize_reliability_qos, serialize_type_consistency_enforcement_qos,
    serialize_type_consistency_enforcement_qos_compact, DataRepresentationId, DurabilityKind,
    QosPolicy, ReliabilityKind, TypeConsistencyKind, RTI_DATA_REPRESENTATION_DEFAULT,
    RTI_TYPE_CONSISTENCY_DEFAULT,
};
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
    pub type_information: Option<Vec<u8>>,
    pub type_object: Option<Vec<u8>>,
    pub group_entity_id: Option<u32>,
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
            type_information: None,
            type_object: None,
            group_entity_id: None,
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
    pub type_information: Option<Vec<u8>>,
    pub type_object: Option<Vec<u8>>,
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
            type_information: None,
            type_object: None,
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
            type_information: None,
            type_object: None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum LocatorPid {
    Endpoint,
    Default,
    Both,
}

impl LocatorPid {
    fn from_str(value: &str) -> Option<Self> {
        match value {
            "endpoint" => Some(Self::Endpoint),
            "default" => Some(Self::Default),
            "both" => Some(Self::Both),
            _ => None,
        }
    }
}

#[derive(Debug, Clone)]
struct SedpInteropOptions {
    profile: String,
    include_participant_guid: bool,
    include_protocol_vendor: bool,
    include_extended_qos: bool,
    include_partition: bool,
    include_unicast_locator: bool,
    locator_pid: LocatorPid,
    include_reliability: bool,
    include_durability: bool,
    include_data_representation: bool,
    data_representation: Vec<DataRepresentationId>,
    xtypes_format: String,
    data_representation_raw: Option<Vec<u8>>,
    data_representation_tail: Option<u32>,
    include_type_consistency: bool,
    type_consistency_kind: TypeConsistencyKind,
    type_consistency_raw: Option<Vec<u8>>,
    type_consistency_mask: Option<u32>,
    include_type_information: bool,
    include_type_object: bool,
    group_entity_id: Option<u32>,
    include_rti_vendor_pids: bool,
    include_rti_pid_8002_guid: bool,
    rti_pid_8000: Option<Vec<u8>>,
    rti_pid_8004: Option<Vec<u8>>,
    rti_pid_8009: Option<Vec<u8>>,
    rti_pid_8015: Option<Vec<u8>>,
    rti_pid_0013: Option<Vec<u8>>,
    rti_pid_0018: Option<Vec<u8>>,
    rti_pid_0060: Option<Vec<u8>>,
}

impl Default for SedpInteropOptions {
    fn default() -> Self {
        Self {
            profile: "minimal".to_string(),
            include_participant_guid: false,
            include_protocol_vendor: false,
            include_extended_qos: false,
            include_partition: false,
            include_unicast_locator: true,
            locator_pid: LocatorPid::Default,
            include_reliability: true,
            include_durability: true,
            include_data_representation: false,
            data_representation: vec![],
            xtypes_format: "standard".to_string(),
            data_representation_raw: None,
            data_representation_tail: None,
            include_type_consistency: false,
            type_consistency_kind: TypeConsistencyKind::DisallowTypeCoercion,
            type_consistency_raw: None,
            type_consistency_mask: None,
            include_type_information: false,
            include_type_object: false,
            group_entity_id: None,
            include_rti_vendor_pids: false,
            include_rti_pid_8002_guid: false,
            rti_pid_8000: None,
            rti_pid_8004: None,
            rti_pid_8009: None,
            rti_pid_8015: None,
            rti_pid_0013: None,
            rti_pid_0018: None,
            rti_pid_0060: None,
        }
    }
}

impl SedpInteropOptions {
    fn env_bool(name: &str) -> Option<bool> {
        env::var(name).ok().map(|v| {
            matches!(
                v.trim().to_lowercase().as_str(),
                "1" | "true" | "yes" | "on"
            )
        })
    }

    fn env_str(name: &str) -> Option<String> {
        env::var(name).ok().map(|v| v.trim().to_string())
    }

    fn parse_data_rep_list(value: &str) -> Vec<DataRepresentationId> {
        value
            .split(',')
            .filter_map(|part| match part.trim().to_lowercase().as_str() {
                "xcdr1" | "xcdr" | "xcdr1_only" => Some(DataRepresentationId::Xcdr1),
                "xcdr2" | "xcdr2_only" => Some(DataRepresentationId::Xcdr2),
                "xml" => Some(DataRepresentationId::Xml),
                _ => None,
            })
            .collect()
    }

    fn parse_hex_bytes(value: &str) -> Option<Vec<u8>> {
        let trimmed = value.trim();
        let cleaned = trimmed.strip_prefix("0x").unwrap_or(trimmed);
        let filtered: String = cleaned
            .chars()
            .filter(|ch| ch.is_ascii_hexdigit())
            .collect();
        if filtered.is_empty() || filtered.len() % 2 != 0 {
            return None;
        }
        let mut bytes = Vec::with_capacity(filtered.len() / 2);
        let mut chars = filtered.chars();
        while let (Some(hi), Some(lo)) = (chars.next(), chars.next()) {
            let hex = [hi, lo].iter().collect::<String>();
            let val = u8::from_str_radix(&hex, 16).ok()?;
            bytes.push(val);
        }
        Some(bytes)
    }

    fn from_env() -> Self {
        let mut opts = Self::default();

        if let Some(profile) = Self::env_str("VIBEDDS_SEDP_PROFILE") {
            let profile_lc = profile.to_lowercase();
            opts.profile = profile_lc.clone();
            if profile_lc == "full" {
                opts.include_participant_guid = true;
                opts.include_protocol_vendor = true;
                opts.include_extended_qos = true;
                opts.include_partition = true;
                opts.include_unicast_locator = true;
                opts.locator_pid = LocatorPid::Endpoint;
                opts.include_data_representation = true;
                opts.data_representation = vec![DataRepresentationId::Xcdr1];
                opts.include_type_consistency = true;
                opts.type_consistency_kind = TypeConsistencyKind::DisallowTypeCoercion;
                opts.include_type_information = true;
            } else if profile_lc == "rti" {
                opts.include_participant_guid = true;
                opts.include_protocol_vendor = true;
                opts.include_extended_qos = true;
                opts.include_partition = true;
                opts.include_unicast_locator = true;
                opts.locator_pid = LocatorPid::Endpoint;
                opts.include_data_representation = true;
                opts.data_representation = vec![DataRepresentationId::Xcdr1];
                opts.include_type_consistency = true;
                opts.type_consistency_kind = TypeConsistencyKind::DisallowTypeCoercion;
                opts.include_type_information = true;
                opts.include_type_object = true;
                opts.xtypes_format = "rti".to_string();
                opts.data_representation_raw = Some(RTI_DATA_REPRESENTATION_DEFAULT.to_vec());
                opts.type_consistency_raw = Some(RTI_TYPE_CONSISTENCY_DEFAULT.to_vec());
                opts.include_rti_vendor_pids = true;
                opts.include_rti_pid_8002_guid = true;
                opts.rti_pid_8000 = Some(vec![0x07, 0x03, 0x00, 0x05]);
                opts.rti_pid_8004 = None;
                opts.rti_pid_8009 = Some(vec![0x00, 0x00, 0x00, 0x00]);
                opts.rti_pid_8015 = Some(vec![0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]);
                opts.rti_pid_0013 = Some(vec![0xff, 0xff, 0xff, 0xff]);
                opts.rti_pid_0018 = Some(vec![0xff, 0xff, 0xff, 0xff]);
                opts.rti_pid_0060 = Some(vec![0x08, 0x01, 0x00, 0x00]);
            } else if profile_lc == "minimal" {
                opts = Self::default();
            } else if profile_lc == "rti_strict" {
                opts.include_participant_guid = false;
                opts.include_protocol_vendor = true;
                opts.include_extended_qos = false;
                opts.include_partition = false;
                opts.include_unicast_locator = false;
                opts.locator_pid = LocatorPid::Endpoint;
                opts.include_reliability = false;
                opts.include_durability = false;
                opts.include_data_representation = true;
                opts.data_representation = vec![DataRepresentationId::Xcdr1];
                opts.include_type_consistency = true;
                opts.type_consistency_kind = TypeConsistencyKind::DisallowTypeCoercion;
                opts.include_type_information = false;
                opts.include_type_object = true;
                opts.xtypes_format = "rti".to_string();
                opts.data_representation_raw = Some(RTI_DATA_REPRESENTATION_DEFAULT.to_vec());
                opts.type_consistency_raw = Some(RTI_TYPE_CONSISTENCY_DEFAULT.to_vec());
                opts.include_rti_vendor_pids = true;
                opts.include_rti_pid_8002_guid = true;
                opts.rti_pid_8000 = Some(vec![0x07, 0x03, 0x00, 0x05]);
                opts.rti_pid_8004 = None;
                opts.rti_pid_8009 = Some(vec![0x00, 0x00, 0x00, 0x00]);
                opts.rti_pid_8015 = Some(vec![0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]);
                opts.rti_pid_0013 = Some(vec![0xff, 0xff, 0xff, 0xff]);
                opts.rti_pid_0018 = Some(vec![0xff, 0xff, 0xff, 0xff]);
                opts.rti_pid_0060 = Some(vec![0x08, 0x01, 0x00, 0x00]);
            }
        }

        if let Some(xtypes) = Self::env_bool("VIBEDDS_SEDP_XTYPES") {
            opts.include_data_representation = xtypes;
            opts.include_type_consistency = xtypes;
            opts.include_type_information = xtypes;
        }

        if let Some(data_rep) = Self::env_str("VIBEDDS_SEDP_DATA_REP") {
            if matches!(
                data_rep.to_lowercase().as_str(),
                "none" | "off" | "false" | "0"
            ) {
                opts.include_data_representation = false;
                opts.data_representation.clear();
            } else {
                let reps = Self::parse_data_rep_list(&data_rep);
                if !reps.is_empty() {
                    opts.include_data_representation = true;
                    opts.data_representation = reps;
                }
            }
        }

        if let Some(fmt) = Self::env_str("VIBEDDS_SEDP_XTYPES_FORMAT") {
            let fmt_lc = fmt.to_lowercase();
            if fmt_lc == "standard" || fmt_lc == "rti" || fmt_lc == "raw" {
                opts.xtypes_format = fmt_lc;
            }
        }

        if let Some(raw) = Self::env_str("VIBEDDS_SEDP_DATA_REP_RAW") {
            if let Some(bytes) = Self::parse_hex_bytes(&raw) {
                opts.data_representation_raw = Some(bytes);
                opts.include_data_representation = true;
            }
        }

        if let Some(tail) = Self::env_str("VIBEDDS_SEDP_DATA_REP_TAIL") {
            if let Ok(val) = u32::from_str_radix(tail.trim_start_matches("0x"), 16) {
                opts.data_representation_tail = Some(val);
            } else if let Ok(val) = tail.parse::<u32>() {
                opts.data_representation_tail = Some(val);
            }
        }

        if let Some(tc) = Self::env_str("VIBEDDS_SEDP_TYPE_CONSISTENCY") {
            match tc.to_lowercase().as_str() {
                "off" | "none" | "false" | "0" => {
                    opts.include_type_consistency = false;
                }
                "allow" | "allow_type_coercion" => {
                    opts.include_type_consistency = true;
                    opts.type_consistency_kind = TypeConsistencyKind::AllowTypeCoercion;
                }
                "disallow" | "disallow_type_coercion" => {
                    opts.include_type_consistency = true;
                    opts.type_consistency_kind = TypeConsistencyKind::DisallowTypeCoercion;
                }
                _ => {}
            }
        }

        if let Some(raw) = Self::env_str("VIBEDDS_SEDP_TYPE_CONSISTENCY_RAW") {
            if let Some(bytes) = Self::parse_hex_bytes(&raw) {
                opts.type_consistency_raw = Some(bytes);
                opts.include_type_consistency = true;
            }
        }

        if let Some(mask) = Self::env_str("VIBEDDS_SEDP_TYPE_CONSISTENCY_MASK") {
            if let Ok(val) = u32::from_str_radix(mask.trim_start_matches("0x"), 16) {
                opts.type_consistency_mask = Some(val);
            } else if let Ok(val) = mask.parse::<u32>() {
                opts.type_consistency_mask = Some(val);
            }
        }

        if let Some(val) = Self::env_bool("VIBEDDS_SEDP_INCLUDE_PARTICIPANT_GUID") {
            opts.include_participant_guid = val;
        }
        if let Some(val) = Self::env_bool("VIBEDDS_SEDP_INCLUDE_PROTOCOL_VENDOR") {
            opts.include_protocol_vendor = val;
        }
        if let Some(val) = Self::env_bool("VIBEDDS_SEDP_INCLUDE_EXTENDED_QOS") {
            opts.include_extended_qos = val;
        }
        if let Some(val) = Self::env_bool("VIBEDDS_SEDP_INCLUDE_PARTITION") {
            opts.include_partition = val;
        }
        if let Some(val) = Self::env_bool("VIBEDDS_SEDP_INCLUDE_UNICAST_LOCATOR") {
            opts.include_unicast_locator = val;
        }
        if let Some(val) = Self::env_bool("VIBEDDS_SEDP_INCLUDE_RELIABILITY") {
            opts.include_reliability = val;
        }
        if let Some(val) = Self::env_bool("VIBEDDS_SEDP_INCLUDE_DURABILITY") {
            opts.include_durability = val;
        }
        if let Some(val) = Self::env_bool("VIBEDDS_SEDP_INCLUDE_TYPE_INFORMATION") {
            opts.include_type_information = val;
        }
        if let Some(val) = Self::env_bool("VIBEDDS_SEDP_INCLUDE_TYPE_OBJECT") {
            opts.include_type_object = val;
        }
        if let Some(val) = Self::env_bool("VIBEDDS_SEDP_INCLUDE_RTI_VENDOR_PIDS") {
            opts.include_rti_vendor_pids = val;
        }
        if let Some(val) = Self::env_bool("VIBEDDS_SEDP_INCLUDE_RTI_PID_8002_GUID") {
            opts.include_rti_pid_8002_guid = val;
        }

        if let Some(locator_pid) = Self::env_str("VIBEDDS_SEDP_LOCATOR_PID") {
            if let Some(pid) = LocatorPid::from_str(locator_pid.to_lowercase().as_str()) {
                opts.locator_pid = pid;
            }
        }

        if let Some(group_entity_id) = Self::env_str("VIBEDDS_SEDP_GROUP_ENTITY_ID") {
            if let Ok(val) = u32::from_str_radix(group_entity_id.trim_start_matches("0x"), 16) {
                opts.group_entity_id = Some(val);
            } else if let Ok(val) = group_entity_id.parse::<u32>() {
                opts.group_entity_id = Some(val);
            }
        }

        for (env_key, slot) in [
            ("VIBEDDS_SEDP_RTI_PID_8000", &mut opts.rti_pid_8000),
            ("VIBEDDS_SEDP_RTI_PID_8004", &mut opts.rti_pid_8004),
            ("VIBEDDS_SEDP_RTI_PID_8009", &mut opts.rti_pid_8009),
            ("VIBEDDS_SEDP_RTI_PID_8015", &mut opts.rti_pid_8015),
            ("VIBEDDS_SEDP_RTI_PID_0013", &mut opts.rti_pid_0013),
            ("VIBEDDS_SEDP_RTI_PID_0018", &mut opts.rti_pid_0018),
            ("VIBEDDS_SEDP_RTI_PID_0060", &mut opts.rti_pid_0060),
        ] {
            if let Some(raw) = Self::env_str(env_key) {
                if let Some(bytes) = Self::parse_hex_bytes(&raw) {
                    *slot = Some(bytes);
                }
            }
        }

        opts
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
fn build_endpoint_data(endpoint: &LocalEndpoint, interop: &SedpInteropOptions) -> Vec<u8> {
    let mut pl = ParameterListBuilder::new(Endian::Little);

    // PID_ENDPOINT_GUID
    pl.add_parameter(PID_ENDPOINT_GUID, &endpoint.guid.to_bytes());

    if let Some(group_entity_id) = interop.group_entity_id {
        pl.add_parameter(PID_GROUP_ENTITY_ID, &group_entity_id.to_le_bytes());
    }

    if interop.include_participant_guid {
        let participant_guid = Guid::new(
            endpoint.guid.prefix,
            EntityId(ENTITYID_PARTICIPANT),
        );
        pl.add_parameter(PID_PARTICIPANT_GUID, &participant_guid.to_bytes());
    }

    if interop.include_protocol_vendor {
        pl.add_parameter(
            PID_PROTOCOL_VERSION,
            &[RTPS_VERSION_MAJOR, RTPS_VERSION_MINOR],
        );
        pl.add_parameter(PID_VENDORID, &VENDOR_ID);
    }

    if interop.include_rti_vendor_pids {
        if let Some(ref pid) = interop.rti_pid_8000 {
            pl.add_parameter(PID_RTI_VENDOR_8000, pid);
        }
        if interop.include_rti_pid_8002_guid {
            pl.add_parameter(PID_RTI_VENDOR_8002, &endpoint.guid.to_bytes());
        }
        if let Some(ref pid) = interop.rti_pid_8004 {
            pl.add_parameter(PID_RTI_VENDOR_8004, pid);
        }
        if let Some(ref pid) = interop.rti_pid_8009 {
            pl.add_parameter(PID_RTI_VENDOR_8009, pid);
        }
        if let Some(ref pid) = interop.rti_pid_8015 {
            pl.add_parameter(PID_RTI_VENDOR_8015, pid);
        }
        if endpoint.is_writer {
            if let Some(ref pid) = interop.rti_pid_0013 {
                pl.add_parameter(PID_RTI_VENDOR_0013, pid);
            }
            if let Some(ref pid) = interop.rti_pid_0060 {
                pl.add_parameter(PID_RTI_VENDOR_0060, pid);
            }
        } else if let Some(ref pid) = interop.rti_pid_0018 {
            pl.add_parameter(PID_RTI_VENDOR_0018, pid);
        }
    }

    // PID_TOPIC_NAME (CDR string)
    let mut ser = CdrSerializer::new(Endian::Little);
    ser.write_string(&endpoint.topic_name);
    pl.add_parameter(PID_TOPIC_NAME, ser.buffer());

    // PID_TYPE_NAME (CDR string)
    let mut ser = CdrSerializer::new(Endian::Little);
    ser.write_string(&endpoint.type_name);
    pl.add_parameter(PID_TYPE_NAME, ser.buffer());

    // PID_RELIABILITY
    if interop.include_reliability {
        pl.add_parameter(PID_RELIABILITY, &serialize_reliability_qos(&endpoint.qos));
    }

    // PID_DURABILITY
    if interop.include_durability {
        pl.add_parameter(PID_DURABILITY, &serialize_durability_qos(&endpoint.qos));
    }

    if interop.include_extended_qos {
        pl.add_parameter(
            PID_OWNERSHIP,
            &serialize_ownership_qos(&endpoint.qos, Endian::Little),
        );
        pl.add_parameter(
            PID_LIVELINESS,
            &serialize_liveliness_qos(&endpoint.qos, Endian::Little),
        );
        pl.add_parameter(
            PID_DESTINATION_ORDER,
            &serialize_destination_order_qos(&endpoint.qos, Endian::Little),
        );
        pl.add_parameter(
            PID_DEADLINE,
            &serialize_deadline_qos(&endpoint.qos, Endian::Little),
        );
        pl.add_parameter(
            PID_HISTORY,
            &serialize_history_qos(&endpoint.qos, Endian::Little),
        );
    }

    if interop.include_data_representation
        && (!interop.data_representation.is_empty() || interop.data_representation_raw.is_some())
    {
        let data_rep = if let Some(ref raw) = interop.data_representation_raw {
            raw.clone()
        } else if interop.xtypes_format == "rti" {
            serialize_data_representation_qos_rti(
                &interop.data_representation,
                Endian::Little,
                interop.data_representation_tail,
            )
        } else {
            serialize_data_representation_qos(&interop.data_representation, Endian::Little)
        };
        pl.add_parameter(PID_DATA_REPRESENTATION, &data_rep);
    }

    if !endpoint.is_writer && interop.include_type_consistency {
        let type_consistency = if let Some(ref raw) = interop.type_consistency_raw {
            raw.clone()
        } else if interop.xtypes_format == "rti" {
            serialize_type_consistency_enforcement_qos_compact(
                interop.type_consistency_kind,
                false,
                false,
                false,
                false,
                false,
                interop.type_consistency_mask,
                Endian::Little,
            )
        } else {
            serialize_type_consistency_enforcement_qos(
                interop.type_consistency_kind,
                false,
                false,
                false,
                false,
                false,
                Endian::Little,
            )
        };
        pl.add_parameter(PID_TYPE_CONSISTENCY_ENFORCEMENT, &type_consistency);
    }

    if interop.include_type_information {
        if let Some(ref info) = endpoint.type_information {
            if !info.is_empty() {
                pl.add_parameter(PID_TYPE_INFORMATION, info);
            }
        }
    }

    if interop.include_type_object {
        if let Some(ref obj) = endpoint.type_object {
            if !obj.is_empty() {
                pl.add_parameter(PID_TYPE_OBJECT, obj);
            }
        }
    }

    if interop.include_partition {
        pl.add_parameter(
            PID_PARTITION,
            &serialize_partition_qos(&endpoint.qos, Endian::Little),
        );
    }

    if interop.include_unicast_locator {
        for loc in &endpoint.unicast_locators {
            match interop.locator_pid {
                LocatorPid::Endpoint => {
                    pl.add_parameter(PID_UNICAST_LOCATOR, &loc.to_bytes());
                }
                LocatorPid::Default => {
                    pl.add_parameter(PID_DEFAULT_UNICAST_LOCATOR, &loc.to_bytes());
                }
                LocatorPid::Both => {
                    pl.add_parameter(PID_UNICAST_LOCATOR, &loc.to_bytes());
                    pl.add_parameter(PID_DEFAULT_UNICAST_LOCATOR, &loc.to_bytes());
                }
            }
        }
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
            PID_GROUP_ENTITY_ID => {
                if value.len() >= 4 {
                    endpoint.group_entity_id = Some(u32::from_le_bytes([
                        value[0], value[1], value[2], value[3],
                    ]));
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
            PID_TYPE_INFORMATION => {
                endpoint.type_information = Some(value.to_vec());
            }
            PID_TYPE_OBJECT => {
                endpoint.type_object = Some(value.to_vec());
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
    interop: SedpInteropOptions,
}

impl SEDPProtocol {
    pub fn new(guid_prefix: GuidPrefix) -> Self {
        Self::new_with_options(guid_prefix, SedpInteropOptions::from_env())
    }

    pub fn new_with_options(guid_prefix: GuidPrefix, interop: SedpInteropOptions) -> Self {
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
            interop,
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
        let pl_data = build_endpoint_data(endpoint, &self.interop);
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

        let pl_data = build_endpoint_data(&endpoint, &SedpInteropOptions::default());
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
