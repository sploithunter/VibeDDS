/// DomainParticipant — the main entry point for VibeDDS.
///
/// Generates a unique GUID prefix, manages transport and discovery protocols,
/// and runs the event loop.

use std::collections::HashMap;
use std::io;
use std::net::Ipv4Addr;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use crate::constants::*;
use crate::endpoint::{DataReader, DataWriter};
use crate::messages::Submessage;
use crate::sedp::{EndpointDatabase, LocalEndpoint, SEDPProtocol};
use crate::spdp::{DiscoveredParticipant, ParticipantDatabase, SpdpReader, SpdpWriter};
use crate::transport::UdpTransport;
use crate::types::{EntityId, Guid, GuidPrefix, Timestamp};
use crate::wire::parse_rtps_message;

/// Generate a unique 12-byte GuidPrefix.
/// Layout: vendorId(2) + PID(4) + timestamp_low(2) + random(4)
pub fn generate_guid_prefix() -> GuidPrefix {
    let mut buf = [0u8; 12];
    buf[0] = VENDOR_ID[0];
    buf[1] = VENDOR_ID[1];

    // PID (process ID)
    let pid = std::process::id();
    buf[2..6].copy_from_slice(&pid.to_le_bytes());

    // Timestamp low bytes
    let ts = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as u16;
    buf[6..8].copy_from_slice(&ts.to_le_bytes());

    // Random bytes
    let random: [u8; 4] = rand::random();
    buf[8..12].copy_from_slice(&random);

    GuidPrefix(buf)
}

/// RTPS DomainParticipant.
pub struct DomainParticipant {
    domain_id: u16,
    participant_id: u16,
    guid_prefix: GuidPrefix,
    transport: UdpTransport,
    participant_db: ParticipantDatabase,
    endpoint_db: EndpointDatabase,
    spdp_writer: Option<SpdpWriter>,
    sedp: Option<SEDPProtocol>,
    spdp_announce_interval: Duration,
    last_spdp_announce: Instant,
    running: bool,
    next_writer_id: u32,
    next_reader_id: u32,

    // User endpoints
    user_writers: HashMap<EntityId, Arc<Mutex<DataWriter>>>,
    user_readers: HashMap<EntityId, Arc<Mutex<DataReader>>>,

    // Track current INFO_TS for incoming messages
    current_timestamp: Option<Timestamp>,

    // Callbacks
    on_discovered: Vec<Box<dyn Fn(&DiscoveredParticipant) + Send>>,
    on_lost: Vec<Box<dyn Fn(&DiscoveredParticipant) + Send>>,
}

impl DomainParticipant {
    pub fn new(domain_id: u16, participant_id: u16) -> Self {
        Self::with_guid_prefix(domain_id, participant_id, generate_guid_prefix())
    }

    pub fn with_guid_prefix(domain_id: u16, participant_id: u16, guid_prefix: GuidPrefix) -> Self {
        Self {
            domain_id,
            participant_id,
            guid_prefix,
            transport: UdpTransport::new(domain_id, participant_id),
            participant_db: ParticipantDatabase::new(),
            endpoint_db: EndpointDatabase::new(),
            spdp_writer: None,
            sedp: None,
            spdp_announce_interval: Duration::from_secs(30),
            last_spdp_announce: Instant::now() - Duration::from_secs(60), // Force immediate announce
            running: false,
            next_writer_id: 1,
            next_reader_id: 1,
            user_writers: HashMap::new(),
            user_readers: HashMap::new(),
            current_timestamp: None,
            on_discovered: Vec::new(),
            on_lost: Vec::new(),
        }
    }

    pub fn guid_prefix(&self) -> GuidPrefix {
        self.guid_prefix
    }

    pub fn domain_id(&self) -> u16 {
        self.domain_id
    }

    pub fn participant_id(&self) -> u16 {
        self.participant_id
    }

    pub fn transport(&self) -> &UdpTransport {
        &self.transport
    }

    pub fn participant_db(&self) -> &ParticipantDatabase {
        &self.participant_db
    }

    pub fn endpoint_db(&self) -> &EndpointDatabase {
        &self.endpoint_db
    }

    /// Set the SPDP announce interval.
    pub fn set_spdp_announce_interval(&mut self, interval: Duration) {
        self.spdp_announce_interval = interval;
    }

    /// Register callback for new participant discovery.
    pub fn on_participant_discovered<F>(&mut self, callback: F)
    where
        F: Fn(&DiscoveredParticipant) + Send + 'static,
    {
        self.on_discovered.push(Box::new(callback));
    }

    /// Register callback for participant loss (lease expiry).
    pub fn on_participant_lost<F>(&mut self, callback: F)
    where
        F: Fn(&DiscoveredParticipant) + Send + 'static,
    {
        self.on_lost.push(Box::new(callback));
    }

    /// Open transport, initialize protocols.
    pub fn start(&mut self) -> io::Result<()> {
        self.transport.open()?;

        self.spdp_writer = Some(SpdpWriter::new(
            self.guid_prefix,
            self.transport.local_ip(),
            self.transport.metatraffic_unicast_port(),
            self.transport.user_unicast_port(),
        ));

        self.sedp = Some(SEDPProtocol::new(self.guid_prefix));

        self.running = true;
        log::info!(
            "Participant started: guid={:?}, domain={}, pid={}",
            self.guid_prefix,
            self.domain_id,
            self.participant_id
        );
        Ok(())
    }

    /// Stop the participant and close transport.
    pub fn stop(&mut self) {
        self.running = false;
        self.transport.close();
        log::info!("Participant stopped");
    }

    /// Send an SPDP announcement now.
    pub fn announce_spdp(&mut self) -> io::Result<()> {
        if let Some(writer) = &mut self.spdp_writer {
            let data = writer.build_announcement();
            self.transport.send_multicast(&data)?;
            self.last_spdp_announce = Instant::now();
            log::debug!("Sent SPDP announcement");
        }
        Ok(())
    }

    /// Register a DataWriter for a topic.
    /// Returns the writer's GUID.
    pub fn register_writer(
        &mut self,
        topic_name: &str,
        type_name: &str,
        qos: crate::qos::QosPolicy,
    ) -> Guid {
        let entity_id = EntityId([0x00, 0x00, (self.next_writer_id & 0xFF) as u8, 0x02]);
        self.next_writer_id += 1;
        let guid = Guid::new(self.guid_prefix, entity_id);

        let mut endpoint = LocalEndpoint::new_writer(guid, topic_name, type_name, qos);
        endpoint.unicast_locators.push(crate::types::Locator::from_ipv4(
            &self.transport.local_ip().to_string(),
            self.transport.user_unicast_port() as u32,
        ));

        // Register with endpoint database
        self.endpoint_db.add_local_writer(endpoint.clone());

        // Announce via SEDP
        if let Some(sedp) = &mut self.sedp {
            sedp.announce_endpoint(&endpoint);
        }

        log::info!(
            "Registered writer: {:?} topic={} type={}",
            guid,
            topic_name,
            type_name
        );

        guid
    }

    /// Register a DataReader for a topic.
    /// Returns the reader's GUID.
    pub fn register_reader(
        &mut self,
        topic_name: &str,
        type_name: &str,
        qos: crate::qos::QosPolicy,
    ) -> Guid {
        let entity_id = EntityId([0x00, 0x00, (self.next_reader_id & 0xFF) as u8, 0x07]);
        self.next_reader_id += 1;
        let guid = Guid::new(self.guid_prefix, entity_id);

        let mut endpoint = LocalEndpoint::new_reader(guid, topic_name, type_name, qos);
        endpoint.unicast_locators.push(crate::types::Locator::from_ipv4(
            &self.transport.local_ip().to_string(),
            self.transport.user_unicast_port() as u32,
        ));

        // Register with endpoint database
        self.endpoint_db.add_local_reader(endpoint.clone());

        // Announce via SEDP
        if let Some(sedp) = &mut self.sedp {
            sedp.announce_endpoint(&endpoint);
        }

        log::info!(
            "Registered reader: {:?} topic={} type={}",
            guid,
            topic_name,
            type_name
        );

        guid
    }

    /// Create a DataWriter for a topic and register it.
    /// Returns a shared reference to the DataWriter.
    pub fn create_writer(
        &mut self,
        topic_name: &str,
        type_name: &str,
        qos: crate::qos::QosPolicy,
    ) -> Arc<Mutex<DataWriter>> {
        let entity_id = EntityId([0x00, 0x00, (self.next_writer_id & 0xFF) as u8, 0x02]);
        self.next_writer_id += 1;
        let guid = Guid::new(self.guid_prefix, entity_id.clone());

        // Create the DataWriter
        let is_reliable = qos.reliability == crate::qos::ReliabilityKind::Reliable;
        let writer = DataWriter::new(
            guid.clone(),
            topic_name.to_string(),
            type_name.to_string(),
            is_reliable,
        );
        let writer_arc = Arc::new(Mutex::new(writer));
        self.user_writers.insert(entity_id.clone(), Arc::clone(&writer_arc));

        // Also register in endpoint database for SEDP
        let mut endpoint = LocalEndpoint::new_writer(guid, topic_name, type_name, qos);
        endpoint.unicast_locators.push(crate::types::Locator::from_ipv4(
            &self.transport.local_ip().to_string(),
            self.transport.user_unicast_port() as u32,
        ));
        self.endpoint_db.add_local_writer(endpoint.clone());

        // Announce via SEDP
        if let Some(sedp) = &mut self.sedp {
            sedp.announce_endpoint(&endpoint);
        }

        log::info!(
            "Created writer: {:?} topic={} type={}",
            guid,
            topic_name,
            type_name
        );

        writer_arc
    }

    /// Create a DataReader for a topic and register it.
    /// Returns a shared reference to the DataReader.
    pub fn create_reader(
        &mut self,
        topic_name: &str,
        type_name: &str,
        qos: crate::qos::QosPolicy,
    ) -> Arc<Mutex<DataReader>> {
        let entity_id = EntityId([0x00, 0x00, (self.next_reader_id & 0xFF) as u8, 0x07]);
        self.next_reader_id += 1;
        let guid = Guid::new(self.guid_prefix, entity_id.clone());

        // Create the DataReader
        let is_reliable = qos.reliability == crate::qos::ReliabilityKind::Reliable;
        let reader = DataReader::new(
            guid.clone(),
            topic_name.to_string(),
            type_name.to_string(),
            is_reliable,
        );
        let reader_arc = Arc::new(Mutex::new(reader));
        self.user_readers.insert(entity_id.clone(), Arc::clone(&reader_arc));

        // Also register in endpoint database for SEDP
        let mut endpoint = LocalEndpoint::new_reader(guid, topic_name, type_name, qos);
        endpoint.unicast_locators.push(crate::types::Locator::from_ipv4(
            &self.transport.local_ip().to_string(),
            self.transport.user_unicast_port() as u32,
        ));
        self.endpoint_db.add_local_reader(endpoint.clone());

        // Announce via SEDP
        if let Some(sedp) = &mut self.sedp {
            sedp.announce_endpoint(&endpoint);
        }

        log::info!(
            "Created reader: {:?} topic={} type={}",
            guid,
            topic_name,
            type_name
        );

        reader_arc
    }

    /// Get a user writer by entity ID.
    pub fn get_writer(&self, entity_id: &EntityId) -> Option<Arc<Mutex<DataWriter>>> {
        self.user_writers.get(entity_id).cloned()
    }

    /// Get a user reader by entity ID.
    pub fn get_reader(&self, entity_id: &EntityId) -> Option<Arc<Mutex<DataReader>>> {
        self.user_readers.get(entity_id).cloned()
    }

    /// Send a DATA message from a writer to all matched readers.
    pub fn send_data(&mut self, writer: &mut DataWriter, payload: &[u8]) -> io::Result<()> {
        let msg = writer.write(payload);

        // Find matched remote readers via endpoint database
        let matched_readers = self.endpoint_db.find_readers_by_topic(
            &writer.topic_name,
            &writer.type_name,
        );

        if matched_readers.is_empty() {
            // Send to user multicast (not implemented yet, use unicast to known participants)
            log::debug!("No matched readers, broadcasting to all participants");
            for participant in self.participant_db.iter() {
                for locator in &participant.default_unicast_locators {
                    if let Some(addr_str) = locator.ipv4_str() {
                        if let Ok(ip) = addr_str.parse::<Ipv4Addr>() {
                            self.transport.send_unicast(&msg, ip, locator.port as u16)?;
                        }
                    }
                }
            }
        } else {
            // Send to matched readers
            for reader_info in matched_readers {
                for locator in &reader_info.unicast_locators {
                    if let Some(addr_str) = locator.ipv4_str() {
                        if let Ok(ip) = addr_str.parse::<Ipv4Addr>() {
                            self.transport.send_unicast(&msg, ip, locator.port as u16)?;
                        }
                    }
                }
            }
        }

        Ok(())
    }

    /// Send SEDP announcements to all discovered participants.
    pub fn announce_sedp(&mut self) -> io::Result<()> {
        if self.sedp.is_none() {
            return Ok(());
        }

        // Collect participant info first to avoid borrow issues
        let participants: Vec<_> = self
            .participant_db
            .iter()
            .map(|p| (p.guid_prefix, p.metatraffic_unicast_locators.clone()))
            .collect();

        for (prefix, locators) in participants {
            if let Some(sedp) = &mut self.sedp {
                let messages = sedp.build_announcement_messages(prefix, &locators);
                for (data, addr, port) in messages {
                    if let Ok(ip) = addr.parse::<Ipv4Addr>() {
                        self.transport.send_unicast(&data, ip, port as u16)?;
                    }
                }
            }
        }

        Ok(())
    }

    /// Run one iteration of the event loop.
    pub fn spin_once(&mut self, timeout: Duration) -> io::Result<()> {
        let now = Instant::now();

        // Periodic SPDP announce
        if now.duration_since(self.last_spdp_announce) >= self.spdp_announce_interval {
            self.announce_spdp()?;
        }

        // Process incoming packets
        let deadline = Instant::now() + timeout;
        while Instant::now() < deadline {
            let mut received_any = false;

            // Check SPDP multicast
            if let Some(pkt) = self.transport.try_recv_spdp_multicast()? {
                self.handle_spdp_packet(&pkt.data)?;
                received_any = true;
            }

            // Check metatraffic unicast
            if let Some(pkt) = self.transport.try_recv_metatraffic()? {
                self.handle_metatraffic_packet(&pkt.data)?;
                received_any = true;
            }

            // Check user unicast
            if let Some(pkt) = self.transport.try_recv_user()? {
                self.handle_user_packet(&pkt.data)?;
                received_any = true;
            }

            if !received_any {
                // Sleep a bit to avoid busy loop
                std::thread::sleep(Duration::from_millis(10));
            }
        }

        // Check lease expiry
        let expired = self.participant_db.remove_expired();
        for p in &expired {
            log::info!("Participant expired: {:?}", p.guid_prefix);
            for cb in &self.on_lost {
                cb(p);
            }
        }

        Ok(())
    }

    /// Run the event loop for the specified duration (or indefinitely if None).
    pub fn spin(&mut self, duration: Option<Duration>) -> io::Result<()> {
        let start = Instant::now();
        while self.running {
            if let Some(d) = duration {
                if start.elapsed() >= d {
                    break;
                }
            }
            self.spin_once(Duration::from_millis(100))?;
        }
        Ok(())
    }

    fn handle_spdp_packet(&mut self, data: &[u8]) -> io::Result<()> {
        if data.len() < 20 {
            return Ok(());
        }

        if let Some(participant) = SpdpReader::parse_announcement(data) {
            // Skip our own announcements
            if participant.guid_prefix == self.guid_prefix {
                return Ok(());
            }

            let is_new = self.participant_db.update(participant.clone());
            if is_new {
                log::info!(
                    "Discovered participant: {:?}, vendor={:?}",
                    participant.guid_prefix,
                    participant.vendor_id
                );

                // Notify SEDP of new participant
                if let Some(sedp) = &mut self.sedp {
                    sedp.on_participant_discovered(&participant);
                }

                // Send SEDP announcements to this participant
                if let Some(sedp) = &mut self.sedp {
                    let messages = sedp.build_announcement_messages(
                        participant.guid_prefix,
                        &participant.metatraffic_unicast_locators,
                    );
                    for (msg_data, addr, port) in messages {
                        if let Ok(ip) = addr.parse::<Ipv4Addr>() {
                            let _ = self.transport.send_unicast(&msg_data, ip, port as u16);
                        }
                    }
                }

                for cb in &self.on_discovered {
                    cb(&participant);
                }
            }
        }

        Ok(())
    }

    fn handle_metatraffic_packet(&mut self, data: &[u8]) -> io::Result<()> {
        let msg = match parse_rtps_message(data) {
            Ok(m) => m,
            Err(_) => return Ok(()),
        };

        // Skip our own messages
        if msg.header.guid_prefix == self.guid_prefix {
            return Ok(());
        }

        let source_prefix = msg.header.guid_prefix;

        for submsg in &msg.submessages {
            match submsg {
                Submessage::Data(data_sm) => {
                    // Check if this is SEDP data
                    let writer_entity = data_sm.writer_id.0;
                    if writer_entity == ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER {
                        if let Some(sedp) = &mut self.sedp {
                            sedp.handle_publications_data(data_sm, source_prefix, &mut self.endpoint_db);
                        }
                    } else if writer_entity == ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER {
                        if let Some(sedp) = &mut self.sedp {
                            sedp.handle_subscriptions_data(data_sm, source_prefix, &mut self.endpoint_db);
                        }
                    }
                }
                Submessage::Heartbeat(hb_sm) => {
                    // Handle SEDP heartbeats
                    if let Some(sedp) = &mut self.sedp {
                        if let Some(acknack_data) = sedp.handle_heartbeat(hb_sm, source_prefix) {
                            // Send ACKNACK back
                            if let Some(participant) = self.participant_db.get(&source_prefix) {
                                if let Some(loc) = participant.metatraffic_unicast_locators.first() {
                                    let addr = loc.ipv4_str().unwrap_or_else(|| "127.0.0.1".to_string());
                                    if let Ok(ip) = addr.parse::<Ipv4Addr>() {
                                        let _ = self.transport.send_unicast(&acknack_data, ip, loc.port as u16);
                                    }
                                }
                            }
                        }
                    }
                }
                _ => {}
            }
        }

        Ok(())
    }

    fn handle_user_packet(&mut self, data: &[u8]) -> io::Result<()> {
        let msg = match parse_rtps_message(data) {
            Ok(m) => m,
            Err(e) => {
                log::debug!("Failed to parse user packet: {:?}", e);
                return Ok(());
            }
        };

        // Skip our own messages
        if msg.header.guid_prefix == self.guid_prefix {
            return Ok(());
        }

        let source_prefix = msg.header.guid_prefix;
        self.current_timestamp = None;

        for submsg in &msg.submessages {
            match submsg {
                Submessage::InfoTimestamp(ts_sm) => {
                    self.current_timestamp = ts_sm.timestamp.clone();
                }
                Submessage::Data(data_sm) => {
                    // Route to appropriate reader
                    let reader_id = &data_sm.reader_id;
                    let writer_id = &data_sm.writer_id;
                    let writer_guid = Guid::new(source_prefix, writer_id.clone());

                    // If reader_id is UNKNOWN, route to all matching readers
                    if reader_id.0 == ENTITYID_UNKNOWN {
                        // Find readers that match by topic/type
                        // First, find the remote writer info to get topic/type
                        if let Some(remote_writer) = self.endpoint_db.get_remote_writer(&writer_guid) {
                            let topic_name = remote_writer.topic_name.clone();
                            let type_name = remote_writer.type_name.clone();

                            // Find local readers matching this topic/type
                            for (entity_id, reader_arc) in &self.user_readers {
                                let mut reader = reader_arc.lock().unwrap();
                                if reader.topic_name == topic_name && reader.type_name == type_name {
                                    if let Some(payload) = &data_sm.serialized_payload {
                                        let sn = data_sm.writer_sn.clone();
                                        reader.receive(
                                            payload.clone(),
                                            writer_guid.clone(),
                                            sn,
                                            self.current_timestamp.clone(),
                                        );
                                        log::debug!(
                                            "Delivered DATA to reader {:?} from writer {:?}",
                                            entity_id, writer_guid
                                        );
                                    }
                                }
                            }
                        } else {
                            // Remote writer not known, try to deliver to any reader with matching entity kind
                            log::debug!(
                                "Unknown remote writer {:?}, attempting broadcast delivery",
                                writer_guid
                            );
                            for (_entity_id, reader_arc) in &self.user_readers {
                                let mut reader = reader_arc.lock().unwrap();
                                if let Some(payload) = &data_sm.serialized_payload {
                                    let sn = data_sm.writer_sn.clone();
                                    reader.receive(
                                        payload.clone(),
                                        writer_guid.clone(),
                                        sn,
                                        self.current_timestamp.clone(),
                                    );
                                }
                            }
                        }
                    } else {
                        // Specific reader targeted
                        if let Some(reader_arc) = self.user_readers.get(reader_id) {
                            let mut reader = reader_arc.lock().unwrap();
                            if let Some(payload) = &data_sm.serialized_payload {
                                let sn = data_sm.writer_sn.clone();
                                reader.receive(
                                    payload.clone(),
                                    writer_guid,
                                    sn,
                                    self.current_timestamp.clone(),
                                );
                                log::debug!(
                                    "Delivered DATA to specific reader {:?}",
                                    reader_id
                                );
                            }
                        }
                    }
                }
                Submessage::Heartbeat(hb_sm) => {
                    // Handle heartbeat from reliable writers
                    let writer_guid = Guid::new(source_prefix, hb_sm.writer_id.clone());
                    log::debug!(
                        "Received HEARTBEAT from {:?}, first={}, last={}, count={}",
                        writer_guid,
                        hb_sm.first_sn.value(),
                        hb_sm.last_sn.value(),
                        hb_sm.count
                    );
                    // TODO: Send ACKNACK if reliable reader
                }
                Submessage::AckNack(an_sm) => {
                    // Handle ACKNACK from reliable readers
                    let reader_guid = Guid::new(source_prefix, an_sm.reader_id.clone());
                    log::debug!(
                        "Received ACKNACK from {:?}, base={}, count={}",
                        reader_guid,
                        an_sm.reader_sn_state.base.value(),
                        an_sm.count
                    );
                    // TODO: Process ACKNACK and potentially retransmit
                }
                _ => {}
            }
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_generate_guid_prefix() {
        let p1 = generate_guid_prefix();
        let p2 = generate_guid_prefix();

        // Should have vendor ID prefix
        assert_eq!(p1.0[0], VENDOR_ID[0]);
        assert_eq!(p1.0[1], VENDOR_ID[1]);

        // Should be unique (random part)
        assert_ne!(p1.0, p2.0);
    }

    #[test]
    fn test_participant_new() {
        let p = DomainParticipant::new(0, 0);
        assert_eq!(p.domain_id(), 0);
        assert_eq!(p.participant_id(), 0);
        assert_eq!(p.guid_prefix().0[0], VENDOR_ID[0]);
    }

    #[test]
    fn test_participant_with_custom_prefix() {
        let prefix = GuidPrefix([0xAA; 12]);
        let p = DomainParticipant::with_guid_prefix(0, 0, prefix);
        assert_eq!(p.guid_prefix(), prefix);
    }

    #[test]
    fn test_participant_different_domain_and_id() {
        let p = DomainParticipant::new(5, 3);
        assert_eq!(p.domain_id(), 5);
        assert_eq!(p.participant_id(), 3);
    }

    #[test]
    fn test_participant_transport_accessor() {
        let p = DomainParticipant::new(0, 0);
        let transport = p.transport();
        // Verify transport has correct ports for domain 0, participant 0
        assert_eq!(transport.spdp_multicast_port(), 7400);
        assert_eq!(transport.metatraffic_unicast_port(), 7410);
        assert_eq!(transport.user_unicast_port(), 7401);
    }

    #[test]
    fn test_participant_db_accessor() {
        let p = DomainParticipant::new(0, 0);
        let db = p.participant_db();
        assert!(db.is_empty());
        assert_eq!(db.len(), 0);
    }

    #[test]
    fn test_set_spdp_announce_interval() {
        let mut p = DomainParticipant::new(0, 0);
        p.set_spdp_announce_interval(Duration::from_secs(10));
        // No direct way to verify, but ensures no panic
    }

    #[test]
    fn test_register_callbacks() {
        let mut p = DomainParticipant::new(0, 0);

        // Register discovery callback
        p.on_participant_discovered(|_participant| {
            // Callback registered successfully
        });

        // Register lost callback
        p.on_participant_lost(|_participant| {
            // Callback registered successfully
        });

        // Can register multiple callbacks
        p.on_participant_discovered(|_participant| {});
        p.on_participant_lost(|_participant| {});
    }

    #[test]
    fn test_participant_start_stop() {
        let mut p = DomainParticipant::new(0, 10); // Use participant_id 10 to avoid port conflicts

        // Start should succeed
        let result = p.start();
        assert!(result.is_ok(), "Failed to start participant: {:?}", result.err());

        // Stop should not panic
        p.stop();
    }

    #[test]
    fn test_participant_announce_before_start() {
        let mut p = DomainParticipant::new(0, 11);

        // Announce before start - should succeed but do nothing (no writer)
        let result = p.announce_spdp();
        assert!(result.is_ok());
    }

    #[test]
    fn test_participant_spin_once_before_start() {
        let mut p = DomainParticipant::new(0, 12);

        // spin_once before start - sockets not open, should handle gracefully
        let result = p.spin_once(Duration::from_millis(10));
        assert!(result.is_ok());
    }

    #[test]
    fn test_create_writer() {
        let mut p = DomainParticipant::new(0, 13);
        p.start().expect("Failed to start");

        let writer_arc = p.create_writer(
            "TestTopic",
            "TestType",
            crate::qos::QosPolicy::best_effort(),
        );

        // Verify writer was created
        let writer = writer_arc.lock().unwrap();
        assert_eq!(writer.topic_name, "TestTopic");
        assert_eq!(writer.type_name, "TestType");
        assert!(!writer.is_reliable());

        // Verify entity ID has writer kind
        let entity_id = writer.entity_id();
        assert_eq!(entity_id.0[3] & 0x0F, 0x02); // user writer kind

        p.stop();
    }

    #[test]
    fn test_create_reader() {
        let mut p = DomainParticipant::new(0, 14);
        p.start().expect("Failed to start");

        let reader_arc = p.create_reader(
            "TestTopic",
            "TestType",
            crate::qos::QosPolicy::reliable(),
        );

        // Verify reader was created
        let reader = reader_arc.lock().unwrap();
        assert_eq!(reader.topic_name, "TestTopic");
        assert_eq!(reader.type_name, "TestType");
        assert!(reader.is_reliable());

        // Verify entity ID has reader kind
        let entity_id = reader.entity_id();
        assert_eq!(entity_id.0[3] & 0x0F, 0x07); // user reader kind

        p.stop();
    }

    #[test]
    fn test_get_writer() {
        let mut p = DomainParticipant::new(0, 15);
        p.start().expect("Failed to start");

        let writer_arc = p.create_writer(
            "TestTopic",
            "TestType",
            crate::qos::QosPolicy::default(),
        );

        let entity_id = {
            let writer = writer_arc.lock().unwrap();
            writer.entity_id()
        };

        // Get writer by entity ID
        let retrieved = p.get_writer(&entity_id);
        assert!(retrieved.is_some());

        // Non-existent writer
        let fake_id = EntityId([0xFF, 0xFF, 0xFF, 0xFF]);
        assert!(p.get_writer(&fake_id).is_none());

        p.stop();
    }

    #[test]
    fn test_get_reader() {
        let mut p = DomainParticipant::new(0, 16);
        p.start().expect("Failed to start");

        let reader_arc = p.create_reader(
            "TestTopic",
            "TestType",
            crate::qos::QosPolicy::default(),
        );

        let entity_id = {
            let reader = reader_arc.lock().unwrap();
            reader.entity_id()
        };

        // Get reader by entity ID
        let retrieved = p.get_reader(&entity_id);
        assert!(retrieved.is_some());

        // Non-existent reader
        let fake_id = EntityId([0xFF, 0xFF, 0xFF, 0xFF]);
        assert!(p.get_reader(&fake_id).is_none());

        p.stop();
    }

    #[test]
    fn test_create_multiple_writers() {
        let mut p = DomainParticipant::new(0, 17);
        p.start().expect("Failed to start");

        let writer1 = p.create_writer("Topic1", "Type1", crate::qos::QosPolicy::default());
        let writer2 = p.create_writer("Topic2", "Type2", crate::qos::QosPolicy::default());

        let id1 = writer1.lock().unwrap().entity_id();
        let id2 = writer2.lock().unwrap().entity_id();

        // Entity IDs should be different
        assert_ne!(id1.0, id2.0);

        p.stop();
    }

    #[test]
    fn test_writer_produces_valid_rtps() {
        let mut p = DomainParticipant::new(0, 18);
        p.start().expect("Failed to start");

        let writer_arc = p.create_writer(
            "HelloWorld",
            "HelloWorld",
            crate::qos::QosPolicy::default(),
        );

        // Write some data
        let payload = crate::type_support::HelloWorldType::serialize("Test");

        {
            let mut writer = writer_arc.lock().unwrap();
            let msg_bytes = writer.write(&payload);

            // Verify RTPS header
            assert_eq!(&msg_bytes[0..4], b"RTPS");
            assert_eq!(msg_bytes[4], 2); // version major
            assert_eq!(msg_bytes[5], 5); // version minor

            // Should parse successfully
            let parsed = parse_rtps_message(&msg_bytes).expect("Failed to parse");
            assert!(!parsed.submessages.is_empty());

            // Sequence number should increment
            assert_eq!(writer.sequence_number().value(), 1);

            // Second write
            let _msg2 = writer.write(&payload);
            assert_eq!(writer.sequence_number().value(), 2);
        }

        p.stop();
    }

    #[test]
    fn test_reader_receive_data() {
        let mut p = DomainParticipant::new(0, 19);
        p.start().expect("Failed to start");

        let reader_arc = p.create_reader(
            "TestTopic",
            "TestType",
            crate::qos::QosPolicy::default(),
        );

        // Simulate receiving data
        let writer_guid = Guid::new(
            GuidPrefix([0xBB; 12]),
            EntityId([0x00, 0x00, 0x01, 0x02]),
        );
        let payload = b"test data".to_vec();

        {
            let mut reader = reader_arc.lock().unwrap();
            reader.receive(
                payload.clone(),
                writer_guid,
                crate::types::SequenceNumber::from_value(1),
                None,
            );

            assert_eq!(reader.buffer_len(), 1);

            let sample = reader.take_one().unwrap();
            assert_eq!(sample.data, payload);
            assert_eq!(sample.sequence_number.value(), 1);

            assert_eq!(reader.buffer_len(), 0);
        }

        p.stop();
    }

    #[test]
    fn test_endpoint_db_registration() {
        let mut p = DomainParticipant::new(0, 20);
        p.start().expect("Failed to start");

        // Create writer and reader
        p.create_writer("TopicA", "TypeA", crate::qos::QosPolicy::default());
        p.create_reader("TopicB", "TypeB", crate::qos::QosPolicy::default());

        // Verify they're registered in endpoint_db
        let db = p.endpoint_db();
        let writers: Vec<_> = db.local_writers().collect();
        let readers: Vec<_> = db.local_readers().collect();

        assert_eq!(writers.len(), 1);
        assert_eq!(readers.len(), 1);
        assert_eq!(writers[0].topic_name, "TopicA");
        assert_eq!(readers[0].topic_name, "TopicB");

        p.stop();
    }
}
