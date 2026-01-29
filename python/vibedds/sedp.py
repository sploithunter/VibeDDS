"""Simple Endpoint Discovery Protocol (SEDP).

After SPDP discovers a remote participant, SEDP exchanges endpoint
information (topic, type, QoS) over reliable unicast. This enables
matching of DataWriters and DataReaders across participants.
"""

from __future__ import annotations

import os
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
    PID_PARTICIPANT_GUID, PID_GROUP_ENTITY_ID, PID_EXPECTS_INLINE_QOS, PID_TYPE_OBJECT,
    PID_PROTOCOL_VERSION, PID_VENDORID,
    PID_DATA_REPRESENTATION, PID_TYPE_CONSISTENCY_ENFORCEMENT,
    PID_TYPE_INFORMATION,
    PID_RTI_VENDOR_0013, PID_RTI_VENDOR_0018, PID_RTI_VENDOR_0060,
    PID_RTI_VENDOR_8000, PID_RTI_VENDOR_8002, PID_RTI_VENDOR_8004,
    PID_RTI_VENDOR_8009, PID_RTI_VENDOR_8015,
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
    DataRepresentationId, TypeConsistencyKind,
    serialize_reliability_qos, serialize_durability_qos,
    serialize_data_representation_qos, serialize_data_representation_qos_rti,
    serialize_partition_qos,
    serialize_type_consistency_enforcement_qos,
    serialize_type_consistency_enforcement_qos_compact,
    RTI_DATA_REPRESENTATION_DEFAULT, RTI_TYPE_CONSISTENCY_DEFAULT,
    deserialize_reliability_qos, deserialize_durability_qos,
    qos_compatible,
)
from vibedds.reliability import ReliableWriter, ReliableReader, CacheChange
from vibedds.spdp import DiscoveredParticipant

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool | None = None) -> bool | None:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _env_str(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def _parse_hex_bytes(value: str) -> bytes:
    cleaned = value.strip().lower()
    if cleaned.startswith("0x"):
        cleaned = cleaned[2:]
    cleaned = "".join(ch for ch in cleaned if ch in "0123456789abcdef")
    if len(cleaned) % 2 == 1:
        cleaned = "0" + cleaned
    return bytes.fromhex(cleaned)


def _parse_data_rep_list(value: str) -> list[DataRepresentationId]:
    parts = [p.strip().lower() for p in value.split(",") if p.strip()]
    reps: list[DataRepresentationId] = []
    for part in parts:
        if part in ("xcdr1", "xcdr", "xcdr1_only"):
            reps.append(DataRepresentationId.XCDR1)
        elif part in ("xcdr2", "xcdr2_only"):
            reps.append(DataRepresentationId.XCDR2)
        elif part in ("xml",):
            reps.append(DataRepresentationId.XML)
    return reps


@dataclass
class SedpInteropOptions:
    """SEDP interop toggles for discovery payloads."""
    profile: str = "full"
    include_info_dst: bool = True
    include_participant_guid: bool = True
    include_protocol_vendor: bool = True
    include_extended_qos: bool = True
    include_partition: bool = True
    include_unicast_locator: bool = True
    locator_pid: str = "endpoint"  # endpoint|default|both
    include_reliability: bool = True
    include_durability: bool = True
    include_data_representation: bool = True
    data_representation: list[DataRepresentationId] = field(
        default_factory=lambda: [DataRepresentationId.XCDR1]
    )
    data_representation_writers: bool = True
    data_representation_readers: bool = True
    xtypes_format: str = "standard"  # standard|rti
    data_representation_raw: bytes | None = None
    data_representation_tail: int | None = None
    include_type_consistency: bool = True
    type_consistency_kind: TypeConsistencyKind = TypeConsistencyKind.DISALLOW_TYPE_COERCION
    type_consistency_raw: bytes | None = None
    type_consistency_mask: int | None = None
    include_type_information: bool = True
    include_type_object: bool = False
    group_entity_id: int | None = None
    include_rti_vendor_pids: bool = False
    include_rti_pid_8002_guid: bool = False
    rti_pid_8000: bytes | None = None
    rti_pid_8004: bytes | None = None
    rti_pid_8009: bytes | None = None
    rti_pid_8015: bytes | None = None
    rti_pid_0013: bytes | None = None
    rti_pid_0018: bytes | None = None
    rti_pid_0060: bytes | None = None

    @classmethod
    def from_env(cls) -> "SedpInteropOptions":
        opts = cls()
        profile = _env_str("VIBEDDS_SEDP_PROFILE")
        if profile:
            profile = profile.lower()
            opts.profile = profile
            if profile == "minimal":
                opts.include_participant_guid = False
                opts.include_protocol_vendor = False
                opts.include_extended_qos = False
                opts.include_partition = False
                opts.include_data_representation = False
                opts.include_type_consistency = False
                opts.include_type_information = False
                opts.locator_pid = "default"
            elif profile == "rti":
                opts.include_participant_guid = True
                opts.include_protocol_vendor = True
                opts.include_extended_qos = True
                opts.include_partition = True
                opts.include_unicast_locator = True
                opts.locator_pid = "endpoint"
                opts.include_data_representation = True
                opts.data_representation = [DataRepresentationId.XCDR1]
                opts.include_type_consistency = True
                opts.type_consistency_kind = TypeConsistencyKind.DISALLOW_TYPE_COERCION
                opts.include_type_information = True
                opts.include_type_object = True
                opts.xtypes_format = "rti"
                opts.data_representation_raw = RTI_DATA_REPRESENTATION_DEFAULT
                opts.type_consistency_raw = RTI_TYPE_CONSISTENCY_DEFAULT
                opts.include_rti_vendor_pids = True
                opts.include_rti_pid_8002_guid = True
                opts.rti_pid_8000 = bytes.fromhex("07030005")
                opts.rti_pid_8004 = None
                opts.rti_pid_8009 = bytes.fromhex("00000000")
                opts.rti_pid_8015 = bytes.fromhex("0100000000000000")
                opts.rti_pid_0013 = bytes.fromhex("ffffffff")
                opts.rti_pid_0018 = bytes.fromhex("ffffffff")
                opts.rti_pid_0060 = bytes.fromhex("08010000")
            elif profile == "rti_strict":
                opts.include_participant_guid = False
                opts.include_protocol_vendor = True
                opts.include_extended_qos = False
                opts.include_partition = False
                opts.include_unicast_locator = False
                opts.locator_pid = "endpoint"
                opts.include_reliability = False
                opts.include_durability = False
                opts.include_data_representation = True
                opts.data_representation = [DataRepresentationId.XCDR1]
                opts.data_representation_writers = False
                opts.data_representation_readers = True
                opts.include_type_consistency = True
                opts.type_consistency_kind = TypeConsistencyKind.DISALLOW_TYPE_COERCION
                opts.include_type_information = False
                opts.include_type_object = True
                opts.xtypes_format = "rti"
                opts.data_representation_raw = RTI_DATA_REPRESENTATION_DEFAULT
                opts.type_consistency_raw = RTI_TYPE_CONSISTENCY_DEFAULT
                opts.include_rti_vendor_pids = True
                opts.include_rti_pid_8002_guid = True
                opts.rti_pid_8000 = bytes.fromhex("07030005")
                opts.rti_pid_8004 = None
                opts.rti_pid_8009 = bytes.fromhex("00000000")
                opts.rti_pid_8015 = bytes.fromhex("0100000000000000")
                opts.rti_pid_0013 = bytes.fromhex("ffffffff")
                opts.rti_pid_0018 = bytes.fromhex("ffffffff")
                opts.rti_pid_0060 = bytes.fromhex("08010000")

        xtypes = _env_bool("VIBEDDS_SEDP_XTYPES")
        if xtypes is not None:
            opts.include_data_representation = xtypes
            opts.include_type_consistency = xtypes
            opts.include_type_information = xtypes

        data_rep = _env_str("VIBEDDS_SEDP_DATA_REP")
        if data_rep:
            reps: list[DataRepresentationId] = []
            if data_rep.lower() in ("none", "off", "false", "0"):
                opts.include_data_representation = False
                opts.data_representation = []
            else:
                reps = _parse_data_rep_list(data_rep)
            if reps:
                opts.include_data_representation = True
                opts.data_representation = reps

        data_rep_writers = _env_bool("VIBEDDS_SEDP_DATA_REP_WRITERS")
        if data_rep_writers is not None:
            opts.data_representation_writers = data_rep_writers
        data_rep_readers = _env_bool("VIBEDDS_SEDP_DATA_REP_READERS")
        if data_rep_readers is not None:
            opts.data_representation_readers = data_rep_readers

        xtypes_format = _env_str("VIBEDDS_SEDP_XTYPES_FORMAT")
        if xtypes_format:
            fmt = xtypes_format.lower()
            if fmt in ("standard", "rti", "raw"):
                opts.xtypes_format = fmt

        data_rep_raw = _env_str("VIBEDDS_SEDP_DATA_REP_RAW")
        if data_rep_raw:
            opts.data_representation_raw = _parse_hex_bytes(data_rep_raw)
            opts.include_data_representation = True

        data_rep_tail = _env_str("VIBEDDS_SEDP_DATA_REP_TAIL")
        if data_rep_tail:
            try:
                opts.data_representation_tail = int(data_rep_tail, 0)
            except ValueError:
                pass

        type_consistency = _env_str("VIBEDDS_SEDP_TYPE_CONSISTENCY")
        if type_consistency:
            tc = type_consistency.lower()
            if tc in ("off", "none", "false", "0"):
                opts.include_type_consistency = False
            elif tc in ("allow", "allow_type_coercion"):
                opts.include_type_consistency = True
                opts.type_consistency_kind = TypeConsistencyKind.ALLOW_TYPE_COERCION
            elif tc in ("disallow", "disallow_type_coercion"):
                opts.include_type_consistency = True
                opts.type_consistency_kind = TypeConsistencyKind.DISALLOW_TYPE_COERCION

        for key, attr in (
            ("VIBEDDS_SEDP_INCLUDE_INFO_DST", "include_info_dst"),
            ("VIBEDDS_SEDP_INCLUDE_PARTICIPANT_GUID", "include_participant_guid"),
            ("VIBEDDS_SEDP_INCLUDE_PROTOCOL_VENDOR", "include_protocol_vendor"),
            ("VIBEDDS_SEDP_INCLUDE_EXTENDED_QOS", "include_extended_qos"),
            ("VIBEDDS_SEDP_INCLUDE_PARTITION", "include_partition"),
            ("VIBEDDS_SEDP_INCLUDE_UNICAST_LOCATOR", "include_unicast_locator"),
            ("VIBEDDS_SEDP_INCLUDE_RELIABILITY", "include_reliability"),
            ("VIBEDDS_SEDP_INCLUDE_DURABILITY", "include_durability"),
            ("VIBEDDS_SEDP_INCLUDE_TYPE_INFORMATION", "include_type_information"),
            ("VIBEDDS_SEDP_INCLUDE_TYPE_OBJECT", "include_type_object"),
            ("VIBEDDS_SEDP_INCLUDE_RTI_VENDOR_PIDS", "include_rti_vendor_pids"),
        ):
            val = _env_bool(key)
            if val is not None:
                setattr(opts, attr, val)

        type_consistency_raw = _env_str("VIBEDDS_SEDP_TYPE_CONSISTENCY_RAW")
        if type_consistency_raw:
            opts.type_consistency_raw = _parse_hex_bytes(type_consistency_raw)
            opts.include_type_consistency = True

        type_consistency_mask = _env_str("VIBEDDS_SEDP_TYPE_CONSISTENCY_MASK")
        if type_consistency_mask:
            try:
                opts.type_consistency_mask = int(type_consistency_mask, 0)
            except ValueError:
                pass

        locator_pid = _env_str("VIBEDDS_SEDP_LOCATOR_PID")
        if locator_pid:
            lp = locator_pid.lower()
            if lp in ("endpoint", "default", "both"):
                opts.locator_pid = lp

        group_entity_id = _env_str("VIBEDDS_SEDP_GROUP_ENTITY_ID")
        if group_entity_id:
            try:
                opts.group_entity_id = int(group_entity_id, 0)
            except ValueError:
                pass

        include_rti_pid_8002 = _env_bool("VIBEDDS_SEDP_INCLUDE_RTI_PID_8002_GUID")
        if include_rti_pid_8002 is not None:
            opts.include_rti_pid_8002_guid = include_rti_pid_8002

        for env_key, attr in (
            ("VIBEDDS_SEDP_RTI_PID_8000", "rti_pid_8000"),
            ("VIBEDDS_SEDP_RTI_PID_8004", "rti_pid_8004"),
            ("VIBEDDS_SEDP_RTI_PID_8009", "rti_pid_8009"),
            ("VIBEDDS_SEDP_RTI_PID_8015", "rti_pid_8015"),
            ("VIBEDDS_SEDP_RTI_PID_0013", "rti_pid_0013"),
            ("VIBEDDS_SEDP_RTI_PID_0018", "rti_pid_0018"),
            ("VIBEDDS_SEDP_RTI_PID_0060", "rti_pid_0060"),
        ):
            raw_val = _env_str(env_key)
            if raw_val:
                setattr(opts, attr, _parse_hex_bytes(raw_val))

        return opts


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
    type_information: bytes | None = None
    type_object: bytes | None = None
    group_entity_id: int | None = None


@dataclass
class LocalEndpoint:
    """Information about a local endpoint to be announced via SEDP."""
    guid: Guid
    topic_name: str
    type_name: str
    qos: QosPolicy
    is_writer: bool
    unicast_locators: list[Locator] = field(default_factory=list)
    type_information: bytes | None = None
    type_object: bytes | None = None


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


def _build_endpoint_data(
    endpoint: LocalEndpoint,
    interop: SedpInteropOptions,
    endian: str = "<",
) -> bytes:
    """Serialize a local endpoint as PL_CDR for SEDP announcement."""
    pl = ParameterListBuilder(endian)

    # PID_ENDPOINT_GUID - required
    pl.add_parameter(PID_ENDPOINT_GUID, endpoint.guid.to_bytes())

    if interop.group_entity_id is not None:
        pl.add_parameter(PID_GROUP_ENTITY_ID, struct.pack(endian + "I", interop.group_entity_id))

    if interop.include_participant_guid:
        # PID_PARTICIPANT_GUID - identifies which participant owns this endpoint
        # Use the GUID prefix + ENTITYID_PARTICIPANT (0xC1)
        participant_entity_id = bytes([0x00, 0x00, 0x01, 0xC1])
        participant_guid = endpoint.guid.prefix.value + participant_entity_id
        pl.add_parameter(PID_PARTICIPANT_GUID, participant_guid)

    if interop.include_protocol_vendor:
        # PID_PROTOCOL_VERSION - RTI includes this
        pl.add_parameter(PID_PROTOCOL_VERSION,
                         bytes([RTPS_VERSION_MAJOR, RTPS_VERSION_MINOR]))

        # PID_VENDORID - RTI includes this
        pl.add_parameter(PID_VENDORID, bytes(VENDOR_ID))

    if interop.include_rti_vendor_pids:
        if interop.rti_pid_8000:
            pl.add_parameter(PID_RTI_VENDOR_8000, interop.rti_pid_8000)
        if interop.include_rti_pid_8002_guid:
            pl.add_parameter(PID_RTI_VENDOR_8002, endpoint.guid.to_bytes())
        if interop.rti_pid_8004:
            pl.add_parameter(PID_RTI_VENDOR_8004, interop.rti_pid_8004)
        if interop.rti_pid_8009:
            pl.add_parameter(PID_RTI_VENDOR_8009, interop.rti_pid_8009)
        if interop.rti_pid_8015:
            pl.add_parameter(PID_RTI_VENDOR_8015, interop.rti_pid_8015)
        if endpoint.is_writer and interop.rti_pid_0013:
            pl.add_parameter(PID_RTI_VENDOR_0013, interop.rti_pid_0013)
        if not endpoint.is_writer and interop.rti_pid_0018:
            pl.add_parameter(PID_RTI_VENDOR_0018, interop.rti_pid_0018)
        if endpoint.is_writer and interop.rti_pid_0060:
            pl.add_parameter(PID_RTI_VENDOR_0060, interop.rti_pid_0060)

    # PID_TOPIC_NAME (CDR string) - required
    ser = CdrSerializer(endian)
    ser.write_string(endpoint.topic_name)
    pl.add_parameter(PID_TOPIC_NAME, ser.getvalue())

    # PID_TYPE_NAME (CDR string) - required
    ser = CdrSerializer(endian)
    ser.write_string(endpoint.type_name)
    pl.add_parameter(PID_TYPE_NAME, ser.getvalue())

    # PID_RELIABILITY - important for QoS matching
    if interop.include_reliability:
        reliability_data = serialize_reliability_qos(endpoint.qos, endian)
        pl.add_parameter(PID_RELIABILITY, reliability_data)

    # PID_DURABILITY - important for QoS matching
    if interop.include_durability:
        durability_data = serialize_durability_qos(endpoint.qos, endian)
        pl.add_parameter(PID_DURABILITY, durability_data)

    if interop.include_extended_qos:
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

    # XTypes PIDs - DATA_REPRESENTATION (0x0073) and TYPE_CONSISTENCY_ENFORCEMENT (0x0074)
    if interop.include_data_representation and (
        interop.data_representation or interop.data_representation_raw
    ):
        if endpoint.is_writer and not interop.data_representation_writers:
            pass
        elif (not endpoint.is_writer) and not interop.data_representation_readers:
            pass
        else:
            if interop.data_representation_raw:
                data_rep = interop.data_representation_raw
            elif interop.xtypes_format == "rti":
                data_rep = serialize_data_representation_qos_rti(
                    interop.data_representation,
                    endian=endian,
                    tail=interop.data_representation_tail,
                )
            else:
                data_rep = serialize_data_representation_qos(
                    interop.data_representation,
                    endian=endian,
                )
            pl.add_parameter(PID_DATA_REPRESENTATION, data_rep)

    if not endpoint.is_writer and interop.include_type_consistency:
        if interop.type_consistency_raw:
            type_consistency = interop.type_consistency_raw
        elif interop.xtypes_format == "rti":
            type_consistency = serialize_type_consistency_enforcement_qos_compact(
                kind=interop.type_consistency_kind,
                mask=interop.type_consistency_mask,
                endian=endian,
            )
        else:
            type_consistency = serialize_type_consistency_enforcement_qos(
                kind=interop.type_consistency_kind,
                endian=endian,
            )
        pl.add_parameter(PID_TYPE_CONSISTENCY_ENFORCEMENT, type_consistency)

    if interop.include_type_information and endpoint.type_information:
        pl.add_parameter(PID_TYPE_INFORMATION, endpoint.type_information)

    if interop.include_type_object and endpoint.type_object:
        pl.add_parameter(PID_TYPE_OBJECT, endpoint.type_object)

    if interop.include_partition:
        # PID_PARTITION - serialize partition list (default is empty list)
        pl.add_parameter(PID_PARTITION, serialize_partition_qos(endpoint.qos, endian))

    # Include endpoint unicast locators so remote participants know where
    # to send user data. This is important for data delivery.
    if interop.include_unicast_locator:
        for loc in endpoint.unicast_locators:
            if interop.locator_pid in ("endpoint", "both"):
                pl.add_parameter(PID_UNICAST_LOCATOR, loc.to_bytes())
            if interop.locator_pid in ("default", "both"):
                pl.add_parameter(PID_DEFAULT_UNICAST_LOCATOR, loc.to_bytes())

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
        elif pid == PID_GROUP_ENTITY_ID:
            # Keep raw group entity id for diagnostics (not used for matching)
            endpoint.group_entity_id = struct.unpack(endian + "I", value[:4])[0]
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
        elif pid == PID_TYPE_INFORMATION:
            endpoint.type_information = value
        elif pid == PID_TYPE_OBJECT:
            endpoint.type_object = value

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

    def __init__(
        self,
        guid_prefix: GuidPrefix,
        endpoint_db: EndpointDatabase,
        interop: SedpInteropOptions | None = None,
    ):
        self._guid_prefix = guid_prefix
        self._endpoint_db = endpoint_db
        self._interop = interop or SedpInteropOptions.from_env()

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
        pl_data = _build_endpoint_data(endpoint, self._interop)
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

        for loc in dest_meta_locators:
            dest_addr = loc.ipv4_str or "127.0.0.1"
            dest_port = loc.port

            # Send publications (our DataWriters)
            for change in self._pub_writer._history:
                builder = RtpsMessageBuilder(self._guid_prefix)
                builder.add_info_ts(Timestamp.from_seconds(time.time()))
                if self._interop.include_info_dst:
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
                if self._interop.include_info_dst:
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
                if self._interop.include_info_dst:
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
                if self._interop.include_info_dst:
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

    def handle_acknack(
        self, sm: AckNackSubmessage, source_prefix: GuidPrefix
    ) -> tuple[bytes, ...] | None:
        """Handle incoming ACKNACK, return DATA retransmit messages if needed."""
        writer_entity = sm.writer_id.value

        writer: ReliableWriter | None = None
        reader_entity = None
        if writer_entity == ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER:
            writer = self._pub_writer
            reader_entity = ENTITYID_SEDP_BUILTIN_PUBLICATIONS_READER
        elif writer_entity == ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER:
            writer = self._sub_writer
            reader_entity = ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_READER

        if writer is None or reader_entity is None:
            return None

        retransmits = writer.process_acknack(sm)
        if not retransmits:
            return None

        messages = []
        for change in retransmits:
            builder = RtpsMessageBuilder(self._guid_prefix)
            builder.add_info_dst(source_prefix)
            builder.add_data(
                reader_id=EntityId(reader_entity),
                writer_id=EntityId(writer_entity),
                writer_sn=change.sequence_number,
                serialized_payload=change.serialized_data,
            )
            messages.append(builder.build())

        return tuple(messages)

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
