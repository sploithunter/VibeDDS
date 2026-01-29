"""Tests for RTPS core types."""

import struct
import pytest

from vibedds.cdr import CdrSerializer, CdrDeserializer
from vibedds.types import (
    GuidPrefix, EntityId, Guid, SequenceNumber, SequenceNumberSet,
    Locator, Timestamp, Duration, ProtocolVersion, VendorId,
)
from vibedds.constants import (
    ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER,
    ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER,
    ENTITYID_PARTICIPANT,
    LOCATOR_KIND_UDPv4,
    spdp_multicast_port, spdp_unicast_port, user_unicast_port,
)


class TestGuidPrefix:
    def test_roundtrip(self):
        prefix = GuidPrefix(b'\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0A\x0B\x0C')
        ser = CdrSerializer("<")
        prefix.serialize(ser)
        de = CdrDeserializer(ser.getvalue(), "<")
        assert GuidPrefix.deserialize(de) == prefix

    def test_wrong_length(self):
        with pytest.raises(ValueError):
            GuidPrefix(b'\x01\x02\x03')

    def test_unknown(self):
        assert GuidPrefix.UNKNOWN.value == b'\x00' * 12

    def test_to_from_bytes(self):
        val = b'\xAB' * 12
        p = GuidPrefix(val)
        assert GuidPrefix.from_bytes(p.to_bytes()) == p


class TestEntityId:
    def test_roundtrip(self):
        eid = EntityId(b'\x00\x01\x00\xC2')
        ser = CdrSerializer("<")
        eid.serialize(ser)
        de = CdrDeserializer(ser.getvalue(), "<")
        assert EntityId.deserialize(de) == eid

    def test_entity_key_and_kind(self):
        eid = EntityId(ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER)
        assert eid.entity_key == b'\x00\x01\x00'
        assert eid.entity_kind == 0xC2

    def test_known_entity_ids(self):
        assert ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER == bytes([0x00, 0x01, 0x00, 0xC2])
        assert ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER == bytes([0x00, 0x00, 0x03, 0xC2])
        assert ENTITYID_PARTICIPANT == bytes([0x00, 0x00, 0x01, 0xC1])

    def test_wrong_length(self):
        with pytest.raises(ValueError):
            EntityId(b'\x00\x01')


class TestGuid:
    def test_roundtrip(self):
        guid = Guid(
            prefix=GuidPrefix(b'\x01' * 12),
            entity_id=EntityId(b'\x00\x01\x00\xC2'),
        )
        ser = CdrSerializer("<")
        guid.serialize(ser)
        de = CdrDeserializer(ser.getvalue(), "<")
        assert Guid.deserialize(de) == guid

    def test_to_from_bytes(self):
        guid = Guid(
            prefix=GuidPrefix(b'\xAA' * 12),
            entity_id=EntityId(b'\xBB\xCC\xDD\xEE'),
        )
        raw = guid.to_bytes()
        assert len(raw) == 16
        assert Guid.from_bytes(raw) == guid


class TestSequenceNumber:
    def test_from_value(self):
        sn = SequenceNumber.from_value(1)
        assert sn.high == 0
        assert sn.low == 1
        assert sn.value == 1

    def test_large_value(self):
        sn = SequenceNumber.from_value(0x100000001)
        assert sn.high == 1
        assert sn.low == 1

    def test_zero(self):
        assert SequenceNumber.ZERO.value == 0

    def test_arithmetic(self):
        sn1 = SequenceNumber.from_value(10)
        sn2 = sn1 + 5
        assert sn2.value == 15

        diff = sn2 - sn1
        assert diff == 5

    def test_comparison(self):
        sn1 = SequenceNumber.from_value(1)
        sn2 = SequenceNumber.from_value(2)
        assert sn1 < sn2
        assert sn2 > sn1
        assert sn1 <= sn1
        assert sn1 >= sn1

    def test_roundtrip(self):
        sn = SequenceNumber.from_value(42)
        ser = CdrSerializer("<")
        sn.serialize(ser)
        de = CdrDeserializer(ser.getvalue(), "<")
        assert SequenceNumber.deserialize(de) == sn


class TestSequenceNumberSet:
    def test_contains(self):
        # base=5, bits 0 and 2 set (= SN 5 and 7 missing)
        bitmap = (0b10100000_00000000_00000000_00000000,)
        snset = SequenceNumberSet(
            base=SequenceNumber.from_value(5),
            num_bits=32,
            bitmap=bitmap,
        )
        assert snset.contains(SequenceNumber.from_value(5))
        assert not snset.contains(SequenceNumber.from_value(6))
        assert snset.contains(SequenceNumber.from_value(7))

    def test_missing_sequence_numbers(self):
        bitmap = (0b11000000_00000000_00000000_00000000,)
        snset = SequenceNumberSet(
            base=SequenceNumber.from_value(1),
            num_bits=32,
            bitmap=bitmap,
        )
        missing = snset.missing_sequence_numbers()
        assert len(missing) == 2
        assert missing[0].value == 1
        assert missing[1].value == 2

    def test_roundtrip(self):
        snset = SequenceNumberSet(
            base=SequenceNumber.from_value(10),
            num_bits=32,
            bitmap=(0xF0000000,),
        )
        ser = CdrSerializer("<")
        snset.serialize(ser)
        de = CdrDeserializer(ser.getvalue(), "<")
        parsed = SequenceNumberSet.deserialize(de)
        assert parsed.base == snset.base
        assert parsed.num_bits == snset.num_bits
        assert parsed.bitmap == snset.bitmap


class TestLocator:
    def test_ipv4(self):
        loc = Locator.from_ipv4("192.168.1.100", 7400)
        assert loc.kind == LOCATOR_KIND_UDPv4
        assert loc.port == 7400
        assert loc.ipv4_str == "192.168.1.100"

    def test_roundtrip(self):
        loc = Locator.from_ipv4("10.0.0.1", 7411)
        ser = CdrSerializer("<")
        loc.serialize(ser)
        de = CdrDeserializer(ser.getvalue(), "<")
        parsed = Locator.deserialize(de)
        assert parsed == loc

    def test_to_from_bytes(self):
        loc = Locator.from_ipv4("127.0.0.1", 7400)
        raw = loc.to_bytes()
        assert len(raw) == 24
        assert Locator.from_bytes(raw) == loc

    def test_invalid(self):
        assert Locator.INVALID.kind == -1


class TestTimestamp:
    def test_from_seconds(self):
        ts = Timestamp.from_seconds(1.5)
        assert ts.seconds == 1
        assert abs(ts.to_seconds() - 1.5) < 1e-6

    def test_roundtrip(self):
        ts = Timestamp(seconds=1000, fraction=500000)
        ser = CdrSerializer("<")
        ts.serialize(ser)
        de = CdrDeserializer(ser.getvalue(), "<")
        assert Timestamp.deserialize(de) == ts

    def test_zero_and_invalid(self):
        assert Timestamp.ZERO.seconds == 0
        assert Timestamp.INVALID.seconds == -1


class TestDuration:
    def test_infinite(self):
        assert Duration.INFINITE.seconds == 0x7FFFFFFF
        assert Duration.INFINITE.fraction == 0xFFFFFFFF

    def test_from_seconds(self):
        d = Duration.from_seconds(100.0)
        assert d.seconds == 100
        assert abs(d.to_seconds() - 100.0) < 1e-6


class TestProtocolVersion:
    def test_roundtrip(self):
        pv = ProtocolVersion(major=2, minor=5)
        assert ProtocolVersion.from_bytes(pv.to_bytes()) == pv


class TestVendorId:
    def test_roundtrip(self):
        vid = VendorId(vendor=(0xFF, 0x01))
        assert VendorId.from_bytes(vid.to_bytes()) == vid


class TestPortCalculations:
    def test_spdp_multicast_port_domain0(self):
        assert spdp_multicast_port(0) == 7400

    def test_spdp_multicast_port_domain1(self):
        assert spdp_multicast_port(1) == 7650

    def test_spdp_unicast_port(self):
        assert spdp_unicast_port(0, 0) == 7410
        assert spdp_unicast_port(0, 1) == 7412

    def test_user_unicast_port(self):
        assert user_unicast_port(0, 0) == 7401
        assert user_unicast_port(0, 1) == 7403
