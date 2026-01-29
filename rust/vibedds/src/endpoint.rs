/// User-facing DataWriter and DataReader endpoints.
///
/// These structs provide the application-level API for publishing
/// and subscribing to data samples.

use std::collections::VecDeque;
use std::sync::{Arc, Mutex};

use crate::constants::*;
use crate::reliability::ReliableWriter;
use crate::types::*;
use crate::wire::RtpsMessageBuilder;

/// Callback type for data arrival notifications.
pub type DataCallback = Box<dyn Fn(&[u8]) + Send + Sync>;

/// A DataWriter publishes samples to matched DataReaders.
pub struct DataWriter {
    pub guid: Guid,
    pub topic_name: String,
    pub type_name: String,
    sequence_number: SequenceNumber,
    reliable_writer: Option<ReliableWriter>,
    is_reliable: bool,
}

impl DataWriter {
    /// Create a new DataWriter.
    pub fn new(
        guid: Guid,
        topic_name: String,
        type_name: String,
        is_reliable: bool,
    ) -> Self {
        let reliable_writer = if is_reliable {
            Some(ReliableWriter::new(guid.clone(), 1.0, 100))
        } else {
            None
        };

        Self {
            guid,
            topic_name,
            type_name,
            sequence_number: SequenceNumber::ZERO,
            reliable_writer,
            is_reliable,
        }
    }

    /// Get the entity ID of this writer.
    pub fn entity_id(&self) -> EntityId {
        self.guid.entity_id.clone()
    }

    /// Write a serialized sample.
    ///
    /// The payload should already include the CDR encapsulation header.
    /// Returns the RTPS message bytes to be sent.
    pub fn write(&mut self, serialized_payload: &[u8]) -> Vec<u8> {
        self.sequence_number = self.sequence_number.increment();

        // If reliable, cache the sample
        if let Some(ref mut rw) = self.reliable_writer {
            rw.new_change(serialized_payload.to_vec());
        }

        // Build RTPS message with DATA submessage
        let mut builder = RtpsMessageBuilder::new(self.guid.prefix.clone());

        // Add timestamp
        builder.add_info_ts(Some(Timestamp::now()));

        // Add DATA submessage
        // reader_id = UNKNOWN means broadcast to all matching readers
        builder.add_data(
            EntityId(ENTITYID_UNKNOWN),
            self.guid.entity_id.clone(),
            self.sequence_number.clone(),
            Some(serialized_payload),
            None,  // no inline QoS
            false, // data payload, not key
        );

        builder.build()
    }

    /// Write a serialized sample with a specific destination reader.
    pub fn write_to(
        &mut self,
        serialized_payload: &[u8],
        dest_prefix: GuidPrefix,
        dest_reader_id: EntityId,
    ) -> Vec<u8> {
        self.sequence_number = self.sequence_number.increment();

        if let Some(ref mut rw) = self.reliable_writer {
            rw.new_change(serialized_payload.to_vec());
        }

        let mut builder = RtpsMessageBuilder::new(self.guid.prefix.clone());
        builder.add_info_ts(Some(Timestamp::now()));
        builder.add_info_dst(dest_prefix);
        builder.add_data(
            dest_reader_id,
            self.guid.entity_id.clone(),
            self.sequence_number.clone(),
            Some(serialized_payload),
            None,
            false,
        );

        builder.build()
    }

    /// Get the current sequence number.
    pub fn sequence_number(&self) -> SequenceNumber {
        self.sequence_number.clone()
    }

    /// Check if this writer is reliable.
    pub fn is_reliable(&self) -> bool {
        self.is_reliable
    }

    /// Get mutable access to the reliable writer (for ACKNACK processing).
    pub fn reliable_writer_mut(&mut self) -> Option<&mut ReliableWriter> {
        self.reliable_writer.as_mut()
    }

    /// Build a HEARTBEAT message if this is a reliable writer.
    pub fn build_heartbeat(&mut self) -> Option<Vec<u8>> {
        let rw = self.reliable_writer.as_mut()?;

        if !rw.should_send_heartbeat() {
            return None;
        }

        let mut builder = RtpsMessageBuilder::new(self.guid.prefix.clone());
        builder.add_heartbeat(
            EntityId(ENTITYID_UNKNOWN), // to all readers
            self.guid.entity_id.clone(),
            rw.first_available_sn(),
            rw.last_available_sn(),
            rw.next_heartbeat_count(),
            false, // final flag
            false, // liveliness flag
        );

        Some(builder.build())
    }
}

/// A received sample with metadata.
#[derive(Debug, Clone)]
pub struct Sample {
    pub data: Vec<u8>,
    pub writer_guid: Guid,
    pub sequence_number: SequenceNumber,
    pub source_timestamp: Option<Timestamp>,
}

/// A DataReader receives samples from matched DataWriters.
pub struct DataReader {
    pub guid: Guid,
    pub topic_name: String,
    pub type_name: String,
    buffer: VecDeque<Sample>,
    max_buffer: usize,
    callbacks: Vec<DataCallback>,
    is_reliable: bool,
}

impl DataReader {
    /// Create a new DataReader.
    pub fn new(
        guid: Guid,
        topic_name: String,
        type_name: String,
        is_reliable: bool,
    ) -> Self {
        Self {
            guid,
            topic_name,
            type_name,
            buffer: VecDeque::new(),
            max_buffer: 100,
            callbacks: Vec::new(),
            is_reliable,
        }
    }

    /// Get the entity ID of this reader.
    pub fn entity_id(&self) -> EntityId {
        self.guid.entity_id.clone()
    }

    /// Register a callback to be invoked when data arrives.
    ///
    /// The callback receives the serialized payload (including CDR header).
    pub fn on_data<F>(&mut self, callback: F)
    where
        F: Fn(&[u8]) + Send + Sync + 'static,
    {
        self.callbacks.push(Box::new(callback));
    }

    /// Receive a sample (called by the participant when DATA arrives).
    pub fn receive(
        &mut self,
        payload: Vec<u8>,
        writer_guid: Guid,
        sequence_number: SequenceNumber,
        source_timestamp: Option<Timestamp>,
    ) {
        // Invoke callbacks
        for cb in &self.callbacks {
            cb(&payload);
        }

        // Buffer the sample
        let sample = Sample {
            data: payload,
            writer_guid,
            sequence_number,
            source_timestamp,
        };

        self.buffer.push_back(sample);

        // Cap buffer size
        while self.buffer.len() > self.max_buffer {
            self.buffer.pop_front();
        }
    }

    /// Take all buffered samples, clearing the buffer.
    pub fn take(&mut self) -> Vec<Sample> {
        self.buffer.drain(..).collect()
    }

    /// Take one sample if available.
    pub fn take_one(&mut self) -> Option<Sample> {
        self.buffer.pop_front()
    }

    /// Peek at buffered samples without removing them.
    pub fn peek(&self) -> &VecDeque<Sample> {
        &self.buffer
    }

    /// Get the number of buffered samples.
    pub fn buffer_len(&self) -> usize {
        self.buffer.len()
    }

    /// Check if this reader is reliable.
    pub fn is_reliable(&self) -> bool {
        self.is_reliable
    }

    /// Set the maximum buffer size.
    pub fn set_max_buffer(&mut self, max: usize) {
        self.max_buffer = max;
    }
}

/// Thread-safe wrapper for DataReader.
pub struct SharedDataReader {
    inner: Arc<Mutex<DataReader>>,
}

impl SharedDataReader {
    pub fn new(reader: DataReader) -> Self {
        Self {
            inner: Arc::new(Mutex::new(reader)),
        }
    }

    pub fn lock(&self) -> std::sync::MutexGuard<'_, DataReader> {
        self.inner.lock().unwrap()
    }

    pub fn clone_arc(&self) -> Arc<Mutex<DataReader>> {
        Arc::clone(&self.inner)
    }
}

impl Clone for SharedDataReader {
    fn clone(&self) -> Self {
        Self {
            inner: Arc::clone(&self.inner),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_guid_prefix() -> GuidPrefix {
        GuidPrefix([0xAA; 12])
    }

    fn test_writer_entity_id() -> EntityId {
        EntityId([0x00, 0x00, 0x01, 0x02]) // user writer
    }

    fn test_reader_entity_id() -> EntityId {
        EntityId([0x00, 0x00, 0x01, 0x07]) // user reader
    }

    #[test]
    fn test_datawriter_write() {
        let guid = Guid {
            prefix: test_guid_prefix(),
            entity_id: test_writer_entity_id(),
        };

        let mut writer = DataWriter::new(
            guid,
            "TestTopic".to_string(),
            "TestType".to_string(),
            false, // best-effort
        );

        // Write a sample
        let payload = b"\x00\x01\x00\x00Hello".to_vec(); // CDR_LE + "Hello"
        let msg = writer.write(&payload);

        // Verify RTPS header
        assert_eq!(&msg[0..4], b"RTPS");
        assert_eq!(msg[4], 2); // version major
        assert_eq!(msg[5], 5); // version minor

        // Sequence number should have incremented
        assert_eq!(writer.sequence_number().value(), 1);
    }

    #[test]
    fn test_datawriter_reliable() {
        let guid = Guid {
            prefix: test_guid_prefix(),
            entity_id: test_writer_entity_id(),
        };

        let mut writer = DataWriter::new(
            guid,
            "TestTopic".to_string(),
            "TestType".to_string(),
            true, // reliable
        );

        assert!(writer.is_reliable());
        assert!(writer.reliable_writer_mut().is_some());

        // Write samples
        for i in 0..5 {
            let payload = format!("\x00\x01\x00\x00Sample{}", i).into_bytes();
            writer.write(&payload);
        }

        // Check reliable writer state
        let rw = writer.reliable_writer_mut().unwrap();
        assert_eq!(rw.last_available_sn().value(), 5);
    }

    #[test]
    fn test_datareader_receive() {
        let guid = Guid {
            prefix: test_guid_prefix(),
            entity_id: test_reader_entity_id(),
        };

        let mut reader = DataReader::new(
            guid,
            "TestTopic".to_string(),
            "TestType".to_string(),
            false,
        );

        let writer_guid = Guid {
            prefix: GuidPrefix([0xBB; 12]),
            entity_id: test_writer_entity_id(),
        };

        // Receive samples
        for i in 0..3 {
            let payload = format!("Sample{}", i).into_bytes();
            reader.receive(
                payload,
                writer_guid.clone(),
                SequenceNumber::from_value(i + 1),
                None,
            );
        }

        assert_eq!(reader.buffer_len(), 3);

        // Take one
        let sample = reader.take_one().unwrap();
        assert_eq!(sample.data, b"Sample0");
        assert_eq!(sample.sequence_number.value(), 1);
        assert_eq!(reader.buffer_len(), 2);

        // Take all
        let samples = reader.take();
        assert_eq!(samples.len(), 2);
        assert_eq!(reader.buffer_len(), 0);
    }

    #[test]
    fn test_datareader_callback() {
        use std::sync::atomic::{AtomicUsize, Ordering};

        let guid = Guid {
            prefix: test_guid_prefix(),
            entity_id: test_reader_entity_id(),
        };

        let mut reader = DataReader::new(
            guid,
            "TestTopic".to_string(),
            "TestType".to_string(),
            false,
        );

        let counter = Arc::new(AtomicUsize::new(0));
        let counter_clone = Arc::clone(&counter);

        reader.on_data(move |_data| {
            counter_clone.fetch_add(1, Ordering::SeqCst);
        });

        let writer_guid = Guid {
            prefix: GuidPrefix([0xBB; 12]),
            entity_id: test_writer_entity_id(),
        };

        // Receive samples - callback should be invoked
        reader.receive(b"data1".to_vec(), writer_guid.clone(), SequenceNumber::from_value(1), None);
        reader.receive(b"data2".to_vec(), writer_guid.clone(), SequenceNumber::from_value(2), None);

        assert_eq!(counter.load(Ordering::SeqCst), 2);
    }

    #[test]
    fn test_datareader_max_buffer() {
        let guid = Guid {
            prefix: test_guid_prefix(),
            entity_id: test_reader_entity_id(),
        };

        let mut reader = DataReader::new(
            guid,
            "TestTopic".to_string(),
            "TestType".to_string(),
            false,
        );

        reader.set_max_buffer(5);

        let writer_guid = Guid {
            prefix: GuidPrefix([0xBB; 12]),
            entity_id: test_writer_entity_id(),
        };

        // Receive more than max_buffer samples
        for i in 0..10 {
            reader.receive(
                format!("Sample{}", i).into_bytes(),
                writer_guid.clone(),
                SequenceNumber::from_value(i + 1),
                None,
            );
        }

        // Should only have max_buffer samples (oldest dropped)
        assert_eq!(reader.buffer_len(), 5);

        let samples = reader.take();
        // Should have samples 5-9 (0-4 were dropped)
        assert_eq!(samples[0].data, b"Sample5");
        assert_eq!(samples[4].data, b"Sample9");
    }
}
