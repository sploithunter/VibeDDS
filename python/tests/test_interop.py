"""Tests for Stage 5: Pub/Sub data exchange, type support, endpoints."""

import struct
import pytest

from vibedds.type_support import HelloWorldType, ShapeType
from vibedds.endpoint import DataWriter, DataReader, EntityIdAllocator
from vibedds.types import GuidPrefix, EntityId, Guid, SequenceNumber, Locator
from vibedds.qos import QosPolicy, ReliabilityKind
from vibedds.topic import Topic, TopicRegistry
from vibedds.cdr import CdrSerializer, CdrDeserializer, encapsulation_header, CDR_LE
from vibedds.sedp import EndpointDatabase, LocalEndpoint, DiscoveredEndpoint


# --- Type support tests ---

class TestHelloWorldType:
    def test_roundtrip(self):
        msg = "Hello DDS World #42"
        payload = HelloWorldType.serialize(msg)
        assert HelloWorldType.deserialize(payload) == msg

    def test_empty_string(self):
        payload = HelloWorldType.serialize("")
        assert HelloWorldType.deserialize(payload) == ""

    def test_unicode(self):
        msg = "Héllo Wörld 日本語"
        payload = HelloWorldType.serialize(msg)
        assert HelloWorldType.deserialize(payload) == msg

    def test_encapsulation_header(self):
        payload = HelloWorldType.serialize("test")
        # First 4 bytes should be CDR_LE encapsulation
        assert payload[0:2] == b'\x00\x01'  # CDR_LE
        assert payload[2:4] == b'\x00\x00'  # options


class TestShapeType:
    def test_roundtrip(self):
        payload = ShapeType.serialize("RED", 100, 200, 30)
        result = ShapeType.deserialize(payload)
        assert result["color"] == "RED"
        assert result["x"] == 100
        assert result["y"] == 200
        assert result["shapesize"] == 30

    def test_negative_coords(self):
        payload = ShapeType.serialize("BLUE", -50, -100, 20)
        result = ShapeType.deserialize(payload)
        assert result["x"] == -50
        assert result["y"] == -100


# --- Entity ID allocator tests ---

class TestEntityIdAllocator:
    def test_unique_ids(self):
        alloc = EntityIdAllocator()
        w1 = alloc.allocate_writer()
        w2 = alloc.allocate_writer()
        r1 = alloc.allocate_reader()
        assert w1 != w2
        assert w1 != r1

    def test_writer_kind(self):
        alloc = EntityIdAllocator()
        w = alloc.allocate_writer(with_key=False)
        assert w.entity_kind == 0x03  # USER_WRITER_NO_KEY

    def test_reader_kind(self):
        alloc = EntityIdAllocator()
        r = alloc.allocate_reader(with_key=False)
        assert r.entity_kind == 0x07  # USER_READER_NO_KEY


# --- Topic registry tests ---

class TestTopicRegistry:
    def test_register(self):
        reg = TopicRegistry()
        t = reg.register(Topic("T1", "Type1"))
        assert t.name == "T1"
        assert reg.get("T1") is t

    def test_register_duplicate_same_type(self):
        reg = TopicRegistry()
        t1 = reg.register(Topic("T1", "Type1"))
        t2 = reg.register(Topic("T1", "Type1"))
        assert t1 is t2

    def test_register_duplicate_different_type(self):
        reg = TopicRegistry()
        reg.register(Topic("T1", "Type1"))
        with pytest.raises(ValueError):
            reg.register(Topic("T1", "Type2"))

    def test_contains(self):
        reg = TopicRegistry()
        reg.register(Topic("T1", "Type1"))
        assert "T1" in reg
        assert "T2" not in reg


# --- DataReader tests ---

class TestDataReader:
    def test_receive_and_take(self):
        reader = DataReader(
            guid=Guid(GuidPrefix(b'\x01' * 12), EntityId(b'\x00\x00\x01\x07')),
            topic=Topic("Test", "TestType"),
            qos=QosPolicy(),
        )

        from vibedds.messages import DataSubmessage
        sm = DataSubmessage(
            flags=0x05,
            reader_id=EntityId(b'\x00\x00\x00\x00'),
            writer_id=EntityId(b'\x00\x00\x01\x03'),
            writer_sn=SequenceNumber.from_value(1),
            serialized_payload=b'\xDE\xAD',
        )
        reader._receive(sm, GuidPrefix(b'\x02' * 12), "127.0.0.1")

        samples = reader.take()
        assert len(samples) == 1
        assert samples[0] == b'\xDE\xAD'
        assert reader.take() == []

    def test_callback(self):
        reader = DataReader(
            guid=Guid(GuidPrefix(b'\x01' * 12), EntityId(b'\x00\x00\x01\x07')),
            topic=Topic("Test", "TestType"),
            qos=QosPolicy(),
        )

        received = []
        reader.on_data(lambda data: received.append(data))

        from vibedds.messages import DataSubmessage
        sm = DataSubmessage(
            flags=0x05,
            reader_id=EntityId(b'\x00\x00\x00\x00'),
            writer_id=EntityId(b'\x00\x00\x01\x03'),
            writer_sn=SequenceNumber.from_value(1),
            serialized_payload=b'\xCA\xFE',
        )
        reader._receive(sm, GuidPrefix(b'\x02' * 12), "127.0.0.1")

        assert len(received) == 1
        assert received[0] == b'\xCA\xFE'

    def test_take_one(self):
        reader = DataReader(
            guid=Guid(GuidPrefix(b'\x01' * 12), EntityId(b'\x00\x00\x01\x07')),
            topic=Topic("Test", "TestType"),
            qos=QosPolicy(),
        )

        from vibedds.messages import DataSubmessage
        for i in range(3):
            sm = DataSubmessage(
                flags=0x05,
                reader_id=EntityId(b'\x00\x00\x00\x00'),
                writer_id=EntityId(b'\x00\x00\x01\x03'),
                writer_sn=SequenceNumber.from_value(i + 1),
                serialized_payload=bytes([i]),
            )
            reader._receive(sm, GuidPrefix(b'\x02' * 12), "127.0.0.1")

        s1 = reader.take_one()
        assert s1 == b'\x00'
        s2 = reader.take_one()
        assert s2 == b'\x01'


# --- Integration test: endpoint matching flow ---

class TestEndpointMatchingFlow:
    def test_writer_reader_match_triggers_callback(self):
        db = EndpointDatabase()
        matches = []
        db.on_match(lambda kind, local, remote: matches.append(
            (kind, local.guid, remote.endpoint_guid)
        ))

        # Local writer
        writer_guid = Guid(GuidPrefix(b'\x01' * 12), EntityId(b'\x00\x00\x01\x03'))
        db.add_local_writer(LocalEndpoint(
            guid=writer_guid,
            topic_name="HelloWorldTopic",
            type_name="HelloWorld",
            qos=QosPolicy(reliability=ReliabilityKind.BEST_EFFORT),
            is_writer=True,
        ))

        # Remote reader (discovered via SEDP)
        reader_guid = Guid(GuidPrefix(b'\x02' * 12), EntityId(b'\x00\x00\x01\x07'))
        db.add_remote_reader(DiscoveredEndpoint(
            endpoint_guid=reader_guid,
            topic_name="HelloWorldTopic",
            type_name="HelloWorld",
            reliability=ReliabilityKind.BEST_EFFORT,
            qos=QosPolicy(reliability=ReliabilityKind.BEST_EFFORT),
        ))

        assert len(matches) == 1
        assert matches[0][0] == "writer_matched"
        assert matches[0][1] == writer_guid
        assert matches[0][2] == reader_guid
