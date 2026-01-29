"""DataWriter and DataReader user endpoint wrappers.

These wrap the underlying RTPS writer/reader mechanics and provide
a simple API for publishing and subscribing to data.
"""

from __future__ import annotations

import struct
import time
import logging
from dataclasses import dataclass, field
from typing import Callable

from vibedds.constants import (
    ENTITY_KIND_USER_WRITER_NO_KEY,
    ENTITY_KIND_USER_WRITER_WITH_KEY,
    ENTITY_KIND_USER_READER_NO_KEY,
    ENTITY_KIND_USER_READER_WITH_KEY,
    ENTITYID_UNKNOWN,
)
from vibedds.types import (
    GuidPrefix, EntityId, Guid, SequenceNumber, Timestamp, Locator,
)
from vibedds.wire import RtpsMessageBuilder
from vibedds.messages import DataSubmessage
from vibedds.qos import QosPolicy, ReliabilityKind
from vibedds.topic import Topic
from vibedds.reliability import ReliableWriter
from vibedds.sedp import LocalEndpoint, EndpointDatabase

logger = logging.getLogger(__name__)


class EntityIdAllocator:
    """Allocates unique user entity IDs."""

    def __init__(self):
        self._next_key = 1

    def allocate_writer(self, with_key: bool = False) -> EntityId:
        key = self._next_key
        self._next_key += 1
        kind = ENTITY_KIND_USER_WRITER_WITH_KEY if with_key else ENTITY_KIND_USER_WRITER_NO_KEY
        return EntityId(struct.pack(">I", (key << 8) | kind)[-4:])

    def allocate_reader(self, with_key: bool = False) -> EntityId:
        key = self._next_key
        self._next_key += 1
        kind = ENTITY_KIND_USER_READER_WITH_KEY if with_key else ENTITY_KIND_USER_READER_NO_KEY
        return EntityId(struct.pack(">I", (key << 8) | kind)[-4:])


class DataWriter:
    """User-facing DataWriter that publishes data on a topic.

    Wraps RTPS message building and transport sending.
    """

    def __init__(
        self,
        guid: Guid,
        topic: Topic,
        qos: QosPolicy,
        transport,  # UdpTransport
        guid_prefix: GuidPrefix,
        endpoint_db: EndpointDatabase | None = None,
    ):
        self.guid = guid
        self.topic = topic
        self.qos = qos
        self._transport = transport
        self._guid_prefix = guid_prefix
        self._endpoint_db = endpoint_db
        self._sequence_number = SequenceNumber.from_value(0)
        self._reliable_writer: ReliableWriter | None = None

        if qos.reliability == ReliabilityKind.RELIABLE:
            self._reliable_writer = ReliableWriter(guid=guid)

    @property
    def entity_id(self) -> EntityId:
        return self.guid.entity_id

    def write(self, serialized_payload: bytes) -> None:
        """Publish a serialized sample.

        The payload should include the CDR encapsulation header.
        """
        self._sequence_number = self._sequence_number + 1

        if self._reliable_writer:
            self._reliable_writer.new_change(serialized_payload)

        # Build RTPS message
        builder = RtpsMessageBuilder(self._guid_prefix)
        builder.add_info_ts(Timestamp.from_seconds(time.time()))
        builder.add_data(
            reader_id=EntityId(ENTITYID_UNKNOWN),
            writer_id=self.guid.entity_id,
            writer_sn=self._sequence_number,
            serialized_payload=serialized_payload,
        )
        msg_bytes = builder.build()

        # Send to all matched remote readers
        if self._endpoint_db:
            local_ep = self._endpoint_db.local_writers.get(self.guid.to_bytes())
            if local_ep:
                remote_readers = self._endpoint_db.find_matching_remote_readers(local_ep)
                for reader in remote_readers:
                    for loc in reader.unicast_locators:
                        addr = loc.ipv4_str or "127.0.0.1"
                        self._transport.send_unicast(msg_bytes, addr, loc.port)
                        logger.debug(
                            "Sent DATA to %s:%d (SN=%d)",
                            addr, loc.port, self._sequence_number.value,
                        )

        # Also send on user multicast (for discovery by rtiddsspy etc.)
        # rtiddsspy listens on user unicast ports it discovers via SEDP
        # For best-effort, we can also multicast
        self._transport.send_multicast(msg_bytes, self._transport.user_unicast_port)


class DataReader:
    """User-facing DataReader that receives data on a topic.

    Incoming DATA submessages are routed here by entity ID.
    """

    def __init__(
        self,
        guid: Guid,
        topic: Topic,
        qos: QosPolicy,
    ):
        self.guid = guid
        self.topic = topic
        self.qos = qos
        self._buffer: list[bytes] = []
        self._callbacks: list[Callable[[bytes], None]] = []
        self._max_buffer = 100

    @property
    def entity_id(self) -> EntityId:
        return self.guid.entity_id

    def on_data(self, callback: Callable[[bytes], None]) -> None:
        """Register a callback for received data."""
        self._callbacks.append(callback)

    def _receive(self, sm: DataSubmessage, source_prefix: GuidPrefix, source_addr: str) -> None:
        """Called by the participant's message router when data arrives."""
        if sm.serialized_payload is None:
            return

        payload = sm.serialized_payload
        self._buffer.append(payload)
        if len(self._buffer) > self._max_buffer:
            self._buffer.pop(0)

        for cb in self._callbacks:
            cb(payload)

    def take(self) -> list[bytes]:
        """Take all buffered samples, clearing the buffer."""
        samples = list(self._buffer)
        self._buffer.clear()
        return samples

    def take_one(self) -> bytes | None:
        """Take one sample if available."""
        if self._buffer:
            return self._buffer.pop(0)
        return None
