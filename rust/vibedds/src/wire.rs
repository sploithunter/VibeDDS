/// RTPS message builder and parser.

use std::io;

use crate::cdr::{CdrDeserializer, Endian};
use crate::constants::*;
use crate::messages::*;
use crate::types::*;

/// Builds an RTPS message from header + submessages.
pub struct RtpsMessageBuilder {
    guid_prefix: GuidPrefix,
    submessages: Vec<Vec<u8>>,
}

impl RtpsMessageBuilder {
    pub fn new(guid_prefix: GuidPrefix) -> Self {
        Self {
            guid_prefix,
            submessages: Vec::new(),
        }
    }

    fn submessage_bytes(submsg_id: u8, flags: u8, data: &[u8]) -> Vec<u8> {
        let mut buf = Vec::with_capacity(4 + data.len());
        buf.push(submsg_id);
        buf.push(flags);
        buf.extend_from_slice(&(data.len() as u16).to_le_bytes());
        buf.extend_from_slice(data);
        buf
    }

    pub fn add_info_ts(&mut self, timestamp: Option<Timestamp>) {
        let mut flags = FLAG_ENDIAN;
        let data = match timestamp {
            Some(ts) => ts.to_bytes_le().to_vec(),
            None => {
                flags |= 0x02;
                Vec::new()
            }
        };
        self.submessages
            .push(Self::submessage_bytes(SUBMSG_INFO_TS, flags, &data));
    }

    pub fn add_info_dst(&mut self, guid_prefix: GuidPrefix) {
        self.submessages.push(Self::submessage_bytes(
            SUBMSG_INFO_DST,
            FLAG_ENDIAN,
            &guid_prefix.0,
        ));
    }

    pub fn add_data(
        &mut self,
        reader_id: EntityId,
        writer_id: EntityId,
        writer_sn: SequenceNumber,
        serialized_payload: Option<&[u8]>,
        inline_qos: Option<&[u8]>,
        key_payload: bool,
    ) {
        let mut flags = FLAG_ENDIAN;
        if inline_qos.is_some() {
            flags |= FLAG_DATA_Q;
        }
        if let Some(_) = serialized_payload {
            if key_payload {
                flags |= FLAG_DATA_K;
            } else {
                flags |= FLAG_DATA_D;
            }
        }

        let mut buf = Vec::new();
        // extraFlags
        buf.extend_from_slice(&0u16.to_le_bytes());
        // octetsToInlineQos = 16
        buf.extend_from_slice(&16u16.to_le_bytes());
        // readerEntityId
        buf.extend_from_slice(&reader_id.0);
        // writerEntityId
        buf.extend_from_slice(&writer_id.0);
        // writerSeqNumber
        buf.extend_from_slice(&writer_sn.high.to_le_bytes());
        buf.extend_from_slice(&writer_sn.low.to_le_bytes());
        // inline QoS
        if let Some(qos) = inline_qos {
            buf.extend_from_slice(qos);
        }
        // payload
        if let Some(payload) = serialized_payload {
            buf.extend_from_slice(payload);
        }

        self.submessages
            .push(Self::submessage_bytes(SUBMSG_DATA, flags, &buf));
    }

    pub fn add_heartbeat(
        &mut self,
        reader_id: EntityId,
        writer_id: EntityId,
        first_sn: SequenceNumber,
        last_sn: SequenceNumber,
        count: u32,
        final_flag: bool,
        liveliness: bool,
    ) {
        let mut flags = FLAG_ENDIAN;
        if final_flag {
            flags |= 0x02;
        }
        if liveliness {
            flags |= 0x04;
        }

        let mut buf = Vec::with_capacity(28);
        buf.extend_from_slice(&reader_id.0);
        buf.extend_from_slice(&writer_id.0);
        buf.extend_from_slice(&first_sn.high.to_le_bytes());
        buf.extend_from_slice(&first_sn.low.to_le_bytes());
        buf.extend_from_slice(&last_sn.high.to_le_bytes());
        buf.extend_from_slice(&last_sn.low.to_le_bytes());
        buf.extend_from_slice(&count.to_le_bytes());

        self.submessages
            .push(Self::submessage_bytes(SUBMSG_HEARTBEAT, flags, &buf));
    }

    pub fn build(&self) -> Vec<u8> {
        let mut buf = Vec::new();
        // RTPS header (20 bytes)
        buf.extend_from_slice(&RTPS_MAGIC);
        buf.push(RTPS_VERSION_MAJOR);
        buf.push(RTPS_VERSION_MINOR);
        buf.extend_from_slice(&VENDOR_ID);
        buf.extend_from_slice(&self.guid_prefix.0);
        // Submessages
        for sm in &self.submessages {
            buf.extend_from_slice(sm);
        }
        buf
    }
}

/// Parses RTPS wire bytes into RtpsMessage.
pub fn parse_rtps_message(data: &[u8]) -> io::Result<RtpsMessage> {
    if data.len() < 20 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!("RTPS message too short: {} bytes", data.len()),
        ));
    }
    if &data[0..4] != &RTPS_MAGIC {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Invalid RTPS magic",
        ));
    }

    let version = ProtocolVersion::new(data[4], data[5]);
    let vendor_id = VendorId([data[6], data[7]]);
    let mut prefix = [0u8; 12];
    prefix.copy_from_slice(&data[8..20]);
    let guid_prefix = GuidPrefix(prefix);

    let header = RtpsHeader {
        version,
        vendor_id,
        guid_prefix,
    };

    let mut submessages = Vec::new();
    let mut pos = 20;

    while pos + 4 <= data.len() {
        let submsg_id = data[pos];
        let flags = data[pos + 1];
        let octets_to_next = u16::from_le_bytes([data[pos + 2], data[pos + 3]]) as usize;
        pos += 4;

        let little_endian = (flags & FLAG_ENDIAN) != 0;
        let endian = if little_endian {
            Endian::Little
        } else {
            Endian::Big
        };

        let body_end = if octets_to_next == 0 && pos < data.len() {
            data.len()
        } else {
            (pos + octets_to_next).min(data.len())
        };
        let body = &data[pos..body_end];
        pos = body_end;

        if let Some(sm) = parse_submessage(submsg_id, flags, endian, body) {
            submessages.push(sm);
        }
    }

    Ok(RtpsMessage {
        header,
        submessages,
    })
}

fn parse_submessage(submsg_id: u8, flags: u8, endian: Endian, body: &[u8]) -> Option<Submessage> {
    match submsg_id {
        SUBMSG_DATA => parse_data(flags, endian, body).map(Submessage::Data),
        SUBMSG_HEARTBEAT => parse_heartbeat(flags, endian, body).map(Submessage::Heartbeat),
        SUBMSG_ACKNACK => parse_acknack(flags, endian, body).map(Submessage::AckNack),
        SUBMSG_INFO_TS => parse_info_ts(flags, endian, body).map(Submessage::InfoTimestamp),
        SUBMSG_INFO_DST => parse_info_dst(flags, body).map(Submessage::InfoDestination),
        SUBMSG_PAD => Some(Submessage::Pad(PadSubmessage { flags })),
        _ => None,
    }
}

fn parse_data(flags: u8, endian: Endian, body: &[u8]) -> Option<DataSubmessage> {
    if body.len() < 20 {
        return None;
    }
    let has_data = (flags & FLAG_DATA_D) != 0;
    let has_key = (flags & FLAG_DATA_K) != 0;
    let has_qos = (flags & FLAG_DATA_Q) != 0;

    let octets_to_inline_qos = match endian {
        Endian::Little => u16::from_le_bytes([body[2], body[3]]) as usize,
        Endian::Big => u16::from_be_bytes([body[2], body[3]]) as usize,
    };

    let mut reader_id = [0u8; 4];
    reader_id.copy_from_slice(&body[4..8]);
    let mut writer_id = [0u8; 4];
    writer_id.copy_from_slice(&body[8..12]);

    let sn_high = match endian {
        Endian::Little => i32::from_le_bytes(body[12..16].try_into().unwrap()),
        Endian::Big => i32::from_be_bytes(body[12..16].try_into().unwrap()),
    };
    let sn_low = match endian {
        Endian::Little => u32::from_le_bytes(body[16..20].try_into().unwrap()),
        Endian::Big => u32::from_be_bytes(body[16..20].try_into().unwrap()),
    };

    let mut payload_offset = 4 + octets_to_inline_qos;
    let inline_qos = if has_qos && payload_offset < body.len() {
        let qos_start = payload_offset;
        let qos_end = find_sentinel(body, qos_start, endian);
        let qos = body[qos_start..qos_end].to_vec();
        payload_offset = qos_end;
        Some(qos)
    } else {
        None
    };

    let serialized_payload = if (has_data || has_key) && payload_offset < body.len() {
        Some(body[payload_offset..].to_vec())
    } else {
        None
    };

    Some(DataSubmessage {
        flags,
        reader_id: EntityId(reader_id),
        writer_id: EntityId(writer_id),
        writer_sn: SequenceNumber {
            high: sn_high,
            low: sn_low,
        },
        inline_qos,
        serialized_payload,
    })
}

fn find_sentinel(data: &[u8], start: usize, endian: Endian) -> usize {
    let mut pos = start;
    while pos + 4 <= data.len() {
        let pid = match endian {
            Endian::Little => u16::from_le_bytes([data[pos], data[pos + 1]]),
            Endian::Big => u16::from_be_bytes([data[pos], data[pos + 1]]),
        };
        let length = match endian {
            Endian::Little => u16::from_le_bytes([data[pos + 2], data[pos + 3]]) as usize,
            Endian::Big => u16::from_be_bytes([data[pos + 2], data[pos + 3]]) as usize,
        };
        pos += 4 + length;
        if pid == PID_SENTINEL {
            return pos;
        }
    }
    pos
}

fn parse_heartbeat(flags: u8, endian: Endian, body: &[u8]) -> Option<HeartbeatSubmessage> {
    if body.len() < 28 {
        return None;
    }
    let mut reader_id = [0u8; 4];
    reader_id.copy_from_slice(&body[0..4]);
    let mut writer_id = [0u8; 4];
    writer_id.copy_from_slice(&body[4..8]);

    macro_rules! read_i32 {
        ($offset:expr) => {
            match endian {
                Endian::Little => i32::from_le_bytes(body[$offset..$offset + 4].try_into().unwrap()),
                Endian::Big => i32::from_be_bytes(body[$offset..$offset + 4].try_into().unwrap()),
            }
        };
    }
    macro_rules! read_u32 {
        ($offset:expr) => {
            match endian {
                Endian::Little => u32::from_le_bytes(body[$offset..$offset + 4].try_into().unwrap()),
                Endian::Big => u32::from_be_bytes(body[$offset..$offset + 4].try_into().unwrap()),
            }
        };
    }

    Some(HeartbeatSubmessage {
        flags,
        reader_id: EntityId(reader_id),
        writer_id: EntityId(writer_id),
        first_sn: SequenceNumber {
            high: read_i32!(8),
            low: read_u32!(12),
        },
        last_sn: SequenceNumber {
            high: read_i32!(16),
            low: read_u32!(20),
        },
        count: read_u32!(24),
    })
}

fn parse_acknack(flags: u8, endian: Endian, body: &[u8]) -> Option<AckNackSubmessage> {
    if body.len() < 8 {
        return None;
    }
    let mut reader_id = [0u8; 4];
    reader_id.copy_from_slice(&body[0..4]);
    let mut writer_id = [0u8; 4];
    writer_id.copy_from_slice(&body[4..8]);

    let mut de = CdrDeserializer::new(&body[8..], endian);
    let sn_state = SequenceNumberSet::deserialize(&mut de).ok()?;
    let count = de.read_u32().ok()?;

    Some(AckNackSubmessage {
        flags,
        reader_id: EntityId(reader_id),
        writer_id: EntityId(writer_id),
        reader_sn_state: sn_state,
        count,
    })
}

fn parse_info_ts(flags: u8, endian: Endian, body: &[u8]) -> Option<InfoTimestampSubmessage> {
    let invalidate = (flags & 0x02) != 0;
    if invalidate || body.len() < 8 {
        return Some(InfoTimestampSubmessage {
            flags,
            timestamp: None,
        });
    }
    let ts = match endian {
        Endian::Little => Timestamp {
            seconds: i32::from_le_bytes(body[0..4].try_into().unwrap()),
            fraction: u32::from_le_bytes(body[4..8].try_into().unwrap()),
        },
        Endian::Big => Timestamp {
            seconds: i32::from_be_bytes(body[0..4].try_into().unwrap()),
            fraction: u32::from_be_bytes(body[4..8].try_into().unwrap()),
        },
    };
    Some(InfoTimestampSubmessage {
        flags,
        timestamp: Some(ts),
    })
}

fn parse_info_dst(flags: u8, body: &[u8]) -> Option<InfoDestinationSubmessage> {
    if body.len() < 12 {
        return None;
    }
    let mut prefix = [0u8; 12];
    prefix.copy_from_slice(&body[..12]);
    Some(InfoDestinationSubmessage {
        flags,
        guid_prefix: GuidPrefix(prefix),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_header_wire_format() {
        let prefix = GuidPrefix([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);
        let builder = RtpsMessageBuilder::new(prefix);
        let data = builder.build();
        assert_eq!(data.len(), 20);
        assert_eq!(&data[0..4], b"RTPS");
        assert_eq!(data[4], RTPS_VERSION_MAJOR);
        assert_eq!(data[5], RTPS_VERSION_MINOR);
        assert_eq!(data[6], 0xFF);
        assert_eq!(data[7], 0x01);
        assert_eq!(&data[8..20], &prefix.0);
    }

    #[test]
    fn test_parse_header() {
        let prefix = GuidPrefix([0xAA; 12]);
        let builder = RtpsMessageBuilder::new(prefix);
        let msg = parse_rtps_message(&builder.build()).unwrap();
        assert_eq!(msg.header.version, ProtocolVersion::new(2, 5));
        assert_eq!(msg.header.vendor_id, VendorId([0xFF, 0x01]));
        assert_eq!(msg.header.guid_prefix, prefix);
    }

    #[test]
    fn test_info_ts_roundtrip() {
        let prefix = GuidPrefix([1; 12]);
        let ts = Timestamp {
            seconds: 1000,
            fraction: 500,
        };
        let mut builder = RtpsMessageBuilder::new(prefix);
        builder.add_info_ts(Some(ts));
        let msg = parse_rtps_message(&builder.build()).unwrap();
        assert_eq!(msg.submessages.len(), 1);
        if let Submessage::InfoTimestamp(its) = &msg.submessages[0] {
            assert_eq!(its.timestamp, Some(ts));
        } else {
            panic!("Expected InfoTimestamp");
        }
    }

    #[test]
    fn test_data_roundtrip() {
        let prefix = GuidPrefix([1; 12]);
        let reader_id = EntityId(ENTITYID_SPDP_BUILTIN_PARTICIPANT_READER);
        let writer_id = EntityId(ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER);
        let sn = SequenceNumber::from_value(1);
        let payload = b"\xDE\xAD\xBE\xEF";

        let mut builder = RtpsMessageBuilder::new(prefix);
        builder.add_data(reader_id, writer_id, sn, Some(payload), None, false);
        let msg = parse_rtps_message(&builder.build()).unwrap();
        assert_eq!(msg.submessages.len(), 1);
        if let Submessage::Data(d) = &msg.submessages[0] {
            assert_eq!(d.reader_id, reader_id);
            assert_eq!(d.writer_id, writer_id);
            assert_eq!(d.writer_sn, sn);
            assert_eq!(d.serialized_payload.as_deref(), Some(payload.as_slice()));
        } else {
            panic!("Expected Data");
        }
    }

    #[test]
    fn test_heartbeat_roundtrip() {
        let prefix = GuidPrefix([1; 12]);
        let reader_id = EntityId(ENTITYID_SPDP_BUILTIN_PARTICIPANT_READER);
        let writer_id = EntityId(ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER);

        let mut builder = RtpsMessageBuilder::new(prefix);
        builder.add_heartbeat(
            reader_id,
            writer_id,
            SequenceNumber::from_value(1),
            SequenceNumber::from_value(10),
            5,
            true,
            false,
        );
        let msg = parse_rtps_message(&builder.build()).unwrap();
        if let Submessage::Heartbeat(hb) = &msg.submessages[0] {
            assert_eq!(hb.first_sn.value(), 1);
            assert_eq!(hb.last_sn.value(), 10);
            assert_eq!(hb.count, 5);
        } else {
            panic!("Expected Heartbeat");
        }
    }

    #[test]
    fn test_multi_submessage() {
        let prefix = GuidPrefix([1; 12]);
        let dst = GuidPrefix([2; 12]);
        let ts = Timestamp {
            seconds: 12345,
            fraction: 0,
        };
        let reader_id = EntityId(ENTITYID_SPDP_BUILTIN_PARTICIPANT_READER);
        let writer_id = EntityId(ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER);

        let mut builder = RtpsMessageBuilder::new(prefix);
        builder.add_info_ts(Some(ts));
        builder.add_info_dst(dst);
        builder.add_data(
            reader_id,
            writer_id,
            SequenceNumber::from_value(1),
            Some(b"\xAB\xCD"),
            None,
            false,
        );
        builder.add_heartbeat(
            reader_id,
            writer_id,
            SequenceNumber::from_value(1),
            SequenceNumber::from_value(1),
            1,
            false,
            false,
        );

        let msg = parse_rtps_message(&builder.build()).unwrap();
        assert_eq!(msg.submessages.len(), 4);
        assert!(matches!(&msg.submessages[0], Submessage::InfoTimestamp(_)));
        assert!(matches!(&msg.submessages[1], Submessage::InfoDestination(_)));
        assert!(matches!(&msg.submessages[2], Submessage::Data(_)));
        assert!(matches!(&msg.submessages[3], Submessage::Heartbeat(_)));
    }

    #[test]
    fn test_parse_too_short() {
        assert!(parse_rtps_message(&[0; 10]).is_err());
    }

    #[test]
    fn test_parse_bad_magic() {
        let mut data = [0u8; 20];
        data[0..4].copy_from_slice(b"XXXX");
        assert!(parse_rtps_message(&data).is_err());
    }
}
