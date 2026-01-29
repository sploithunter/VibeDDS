"""Reliability state machines for RTPS.

ReliableWriter: maintains history cache, tracks per-reader acked state,
sends HEARTBEAT, processes ACKNACK, retransmits.

ReliableReader: tracks per-writer received state, responds to HEARTBEAT
with ACKNACK, detects gaps.
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import Callable

from vibedds.types import (
    GuidPrefix, EntityId, Guid, SequenceNumber, SequenceNumberSet,
)
from vibedds.messages import (
    DataSubmessage, HeartbeatSubmessage, AckNackSubmessage,
)

logger = logging.getLogger(__name__)


@dataclass
class CacheChange:
    """A single entry in the writer's history cache."""
    sequence_number: SequenceNumber
    serialized_data: bytes
    timestamp: float = field(default_factory=time.time)


@dataclass
class ReaderProxy:
    """Tracks state for a matched remote reader (writer side)."""
    remote_reader_guid: Guid
    highest_acked_sn: SequenceNumber = SequenceNumber.ZERO
    requested_changes: list[SequenceNumber] = field(default_factory=list)


@dataclass
class WriterProxy:
    """Tracks state for a matched remote writer (reader side)."""
    remote_writer_guid: Guid
    highest_received_sn: SequenceNumber = SequenceNumber.ZERO
    received_sns: set[int] = field(default_factory=set)  # set of SN values


class ReliableWriter:
    """Stateful reliable writer with history cache and per-reader proxies.

    Maintains a history of CacheChange entries and tracks which readers
    have acknowledged which sequence numbers.
    """

    def __init__(
        self,
        guid: Guid,
        heartbeat_period: float = 1.0,
        max_history: int = 100,
    ):
        self.guid = guid
        self.heartbeat_period = heartbeat_period
        self.max_history = max_history

        self._next_sn = SequenceNumber.from_value(1)
        self._history: list[CacheChange] = []
        self._reader_proxies: dict[bytes, ReaderProxy] = {}  # guid bytes -> proxy
        self._heartbeat_count = 0
        self._last_heartbeat_time = 0.0

    @property
    def next_sequence_number(self) -> SequenceNumber:
        return self._next_sn

    @property
    def first_available_sn(self) -> SequenceNumber:
        if self._history:
            return self._history[0].sequence_number
        return self._next_sn

    @property
    def last_available_sn(self) -> SequenceNumber:
        if self._history:
            return self._history[-1].sequence_number
        return SequenceNumber.ZERO

    def add_reader_proxy(self, reader_guid: Guid) -> None:
        key = reader_guid.to_bytes()
        if key not in self._reader_proxies:
            self._reader_proxies[key] = ReaderProxy(remote_reader_guid=reader_guid)
            logger.debug("Added reader proxy: %s", reader_guid)

    def remove_reader_proxy(self, reader_guid: Guid) -> None:
        key = reader_guid.to_bytes()
        self._reader_proxies.pop(key, None)

    def new_change(self, data: bytes) -> CacheChange:
        """Add a new cache change and return it."""
        change = CacheChange(
            sequence_number=self._next_sn,
            serialized_data=data,
        )
        self._history.append(change)
        self._next_sn = self._next_sn + 1

        # Trim history
        while len(self._history) > self.max_history:
            self._history.pop(0)

        return change

    def get_change(self, sn: SequenceNumber) -> CacheChange | None:
        for change in self._history:
            if change.sequence_number == sn:
                return change
        return None

    def should_send_heartbeat(self) -> bool:
        now = time.time()
        return (now - self._last_heartbeat_time) >= self.heartbeat_period

    def next_heartbeat_count(self) -> int:
        self._heartbeat_count += 1
        self._last_heartbeat_time = time.time()
        return self._heartbeat_count

    def process_acknack(self, acknack: AckNackSubmessage) -> list[CacheChange]:
        """Process an ACKNACK, return changes that need retransmission."""
        # Find reader proxy
        reader_guid_key = None
        for key, proxy in self._reader_proxies.items():
            if proxy.remote_reader_guid.entity_id == acknack.reader_id:
                reader_guid_key = key
                break

        if reader_guid_key is None:
            # Unknown reader — try to find by entity ID alone
            pass

        # Collect missing sequence numbers from bitmap
        missing = acknack.reader_sn_state.missing_sequence_numbers()
        retransmits = []
        for sn in missing:
            change = self.get_change(sn)
            if change is not None:
                retransmits.append(change)

        return retransmits

    @property
    def reader_proxies(self) -> dict[bytes, ReaderProxy]:
        return self._reader_proxies


class ReliableReader:
    """Stateful reliable reader that tracks received sequence numbers
    and generates ACKNACKs in response to HEARTBEATs.
    """

    def __init__(self, guid: Guid):
        self.guid = guid
        self._writer_proxies: dict[bytes, WriterProxy] = {}
        self._acknack_count = 0

    def add_writer_proxy(self, writer_guid: Guid) -> None:
        key = writer_guid.to_bytes()
        if key not in self._writer_proxies:
            self._writer_proxies[key] = WriterProxy(remote_writer_guid=writer_guid)
            logger.debug("Added writer proxy: %s", writer_guid)

    def remove_writer_proxy(self, writer_guid: Guid) -> None:
        key = writer_guid.to_bytes()
        self._writer_proxies.pop(key, None)

    def record_received(self, writer_guid: Guid, sn: SequenceNumber) -> None:
        """Record that we received a sample with this sequence number."""
        key = writer_guid.to_bytes()
        proxy = self._writer_proxies.get(key)
        if proxy is None:
            return
        proxy.received_sns.add(sn.value)
        if sn > proxy.highest_received_sn:
            proxy.highest_received_sn = sn

    def process_heartbeat(
        self, heartbeat: HeartbeatSubmessage, writer_guid_prefix: GuidPrefix
    ) -> SequenceNumberSet | None:
        """Process a heartbeat and return a SequenceNumberSet for ACKNACK if needed.

        Returns None if no ACKNACK is needed (all caught up).
        """
        writer_guid = Guid(prefix=writer_guid_prefix, entity_id=heartbeat.writer_id)
        key = writer_guid.to_bytes()
        proxy = self._writer_proxies.get(key)
        if proxy is None:
            # Auto-create proxy for builtin endpoints
            proxy = WriterProxy(remote_writer_guid=writer_guid)
            self._writer_proxies[key] = proxy

        first_sn = heartbeat.first_sn.value
        last_sn = heartbeat.last_sn.value

        if last_sn < first_sn:
            # Empty range — nothing to request
            return None

        # Find missing sequence numbers
        missing = []
        for sn_val in range(first_sn, last_sn + 1):
            if sn_val not in proxy.received_sns:
                missing.append(sn_val)

        if not missing:
            # All caught up — still send ACKNACK to confirm
            base = SequenceNumber.from_value(last_sn + 1)
            return SequenceNumberSet(base=base, num_bits=0, bitmap=())

        # Build bitmap of missing SNs
        base_val = missing[0]
        max_offset = missing[-1] - base_val
        num_bits = max_offset + 1
        if num_bits > 256:
            num_bits = 256
        num_words = (num_bits + 31) // 32
        bitmap = [0] * num_words
        for sn_val in missing:
            offset = sn_val - base_val
            if offset < num_bits:
                word_idx = offset // 32
                bit_idx = 31 - (offset % 32)
                bitmap[word_idx] |= (1 << bit_idx)

        return SequenceNumberSet(
            base=SequenceNumber.from_value(base_val),
            num_bits=num_bits,
            bitmap=tuple(bitmap),
        )

    def next_acknack_count(self) -> int:
        self._acknack_count += 1
        return self._acknack_count

    @property
    def writer_proxies(self) -> dict[bytes, WriterProxy]:
        return self._writer_proxies
