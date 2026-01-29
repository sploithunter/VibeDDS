"""QoS policies and RxO (Requested/Offered) compatibility matching."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

from vibedds.cdr import CdrSerializer
from vibedds.types import Duration


class ReliabilityKind(IntEnum):
    BEST_EFFORT = 1
    RELIABLE = 2


class DurabilityKind(IntEnum):
    VOLATILE = 0
    TRANSIENT_LOCAL = 1
    TRANSIENT = 2
    PERSISTENT = 3


class OwnershipKind(IntEnum):
    SHARED = 0
    EXCLUSIVE = 1


class LivelinessKind(IntEnum):
    AUTOMATIC = 0
    MANUAL_BY_PARTICIPANT = 1
    MANUAL_BY_TOPIC = 2


class DestinationOrderKind(IntEnum):
    BY_RECEPTION_TIMESTAMP = 0
    BY_SOURCE_TIMESTAMP = 1


class HistoryKind(IntEnum):
    KEEP_LAST = 0
    KEEP_ALL = 1


class DataRepresentationId(IntEnum):
    XCDR1 = 0
    XML = 1
    XCDR2 = 2


class TypeConsistencyKind(IntEnum):
    DISALLOW_TYPE_COERCION = 0
    ALLOW_TYPE_COERCION = 1


@dataclass
class QosPolicy:
    """Aggregated QoS settings for an endpoint."""
    reliability: ReliabilityKind = ReliabilityKind.BEST_EFFORT
    reliability_max_blocking_time: Duration = Duration.ZERO
    durability: DurabilityKind = DurabilityKind.VOLATILE
    ownership: OwnershipKind = OwnershipKind.SHARED
    liveliness: LivelinessKind = LivelinessKind.AUTOMATIC
    liveliness_lease_duration: Duration = Duration.INFINITE
    deadline_period: Duration = Duration.INFINITE
    destination_order: DestinationOrderKind = DestinationOrderKind.BY_RECEPTION_TIMESTAMP
    history: HistoryKind = HistoryKind.KEEP_LAST
    history_depth: int = 1
    partition: list[str] | None = None


# Default QoS for builtin endpoints (SEDP)
BUILTIN_ENDPOINT_QOS = QosPolicy(
    reliability=ReliabilityKind.RELIABLE,
    durability=DurabilityKind.TRANSIENT_LOCAL,
    history=HistoryKind.KEEP_LAST,
    history_depth=1,
)


def qos_compatible(offered: QosPolicy, requested: QosPolicy) -> bool:
    """Check if offered QoS is compatible with requested QoS (RxO rules).

    Returns True if the writer's offered QoS satisfies the reader's requested QoS.
    """
    # Reliability: offered must be >= requested
    if offered.reliability < requested.reliability:
        return False

    # Durability: offered must be >= requested
    if offered.durability < requested.durability:
        return False

    # Ownership: must match exactly
    if offered.ownership != requested.ownership:
        return False

    # Liveliness: offered must be >= requested (stricter is higher)
    if offered.liveliness < requested.liveliness:
        return False

    # Destination order: offered must be >= requested
    if offered.destination_order < requested.destination_order:
        return False

    # Deadline: offered period must be <= requested period
    # (shorter deadline satisfies longer requirement)
    # We skip this for now since Duration comparison isn't trivial

    # Partition: if both specify partitions, they must have at least one in common
    # Empty / None means default partition which matches default partition
    if offered.partition is not None and requested.partition is not None:
        if not set(offered.partition) & set(requested.partition):
            return False

    return True


def serialize_reliability_qos(qos: QosPolicy, endian: str = "<") -> bytes:
    """Serialize reliability QoS for SEDP parameter list."""
    # kind(u32) + max_blocking_time(Duration: i32+u32) = 12 bytes
    kind = int(qos.reliability)
    return struct.pack(
        endian + "IiI",
        kind,
        qos.reliability_max_blocking_time.seconds,
        qos.reliability_max_blocking_time.fraction,
    )


def deserialize_reliability_qos(data: bytes, endian: str = "<") -> tuple[ReliabilityKind, Duration]:
    """Deserialize reliability QoS from parameter value."""
    kind, secs, frac = struct.unpack(endian + "IiI", data[:12])
    return ReliabilityKind(kind), Duration(seconds=secs, fraction=frac)


def serialize_durability_qos(qos: QosPolicy, endian: str = "<") -> bytes:
    """Serialize durability QoS for SEDP parameter list."""
    return struct.pack(endian + "I", int(qos.durability))


def deserialize_durability_qos(data: bytes, endian: str = "<") -> DurabilityKind:
    """Deserialize durability QoS from parameter value."""
    kind = struct.unpack(endian + "I", data[:4])[0]
    return DurabilityKind(kind)


def serialize_partition_qos(qos: QosPolicy, endian: str = "<") -> bytes:
    """Serialize PartitionQosPolicy (sequence<string>) in XCDR1."""
    ser = CdrSerializer(endian)
    ser.set_origin()
    if qos.partition:
        ser.write_uint32(len(qos.partition))
        for part in qos.partition:
            ser.write_string(part)
    else:
        ser.write_uint32(0)
    return ser.getvalue()


def serialize_data_representation_qos(
    representations: list[DataRepresentationId],
    endian: str = "<",
) -> bytes:
    """Serialize DataRepresentationQosPolicy (sequence<short>) in XCDR1."""
    ser = CdrSerializer(endian)
    ser.set_origin()
    ser.write_sequence(
        representations,
        lambda s, rep: s.write_int16(int(rep)),
    )
    return ser.getvalue()


RTI_DATA_REPRESENTATION_DEFAULT = bytes.fromhex(
    "010000000000000007000000"
)
RTI_TYPE_CONSISTENCY_DEFAULT = bytes.fromhex(
    "0100010100000000"
)


def serialize_data_representation_qos_rti(
    representations: list[DataRepresentationId],
    endian: str = "<",
    tail: int | None = None,
) -> bytes:
    """Serialize DataRepresentationQosPolicy using RTI-observed layout.

    RTI observed a 12-byte payload for HelloWorld:
      01 00 00 00 00 00 00 00 07 00 00 00
    The exact semantics are unclear, so we allow an optional tail value.
    """
    if representations == [DataRepresentationId.XCDR1] and tail is None:
        return RTI_DATA_REPRESENTATION_DEFAULT
    count = len(representations)
    data = bytearray()
    data.extend(struct.pack(endian + "I", count))
    for rep in representations:
        data.extend(struct.pack(endian + "I", int(rep)))
    if tail is not None:
        data.extend(struct.pack(endian + "I", tail))
    return bytes(data)


def serialize_type_consistency_enforcement_qos(
    kind: TypeConsistencyKind = TypeConsistencyKind.DISALLOW_TYPE_COERCION,
    ignore_sequence_bounds: bool = False,
    ignore_string_bounds: bool = False,
    ignore_member_names: bool = False,
    prevent_type_widening: bool = False,
    force_type_validation: bool = False,
    endian: str = "<",
) -> bytes:
    """Serialize TypeConsistencyEnforcementQosPolicy in XCDR1."""
    ser = CdrSerializer(endian)
    ser.set_origin()
    ser.write_int32(int(kind))
    ser.write_bool(ignore_sequence_bounds)
    ser.write_bool(ignore_string_bounds)
    ser.write_bool(ignore_member_names)
    ser.write_bool(prevent_type_widening)
    ser.write_bool(force_type_validation)
    return ser.getvalue()


def serialize_type_consistency_enforcement_qos_compact(
    kind: TypeConsistencyKind = TypeConsistencyKind.DISALLOW_TYPE_COERCION,
    ignore_sequence_bounds: bool = False,
    ignore_string_bounds: bool = False,
    ignore_member_names: bool = False,
    prevent_type_widening: bool = False,
    force_type_validation: bool = False,
    mask: int | None = None,
    endian: str = "<",
) -> bytes:
    """Serialize TypeConsistencyEnforcementQosPolicy in a compact RTI-style form.

    Encodes kind (u32) + flags mask (u32). This is not standard XCDR1 but
    matches the 8-byte length observed in RTI captures.
    """
    if mask is None:
        mask = 0
        if ignore_sequence_bounds:
            mask |= 1 << 0
        if ignore_string_bounds:
            mask |= 1 << 1
        if ignore_member_names:
            mask |= 1 << 2
        if prevent_type_widening:
            mask |= 1 << 3
        if force_type_validation:
            mask |= 1 << 4
    return struct.pack(endian + "II", int(kind), mask)
