"""Tests for RTPS message building and parsing."""

import struct
import pytest

from vibedds.types import (
    GuidPrefix, EntityId, SequenceNumber, SequenceNumberSet,
    Timestamp, ProtocolVersion, VendorId,
)
from vibedds.messages import (
    RtpsHeader, RtpsMessage,
    DataSubmessage, HeartbeatSubmessage, AckNackSubmessage,
    InfoTimestampSubmessage, InfoDestinationSubmessage, PadSubmessage,
)
from vibedds.wire import RtpsMessageBuilder, RtpsMessageParser
from vibedds.constants import (
    RTPS_MAGIC, RTPS_VERSION_MAJOR, RTPS_VERSION_MINOR,
    ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER,
    ENTITYID_SPDP_BUILTIN_PARTICIPANT_READER,
    ENTITYID_UNKNOWN,
    SUBMSG_DATA, SUBMSG_HEARTBEAT, SUBMSG_INFO_TS, SUBMSG_INFO_DST,
    FLAG_ENDIAN, FLAG_DATA_D,
)
from vibedds.cdr import ParameterListBuilder, PID_SENTINEL, encapsulation_header, PL_CDR_LE


class TestRtpsHeader:
    def test_header_wire_format(self):
        """20-byte header: RTPS(4) + version(2) + vendorId(2) + guidPrefix(12)."""
        prefix = GuidPrefix(b'\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0A\x0B\x0C')
        builder = RtpsMessageBuilder(prefix)
        data = builder.build()
        assert len(data) == 20
        assert data[0:4] == RTPS_MAGIC
        assert data[4] == RTPS_VERSION_MAJOR
        assert data[5] == RTPS_VERSION_MINOR
        assert data[6] == 0xFF
        assert data[7] == 0x01
        assert data[8:20] == prefix.value

    def test_parse_header(self):
        prefix = GuidPrefix(b'\xAA' * 12)
        builder = RtpsMessageBuilder(prefix)
        msg = RtpsMessageParser.parse(builder.build())
        assert msg.header.version == ProtocolVersion(2, 5)
        assert msg.header.vendor_id == VendorId((0xFF, 0x01))
        assert msg.header.guid_prefix == prefix


class TestInfoTimestamp:
    def test_roundtrip(self):
        prefix = GuidPrefix(b'\x01' * 12)
        ts = Timestamp(seconds=1000, fraction=500)

        builder = RtpsMessageBuilder(prefix)
        builder.add_info_ts(ts)
        msg = RtpsMessageParser.parse(builder.build())

        assert len(msg.submessages) == 1
        sm = msg.submessages[0]
        assert isinstance(sm, InfoTimestampSubmessage)
        assert sm.timestamp == ts

    def test_invalidate(self):
        prefix = GuidPrefix(b'\x01' * 12)
        builder = RtpsMessageBuilder(prefix)
        builder.add_info_ts(None)
        msg = RtpsMessageParser.parse(builder.build())

        sm = msg.submessages[0]
        assert isinstance(sm, InfoTimestampSubmessage)
        assert sm.timestamp is None


class TestInfoDestination:
    def test_roundtrip(self):
        prefix = GuidPrefix(b'\x01' * 12)
        dst_prefix = GuidPrefix(b'\xBB' * 12)

        builder = RtpsMessageBuilder(prefix)
        builder.add_info_dst(dst_prefix)
        msg = RtpsMessageParser.parse(builder.build())

        assert len(msg.submessages) == 1
        sm = msg.submessages[0]
        assert isinstance(sm, InfoDestinationSubmessage)
        assert sm.guid_prefix == dst_prefix


class TestDataSubmessage:
    def test_roundtrip_with_payload(self):
        prefix = GuidPrefix(b'\x01' * 12)
        reader_id = EntityId(ENTITYID_SPDP_BUILTIN_PARTICIPANT_READER)
        writer_id = EntityId(ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER)
        sn = SequenceNumber.from_value(1)
        payload = b'\xDE\xAD\xBE\xEF'

        builder = RtpsMessageBuilder(prefix)
        builder.add_data(reader_id, writer_id, sn, serialized_payload=payload)
        msg = RtpsMessageParser.parse(builder.build())

        assert len(msg.submessages) == 1
        sm = msg.submessages[0]
        assert isinstance(sm, DataSubmessage)
        assert sm.reader_id == reader_id
        assert sm.writer_id == writer_id
        assert sm.writer_sn == sn
        assert sm.serialized_payload == payload

    def test_data_no_payload(self):
        prefix = GuidPrefix(b'\x01' * 12)
        reader_id = EntityId(ENTITYID_UNKNOWN)
        writer_id = EntityId(ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER)
        sn = SequenceNumber.from_value(42)

        builder = RtpsMessageBuilder(prefix)
        builder.add_data(reader_id, writer_id, sn)
        msg = RtpsMessageParser.parse(builder.build())

        sm = msg.submessages[0]
        assert isinstance(sm, DataSubmessage)
        assert sm.serialized_payload is None

    def test_data_with_inline_qos(self):
        prefix = GuidPrefix(b'\x01' * 12)
        reader_id = EntityId(ENTITYID_UNKNOWN)
        writer_id = EntityId(ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER)
        sn = SequenceNumber.from_value(1)

        # Build inline QoS as parameter list
        qos_builder = ParameterListBuilder("<")
        qos_builder.add_parameter(0x0070, b'\x00' * 16)  # PID_KEY_HASH
        qos_data = qos_builder.finalize()

        payload = b'\xCA\xFE'

        builder = RtpsMessageBuilder(prefix)
        builder.add_data(reader_id, writer_id, sn,
                         serialized_payload=payload, inline_qos=qos_data)
        msg = RtpsMessageParser.parse(builder.build())

        sm = msg.submessages[0]
        assert isinstance(sm, DataSubmessage)
        assert sm.inline_qos is not None
        assert sm.serialized_payload == payload


class TestHeartbeat:
    def test_roundtrip(self):
        prefix = GuidPrefix(b'\x01' * 12)
        reader_id = EntityId(ENTITYID_SPDP_BUILTIN_PARTICIPANT_READER)
        writer_id = EntityId(ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER)

        builder = RtpsMessageBuilder(prefix)
        builder.add_heartbeat(
            reader_id, writer_id,
            first_sn=SequenceNumber.from_value(1),
            last_sn=SequenceNumber.from_value(10),
            count=5,
            final=True,
        )
        msg = RtpsMessageParser.parse(builder.build())

        sm = msg.submessages[0]
        assert isinstance(sm, HeartbeatSubmessage)
        assert sm.reader_id == reader_id
        assert sm.writer_id == writer_id
        assert sm.first_sn.value == 1
        assert sm.last_sn.value == 10
        assert sm.count == 5


class TestAckNack:
    def test_roundtrip(self):
        prefix = GuidPrefix(b'\x01' * 12)
        reader_id = EntityId(ENTITYID_SPDP_BUILTIN_PARTICIPANT_READER)
        writer_id = EntityId(ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER)

        sn_state = SequenceNumberSet(
            base=SequenceNumber.from_value(5),
            num_bits=32,
            bitmap=(0xA0000000,),
        )

        builder = RtpsMessageBuilder(prefix)
        builder.add_acknack(reader_id, writer_id, sn_state, count=3)
        msg = RtpsMessageParser.parse(builder.build())

        sm = msg.submessages[0]
        assert isinstance(sm, AckNackSubmessage)
        assert sm.reader_id == reader_id
        assert sm.writer_id == writer_id
        assert sm.reader_sn_state.base.value == 5
        assert sm.reader_sn_state.bitmap == (0xA0000000,)
        assert sm.count == 3


class TestMultiSubmessage:
    def test_info_ts_info_dst_data_heartbeat(self):
        """Build a message with 4 submessages, parse all back."""
        prefix = GuidPrefix(b'\x01' * 12)
        dst_prefix = GuidPrefix(b'\x02' * 12)
        ts = Timestamp(seconds=12345, fraction=0)
        reader_id = EntityId(ENTITYID_SPDP_BUILTIN_PARTICIPANT_READER)
        writer_id = EntityId(ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER)

        builder = RtpsMessageBuilder(prefix)
        builder.add_info_ts(ts)
        builder.add_info_dst(dst_prefix)
        builder.add_data(reader_id, writer_id, SequenceNumber.from_value(1),
                         serialized_payload=b'\xAB\xCD')
        builder.add_heartbeat(reader_id, writer_id,
                              first_sn=SequenceNumber.from_value(1),
                              last_sn=SequenceNumber.from_value(1),
                              count=1)

        msg = RtpsMessageParser.parse(builder.build())
        assert len(msg.submessages) == 4

        assert isinstance(msg.submessages[0], InfoTimestampSubmessage)
        assert msg.submessages[0].timestamp == ts

        assert isinstance(msg.submessages[1], InfoDestinationSubmessage)
        assert msg.submessages[1].guid_prefix == dst_prefix

        assert isinstance(msg.submessages[2], DataSubmessage)
        assert msg.submessages[2].serialized_payload == b'\xAB\xCD'

        assert isinstance(msg.submessages[3], HeartbeatSubmessage)
        assert msg.submessages[3].count == 1


class TestUnknownSubmessage:
    def test_skip_unknown(self):
        """Unknown submessage types should be skipped without error."""
        prefix = GuidPrefix(b'\x01' * 12)
        builder = RtpsMessageBuilder(prefix)
        builder.add_info_ts(Timestamp(1, 0))

        raw = bytearray(builder.build())

        # Append a fake unknown submessage (ID=0xFE)
        fake_body = b'\x00' * 8
        raw.extend(struct.pack("<BBH", 0xFE, 0x01, len(fake_body)))
        raw.extend(fake_body)

        # Append another INFO_TS
        ts_data = struct.pack("<iI", 2, 0)
        raw.extend(struct.pack("<BBH", 0x09, 0x01, len(ts_data)))
        raw.extend(ts_data)

        msg = RtpsMessageParser.parse(bytes(raw))
        # Should have 2 INFO_TS, unknown skipped
        assert len(msg.submessages) == 2
        assert isinstance(msg.submessages[0], InfoTimestampSubmessage)
        assert isinstance(msg.submessages[1], InfoTimestampSubmessage)
        assert msg.submessages[1].timestamp.seconds == 2


class TestParseErrors:
    def test_too_short(self):
        with pytest.raises(ValueError, match="too short"):
            RtpsMessageParser.parse(b'\x00' * 10)

    def test_bad_magic(self):
        with pytest.raises(ValueError, match="Invalid RTPS magic"):
            RtpsMessageParser.parse(b'XXXX' + b'\x00' * 16)


class TestEndianness:
    def test_big_endian_not_crashed(self):
        """A message with big-endian flag=0 should still parse."""
        # Build a minimal message manually with BE submessage
        buf = bytearray()
        buf.extend(RTPS_MAGIC)
        buf.extend(bytes([2, 5, 0xFF, 0x01]))
        buf.extend(b'\x01' * 12)

        # INFO_TS with big-endian (flags=0x00, no E bit)
        ts_data = struct.pack(">iI", 999, 0)
        buf.extend(struct.pack("<BBH", 0x09, 0x00, len(ts_data)))
        buf.extend(ts_data)

        msg = RtpsMessageParser.parse(bytes(buf))
        assert len(msg.submessages) == 1
        assert isinstance(msg.submessages[0], InfoTimestampSubmessage)
        assert msg.submessages[0].timestamp.seconds == 999
