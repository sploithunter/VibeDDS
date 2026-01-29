"""RTPS message builder and parser.

Converts between bytes on the wire and RtpsMessage/submessage objects.
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

from vibedds.constants import (
    RTPS_MAGIC, RTPS_VERSION_MAJOR, RTPS_VERSION_MINOR, VENDOR_ID,
    SUBMSG_PAD, SUBMSG_ACKNACK, SUBMSG_HEARTBEAT, SUBMSG_GAP,
    SUBMSG_INFO_TS, SUBMSG_INFO_SRC, SUBMSG_INFO_DST, SUBMSG_DATA,
    FLAG_ENDIAN, FLAG_DATA_Q, FLAG_DATA_D, FLAG_DATA_K,
)
from vibedds.types import (
    GuidPrefix, EntityId, SequenceNumber, SequenceNumberSet,
    Timestamp, ProtocolVersion, VendorId,
)
from vibedds.messages import (
    RtpsHeader, RtpsMessage,
    DataSubmessage, HeartbeatSubmessage, AckNackSubmessage, GapSubmessage,
    InfoTimestampSubmessage, InfoDestinationSubmessage, InfoSourceSubmessage,
    PadSubmessage, Submessage,
)
from vibedds.cdr import CdrSerializer, CdrDeserializer


class RtpsMessageBuilder:
    """Builds an RTPS message from header + submessages into wire bytes."""

    def __init__(self, guid_prefix: GuidPrefix):
        self._guid_prefix = guid_prefix
        self._submessages: list[bytes] = []

    def _submessage_header(self, submsg_id: int, flags: int, data: bytes) -> bytes:
        """Build a 4-byte submessage header + data."""
        # Header: submessageId(1) + flags(1) + octetsToNextHeader(2, LE always)
        length = len(data)
        header = struct.pack("<BBH", submsg_id, flags, length)
        return header + data

    def add_info_ts(self, timestamp: Timestamp | None = None) -> None:
        """Add INFO_TS submessage."""
        flags = FLAG_ENDIAN  # little-endian
        if timestamp is None:
            flags |= 0x02  # invalidate flag
            data = b''
        else:
            data = timestamp.to_bytes("<")
        self._submessages.append(
            self._submessage_header(SUBMSG_INFO_TS, flags, data)
        )

    def add_info_dst(self, guid_prefix: GuidPrefix) -> None:
        """Add INFO_DST submessage."""
        flags = FLAG_ENDIAN
        self._submessages.append(
            self._submessage_header(SUBMSG_INFO_DST, flags, guid_prefix.to_bytes())
        )

    def add_data(
        self,
        reader_id: EntityId,
        writer_id: EntityId,
        writer_sn: SequenceNumber,
        serialized_payload: bytes | None = None,
        inline_qos: bytes | None = None,
        key_payload: bool = False,
    ) -> None:
        """Add DATA submessage."""
        flags = FLAG_ENDIAN
        if inline_qos is not None:
            flags |= FLAG_DATA_Q
        if serialized_payload is not None:
            if key_payload:
                flags |= FLAG_DATA_K
            else:
                flags |= FLAG_DATA_D

        buf = bytearray()
        # extraFlags (2 bytes, always 0)
        buf.extend(struct.pack("<H", 0))
        # octetsToInlineQos (2 bytes, always 16 from start of readerEntityId)
        buf.extend(struct.pack("<H", 16))
        # readerEntityId (4 bytes)
        buf.extend(reader_id.to_bytes())
        # writerEntityId (4 bytes)
        buf.extend(writer_id.to_bytes())
        # writerSeqNumber (8 bytes)
        buf.extend(struct.pack("<iI", writer_sn.high, writer_sn.low))
        # inline QoS
        if inline_qos is not None:
            buf.extend(inline_qos)
        # serialized payload
        if serialized_payload is not None:
            buf.extend(serialized_payload)

        self._submessages.append(
            self._submessage_header(SUBMSG_DATA, flags, bytes(buf))
        )

    def add_heartbeat(
        self,
        reader_id: EntityId,
        writer_id: EntityId,
        first_sn: SequenceNumber,
        last_sn: SequenceNumber,
        count: int,
        final: bool = False,
        liveliness: bool = False,
    ) -> None:
        """Add HEARTBEAT submessage."""
        flags = FLAG_ENDIAN
        if final:
            flags |= 0x02  # F
        if liveliness:
            flags |= 0x04  # L

        buf = bytearray()
        buf.extend(reader_id.to_bytes())
        buf.extend(writer_id.to_bytes())
        buf.extend(struct.pack("<iI", first_sn.high, first_sn.low))
        buf.extend(struct.pack("<iI", last_sn.high, last_sn.low))
        buf.extend(struct.pack("<I", count))

        self._submessages.append(
            self._submessage_header(SUBMSG_HEARTBEAT, flags, bytes(buf))
        )

    def add_acknack(
        self,
        reader_id: EntityId,
        writer_id: EntityId,
        reader_sn_state: SequenceNumberSet,
        count: int,
        final: bool = False,
    ) -> None:
        """Add ACKNACK submessage."""
        flags = FLAG_ENDIAN
        if final:
            flags |= 0x02

        ser = CdrSerializer("<")
        ser.write_bytes_raw(reader_id.to_bytes())
        ser.write_bytes_raw(writer_id.to_bytes())
        reader_sn_state.serialize(ser)
        ser.write_uint32(count)

        self._submessages.append(
            self._submessage_header(SUBMSG_ACKNACK, flags, ser.getvalue())
        )

    def add_gap(
        self,
        reader_id: EntityId,
        writer_id: EntityId,
        gap_start: SequenceNumber,
        gap_list: SequenceNumberSet,
    ) -> None:
        """Add GAP submessage."""
        flags = FLAG_ENDIAN

        ser = CdrSerializer("<")
        ser.write_bytes_raw(reader_id.to_bytes())
        ser.write_bytes_raw(writer_id.to_bytes())
        gap_start.serialize(ser)
        gap_list.serialize(ser)

        self._submessages.append(
            self._submessage_header(SUBMSG_GAP, flags, ser.getvalue())
        )

    def build(self) -> bytes:
        """Build the complete RTPS message bytes."""
        buf = bytearray()
        # RTPS header (20 bytes)
        buf.extend(RTPS_MAGIC)
        buf.extend(bytes([RTPS_VERSION_MAJOR, RTPS_VERSION_MINOR]))
        buf.extend(bytes(VENDOR_ID))
        buf.extend(self._guid_prefix.to_bytes())
        # Submessages
        for sm in self._submessages:
            buf.extend(sm)
        return bytes(buf)


class RtpsMessageParser:
    """Parses RTPS wire bytes into RtpsMessage objects."""

    @staticmethod
    def parse(data: bytes | bytearray | memoryview) -> RtpsMessage:
        """Parse a complete RTPS message from wire bytes.

        Raises ValueError on invalid data.
        """
        data = bytes(data)
        if len(data) < 20:
            raise ValueError(f"RTPS message too short: {len(data)} bytes (need >= 20)")

        # Validate magic
        if data[0:4] != RTPS_MAGIC:
            raise ValueError(f"Invalid RTPS magic: {data[0:4]!r}")

        # Parse header
        version = ProtocolVersion(major=data[4], minor=data[5])
        vendor_id = VendorId(vendor=(data[6], data[7]))
        guid_prefix = GuidPrefix(data[8:20])
        header = RtpsHeader(version=version, vendor_id=vendor_id, guid_prefix=guid_prefix)

        # Parse submessages
        submessages: list[Submessage] = []
        pos = 20
        while pos < len(data):
            if pos + 4 > len(data):
                break  # incomplete submessage header

            submsg_id = data[pos]
            flags = data[pos + 1]
            octets_to_next = struct.unpack_from("<H", data, pos + 2)[0]
            pos += 4

            little_endian = bool(flags & FLAG_ENDIAN)
            endian = "<" if little_endian else ">"

            # Get submessage body
            if octets_to_next == 0 and pos < len(data):
                # Last submessage may use 0 to mean "rest of message"
                body = data[pos:]
                pos = len(data)
            else:
                body = data[pos:pos + octets_to_next]
                pos += octets_to_next

            submsg = RtpsMessageParser._parse_submessage(submsg_id, flags, endian, body)
            if submsg is not None:
                submessages.append(submsg)

        return RtpsMessage(header=header, submessages=submessages)

    @staticmethod
    def _parse_submessage(
        submsg_id: int, flags: int, endian: str, body: bytes
    ) -> Submessage | None:
        """Parse a single submessage body. Returns None for unknown types."""
        try:
            if submsg_id == SUBMSG_DATA:
                return RtpsMessageParser._parse_data(flags, endian, body)
            elif submsg_id == SUBMSG_HEARTBEAT:
                return RtpsMessageParser._parse_heartbeat(flags, endian, body)
            elif submsg_id == SUBMSG_ACKNACK:
                return RtpsMessageParser._parse_acknack(flags, endian, body)
            elif submsg_id == SUBMSG_GAP:
                return RtpsMessageParser._parse_gap(flags, endian, body)
            elif submsg_id == SUBMSG_INFO_TS:
                return RtpsMessageParser._parse_info_ts(flags, endian, body)
            elif submsg_id == SUBMSG_INFO_DST:
                return RtpsMessageParser._parse_info_dst(flags, endian, body)
            elif submsg_id == SUBMSG_INFO_SRC:
                return RtpsMessageParser._parse_info_src(flags, endian, body)
            elif submsg_id == SUBMSG_PAD:
                return PadSubmessage(flags=flags)
            else:
                # Unknown submessage — skip
                return None
        except Exception:
            # Malformed submessage — skip rather than crash
            return None

    @staticmethod
    def _parse_data(flags: int, endian: str, body: bytes) -> DataSubmessage:
        has_inline_qos = bool(flags & FLAG_DATA_Q)
        has_data = bool(flags & FLAG_DATA_D)
        has_key = bool(flags & FLAG_DATA_K)

        # extraFlags(2) + octetsToInlineQos(2) + readerId(4) + writerId(4) + writerSN(8) = 20
        if len(body) < 20:
            raise ValueError("DATA submessage too short")

        octets_to_inline_qos = struct.unpack_from(endian + "H", body, 2)[0]
        reader_id = EntityId(body[4:8])
        writer_id = EntityId(body[8:12])

        sn_high = struct.unpack_from(endian + "i", body, 12)[0]
        sn_low = struct.unpack_from(endian + "I", body, 16)[0]
        writer_sn = SequenceNumber(high=sn_high, low=sn_low)

        payload_offset = 4 + octets_to_inline_qos  # from start of body
        inline_qos = None
        serialized_payload = None

        if has_inline_qos:
            # Find PID_SENTINEL to determine end of inline QoS
            qos_start = payload_offset
            qos_end = RtpsMessageParser._find_sentinel(body, qos_start, endian)
            inline_qos = body[qos_start:qos_end]
            payload_offset = qos_end

        if has_data or has_key:
            serialized_payload = body[payload_offset:]

        return DataSubmessage(
            flags=flags,
            reader_id=reader_id,
            writer_id=writer_id,
            writer_sn=writer_sn,
            inline_qos=inline_qos,
            serialized_payload=serialized_payload,
        )

    @staticmethod
    def _find_sentinel(data: bytes, start: int, endian: str) -> int:
        """Scan parameter list for PID_SENTINEL, return position after sentinel."""
        pos = start
        while pos + 4 <= len(data):
            pid = struct.unpack_from(endian + "H", data, pos)[0]
            length = struct.unpack_from(endian + "H", data, pos + 2)[0]
            pos += 4 + length
            if pid == 0x0001:  # PID_SENTINEL
                return pos
        return pos

    @staticmethod
    def _parse_heartbeat(flags: int, endian: str, body: bytes) -> HeartbeatSubmessage:
        if len(body) < 28:
            raise ValueError("HEARTBEAT submessage too short")

        reader_id = EntityId(body[0:4])
        writer_id = EntityId(body[4:8])
        first_high = struct.unpack_from(endian + "i", body, 8)[0]
        first_low = struct.unpack_from(endian + "I", body, 12)[0]
        last_high = struct.unpack_from(endian + "i", body, 16)[0]
        last_low = struct.unpack_from(endian + "I", body, 20)[0]
        count = struct.unpack_from(endian + "I", body, 24)[0]

        return HeartbeatSubmessage(
            flags=flags,
            reader_id=reader_id,
            writer_id=writer_id,
            first_sn=SequenceNumber(high=first_high, low=first_low),
            last_sn=SequenceNumber(high=last_high, low=last_low),
            count=count,
        )

    @staticmethod
    def _parse_acknack(flags: int, endian: str, body: bytes) -> AckNackSubmessage:
        reader_id = EntityId(body[0:4])
        writer_id = EntityId(body[4:8])

        de = CdrDeserializer(body[8:], endian)
        sn_state = SequenceNumberSet.deserialize(de)
        count = de.read_uint32()

        return AckNackSubmessage(
            flags=flags,
            reader_id=reader_id,
            writer_id=writer_id,
            reader_sn_state=sn_state,
            count=count,
        )

    @staticmethod
    def _parse_gap(flags: int, endian: str, body: bytes) -> GapSubmessage:
        reader_id = EntityId(body[0:4])
        writer_id = EntityId(body[4:8])

        de = CdrDeserializer(body[8:], endian)
        gap_start = SequenceNumber.deserialize(de)
        gap_list = SequenceNumberSet.deserialize(de)

        return GapSubmessage(
            flags=flags,
            reader_id=reader_id,
            writer_id=writer_id,
            gap_start=gap_start,
            gap_list=gap_list,
        )

    @staticmethod
    def _parse_info_ts(flags: int, endian: str, body: bytes) -> InfoTimestampSubmessage:
        invalidate = bool(flags & 0x02)
        if invalidate or len(body) < 8:
            return InfoTimestampSubmessage(flags=flags, timestamp=None)
        ts = Timestamp.from_bytes(body[:8], endian)
        return InfoTimestampSubmessage(flags=flags, timestamp=ts)

    @staticmethod
    def _parse_info_dst(flags: int, endian: str, body: bytes) -> InfoDestinationSubmessage:
        if len(body) < 12:
            raise ValueError("INFO_DST too short")
        return InfoDestinationSubmessage(
            flags=flags,
            guid_prefix=GuidPrefix(body[:12]),
        )

    @staticmethod
    def _parse_info_src(flags: int, endian: str, body: bytes) -> InfoSourceSubmessage:
        if len(body) < 20:
            raise ValueError("INFO_SRC too short")
        # unused(4) + version(2) + vendorId(2) + guidPrefix(12) = 20
        version = ProtocolVersion(major=body[4], minor=body[5])
        vendor_id = VendorId(vendor=(body[6], body[7]))
        guid_prefix = GuidPrefix(body[8:20])
        return InfoSourceSubmessage(
            flags=flags,
            protocol_version=version,
            vendor_id=vendor_id,
            guid_prefix=guid_prefix,
        )
