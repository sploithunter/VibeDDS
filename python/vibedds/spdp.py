"""Simple Participant Discovery Protocol (SPDP).

Handles announcing our participant via multicast and discovering
remote participants from their SPDP announcements.
"""

from __future__ import annotations

import struct
import time
import logging
from dataclasses import dataclass, field

from vibedds.constants import (
    PID_PROTOCOL_VERSION, PID_VENDORID, PID_PARTICIPANT_GUID,
    PID_PARTICIPANT_LEASE_DURATION, PID_DEFAULT_UNICAST_LOCATOR,
    PID_METATRAFFIC_UNICAST_LOCATOR, PID_BUILTIN_ENDPOINT_SET,
    PID_DEFAULT_MULTICAST_LOCATOR, PID_METATRAFFIC_MULTICAST_LOCATOR,
    ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER,
    ENTITYID_SPDP_BUILTIN_PARTICIPANT_READER,
    ENTITYID_UNKNOWN, ENTITYID_PARTICIPANT,
    BUILTIN_ENDPOINT_SET_DEFAULT,
    RTPS_VERSION_MAJOR, RTPS_VERSION_MINOR, VENDOR_ID,
    SPDP_MULTICAST_ADDRESS,
    spdp_multicast_port,
)
from vibedds.types import (
    GuidPrefix, EntityId, Guid, SequenceNumber,
    Timestamp, Duration, Locator, ProtocolVersion, VendorId,
)
from vibedds.cdr import (
    ParameterListBuilder, ParameterListParser,
    encapsulation_header, PL_CDR_LE, parse_encapsulation_header,
)
from vibedds.wire import RtpsMessageBuilder, RtpsMessageParser
from vibedds.messages import DataSubmessage

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredParticipant:
    """Information about a discovered remote participant."""
    guid_prefix: GuidPrefix
    protocol_version: ProtocolVersion | None = None
    vendor_id: VendorId | None = None
    participant_guid: Guid | None = None
    lease_duration: Duration | None = None
    default_unicast_locators: list[Locator] = field(default_factory=list)
    default_multicast_locators: list[Locator] = field(default_factory=list)
    metatraffic_unicast_locators: list[Locator] = field(default_factory=list)
    metatraffic_multicast_locators: list[Locator] = field(default_factory=list)
    builtin_endpoints: int = 0
    last_seen: float = 0.0

    def is_expired(self, now: float) -> bool:
        if self.lease_duration is None:
            return False
        lease_secs = self.lease_duration.to_seconds()
        return (now - self.last_seen) > lease_secs


class SPDPWriter:
    """Writes SPDP participant announcements to multicast."""

    def __init__(
        self,
        guid_prefix: GuidPrefix,
        local_ip: str,
        metatraffic_unicast_port: int,
        user_unicast_port: int,
        domain_id: int = 0,
        builtin_endpoints: int = BUILTIN_ENDPOINT_SET_DEFAULT,
        lease_duration_seconds: int = 100,
    ):
        self._guid_prefix = guid_prefix
        self._local_ip = local_ip
        self._metatraffic_unicast_port = metatraffic_unicast_port
        self._user_unicast_port = user_unicast_port
        self._domain_id = domain_id
        self._builtin_endpoints = builtin_endpoints
        self._lease_duration = Duration(seconds=lease_duration_seconds, fraction=0)
        self._sequence_number = SequenceNumber.from_value(0)

    def build_announcement(self) -> bytes:
        """Build an SPDP announcement RTPS message."""
        self._sequence_number = self._sequence_number + 1

        # Build parameter list payload
        pl = ParameterListBuilder("<")

        # PID_PROTOCOL_VERSION
        pl.add_parameter(PID_PROTOCOL_VERSION,
                         bytes([RTPS_VERSION_MAJOR, RTPS_VERSION_MINOR]))

        # PID_VENDORID
        pl.add_parameter(PID_VENDORID, bytes(VENDOR_ID))

        # PID_PARTICIPANT_GUID (16 bytes: guidPrefix + participantEntityId)
        participant_guid = self._guid_prefix.value + ENTITYID_PARTICIPANT
        pl.add_parameter(PID_PARTICIPANT_GUID, participant_guid)

        # PID_PARTICIPANT_LEASE_DURATION
        pl.add_parameter(PID_PARTICIPANT_LEASE_DURATION,
                         self._lease_duration.to_bytes("<"))

        # PID_DEFAULT_UNICAST_LOCATOR
        user_loc = Locator.from_ipv4(self._local_ip, self._user_unicast_port)
        pl.add_parameter(PID_DEFAULT_UNICAST_LOCATOR, user_loc.to_bytes())

        # PID_METATRAFFIC_UNICAST_LOCATOR
        meta_loc = Locator.from_ipv4(self._local_ip, self._metatraffic_unicast_port)
        pl.add_parameter(PID_METATRAFFIC_UNICAST_LOCATOR, meta_loc.to_bytes())

        # PID_BUILTIN_ENDPOINT_SET
        pl.add_parameter(PID_BUILTIN_ENDPOINT_SET,
                         struct.pack("<I", self._builtin_endpoints))

        payload_bytes = pl.finalize()

        # Wrap in PL_CDR_LE encapsulation
        serialized_payload = encapsulation_header(PL_CDR_LE) + payload_bytes

        # Build RTPS message: Header + INFO_TS + DATA
        builder = RtpsMessageBuilder(self._guid_prefix)
        builder.add_info_ts(Timestamp.from_seconds(time.time()))
        builder.add_data(
            reader_id=EntityId(ENTITYID_UNKNOWN),
            writer_id=EntityId(ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER),
            writer_sn=self._sequence_number,
            serialized_payload=serialized_payload,
        )
        return builder.build()


class SPDPReader:
    """Reads and parses SPDP participant announcements."""

    SPDP_WRITER_ENTITY = EntityId(ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER)

    @staticmethod
    def parse_announcement(data: bytes) -> DiscoveredParticipant | None:
        """Parse an RTPS message and extract SPDP participant data.

        Returns None if the message doesn't contain SPDP data.
        """
        try:
            msg = RtpsMessageParser.parse(data)
        except ValueError as e:
            logger.debug("Failed to parse RTPS message: %s", e)
            return None

        # Look for DATA submessage from SPDP writer
        for sm in msg.submessages:
            if not isinstance(sm, DataSubmessage):
                continue
            if sm.writer_id != SPDPReader.SPDP_WRITER_ENTITY:
                continue
            if sm.serialized_payload is None:
                continue

            return SPDPReader._parse_spdp_data(
                sm.serialized_payload, msg.header.guid_prefix
            )

        return None

    @staticmethod
    def _parse_spdp_data(
        payload: bytes, source_prefix: GuidPrefix
    ) -> DiscoveredParticipant:
        """Parse SPDP DATA payload (encapsulated parameter list)."""
        scheme, pl_data = parse_encapsulation_header(payload)
        endian = "<" if scheme in (0x0003, 0x0001) else ">"

        participant = DiscoveredParticipant(
            guid_prefix=source_prefix,
            last_seen=time.time(),
        )

        for pid, value in ParameterListParser(pl_data, endian):
            if pid == PID_PROTOCOL_VERSION:
                participant.protocol_version = ProtocolVersion.from_bytes(value)
            elif pid == PID_VENDORID:
                participant.vendor_id = VendorId.from_bytes(value)
            elif pid == PID_PARTICIPANT_GUID:
                participant.participant_guid = Guid.from_bytes(value)
                # Update guid_prefix from the GUID parameter
                participant.guid_prefix = GuidPrefix(value[:12])
            elif pid == PID_PARTICIPANT_LEASE_DURATION:
                participant.lease_duration = Duration.from_bytes(value, endian)
            elif pid == PID_DEFAULT_UNICAST_LOCATOR:
                participant.default_unicast_locators.append(
                    Locator.from_bytes(value)
                )
            elif pid == PID_DEFAULT_MULTICAST_LOCATOR:
                participant.default_multicast_locators.append(
                    Locator.from_bytes(value)
                )
            elif pid == PID_METATRAFFIC_UNICAST_LOCATOR:
                participant.metatraffic_unicast_locators.append(
                    Locator.from_bytes(value)
                )
            elif pid == PID_METATRAFFIC_MULTICAST_LOCATOR:
                participant.metatraffic_multicast_locators.append(
                    Locator.from_bytes(value)
                )
            elif pid == PID_BUILTIN_ENDPOINT_SET:
                participant.builtin_endpoints = struct.unpack(endian + "I", value[:4])[0]

        return participant


class ParticipantDatabase:
    """Tracks discovered participants, handles lease expiry."""

    def __init__(self):
        self._participants: dict[bytes, DiscoveredParticipant] = {}

    def update(self, participant: DiscoveredParticipant) -> bool:
        """Add or update a participant. Returns True if new."""
        key = participant.guid_prefix.value
        is_new = key not in self._participants
        self._participants[key] = participant
        return is_new

    def get(self, guid_prefix: GuidPrefix) -> DiscoveredParticipant | None:
        return self._participants.get(guid_prefix.value)

    def remove_expired(self) -> list[DiscoveredParticipant]:
        """Remove and return expired participants."""
        now = time.time()
        expired = []
        to_remove = []
        for key, p in self._participants.items():
            if p.is_expired(now):
                expired.append(p)
                to_remove.append(key)
        for key in to_remove:
            del self._participants[key]
        return expired

    @property
    def participants(self) -> dict[bytes, DiscoveredParticipant]:
        return self._participants

    def __len__(self) -> int:
        return len(self._participants)
