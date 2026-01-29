"""RTPS submessage dataclasses.

Each submessage type corresponds to an RTPS submessage ID.
The RtpsMessage wraps a header + list of submessages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from vibedds.types import (
    GuidPrefix, EntityId, SequenceNumber, SequenceNumberSet,
    Timestamp, ProtocolVersion, VendorId,
)


@dataclass(frozen=True)
class RtpsHeader:
    """RTPS message header (20 bytes on wire)."""
    version: ProtocolVersion
    vendor_id: VendorId
    guid_prefix: GuidPrefix


@dataclass(frozen=True)
class DataSubmessage:
    """DATA submessage (ID=0x15).

    Carries serialized data or key for a specific writer sequence number.
    """
    flags: int  # E, Q, D, K bits
    reader_id: EntityId
    writer_id: EntityId
    writer_sn: SequenceNumber
    inline_qos: bytes | None = None  # raw parameter list bytes if Q flag set
    serialized_payload: bytes | None = None  # if D or K flag set


@dataclass(frozen=True)
class HeartbeatSubmessage:
    """HEARTBEAT submessage (ID=0x07).

    Writer announces available sequence number range.
    """
    flags: int  # E, F, L bits
    reader_id: EntityId
    writer_id: EntityId
    first_sn: SequenceNumber
    last_sn: SequenceNumber
    count: int  # u32


@dataclass(frozen=True)
class AckNackSubmessage:
    """ACKNACK submessage (ID=0x06).

    Reader acknowledges received sequences and requests missing ones.
    """
    flags: int  # E, F bits
    reader_id: EntityId
    writer_id: EntityId
    reader_sn_state: SequenceNumberSet
    count: int  # u32


@dataclass(frozen=True)
class GapSubmessage:
    """GAP submessage (ID=0x08).

    Writer tells reader that certain sequence numbers are irrelevant.
    """
    flags: int
    reader_id: EntityId
    writer_id: EntityId
    gap_start: SequenceNumber
    gap_list: SequenceNumberSet


@dataclass(frozen=True)
class InfoTimestampSubmessage:
    """INFO_TS submessage (ID=0x09).

    Sets timestamp for subsequent submessages, or invalidates it.
    """
    flags: int
    timestamp: Timestamp | None  # None if invalidate flag set


@dataclass(frozen=True)
class InfoDestinationSubmessage:
    """INFO_DST submessage (ID=0x0E).

    Sets the destination participant for subsequent submessages.
    """
    flags: int
    guid_prefix: GuidPrefix


@dataclass(frozen=True)
class InfoSourceSubmessage:
    """INFO_SRC submessage (ID=0x0C)."""
    flags: int
    protocol_version: ProtocolVersion
    vendor_id: VendorId
    guid_prefix: GuidPrefix


@dataclass(frozen=True)
class PadSubmessage:
    """PAD submessage (ID=0x01). Padding, no meaningful content."""
    flags: int


# Union type for all submessages
Submessage = (
    DataSubmessage
    | HeartbeatSubmessage
    | AckNackSubmessage
    | GapSubmessage
    | InfoTimestampSubmessage
    | InfoDestinationSubmessage
    | InfoSourceSubmessage
    | PadSubmessage
)


@dataclass
class RtpsMessage:
    """Complete RTPS message: header + list of submessages."""
    header: RtpsHeader
    submessages: list[Submessage] = field(default_factory=list)
