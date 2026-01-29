"""Tests for SEDP endpoint discovery."""

import struct
import pytest

from vibedds.types import (
    GuidPrefix, EntityId, Guid, SequenceNumber, SequenceNumberSet,
    Locator, Timestamp, Duration,
)
from vibedds.constants import (
    ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER,
    ENTITYID_SEDP_BUILTIN_PUBLICATIONS_READER,
    ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER,
    ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_READER,
    BUILTIN_ENDPOINT_SET_DEFAULT,
    ENTITY_KIND_USER_WRITER_NO_KEY,
    ENTITY_KIND_USER_READER_NO_KEY,
)
from vibedds.qos import (
    QosPolicy, ReliabilityKind, DurabilityKind, qos_compatible,
)
from vibedds.reliability import ReliableWriter, ReliableReader, CacheChange
from vibedds.sedp import (
    SEDPProtocol, EndpointDatabase, LocalEndpoint, DiscoveredEndpoint,
    _build_endpoint_data, _parse_endpoint_data,
)
from vibedds.spdp import DiscoveredParticipant
from vibedds.cdr import encapsulation_header, PL_CDR_LE
from vibedds.messages import HeartbeatSubmessage


# --- QoS compatibility tests ---

class TestQosCompatibility:
    def test_reliable_offered_besteff_requested(self):
        offered = QosPolicy(reliability=ReliabilityKind.RELIABLE)
        requested = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
        assert qos_compatible(offered, requested)

    def test_besteff_offered_reliable_requested(self):
        offered = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
        requested = QosPolicy(reliability=ReliabilityKind.RELIABLE)
        assert not qos_compatible(offered, requested)

    def test_same_reliability(self):
        offered = QosPolicy(reliability=ReliabilityKind.RELIABLE)
        requested = QosPolicy(reliability=ReliabilityKind.RELIABLE)
        assert qos_compatible(offered, requested)

    def test_transient_local_offered_volatile_requested(self):
        offered = QosPolicy(durability=DurabilityKind.TRANSIENT_LOCAL)
        requested = QosPolicy(durability=DurabilityKind.VOLATILE)
        assert qos_compatible(offered, requested)

    def test_volatile_offered_transient_local_requested(self):
        offered = QosPolicy(durability=DurabilityKind.VOLATILE)
        requested = QosPolicy(durability=DurabilityKind.TRANSIENT_LOCAL)
        assert not qos_compatible(offered, requested)

    def test_partition_match(self):
        offered = QosPolicy(partition=["A", "B"])
        requested = QosPolicy(partition=["B", "C"])
        assert qos_compatible(offered, requested)

    def test_partition_no_match(self):
        offered = QosPolicy(partition=["A"])
        requested = QosPolicy(partition=["B"])
        assert not qos_compatible(offered, requested)

    def test_partition_default(self):
        offered = QosPolicy()
        requested = QosPolicy()
        assert qos_compatible(offered, requested)


# --- Reliability tests ---

class TestReliableWriter:
    def test_new_change(self):
        writer = ReliableWriter(
            guid=Guid(GuidPrefix(b'\x01' * 12), EntityId(b'\x00\x00\x03\xC2')),
        )
        change = writer.new_change(b'\xDE\xAD')
        assert change.sequence_number.value == 1
        change2 = writer.new_change(b'\xBE\xEF')
        assert change2.sequence_number.value == 2

    def test_get_change(self):
        writer = ReliableWriter(
            guid=Guid(GuidPrefix(b'\x01' * 12), EntityId(b'\x00\x00\x03\xC2')),
        )
        writer.new_change(b'\x01')
        change = writer.new_change(b'\x02')
        assert writer.get_change(SequenceNumber.from_value(2)) is change
        assert writer.get_change(SequenceNumber.from_value(99)) is None

    def test_history_limit(self):
        writer = ReliableWriter(
            guid=Guid(GuidPrefix(b'\x01' * 12), EntityId(b'\x00\x00\x03\xC2')),
            max_history=3,
        )
        for i in range(5):
            writer.new_change(bytes([i]))
        assert len(writer._history) == 3
        assert writer._history[0].sequence_number.value == 3

    def test_add_reader_proxy(self):
        writer = ReliableWriter(
            guid=Guid(GuidPrefix(b'\x01' * 12), EntityId(b'\x00\x00\x03\xC2')),
        )
        reader_guid = Guid(GuidPrefix(b'\x02' * 12), EntityId(b'\x00\x00\x03\xC7'))
        writer.add_reader_proxy(reader_guid)
        assert len(writer.reader_proxies) == 1


class TestReliableReader:
    def test_process_heartbeat_missing(self):
        reader = ReliableReader(
            guid=Guid(GuidPrefix(b'\x01' * 12), EntityId(b'\x00\x00\x03\xC7')),
        )
        writer_guid = Guid(GuidPrefix(b'\x02' * 12), EntityId(b'\x00\x00\x03\xC2'))
        reader.add_writer_proxy(writer_guid)

        # Writer has SNs 1..3, we received only SN 2
        reader.record_received(writer_guid, SequenceNumber.from_value(2))

        hb = HeartbeatSubmessage(
            flags=0x01,
            reader_id=EntityId(b'\x00\x00\x03\xC7'),
            writer_id=EntityId(b'\x00\x00\x03\xC2'),
            first_sn=SequenceNumber.from_value(1),
            last_sn=SequenceNumber.from_value(3),
            count=1,
        )

        sn_set = reader.process_heartbeat(hb, GuidPrefix(b'\x02' * 12))
        assert sn_set is not None
        missing = sn_set.missing_sequence_numbers()
        missing_vals = [s.value for s in missing]
        assert 1 in missing_vals
        assert 3 in missing_vals
        assert 2 not in missing_vals

    def test_process_heartbeat_all_received(self):
        reader = ReliableReader(
            guid=Guid(GuidPrefix(b'\x01' * 12), EntityId(b'\x00\x00\x03\xC7')),
        )
        writer_guid = Guid(GuidPrefix(b'\x02' * 12), EntityId(b'\x00\x00\x03\xC2'))
        reader.add_writer_proxy(writer_guid)

        reader.record_received(writer_guid, SequenceNumber.from_value(1))
        reader.record_received(writer_guid, SequenceNumber.from_value(2))

        hb = HeartbeatSubmessage(
            flags=0x01,
            reader_id=EntityId(b'\x00\x00\x03\xC7'),
            writer_id=EntityId(b'\x00\x00\x03\xC2'),
            first_sn=SequenceNumber.from_value(1),
            last_sn=SequenceNumber.from_value(2),
            count=1,
        )

        sn_set = reader.process_heartbeat(hb, GuidPrefix(b'\x02' * 12))
        assert sn_set is not None
        assert sn_set.num_bits == 0  # All caught up


# --- SEDP endpoint serialization tests ---

class TestEndpointSerialization:
    def test_roundtrip(self):
        endpoint = LocalEndpoint(
            guid=Guid(GuidPrefix(b'\xAA' * 12), EntityId(b'\x00\x00\x01\x02')),
            topic_name="HelloWorld",
            type_name="HelloWorldType",
            qos=QosPolicy(
                reliability=ReliabilityKind.RELIABLE,
                durability=DurabilityKind.TRANSIENT_LOCAL,
            ),
            is_writer=True,
            unicast_locators=[Locator.from_ipv4("192.168.1.10", 7401)],
        )
        pl_data = _build_endpoint_data(endpoint)
        payload = encapsulation_header(PL_CDR_LE) + pl_data

        parsed = _parse_endpoint_data(payload)
        assert parsed is not None
        assert parsed.endpoint_guid == endpoint.guid
        assert parsed.topic_name == "HelloWorld"
        assert parsed.type_name == "HelloWorldType"
        assert parsed.reliability == ReliabilityKind.RELIABLE
        assert parsed.durability == DurabilityKind.TRANSIENT_LOCAL
        assert len(parsed.unicast_locators) == 1
        assert parsed.unicast_locators[0].ipv4_str == "192.168.1.10"


# --- Endpoint database tests ---

class TestEndpointDatabase:
    def test_match_writer_reader(self):
        db = EndpointDatabase()
        matches = []
        db.on_match(lambda kind, a, b: matches.append((kind, a, b)))

        writer = LocalEndpoint(
            guid=Guid(GuidPrefix(b'\x01' * 12), EntityId(b'\x00\x00\x01\x03')),
            topic_name="Test",
            type_name="TestType",
            qos=QosPolicy(reliability=ReliabilityKind.RELIABLE),
            is_writer=True,
        )
        db.add_local_writer(writer)

        remote_reader = DiscoveredEndpoint(
            endpoint_guid=Guid(GuidPrefix(b'\x02' * 12), EntityId(b'\x00\x00\x01\x07')),
            topic_name="Test",
            type_name="TestType",
            reliability=ReliabilityKind.BEST_EFFORT,
            qos=QosPolicy(reliability=ReliabilityKind.BEST_EFFORT),
        )
        db.add_remote_reader(remote_reader)

        assert len(matches) == 1
        assert matches[0][0] == "writer_matched"

    def test_no_match_different_topic(self):
        db = EndpointDatabase()
        matches = []
        db.on_match(lambda kind, a, b: matches.append((kind, a, b)))

        writer = LocalEndpoint(
            guid=Guid(GuidPrefix(b'\x01' * 12), EntityId(b'\x00\x00\x01\x03')),
            topic_name="TopicA",
            type_name="Type",
            qos=QosPolicy(),
            is_writer=True,
        )
        db.add_local_writer(writer)

        remote_reader = DiscoveredEndpoint(
            endpoint_guid=Guid(GuidPrefix(b'\x02' * 12), EntityId(b'\x00\x00\x01\x07')),
            topic_name="TopicB",
            type_name="Type",
            qos=QosPolicy(),
        )
        db.add_remote_reader(remote_reader)
        assert len(matches) == 0

    def test_no_match_qos_incompatible(self):
        db = EndpointDatabase()
        matches = []
        db.on_match(lambda kind, a, b: matches.append((kind, a, b)))

        writer = LocalEndpoint(
            guid=Guid(GuidPrefix(b'\x01' * 12), EntityId(b'\x00\x00\x01\x03')),
            topic_name="Test",
            type_name="TestType",
            qos=QosPolicy(reliability=ReliabilityKind.BEST_EFFORT),
            is_writer=True,
        )
        db.add_local_writer(writer)

        remote_reader = DiscoveredEndpoint(
            endpoint_guid=Guid(GuidPrefix(b'\x02' * 12), EntityId(b'\x00\x00\x01\x07')),
            topic_name="Test",
            type_name="TestType",
            reliability=ReliabilityKind.RELIABLE,
            qos=QosPolicy(reliability=ReliabilityKind.RELIABLE),
        )
        db.add_remote_reader(remote_reader)
        assert len(matches) == 0


# --- SEDP Protocol tests ---

class TestSEDPProtocol:
    def test_on_participant_discovered(self):
        prefix = GuidPrefix(b'\x01' * 12)
        db = EndpointDatabase()
        sedp = SEDPProtocol(prefix, db)

        pd = DiscoveredParticipant(
            guid_prefix=GuidPrefix(b'\x02' * 12),
            builtin_endpoints=BUILTIN_ENDPOINT_SET_DEFAULT,
        )
        sedp.on_participant_discovered(pd)

        # Should have proxies for publications and subscriptions
        assert len(sedp.pub_writer.reader_proxies) == 1
        assert len(sedp.pub_reader.writer_proxies) == 1
        assert len(sedp.sub_writer.reader_proxies) == 1
        assert len(sedp.sub_reader.writer_proxies) == 1

    def test_announce_endpoint(self):
        prefix = GuidPrefix(b'\x01' * 12)
        db = EndpointDatabase()
        sedp = SEDPProtocol(prefix, db)

        endpoint = LocalEndpoint(
            guid=Guid(prefix, EntityId(b'\x00\x00\x01\x03')),
            topic_name="HelloWorld",
            type_name="HelloWorldType",
            qos=QosPolicy(reliability=ReliabilityKind.BEST_EFFORT),
            is_writer=True,
            unicast_locators=[Locator.from_ipv4("127.0.0.1", 7401)],
        )
        sedp.announce_endpoint(endpoint)

        # Publications writer should have one cache change
        assert len(sedp.pub_writer._history) == 1

    def test_build_announcement_messages(self):
        prefix = GuidPrefix(b'\x01' * 12)
        db = EndpointDatabase()
        sedp = SEDPProtocol(prefix, db)

        endpoint = LocalEndpoint(
            guid=Guid(prefix, EntityId(b'\x00\x00\x01\x03')),
            topic_name="HelloWorld",
            type_name="HelloWorldType",
            qos=QosPolicy(reliability=ReliabilityKind.BEST_EFFORT),
            is_writer=True,
        )
        sedp.announce_endpoint(endpoint)

        dest_prefix = GuidPrefix(b'\x02' * 12)
        dest_locators = [Locator.from_ipv4("192.168.1.50", 7410)]

        messages = sedp.build_announcement_messages(dest_prefix, dest_locators)
        # Should have at least the DATA + HEARTBEAT for publications
        assert len(messages) >= 1
        for msg_bytes, addr, port in messages:
            assert len(msg_bytes) > 20  # valid RTPS
            assert addr == "192.168.1.50"
            assert port == 7410
