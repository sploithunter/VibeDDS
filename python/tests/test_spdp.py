"""Tests for SPDP discovery protocol."""

import time
import struct
import pytest

from vibedds.types import GuidPrefix, EntityId, Guid, Duration, Locator
from vibedds.spdp import SPDPWriter, SPDPReader, ParticipantDatabase, DiscoveredParticipant
from vibedds.wire import RtpsMessageParser
from vibedds.messages import DataSubmessage
from vibedds.constants import (
    ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER,
    ENTITYID_PARTICIPANT,
    BUILTIN_ENDPOINT_SET_DEFAULT,
    PID_PROTOCOL_VERSION, PID_VENDORID, PID_PARTICIPANT_GUID,
    PID_PARTICIPANT_LEASE_DURATION, PID_BUILTIN_ENDPOINT_SET,
    PID_DEFAULT_UNICAST_LOCATOR, PID_METATRAFFIC_UNICAST_LOCATOR,
    RTPS_VERSION_MAJOR, RTPS_VERSION_MINOR, VENDOR_ID,
)
from vibedds.cdr import ParameterListParser, parse_encapsulation_header


class TestSPDPWriter:
    def _make_writer(self):
        return SPDPWriter(
            guid_prefix=GuidPrefix(b'\x01' * 12),
            local_ip="192.168.1.100",
            metatraffic_unicast_port=7410,
            user_unicast_port=7401,
            domain_id=0,
        )

    def test_build_announcement(self):
        writer = self._make_writer()
        data = writer.build_announcement()
        assert len(data) > 20  # header + submessages

        # Must be valid RTPS
        msg = RtpsMessageParser.parse(data)
        assert msg.header.guid_prefix == GuidPrefix(b'\x01' * 12)

        # Should have INFO_TS + DATA
        assert len(msg.submessages) >= 1
        data_sms = [sm for sm in msg.submessages if isinstance(sm, DataSubmessage)]
        assert len(data_sms) == 1

        dsm = data_sms[0]
        assert dsm.writer_id == EntityId(ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER)
        assert dsm.writer_sn.value == 1
        assert dsm.serialized_payload is not None

    def test_sequence_increments(self):
        writer = self._make_writer()
        data1 = writer.build_announcement()
        data2 = writer.build_announcement()

        msg1 = RtpsMessageParser.parse(data1)
        msg2 = RtpsMessageParser.parse(data2)

        dsm1 = [sm for sm in msg1.submessages if isinstance(sm, DataSubmessage)][0]
        dsm2 = [sm for sm in msg2.submessages if isinstance(sm, DataSubmessage)][0]
        assert dsm2.writer_sn.value == dsm1.writer_sn.value + 1

    def test_payload_contains_required_pids(self):
        writer = self._make_writer()
        data = writer.build_announcement()
        msg = RtpsMessageParser.parse(data)
        dsm = [sm for sm in msg.submessages if isinstance(sm, DataSubmessage)][0]

        # Parse encapsulation + parameter list
        scheme, pl_data = parse_encapsulation_header(dsm.serialized_payload)
        assert scheme == 0x0003  # PL_CDR_LE

        pids_found = set()
        for pid, value in ParameterListParser(pl_data, "<"):
            pids_found.add(pid)

        # Must contain these PIDs
        assert PID_PROTOCOL_VERSION in pids_found
        assert PID_VENDORID in pids_found
        assert PID_PARTICIPANT_GUID in pids_found
        assert PID_PARTICIPANT_LEASE_DURATION in pids_found
        assert PID_DEFAULT_UNICAST_LOCATOR in pids_found
        assert PID_METATRAFFIC_UNICAST_LOCATOR in pids_found
        assert PID_BUILTIN_ENDPOINT_SET in pids_found


class TestSPDPReader:
    def test_parse_own_announcement(self):
        writer = SPDPWriter(
            guid_prefix=GuidPrefix(b'\xAA' * 12),
            local_ip="10.0.0.5",
            metatraffic_unicast_port=7410,
            user_unicast_port=7401,
            domain_id=0,
        )
        data = writer.build_announcement()
        participant = SPDPReader.parse_announcement(data)
        assert participant is not None
        assert participant.guid_prefix == GuidPrefix(b'\xAA' * 12)
        assert participant.protocol_version.major == RTPS_VERSION_MAJOR
        assert participant.protocol_version.minor == RTPS_VERSION_MINOR
        assert participant.vendor_id.vendor == tuple(VENDOR_ID)
        assert participant.builtin_endpoints == BUILTIN_ENDPOINT_SET_DEFAULT
        assert participant.lease_duration is not None
        assert participant.lease_duration.seconds == 100
        assert len(participant.default_unicast_locators) == 1
        assert len(participant.metatraffic_unicast_locators) == 1
        assert participant.default_unicast_locators[0].ipv4_str == "10.0.0.5"
        assert participant.default_unicast_locators[0].port == 7401
        assert participant.metatraffic_unicast_locators[0].ipv4_str == "10.0.0.5"
        assert participant.metatraffic_unicast_locators[0].port == 7410

    def test_invalid_data(self):
        assert SPDPReader.parse_announcement(b'\x00' * 10) is None

    def test_non_spdp_data(self):
        """A valid RTPS message without SPDP data should return None."""
        from vibedds.wire import RtpsMessageBuilder
        from vibedds.types import Timestamp
        prefix = GuidPrefix(b'\x01' * 12)
        builder = RtpsMessageBuilder(prefix)
        builder.add_info_ts(Timestamp(1, 0))
        assert SPDPReader.parse_announcement(builder.build()) is None


class TestParticipantDatabase:
    def test_add_new(self):
        db = ParticipantDatabase()
        p = DiscoveredParticipant(
            guid_prefix=GuidPrefix(b'\x01' * 12),
            last_seen=time.time(),
        )
        assert db.update(p) is True
        assert len(db) == 1

    def test_update_existing(self):
        db = ParticipantDatabase()
        p = DiscoveredParticipant(
            guid_prefix=GuidPrefix(b'\x01' * 12),
            last_seen=time.time(),
        )
        db.update(p)
        assert db.update(p) is False  # not new
        assert len(db) == 1

    def test_expiry(self):
        db = ParticipantDatabase()
        p = DiscoveredParticipant(
            guid_prefix=GuidPrefix(b'\x01' * 12),
            lease_duration=Duration(seconds=1, fraction=0),
            last_seen=time.time() - 2,  # expired
        )
        db.update(p)
        expired = db.remove_expired()
        assert len(expired) == 1
        assert len(db) == 0

    def test_no_expiry_without_lease(self):
        db = ParticipantDatabase()
        p = DiscoveredParticipant(
            guid_prefix=GuidPrefix(b'\x01' * 12),
            last_seen=time.time() - 1000,
        )
        db.update(p)
        expired = db.remove_expired()
        assert len(expired) == 0

    def test_get(self):
        db = ParticipantDatabase()
        prefix = GuidPrefix(b'\xAB' * 12)
        p = DiscoveredParticipant(guid_prefix=prefix, last_seen=time.time())
        db.update(p)
        assert db.get(prefix) is not None
        assert db.get(GuidPrefix(b'\xCD' * 12)) is None
