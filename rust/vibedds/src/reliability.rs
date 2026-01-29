/// Reliability state machines for RTPS.
///
/// ReliableWriter: maintains history cache, tracks per-reader acked state,
/// sends HEARTBEAT, processes ACKNACK, retransmits.
///
/// ReliableReader: tracks per-writer received state, responds to HEARTBEAT
/// with ACKNACK, detects gaps.

use std::collections::{HashMap, HashSet};
use std::time::Instant;

use crate::messages::{AckNackSubmessage, HeartbeatSubmessage};
use crate::types::{Guid, SequenceNumber, SequenceNumberSet};

/// A single entry in the writer's history cache.
#[derive(Debug, Clone)]
pub struct CacheChange {
    pub sequence_number: SequenceNumber,
    pub serialized_data: Vec<u8>,
    pub timestamp: Instant,
}

impl CacheChange {
    pub fn new(sequence_number: SequenceNumber, data: Vec<u8>) -> Self {
        Self {
            sequence_number,
            serialized_data: data,
            timestamp: Instant::now(),
        }
    }
}

/// Tracks state for a matched remote reader (writer side).
#[derive(Debug, Clone)]
pub struct ReaderProxy {
    pub remote_reader_guid: Guid,
    pub highest_acked_sn: SequenceNumber,
    pub requested_changes: Vec<SequenceNumber>,
}

impl ReaderProxy {
    pub fn new(remote_reader_guid: Guid) -> Self {
        Self {
            remote_reader_guid,
            highest_acked_sn: SequenceNumber::ZERO,
            requested_changes: Vec::new(),
        }
    }
}

/// Tracks state for a matched remote writer (reader side).
#[derive(Debug, Clone)]
pub struct WriterProxy {
    pub remote_writer_guid: Guid,
    pub highest_received_sn: SequenceNumber,
    pub received_sns: HashSet<i64>,
}

impl WriterProxy {
    pub fn new(remote_writer_guid: Guid) -> Self {
        Self {
            remote_writer_guid,
            highest_received_sn: SequenceNumber::ZERO,
            received_sns: HashSet::new(),
        }
    }
}

/// Stateful reliable writer with history cache and per-reader proxies.
pub struct ReliableWriter {
    pub guid: Guid,
    heartbeat_period_secs: f64,
    max_history: usize,

    next_sn: SequenceNumber,
    history: Vec<CacheChange>,
    reader_proxies: HashMap<[u8; 16], ReaderProxy>,
    heartbeat_count: u32,
    last_heartbeat_time: Instant,
}

impl ReliableWriter {
    pub fn new(guid: Guid, heartbeat_period: f64, max_history: usize) -> Self {
        Self {
            guid,
            heartbeat_period_secs: heartbeat_period,
            max_history,
            next_sn: SequenceNumber::from_value(1),
            history: Vec::new(),
            reader_proxies: HashMap::new(),
            heartbeat_count: 0,
            last_heartbeat_time: Instant::now(),
        }
    }

    pub fn next_sequence_number(&self) -> SequenceNumber {
        self.next_sn
    }

    pub fn first_available_sn(&self) -> SequenceNumber {
        self.history
            .first()
            .map(|c| c.sequence_number)
            .unwrap_or(self.next_sn)
    }

    pub fn last_available_sn(&self) -> SequenceNumber {
        self.history
            .last()
            .map(|c| c.sequence_number)
            .unwrap_or(SequenceNumber::ZERO)
    }

    pub fn history(&self) -> &[CacheChange] {
        &self.history
    }

    pub fn add_reader_proxy(&mut self, reader_guid: Guid) {
        let key = reader_guid.to_bytes();
        if !self.reader_proxies.contains_key(&key) {
            self.reader_proxies
                .insert(key, ReaderProxy::new(reader_guid));
            log::debug!("Added reader proxy: {:?}", reader_guid);
        }
    }

    pub fn remove_reader_proxy(&mut self, reader_guid: &Guid) {
        self.reader_proxies.remove(&reader_guid.to_bytes());
    }

    pub fn has_reader_proxies(&self) -> bool {
        !self.reader_proxies.is_empty()
    }

    /// Add a new cache change and return a reference to it.
    pub fn new_change(&mut self, data: Vec<u8>) -> &CacheChange {
        let change = CacheChange::new(self.next_sn, data);
        self.history.push(change);
        self.next_sn = self.next_sn.increment();

        // Trim history if needed
        while self.history.len() > self.max_history {
            self.history.remove(0);
        }

        self.history.last().unwrap()
    }

    pub fn get_change(&self, sn: SequenceNumber) -> Option<&CacheChange> {
        self.history.iter().find(|c| c.sequence_number == sn)
    }

    pub fn should_send_heartbeat(&self) -> bool {
        self.last_heartbeat_time.elapsed().as_secs_f64() >= self.heartbeat_period_secs
    }

    pub fn next_heartbeat_count(&mut self) -> u32 {
        self.heartbeat_count += 1;
        self.last_heartbeat_time = Instant::now();
        self.heartbeat_count
    }

    /// Process an ACKNACK, return changes that need retransmission.
    pub fn process_acknack(&mut self, acknack: &AckNackSubmessage) -> Vec<CacheChange> {
        let missing = acknack.reader_sn_state.missing_sequence_numbers();
        let mut retransmits = Vec::new();

        for sn in missing {
            if let Some(change) = self.get_change(sn) {
                retransmits.push(change.clone());
            }
        }

        retransmits
    }
}

/// Stateful reliable reader that tracks received samples and detects gaps.
pub struct ReliableReader {
    pub guid: Guid,
    writer_proxies: HashMap<[u8; 16], WriterProxy>,
    acknack_count: u32,
}

impl ReliableReader {
    pub fn new(guid: Guid) -> Self {
        Self {
            guid,
            writer_proxies: HashMap::new(),
            acknack_count: 0,
        }
    }

    pub fn add_writer_proxy(&mut self, writer_guid: Guid) {
        let key = writer_guid.to_bytes();
        if !self.writer_proxies.contains_key(&key) {
            self.writer_proxies
                .insert(key, WriterProxy::new(writer_guid));
            log::debug!("Added writer proxy: {:?}", writer_guid);
        }
    }

    pub fn remove_writer_proxy(&mut self, writer_guid: &Guid) {
        self.writer_proxies.remove(&writer_guid.to_bytes());
    }

    pub fn get_writer_proxy(&self, writer_guid: &Guid) -> Option<&WriterProxy> {
        self.writer_proxies.get(&writer_guid.to_bytes())
    }

    pub fn get_writer_proxy_mut(&mut self, writer_guid: &Guid) -> Option<&mut WriterProxy> {
        self.writer_proxies.get_mut(&writer_guid.to_bytes())
    }

    /// Record that we received a sample from a writer.
    pub fn record_received(&mut self, writer_guid: &Guid, sn: SequenceNumber) {
        if let Some(proxy) = self.writer_proxies.get_mut(&writer_guid.to_bytes()) {
            proxy.received_sns.insert(sn.value());
            if sn > proxy.highest_received_sn {
                proxy.highest_received_sn = sn;
            }
        }
    }

    /// Process a HEARTBEAT, return missing sequence numbers for ACKNACK.
    pub fn process_heartbeat(
        &mut self,
        heartbeat: &HeartbeatSubmessage,
        writer_guid: &Guid,
    ) -> SequenceNumberSet {
        let proxy = match self.writer_proxies.get(&writer_guid.to_bytes()) {
            Some(p) => p,
            None => {
                // Unknown writer, return empty set
                return SequenceNumberSet::new(heartbeat.last_sn);
            }
        };

        // Find missing sequence numbers between first_sn and last_sn
        let mut missing = Vec::new();
        let mut sn = heartbeat.first_sn;
        while sn <= heartbeat.last_sn {
            if !proxy.received_sns.contains(&sn.value()) {
                missing.push(sn);
            }
            sn = sn.increment();
        }

        // Build bitmap
        let base = if missing.is_empty() {
            heartbeat.last_sn.increment()
        } else {
            missing[0]
        };

        let mut bitmap = Vec::new();
        for sn in &missing {
            let bit_pos = (sn.value() - base.value()) as usize;
            while bitmap.len() * 32 <= bit_pos {
                bitmap.push(0u32);
            }
            let word_idx = bit_pos / 32;
            let bit_idx = bit_pos % 32;
            bitmap[word_idx] |= 1 << (31 - bit_idx);
        }

        SequenceNumberSet {
            base,
            num_bits: if missing.is_empty() {
                0
            } else {
                ((missing.last().unwrap().value() - base.value()) as u32) + 1
            },
            bitmap,
        }
    }

    pub fn next_acknack_count(&mut self) -> u32 {
        self.acknack_count += 1;
        self.acknack_count
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::{EntityId, GuidPrefix};

    fn test_guid() -> Guid {
        Guid {
            prefix: GuidPrefix([0xAA; 12]),
            entity_id: EntityId([0x00, 0x00, 0x01, 0x02]),
        }
    }

    fn other_guid() -> Guid {
        Guid {
            prefix: GuidPrefix([0xBB; 12]),
            entity_id: EntityId([0x00, 0x00, 0x02, 0x02]),
        }
    }

    #[test]
    fn test_reliable_writer_new() {
        let writer = ReliableWriter::new(test_guid(), 1.0, 100);
        assert_eq!(writer.next_sequence_number().value(), 1);
        assert!(writer.history().is_empty());
    }

    #[test]
    fn test_reliable_writer_new_change() {
        let mut writer = ReliableWriter::new(test_guid(), 1.0, 100);

        let change1 = writer.new_change(vec![1, 2, 3]);
        assert_eq!(change1.sequence_number.value(), 1);

        let change2 = writer.new_change(vec![4, 5, 6]);
        assert_eq!(change2.sequence_number.value(), 2);

        assert_eq!(writer.history().len(), 2);
        assert_eq!(writer.next_sequence_number().value(), 3);
    }

    #[test]
    fn test_reliable_writer_history_trim() {
        let mut writer = ReliableWriter::new(test_guid(), 1.0, 3);

        writer.new_change(vec![1]);
        writer.new_change(vec![2]);
        writer.new_change(vec![3]);
        writer.new_change(vec![4]);

        assert_eq!(writer.history().len(), 3);
        assert_eq!(writer.first_available_sn().value(), 2); // oldest is SN 2
        assert_eq!(writer.last_available_sn().value(), 4);
    }

    #[test]
    fn test_reliable_writer_get_change() {
        let mut writer = ReliableWriter::new(test_guid(), 1.0, 100);

        writer.new_change(vec![1, 2, 3]);
        writer.new_change(vec![4, 5, 6]);

        let change = writer.get_change(SequenceNumber::from_value(1));
        assert!(change.is_some());
        assert_eq!(change.unwrap().serialized_data, vec![1, 2, 3]);

        let change = writer.get_change(SequenceNumber::from_value(2));
        assert!(change.is_some());
        assert_eq!(change.unwrap().serialized_data, vec![4, 5, 6]);

        let change = writer.get_change(SequenceNumber::from_value(99));
        assert!(change.is_none());
    }

    #[test]
    fn test_reliable_writer_reader_proxy() {
        let mut writer = ReliableWriter::new(test_guid(), 1.0, 100);

        assert!(!writer.has_reader_proxies());

        writer.add_reader_proxy(other_guid());
        assert!(writer.has_reader_proxies());

        writer.remove_reader_proxy(&other_guid());
        assert!(!writer.has_reader_proxies());
    }

    #[test]
    fn test_reliable_reader_new() {
        let reader = ReliableReader::new(test_guid());
        assert_eq!(reader.guid, test_guid());
    }

    #[test]
    fn test_reliable_reader_writer_proxy() {
        let mut reader = ReliableReader::new(test_guid());

        assert!(reader.get_writer_proxy(&other_guid()).is_none());

        reader.add_writer_proxy(other_guid());
        assert!(reader.get_writer_proxy(&other_guid()).is_some());

        reader.remove_writer_proxy(&other_guid());
        assert!(reader.get_writer_proxy(&other_guid()).is_none());
    }

    #[test]
    fn test_reliable_reader_record_received() {
        let mut reader = ReliableReader::new(test_guid());
        let writer_guid = other_guid();

        reader.add_writer_proxy(writer_guid);
        reader.record_received(&writer_guid, SequenceNumber::from_value(1));
        reader.record_received(&writer_guid, SequenceNumber::from_value(3));

        let proxy = reader.get_writer_proxy(&writer_guid).unwrap();
        assert!(proxy.received_sns.contains(&1));
        assert!(!proxy.received_sns.contains(&2));
        assert!(proxy.received_sns.contains(&3));
        assert_eq!(proxy.highest_received_sn.value(), 3);
    }

    #[test]
    fn test_heartbeat_count() {
        let mut writer = ReliableWriter::new(test_guid(), 1.0, 100);
        assert_eq!(writer.next_heartbeat_count(), 1);
        assert_eq!(writer.next_heartbeat_count(), 2);
        assert_eq!(writer.next_heartbeat_count(), 3);
    }

    #[test]
    fn test_acknack_count() {
        let mut reader = ReliableReader::new(test_guid());
        assert_eq!(reader.next_acknack_count(), 1);
        assert_eq!(reader.next_acknack_count(), 2);
    }

    #[test]
    fn test_cache_change() {
        let change = CacheChange::new(SequenceNumber::from_value(5), vec![0xAA, 0xBB]);
        assert_eq!(change.sequence_number.value(), 5);
        assert_eq!(change.serialized_data, vec![0xAA, 0xBB]);
    }
}
