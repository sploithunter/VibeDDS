"""DomainParticipant — the main entry point for VibeDDS.

Generates a unique GUID prefix, manages transport and discovery protocols,
and runs the event loop.
"""

from __future__ import annotations

import os
import struct
import time
import select
import logging
from dataclasses import dataclass, field

from vibedds.constants import (
    VENDOR_ID,
    ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER,
    ENTITYID_SPDP_BUILTIN_PARTICIPANT_READER,
    ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER,
    ENTITYID_SEDP_BUILTIN_PUBLICATIONS_READER,
    ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER,
    ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_READER,
    BUILTIN_ENDPOINT_SET_DEFAULT,
    spdp_multicast_port,
)
from vibedds.types import GuidPrefix, EntityId, Guid, Locator
from vibedds.transport import UdpTransport
from vibedds.spdp import SPDPWriter, SPDPReader, ParticipantDatabase, DiscoveredParticipant
from vibedds.wire import RtpsMessageParser
from vibedds.messages import DataSubmessage, HeartbeatSubmessage
from vibedds.sedp import SEDPProtocol, EndpointDatabase, LocalEndpoint
from vibedds.qos import QosPolicy, ReliabilityKind, DurabilityKind
from vibedds.topic import Topic, TopicRegistry
from vibedds.endpoint import DataWriter, DataReader, EntityIdAllocator

logger = logging.getLogger(__name__)


def generate_guid_prefix() -> GuidPrefix:
    """Generate a unique 12-byte GuidPrefix.

    Layout: vendorId(2) + PID(4) + timestamp_low(2) + random(4)
    """
    buf = bytearray(12)
    buf[0:2] = bytes(VENDOR_ID)
    buf[2:6] = struct.pack("<I", os.getpid() & 0xFFFFFFFF)
    buf[6:8] = struct.pack("<H", int(time.time()) & 0xFFFF)
    buf[8:12] = os.urandom(4)
    return GuidPrefix(bytes(buf))


class DomainParticipant:
    """RTPS DomainParticipant.

    Manages transport, SPDP discovery, and (later) SEDP + user endpoints.
    """

    def __init__(
        self,
        domain_id: int = 0,
        participant_id: int = 0,
        guid_prefix: GuidPrefix | None = None,
    ):
        self.domain_id = domain_id
        self.participant_id = participant_id
        self.guid_prefix = guid_prefix or generate_guid_prefix()

        self._transport = UdpTransport(domain_id, participant_id)
        self._participant_db = ParticipantDatabase()

        self._spdp_writer: SPDPWriter | None = None
        self._spdp_announce_interval = 30.0  # seconds
        self._last_spdp_announce = 0.0
        self._running = False

        # Callbacks
        self._on_participant_discovered: list = []
        self._on_participant_lost: list = []

        # SEDP
        self._endpoint_db = EndpointDatabase()
        self._sedp = SEDPProtocol(self.guid_prefix, self._endpoint_db)
        self._topic_registry = TopicRegistry()
        self._entity_allocator = EntityIdAllocator()

        # User endpoints
        self._writers: list[DataWriter] = []
        self._readers: list[DataReader] = []

        # Message dispatch by writer entity ID
        self._message_handlers: dict[bytes, list] = {}

    @property
    def transport(self) -> UdpTransport:
        return self._transport

    @property
    def participant_db(self) -> ParticipantDatabase:
        return self._participant_db

    @property
    def endpoint_db(self) -> EndpointDatabase:
        return self._endpoint_db

    @property
    def sedp(self) -> SEDPProtocol:
        return self._sedp

    def on_participant_discovered(self, callback) -> None:
        """Register callback for new participant discovery."""
        self._on_participant_discovered.append(callback)

    def on_participant_lost(self, callback) -> None:
        """Register callback for participant loss (lease expiry)."""
        self._on_participant_lost.append(callback)

    def register_message_handler(self, writer_entity_id: bytes, handler) -> None:
        """Register a handler for DATA submessages from a specific writer entity."""
        self._message_handlers.setdefault(writer_entity_id, []).append(handler)

    def create_topic(self, name: str, type_name: str, qos: QosPolicy | None = None) -> Topic:
        """Register a topic."""
        topic = Topic(name=name, type_name=type_name, qos=qos)
        return self._topic_registry.register(topic)

    def create_writer(self, topic: Topic, qos: QosPolicy | None = None) -> DataWriter:
        """Create a DataWriter for the given topic."""
        if qos is None:
            qos = topic.qos or QosPolicy()

        entity_id = self._entity_allocator.allocate_writer()
        guid = Guid(self.guid_prefix, entity_id)

        writer = DataWriter(
            guid=guid,
            topic=topic,
            qos=qos,
            transport=self._transport,
            guid_prefix=self.guid_prefix,
            endpoint_db=self._endpoint_db,
            participant_db=self._participant_db,
        )
        self._writers.append(writer)

        # Register in endpoint DB and announce via SEDP
        local_ep = LocalEndpoint(
            guid=guid,
            topic_name=topic.name,
            type_name=topic.type_name,
            qos=qos,
            is_writer=True,
            unicast_locators=[
                Locator.from_ipv4(self._transport.local_ip,
                                  self._transport.user_unicast_port),
            ],
        )
        self._endpoint_db.add_local_writer(local_ep)
        self._sedp.announce_endpoint(local_ep)

        logger.info("Created DataWriter: %s on topic '%s'", guid, topic.name)
        return writer

    def create_reader(
        self, topic: Topic, qos: QosPolicy | None = None
    ) -> DataReader:
        """Create a DataReader for the given topic."""
        if qos is None:
            qos = topic.qos or QosPolicy()

        entity_id = self._entity_allocator.allocate_reader()
        guid = Guid(self.guid_prefix, entity_id)

        reader = DataReader(guid=guid, topic=topic, qos=qos)
        self._readers.append(reader)

        # Register handler for incoming data routed by writer entity
        # We actually route by reader entity — but since remote writers
        # send to ENTITYID_UNKNOWN, we need to match by topic.
        # Register the reader's _receive as a handler for any writer entity
        # on user traffic. For now, we register as a generic user handler.

        # Register in endpoint DB and announce via SEDP
        local_ep = LocalEndpoint(
            guid=guid,
            topic_name=topic.name,
            type_name=topic.type_name,
            qos=qos,
            is_writer=False,
            unicast_locators=[
                Locator.from_ipv4(self._transport.local_ip,
                                  self._transport.user_unicast_port),
            ],
        )
        self._endpoint_db.add_local_reader(local_ep)
        self._sedp.announce_endpoint(local_ep)

        logger.info("Created DataReader: %s on topic '%s'", guid, topic.name)
        return reader

    def start(self) -> None:
        """Open transport, initialize protocols."""
        self._transport.open()

        self._spdp_writer = SPDPWriter(
            guid_prefix=self.guid_prefix,
            local_ip=self._transport.local_ip,
            metatraffic_unicast_port=self._transport.metatraffic_unicast_port,
            user_unicast_port=self._transport.user_unicast_port,
            domain_id=self.domain_id,
        )

        # Register SEDP message handlers for metatraffic
        self.register_message_handler(
            ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER,
            self._sedp.handle_publications_data,
        )
        self.register_message_handler(
            ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER,
            self._sedp.handle_subscriptions_data,
        )

        # Register SPDP discovery callback to trigger SEDP
        self.on_participant_discovered(self._on_new_participant)

        self._running = True
        logger.info(
            "Participant started: guid=%s, domain=%d, pid=%d",
            self.guid_prefix, self.domain_id, self.participant_id,
        )

    def stop(self) -> None:
        """Stop the participant and close transport."""
        self._running = False
        self._transport.close()
        logger.info("Participant stopped")

    def announce_spdp(self) -> None:
        """Send an SPDP announcement now."""
        if self._spdp_writer:
            data = self._spdp_writer.build_announcement()
            self._transport.send_multicast(data)
            self._last_spdp_announce = time.time()
            logger.debug("Sent SPDP announcement")

    def spin_once(self, timeout: float = 0.1) -> None:
        """Run one iteration of the event loop.

        Checks for incoming packets, sends periodic announcements,
        and checks lease expiry.
        """
        now = time.time()

        # Periodic SPDP announce
        if now - self._last_spdp_announce >= self._spdp_announce_interval:
            self.announce_spdp()

        # Check for incoming packets
        sockets = self._transport.get_sockets()
        if not sockets:
            return

        sock_list = list(sockets.values())
        readable, _, _ = select.select(sock_list, [], [], timeout)

        # Map socket objects back to names
        sock_to_name = {v: k for k, v in sockets.items()}

        for sock in readable:
            name = sock_to_name.get(sock, "unknown")
            try:
                data, (addr, port) = sock.recvfrom(65536)
            except BlockingIOError:
                continue
            except Exception as e:
                logger.warning("Error receiving from %s: %s", name, e)
                continue

            self._handle_packet(data, addr, port, name)

        # Check lease expiry
        expired = self._participant_db.remove_expired()
        for p in expired:
            logger.info("Participant expired: %s", p.guid_prefix)
            for cb in self._on_participant_lost:
                cb(p)

    def _handle_packet(self, data: bytes, addr: str, port: int, socket_name: str) -> None:
        """Process a received RTPS packet."""
        if len(data) < 20:
            return

        if socket_name == "spdp_multicast":
            self._handle_spdp_packet(data, addr, port)
        elif socket_name == "metatraffic_unicast":
            self._handle_metatraffic_packet(data, addr, port)
        elif socket_name == "user_unicast":
            self._handle_user_packet(data, addr, port)

    def _on_new_participant(self, pd: DiscoveredParticipant) -> None:
        """Called when SPDP discovers a new participant. Triggers SEDP."""
        self._sedp.on_participant_discovered(pd)

        # Send SEDP announcements to the new participant
        if pd.metatraffic_unicast_locators:
            messages = self._sedp.build_announcement_messages(
                pd.guid_prefix, pd.metatraffic_unicast_locators
            )
            logger.info("Sending %d SEDP messages to %s", len(messages),
                       [(m[1], m[2]) for m in messages])
            for msg_bytes, addr, port in messages:
                self._transport.send_unicast(msg_bytes, addr, port)

    def _handle_spdp_packet(self, data: bytes, addr: str, port: int) -> None:
        """Handle SPDP multicast packet."""
        participant = SPDPReader.parse_announcement(data)
        if participant is None:
            return

        # Skip our own announcements
        if participant.guid_prefix == self.guid_prefix:
            return

        is_new = self._participant_db.update(participant)
        if is_new:
            logger.info(
                "Discovered participant: %s from %s:%d",
                participant.guid_prefix, addr, port,
            )
            for cb in self._on_participant_discovered:
                cb(participant)

    def _handle_metatraffic_packet(self, data: bytes, addr: str, port: int) -> None:
        """Handle metatraffic unicast packet (SEDP, etc.)."""
        try:
            msg = RtpsMessageParser.parse(data)
        except ValueError:
            return

        for sm in msg.submessages:
            if isinstance(sm, DataSubmessage):
                writer_id = sm.writer_id.value
                handlers = self._message_handlers.get(writer_id, [])
                for handler in handlers:
                    handler(sm, msg.header.guid_prefix, addr)
            elif isinstance(sm, HeartbeatSubmessage):
                # Route heartbeats to SEDP for ACKNACK response
                responses = self._sedp.handle_heartbeat(sm, msg.header.guid_prefix)
                if responses:
                    # Find the participant to get their metatraffic address
                    pd = self._participant_db.get(msg.header.guid_prefix)
                    if pd and pd.metatraffic_unicast_locators:
                        loc = pd.metatraffic_unicast_locators[0]
                        dest_addr = loc.ipv4_str or addr
                        dest_port = loc.port
                    else:
                        dest_addr = addr
                        dest_port = port
                    for resp_bytes in responses:
                        self._transport.send_unicast(resp_bytes, dest_addr, dest_port)

    def _handle_user_packet(self, data: bytes, addr: str, port: int) -> None:
        """Handle user data unicast packet."""
        try:
            msg = RtpsMessageParser.parse(data)
        except ValueError:
            return

        for sm in msg.submessages:
            if isinstance(sm, DataSubmessage):
                # Try registered handlers first
                writer_id = sm.writer_id.value
                handlers = self._message_handlers.get(writer_id, [])
                for handler in handlers:
                    handler(sm, msg.header.guid_prefix, addr)

                # Route to matching DataReaders based on writer entity
                # Since remote writers send to ENTITYID_UNKNOWN as reader,
                # we match by looking up the remote writer in endpoint_db
                source_guid_prefix = msg.header.guid_prefix
                writer_guid_bytes = (source_guid_prefix.value + sm.writer_id.value)
                remote_writer = self._endpoint_db.remote_writers.get(writer_guid_bytes)
                if remote_writer:
                    for reader in self._readers:
                        if (reader.topic.name == remote_writer.topic_name
                                and reader.topic.type_name == remote_writer.type_name):
                            reader._receive(sm, source_guid_prefix, addr)
                else:
                    # Fallback: deliver to all readers (for best-effort / unknown writers)
                    for reader in self._readers:
                        reader._receive(sm, source_guid_prefix, addr)

    def spin(self, duration: float | None = None) -> None:
        """Run the event loop for the specified duration (or indefinitely).

        Args:
            duration: Seconds to run, or None for indefinitely.
        """
        start = time.time()
        while self._running:
            if duration is not None and (time.time() - start) >= duration:
                break
            self.spin_once(timeout=0.1)
