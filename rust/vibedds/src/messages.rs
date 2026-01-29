/// RTPS submessage types.

use crate::types::*;

#[derive(Debug, Clone)]
pub struct RtpsHeader {
    pub version: ProtocolVersion,
    pub vendor_id: VendorId,
    pub guid_prefix: GuidPrefix,
}

#[derive(Debug, Clone)]
pub struct DataSubmessage {
    pub flags: u8,
    pub reader_id: EntityId,
    pub writer_id: EntityId,
    pub writer_sn: SequenceNumber,
    pub inline_qos: Option<Vec<u8>>,
    pub serialized_payload: Option<Vec<u8>>,
}

#[derive(Debug, Clone)]
pub struct HeartbeatSubmessage {
    pub flags: u8,
    pub reader_id: EntityId,
    pub writer_id: EntityId,
    pub first_sn: SequenceNumber,
    pub last_sn: SequenceNumber,
    pub count: u32,
}

#[derive(Debug, Clone)]
pub struct AckNackSubmessage {
    pub flags: u8,
    pub reader_id: EntityId,
    pub writer_id: EntityId,
    pub reader_sn_state: SequenceNumberSet,
    pub count: u32,
}

#[derive(Debug, Clone)]
pub struct GapSubmessage {
    pub flags: u8,
    pub reader_id: EntityId,
    pub writer_id: EntityId,
    pub gap_start: SequenceNumber,
    pub gap_list: SequenceNumberSet,
}

#[derive(Debug, Clone)]
pub struct InfoTimestampSubmessage {
    pub flags: u8,
    pub timestamp: Option<Timestamp>,
}

#[derive(Debug, Clone)]
pub struct InfoDestinationSubmessage {
    pub flags: u8,
    pub guid_prefix: GuidPrefix,
}

#[derive(Debug, Clone)]
pub struct InfoSourceSubmessage {
    pub flags: u8,
    pub protocol_version: ProtocolVersion,
    pub vendor_id: VendorId,
    pub guid_prefix: GuidPrefix,
}

#[derive(Debug, Clone)]
pub struct PadSubmessage {
    pub flags: u8,
}

#[derive(Debug, Clone)]
pub enum Submessage {
    Data(DataSubmessage),
    Heartbeat(HeartbeatSubmessage),
    AckNack(AckNackSubmessage),
    Gap(GapSubmessage),
    InfoTimestamp(InfoTimestampSubmessage),
    InfoDestination(InfoDestinationSubmessage),
    InfoSource(InfoSourceSubmessage),
    Pad(PadSubmessage),
}

#[derive(Debug, Clone)]
pub struct RtpsMessage {
    pub header: RtpsHeader,
    pub submessages: Vec<Submessage>,
}
