"""End-to-end SPDP discovery tests.

Tests actual multicast networking — two DomainParticipants in the same
process discover each other via multicast loopback.
"""

import time
import pytest
import logging

from vibedds.participant import DomainParticipant, generate_guid_prefix
from vibedds.spdp import DiscoveredParticipant

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(name)s %(levelname)s: %(message)s")


class TestSPDPSelfDiscovery:
    """Two participants discover each other via multicast loopback."""

    def test_two_participants_discover_each_other(self):
        """Create two participants with different participant_ids on the same
        domain. Both announce SPDP and should discover each other."""

        discovered_by_a: list[DiscoveredParticipant] = []
        discovered_by_b: list[DiscoveredParticipant] = []

        # Use distinct guid_prefix to guarantee uniqueness
        prefix_a = generate_guid_prefix()
        prefix_b = generate_guid_prefix()

        pa = DomainParticipant(domain_id=0, participant_id=0, guid_prefix=prefix_a)
        pb = DomainParticipant(domain_id=0, participant_id=1, guid_prefix=prefix_b)

        pa.on_participant_discovered(lambda p: discovered_by_a.append(p))
        pb.on_participant_discovered(lambda p: discovered_by_b.append(p))

        try:
            pa.start()
            pb.start()

            # Send initial announcements
            pa.announce_spdp()
            pb.announce_spdp()

            # Spin both participants for up to 5 seconds, checking for discovery
            deadline = time.time() + 5.0
            while time.time() < deadline:
                pa.spin_once(timeout=0.05)
                pb.spin_once(timeout=0.05)
                if discovered_by_a and discovered_by_b:
                    break

            # Verify mutual discovery
            assert len(discovered_by_a) >= 1, "Participant A did not discover B"
            assert len(discovered_by_b) >= 1, "Participant B did not discover A"

            # Verify A discovered B (by checking guid_prefix)
            found_b = any(d.guid_prefix == prefix_b for d in discovered_by_a)
            assert found_b, f"A did not discover B's prefix. Discovered: {[d.guid_prefix for d in discovered_by_a]}"

            # Verify B discovered A
            found_a = any(d.guid_prefix == prefix_a for d in discovered_by_b)
            assert found_a, f"B did not discover A's prefix. Discovered: {[d.guid_prefix for d in discovered_by_b]}"

            # Verify discovered participant data has expected fields
            b_info = next(d for d in discovered_by_a if d.guid_prefix == prefix_b)
            assert b_info.protocol_version is not None
            assert b_info.protocol_version.major == 2
            assert b_info.protocol_version.minor == 5
            assert b_info.vendor_id is not None
            assert b_info.vendor_id.vendor == (0xFF, 0x01)
            assert b_info.lease_duration is not None
            assert b_info.lease_duration.to_seconds() == 100.0
            assert len(b_info.default_unicast_locators) >= 1
            assert len(b_info.metatraffic_unicast_locators) >= 1
            assert b_info.builtin_endpoints != 0

            print(f"\nParticipant A ({prefix_a}) discovered B ({prefix_b})")
            print(f"Participant B ({prefix_b}) discovered A ({prefix_a})")
            print(f"B's metatraffic locator: {b_info.metatraffic_unicast_locators[0].ipv4_str}:{b_info.metatraffic_unicast_locators[0].port}")
            print(f"B's user locator: {b_info.default_unicast_locators[0].ipv4_str}:{b_info.default_unicast_locators[0].port}")

        finally:
            pa.stop()
            pb.stop()

    def test_participant_ignores_own_announcement(self):
        """A participant should not discover itself."""
        prefix = generate_guid_prefix()
        pa = DomainParticipant(domain_id=0, participant_id=0, guid_prefix=prefix)
        discovered: list[DiscoveredParticipant] = []
        pa.on_participant_discovered(lambda p: discovered.append(p))

        try:
            pa.start()

            # Announce multiple times and spin
            for _ in range(5):
                pa.announce_spdp()
                pa.spin_once(timeout=0.1)

            # Should NOT have discovered ourselves
            assert len(discovered) == 0, f"Participant discovered itself! Found: {[d.guid_prefix for d in discovered]}"
            print("\nCorrectly ignored own SPDP announcement")

        finally:
            pa.stop()

    def test_spdp_announcement_wire_format(self):
        """Verify the SPDP announcement can be parsed back correctly."""
        from vibedds.spdp import SPDPWriter, SPDPReader
        from vibedds.wire import RtpsMessageParser
        from vibedds.messages import DataSubmessage

        prefix = generate_guid_prefix()
        writer = SPDPWriter(
            guid_prefix=prefix,
            local_ip="192.168.1.100",
            metatraffic_unicast_port=7410,
            user_unicast_port=7401,
            domain_id=0,
        )

        data = writer.build_announcement()

        # Verify RTPS header
        assert data[:4] == b'RTPS', f"Bad magic: {data[:4]}"
        assert data[4] == 2  # version major
        assert data[5] == 5  # version minor

        # Parse and verify
        msg = RtpsMessageParser.parse(data)
        assert msg.header.guid_prefix == prefix

        # Should have INFO_TS + DATA
        assert len(msg.submessages) >= 2

        # Find DATA submessage
        data_sms = [sm for sm in msg.submessages if isinstance(sm, DataSubmessage)]
        assert len(data_sms) == 1

        # Parse as SPDP announcement
        participant = SPDPReader.parse_announcement(data)
        assert participant is not None
        assert participant.guid_prefix == prefix
        assert participant.protocol_version.major == 2
        assert participant.protocol_version.minor == 5
        assert participant.vendor_id.vendor == (0xFF, 0x01)
        assert participant.lease_duration.to_seconds() == 100.0
        assert len(participant.default_unicast_locators) == 1
        assert participant.default_unicast_locators[0].ipv4_str == "192.168.1.100"
        assert participant.default_unicast_locators[0].port == 7401
        assert len(participant.metatraffic_unicast_locators) == 1
        assert participant.metatraffic_unicast_locators[0].ipv4_str == "192.168.1.100"
        assert participant.metatraffic_unicast_locators[0].port == 7410

        print(f"\nSPDP announcement: {len(data)} bytes, parsed correctly")
        print(f"  Submessages: {len(msg.submessages)}")

    def test_repeated_announcements_update_not_duplicate(self):
        """Multiple announcements from same participant should update, not add."""
        discovered: list[DiscoveredParticipant] = []
        prefix_a = generate_guid_prefix()
        prefix_b = generate_guid_prefix()

        pa = DomainParticipant(domain_id=0, participant_id=0, guid_prefix=prefix_a)
        pb = DomainParticipant(domain_id=0, participant_id=1, guid_prefix=prefix_b)
        pa.on_participant_discovered(lambda p: discovered.append(p))

        try:
            pa.start()
            pb.start()

            # B announces multiple times
            for _ in range(5):
                pb.announce_spdp()
                pa.spin_once(timeout=0.1)
                pb.spin_once(timeout=0.05)

            # A should have discovered B exactly once (updates don't trigger callback again)
            assert len(discovered) == 1, f"Expected 1 discovery event, got {len(discovered)}"
            assert discovered[0].guid_prefix == prefix_b

            # ParticipantDatabase should have exactly 1 entry
            assert len(pa.participant_db) == 1

            print("\nRepeated announcements correctly handled (1 discovery event)")

        finally:
            pa.stop()
            pb.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
