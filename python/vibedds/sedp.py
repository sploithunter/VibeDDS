"""Simple Endpoint Discovery Protocol (SEDP).

After SPDP discovers a remote participant, SEDP exchanges endpoint
information (topic, type, QoS) over reliable unicast. This enables
matching of DataWriters and DataReaders across participants.
"""

from __future__ import annotations

import struct
import time
import logging
from dataclasses import dataclass, field
from typing import Callable

from vibedds.constants import (
    ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER,
    ENTITYID_SEDP_BUILTIN_PUBLICATIONS_READER,
    ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER,
    ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_READER,
    ENTITYID_UNKNOWN,
    PID_ENDPOINT_GUID, PID_TOPIC_NAME, PID_TYPE_NAME,
    PID_RELIABILITY, PID_DURABILITY, PID_OWNERSHIP, PID_LIVELINESS,
    PID_DESTINATION_ORDER, PID_DEADLINE, PID_PARTITION, PID_HISTORY,
    PID_UNICAST_LOCATOR, PID_MULTICAST_LOCATOR,
    PID_DEFAULT_UNICAST_LOCATOR, PID_KEY_HASH,
    PID_PARTICIPANT_GUID, PID_EXPECTS_INLINE_QOS, PID_TYPE_OBJECT,
    PID_PROTOCOL_VERSION, PID_VENDORID,
    PID_DATA_REPRESENTATION, PID_TYPE_CONSISTENCY_ENFORCEMENT,
    DISC_BUILTIN_ENDPOINT_PUBLICATIONS_ANNOUNCER,
    DISC_BUILTIN_ENDPOINT_PUBLICATIONS_DETECTOR,
    DISC_BUILTIN_ENDPOINT_SUBSCRIPTIONS_ANNOUNCER,
    DISC_BUILTIN_ENDPOINT_SUBSCRIPTIONS_DETECTOR,
    RTPS_VERSION_MAJOR, RTPS_VERSION_MINOR, VENDOR_ID,
)
from vibedds.types import (
    GuidPrefix, EntityId, Guid, SequenceNumber, SequenceNumberSet,
    Timestamp, Locator,
)
from vibedds.cdr import (
    CdrSerializer, CdrDeserializer,
    ParameterListBuilder, ParameterListParser,
    encapsulation_header, parse_encapsulation_header,
    PL_CDR_LE,
)
from vibedds.wire import RtpsMessageBuilder, RtpsMessageParser
from vibedds.messages import DataSubmessage, HeartbeatSubmessage, AckNackSubmessage
from vibedds.qos import (
    QosPolicy, ReliabilityKind, DurabilityKind,
    serialize_reliability_qos, serialize_durability_qos,
    deserialize_reliability_qos, deserialize_durability_qos,
    qos_compatible,
)
from vibedds.reliability import ReliableWriter, ReliableReader, CacheChange
from vibedds.spdp import DiscoveredParticipant

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredEndpoint:
    """Information about a discovered remote endpoint (writer or reader)."""
    endpoint_guid: Guid
    topic_name: str = ""
    type_name: str = ""
    reliability: ReliabilityKind = ReliabilityKind.BEST_EFFORT
    durability: DurabilityKind = DurabilityKind.VOLATILE
    unicast_locators: list[Locator] = field(default_factory=list)
    qos: QosPolicy | None = None


@dataclass
class LocalEndpoint:
    """Information about a local endpoint to be announced via SEDP."""
    guid: Guid
    topic_name: str
    type_name: str
    qos: QosPolicy
    is_writer: bool
    unicast_locators: list[Locator] = field(default_factory=list)


class EndpointDatabase:
    """Stores local and discovered remote endpoints, finds matches."""

    def __init__(self):
        self.local_writers: dict[bytes, LocalEndpoint] = {}
        self.local_readers: dict[bytes, LocalEndpoint] = {}
        self.remote_writers: dict[bytes, DiscoveredEndpoint] = {}
        self.remote_readers: dict[bytes, DiscoveredEndpoint] = {}
        self._on_match_callbacks: list[Callable] = []

    def on_match(self, callback: Callable) -> None:
        self._on_match_callbacks.append(callback)

    def add_local_writer(self, endpoint: LocalEndpoint) -> None:
        self.local_writers[endpoint.guid.to_bytes()] = endpoint
        self._check_matches_for_local_writer(endpoint)

    def add_local_reader(self, endpoint: LocalEndpoint) -> None:
        self.local_readers[endpoint.guid.to_bytes()] = endpoint
        self._check_matches_for_local_reader(endpoint)

    def add_remote_writer(self, endpoint: DiscoveredEndpoint) -> None:
        self.remote_writers[endpoint.endpoint_guid.to_bytes()] = endpoint
        self._check_matches_for_remote_writer(endpoint)

    def add_remote_reader(self, endpoint: DiscoveredEndpoint) -> None:
        self.remote_readers[endpoint.endpoint_guid.to_bytes()] = endpoint
        self._check_matches_for_remote_reader(endpoint)

    def find_matching_remote_readers(self, local_writer: LocalEndpoint) -> list[DiscoveredEndpoint]:
        matches = []
        for remote_reader in self.remote_readers.values():
            if self._endpoints_match(local_writer, remote_reader):
                matches.append(remote_reader)
        return matches

    def find_matching_remote_writers(self, local_reader: LocalEndpoint) -> list[DiscoveredEndpoint]:
        matches = []
        for remote_writer in self.remote_writers.values():
            if self._endpoints_match_wr(remote_writer, local_reader):
                matches.append(remote_writer)
        return matches

    @staticmethod
    def _endpoints_match(local_writer: LocalEndpoint, remote_reader: DiscoveredEndpoint) -> bool:
        if local_writer.topic_name != remote_reader.topic_name:
            return False
        if local_writer.type_name != remote_reader.type_name:
            return False
        reader_qos = remote_reader.qos or QosPolicy(
            reliability=remote_reader.reliability,
            durability=remote_reader.durability,
        )
        return qos_compatible(local_writer.qos, reader_qos)

    @staticmethod
    def _endpoints_match_wr(remote_writer: DiscoveredEndpoint, local_reader: LocalEndpoint) -> bool:
        if remote_writer.topic_name != local_reader.topic_name:
            return False
        if remote_writer.type_name != local_reader.type_name:
            return False
        writer_qos = remote_writer.qos or QosPolicy(
            reliability=remote_writer.reliability,
            durability=remote_writer.durability,
        )
        return qos_compatible(writer_qos, local_reader.qos)

    def _check_matches_for_local_writer(self, writer: LocalEndpoint) -> None:
        for reader in self.remote_readers.values():
            if self._endpoints_match(writer, reader):
                for cb in self._on_match_callbacks:
                    cb("writer_matched", writer, reader)

    def _check_matches_for_local_reader(self, reader: LocalEndpoint) -> None:
        for writer in self.remote_writers.values():
            if self._endpoints_match_wr(writer, reader):
                for cb in self._on_match_callbacks:
                    cb("reader_matched", reader, writer)

    def _check_matches_for_remote_writer(self, remote_writer: DiscoveredEndpoint) -> None:
        for local_reader in self.local_readers.values():
            if self._endpoints_match_wr(remote_writer, local_reader):
                for cb in self._on_match_callbacks:
                    cb("reader_matched", local_reader, remote_writer)

    def _check_matches_for_remote_reader(self, remote_reader: DiscoveredEndpoint) -> None:
        for local_writer in self.local_writers.values():
            if self._endpoints_match(local_writer, remote_reader):
                for cb in self._on_match_callbacks:
                    cb("writer_matched", local_writer, remote_reader)


def _build_endpoint_data(endpoint: LocalEndpoint, endian: str = "<") -> bytes:
    """Serialize a local endpoint as PL_CDR for SEDP announcement."""
    pl = ParameterListBuilder(endian)

    # PID_ENDPOINT_GUID - required
    pl.add_parameter(PID_ENDPOINT_GUID, endpoint.guid.to_bytes())

    # PID_PARTICIPANT_GUID - identifies which participant owns this endpoint
    # Use the GUID prefix + ENTITYID_PARTICIPANT (0xC1)
    participant_entity_id = bytes([0x00, 0x00, 0x01, 0xC1])
    participant_guid = endpoint.guid.prefix.value + participant_entity_id
    pl.add_parameter(PID_PARTICIPANT_GUID, participant_guid)

    # PID_PROTOCOL_VERSION - RTI includes this
    pl.add_parameter(PID_PROTOCOL_VERSION,
                     bytes([RTPS_VERSION_MAJOR, RTPS_VERSION_MINOR]))

    # PID_VENDORID - RTI includes this
    pl.add_parameter(PID_VENDORID, bytes(VENDOR_ID))

    # PID_TOPIC_NAME (CDR string) - required
    ser = CdrSerializer(endian)
    ser.write_string(endpoint.topic_name)
    pl.add_parameter(PID_TOPIC_NAME, ser.getvalue())

    # PID_TYPE_NAME (CDR string) - required
    ser = CdrSerializer(endian)
    ser.write_string(endpoint.type_name)
    pl.add_parameter(PID_TYPE_NAME, ser.getvalue())

    # PID_RELIABILITY - important for QoS matching
    # RTI includes this in its SEDP publications
    reliability_data = serialize_reliability_qos(endpoint.qos, endian)
    pl.add_parameter(PID_RELIABILITY, reliability_data)

    # PID_DURABILITY - important for QoS matching
    durability_data = serialize_durability_qos(endpoint.qos, endian)
    pl.add_parameter(PID_DURABILITY, durability_data)

    # PID_OWNERSHIP - QoS matching
    ownership_kind = int(endpoint.qos.ownership) if hasattr(endpoint.qos, 'ownership') else 0
    pl.add_parameter(PID_OWNERSHIP, struct.pack(endian + "I", ownership_kind))

    # PID_LIVELINESS - QoS matching (kind + lease_duration)
    liveliness_kind = int(endpoint.qos.liveliness) if hasattr(endpoint.qos, 'liveliness') else 0
    liveliness_data = struct.pack(endian + "IiI", liveliness_kind, 0x7FFFFFFF, 0xFFFFFFFF)  # INFINITE duration
    pl.add_parameter(PID_LIVELINESS, liveliness_data)

    # PID_DESTINATION_ORDER - QoS matching
    dest_order_kind = int(endpoint.qos.destination_order) if hasattr(endpoint.qos, 'destination_order') else 0
    pl.add_parameter(PID_DESTINATION_ORDER, struct.pack(endian + "I", dest_order_kind))

    # PID_DEADLINE - QoS matching (infinite period)
    deadline_data = struct.pack(endian + "iI", 0x7FFFFFFF, 0xFFFFFFFF)  # INFINITE
    pl.add_parameter(PID_DEADLINE, deadline_data)

    # PID_HISTORY - QoS matching (KEEP_LAST with depth 1)
    history_kind = int(endpoint.qos.history) if hasattr(endpoint.qos, 'history') else 0  # KEEP_LAST
    history_depth = endpoint.qos.history_depth if hasattr(endpoint.qos, 'history_depth') else 1
    pl.add_parameter(PID_HISTORY, struct.pack(endian + "II", history_kind, history_depth))

    # XTypes PIDs - DATA_REPRESENTATION (0x0073) and TYPE_CONSISTENCY_ENFORCEMENT (0x0053)
    # These help with XTypes type negotiation
    if not endpoint.is_writer:
        # DATA_REPRESENTATION: Use RTI's exact format for interop
        # RTI sends: 01 00 00 00 | 00 00 00 00 | 07 00 00 00 (12 bytes)
        # First u32 = count, then XCDR1 rep (0x0000) with padding, then 0x07 (XCDR2 flags?)
        data_rep = bytes([
            0x01, 0x00, 0x00, 0x00,  # count = 1
            0x00, 0x00,              # XCDR1 = 0
            0x00, 0x00,              # padding
            0x07, 0x00, 0x00, 0x00,  # RTI's extra bytes (may indicate XCDR1+XCDR2 support)
        ])
        pl.add_parameter(PID_DATA_REPRESENTATION, data_rep)

        # TYPE_CONSISTENCY_ENFORCEMENT: Use RTI's exact format
        # RTI sends: 00 00 01 09 (4 bytes)
        type_consistency = bytes([
            0x00, 0x00,  # kind = DISALLOW_TYPE_COERCION
            0x01, 0x09,  # flags: ignore_sequence_bounds=true, other flags
        ])
        pl.add_parameter(PID_TYPE_CONSISTENCY_ENFORCEMENT, type_consistency)

    # PID_PARTITION - empty partition list (matches default partition)
    # Format: count(u32) = 0 means empty partition list (default)
    pl.add_parameter(PID_PARTITION, struct.pack(endian + "I", 0))

    # Include endpoint unicast locators so remote participants know where
    # to send user data. This is important for data delivery.
    for loc in endpoint.unicast_locators:
        pl.add_parameter(PID_UNICAST_LOCATOR, loc.to_bytes())

    return pl.finalize()


def _parse_endpoint_data(payload: bytes) -> DiscoveredEndpoint | None:
    """Parse SEDP endpoint data from encapsulated parameter list."""
    scheme, pl_data = parse_encapsulation_header(payload)
    endian = "<" if scheme in (0x0003, 0x0001) else ">"

    endpoint = DiscoveredEndpoint(
        endpoint_guid=Guid(GuidPrefix.UNKNOWN, EntityId.UNKNOWN),
    )

    for pid, value in ParameterListParser(pl_data, endian):
        if pid == PID_ENDPOINT_GUID:
            endpoint.endpoint_guid = Guid.from_bytes(value)
        elif pid == PID_TOPIC_NAME:
            de = CdrDeserializer(value, endian)
            endpoint.topic_name = de.read_string()
        elif pid == PID_TYPE_NAME:
            de = CdrDeserializer(value, endian)
            endpoint.type_name = de.read_string()
        elif pid == PID_RELIABILITY:
            kind, max_block = deserialize_reliability_qos(value, endian)
            endpoint.reliability = kind
        elif pid == PID_DURABILITY:
            endpoint.durability = deserialize_durability_qos(value, endian)
        elif pid == PID_DEFAULT_UNICAST_LOCATOR or pid == PID_UNICAST_LOCATOR:
            endpoint.unicast_locators.append(Locator.from_bytes(value))

    endpoint.qos = QosPolicy(
        reliability=endpoint.reliability,
        durability=endpoint.durability,
    )

    return endpoint


class SEDPProtocol:
    """Manages SEDP builtin endpoints for endpoint discovery.

    Creates 4 builtin endpoints:
    - publications writer/reader (announce/discover DataWriters)
    - subscriptions writer/reader (announce/discover DataReaders)
    """

    def __init__(self, guid_prefix: GuidPrefix, endpoint_db: EndpointDatabase):
        self._guid_prefix = guid_prefix
        self._endpoint_db = endpoint_db

        # Publication writer (announces our DataWriters)
        self._pub_writer = ReliableWriter(
            guid=Guid(guid_prefix, EntityId(ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER)),
            heartbeat_period=2.0,
        )
        # Publication reader (discovers remote DataWriters)
        self._pub_reader = ReliableReader(
            guid=Guid(guid_prefix, EntityId(ENTITYID_SEDP_BUILTIN_PUBLICATIONS_READER)),
        )
        # Subscription writer (announces our DataReaders)
        self._sub_writer = ReliableWriter(
            guid=Guid(guid_prefix, EntityId(ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER)),
            heartbeat_period=2.0,
        )
        # Subscription reader (discovers remote DataReaders)
        self._sub_reader = ReliableReader(
            guid=Guid(guid_prefix, EntityId(ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_READER)),
        )

        self._pending_announcements: list[tuple[LocalEndpoint, bytes]] = []

    def on_participant_discovered(self, pd: DiscoveredParticipant) -> None:
        """Called when SPDP discovers a new participant.

        Sets up reader/writer proxies based on the participant's
        builtin_endpoints bitmap.
        """
        endpoints = pd.builtin_endpoints

        if endpoints & DISC_BUILTIN_ENDPOINT_PUBLICATIONS_DETECTOR:
            # Remote has publications reader → our publications writer needs a proxy
            reader_guid = Guid(
                pd.guid_prefix,
                EntityId(ENTITYID_SEDP_BUILTIN_PUBLICATIONS_READER),
            )
            self._pub_writer.add_reader_proxy(reader_guid)

        if endpoints & DISC_BUILTIN_ENDPOINT_PUBLICATIONS_ANNOUNCER:
            # Remote has publications writer → our publications reader needs a proxy
            writer_guid = Guid(
                pd.guid_prefix,
                EntityId(ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER),
            )
            self._pub_reader.add_writer_proxy(writer_guid)

        if endpoints & DISC_BUILTIN_ENDPOINT_SUBSCRIPTIONS_DETECTOR:
            reader_guid = Guid(
                pd.guid_prefix,
                EntityId(ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_READER),
            )
            self._sub_writer.add_reader_proxy(reader_guid)

        if endpoints & DISC_BUILTIN_ENDPOINT_SUBSCRIPTIONS_ANNOUNCER:
            writer_guid = Guid(
                pd.guid_prefix,
                EntityId(ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER),
            )
            self._sub_reader.add_writer_proxy(writer_guid)

    def announce_endpoint(self, endpoint: LocalEndpoint) -> None:
        """Queue a local endpoint for SEDP announcement."""
        pl_data = _build_endpoint_data(endpoint)
        payload = encapsulation_header(PL_CDR_LE) + pl_data

        if endpoint.is_writer:
            change = self._pub_writer.new_change(payload)
        else:
            change = self._sub_writer.new_change(payload)

        self._pending_announcements.append((endpoint, payload))

    def build_announcement_messages(
        self, dest_prefix: GuidPrefix, dest_meta_locators: list[Locator]
    ) -> list[tuple[bytes, str, int]]:
        """Build SEDP DATA messages for a specific remote participant.

        Returns list of (message_bytes, dest_addr, dest_port).
        """
        messages = []

        if not dest_meta_locators:
            return messages

        dest_addr = dest_meta_locators[0].ipv4_str or "127.0.0.1"
        dest_port = dest_meta_locators[0].port

        # Send publications (our DataWriters)
        for change in self._pub_writer._history:
            builder = RtpsMessageBuilder(self._guid_prefix)
            builder.add_info_ts(Timestamp.from_seconds(time.time()))
            builder.add_info_dst(dest_prefix)
            builder.add_data(
                reader_id=EntityId(ENTITYID_SEDP_BUILTIN_PUBLICATIONS_READER),
                writer_id=EntityId(ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER),
                writer_sn=change.sequence_number,
                serialized_payload=change.serialized_data,
            )
            messages.append((builder.build(), dest_addr, dest_port))

        # Send subscriptions (our DataReaders)
        for change in self._sub_writer._history:
            builder = RtpsMessageBuilder(self._guid_prefix)
            builder.add_info_ts(Timestamp.from_seconds(time.time()))
            builder.add_info_dst(dest_prefix)
            builder.add_data(
                reader_id=EntityId(ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_READER),
                writer_id=EntityId(ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER),
                writer_sn=change.sequence_number,
                serialized_payload=change.serialized_data,
            )
            messages.append((builder.build(), dest_addr, dest_port))

        # Send heartbeats
        if self._pub_writer._history:
            builder = RtpsMessageBuilder(self._guid_prefix)
            builder.add_info_dst(dest_prefix)
            builder.add_heartbeat(
                reader_id=EntityId(ENTITYID_SEDP_BUILTIN_PUBLICATIONS_READER),
                writer_id=EntityId(ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER),
                first_sn=self._pub_writer.first_available_sn,
                last_sn=self._pub_writer.last_available_sn,
                count=self._pub_writer.next_heartbeat_count(),
            )
            messages.append((builder.build(), dest_addr, dest_port))

        if self._sub_writer._history:
            builder = RtpsMessageBuilder(self._guid_prefix)
            builder.add_info_dst(dest_prefix)
            builder.add_heartbeat(
                reader_id=EntityId(ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_READER),
                writer_id=EntityId(ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER),
                first_sn=self._sub_writer.first_available_sn,
                last_sn=self._sub_writer.last_available_sn,
                count=self._sub_writer.next_heartbeat_count(),
            )
            messages.append((builder.build(), dest_addr, dest_port))

        return messages

    def handle_publications_data(
        self, sm: DataSubmessage, source_prefix: GuidPrefix, source_addr: str
    ) -> None:
        """Handle incoming SEDP publications DATA (remote DataWriter info)."""
        if sm.serialized_payload is None:
            return

        endpoint = _parse_endpoint_data(sm.serialized_payload)
        if endpoint is None:
            return

        writer_guid = Guid(source_prefix, sm.writer_id)
        self._pub_reader.record_received(writer_guid, sm.writer_sn)

        logger.info(
            "Discovered remote writer: %s topic=%s type=%s",
            endpoint.endpoint_guid, endpoint.topic_name, endpoint.type_name,
        )
        self._endpoint_db.add_remote_writer(endpoint)

    def handle_subscriptions_data(
        self, sm: DataSubmessage, source_prefix: GuidPrefix, source_addr: str
    ) -> None:
        """Handle incoming SEDP subscriptions DATA (remote DataReader info)."""
        if sm.serialized_payload is None:
            return

        endpoint = _parse_endpoint_data(sm.serialized_payload)
        if endpoint is None:
            return

        writer_guid = Guid(source_prefix, sm.writer_id)
        self._sub_reader.record_received(writer_guid, sm.writer_sn)

        logger.info(
            "Discovered remote reader: %s topic=%s type=%s",
            endpoint.endpoint_guid, endpoint.topic_name, endpoint.type_name,
        )
        self._endpoint_db.add_remote_reader(endpoint)

    def handle_heartbeat(
        self, sm: HeartbeatSubmessage, source_prefix: GuidPrefix
    ) -> tuple[bytes, ...] | None:
        """Handle incoming HEARTBEAT, return ACKNACK messages if needed."""
        writer_entity = sm.writer_id.value

        reader: ReliableReader | None = None
        if writer_entity == ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER:
            reader = self._pub_reader
        elif writer_entity == ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER:
            reader = self._sub_reader

        if reader is None:
            return None

        sn_set = reader.process_heartbeat(sm, source_prefix)
        if sn_set is None:
            return None

        # Build ACKNACK
        builder = RtpsMessageBuilder(self._guid_prefix)
        builder.add_info_dst(source_prefix)
        builder.add_acknack(
            reader_id=EntityId(reader.guid.entity_id.value),
            writer_id=sm.writer_id,
            reader_sn_state=sn_set,
            count=reader.next_acknack_count(),
        )
        return (builder.build(),)

    @property
    def pub_writer(self) -> ReliableWriter:
        return self._pub_writer

    @property
    def sub_writer(self) -> ReliableWriter:
        return self._sub_writer

    @property
    def pub_reader(self) -> ReliableReader:
        return self._pub_reader

    @property
    def sub_reader(self) -> ReliableReader:
        return self._sub_reader
