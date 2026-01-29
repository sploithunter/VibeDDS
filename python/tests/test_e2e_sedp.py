#!/usr/bin/env python3
"""E2E test: SEDP exchange between two VibeDDS participants.

Tests that endpoints are discovered via SEDP after SPDP.
"""

import time
import pytest
import logging

from vibedds.participant import DomainParticipant, generate_guid_prefix
from vibedds.spdp import DiscoveredParticipant
from vibedds.qos import QosPolicy, ReliabilityKind, DurabilityKind
from vibedds.type_support import HelloWorldType

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(name)s %(levelname)s: %(message)s")


class TestSEDPEndpointDiscovery:
    """Two VibeDDS participants discover each other's endpoints via SEDP."""

    def test_writer_discovered_via_sedp(self):
        """Participant A creates a DataWriter, Participant B discovers it via SEDP."""

        prefix_a = generate_guid_prefix()
        prefix_b = generate_guid_prefix()

        pa = DomainParticipant(domain_id=0, participant_id=0, guid_prefix=prefix_a)
        pb = DomainParticipant(domain_id=0, participant_id=1, guid_prefix=prefix_b)

        try:
            pa.start()
            pb.start()

            # A creates a DataWriter
            topic_a = pa.create_topic("HelloWorldTopic", HelloWorldType.TYPE_NAME)
            writer_a = pa.create_writer(topic_a, QosPolicy(reliability=ReliabilityKind.BEST_EFFORT))

            # Exchange SPDP
            pa.announce_spdp()
            pb.announce_spdp()

            # Spin to let SPDP + SEDP complete
            deadline = time.time() + 10.0
            sedp_done = False
            while time.time() < deadline:
                pa.spin_once(timeout=0.05)
                pb.spin_once(timeout=0.05)

                # Check if B has discovered A's writer
                if pb.endpoint_db.remote_writers:
                    sedp_done = True
                    break

            # Verify B discovered A's writer
            assert sedp_done, (
                f"B did not discover A's writer via SEDP. "
                f"B's remote writers: {list(pb.endpoint_db.remote_writers.keys())}"
            )

            remote_writer = list(pb.endpoint_db.remote_writers.values())[0]
            assert remote_writer.topic_name == "HelloWorldTopic"
            assert remote_writer.type_name == HelloWorldType.TYPE_NAME

            print(f"\nB discovered A's writer:")
            print(f"  GUID: {remote_writer.endpoint_guid}")
            print(f"  Topic: {remote_writer.topic_name}")
            print(f"  Type: {remote_writer.type_name}")
            print(f"  Reliability: {remote_writer.reliability}")

        finally:
            pa.stop()
            pb.stop()

    def test_reader_discovered_via_sedp(self):
        """Participant A creates a DataReader, Participant B discovers it via SEDP."""

        prefix_a = generate_guid_prefix()
        prefix_b = generate_guid_prefix()

        pa = DomainParticipant(domain_id=0, participant_id=0, guid_prefix=prefix_a)
        pb = DomainParticipant(domain_id=0, participant_id=1, guid_prefix=prefix_b)

        try:
            pa.start()
            pb.start()

            # A creates a DataReader
            topic_a = pa.create_topic("TestTopic", "TestType")
            reader_a = pa.create_reader(topic_a, QosPolicy(reliability=ReliabilityKind.RELIABLE))

            # Exchange SPDP
            pa.announce_spdp()
            pb.announce_spdp()

            # Spin to let SPDP + SEDP complete
            deadline = time.time() + 10.0
            sedp_done = False
            while time.time() < deadline:
                pa.spin_once(timeout=0.05)
                pb.spin_once(timeout=0.05)

                if pb.endpoint_db.remote_readers:
                    sedp_done = True
                    break

            assert sedp_done, "B did not discover A's reader via SEDP"

            remote_reader = list(pb.endpoint_db.remote_readers.values())[0]
            assert remote_reader.topic_name == "TestTopic"
            assert remote_reader.type_name == "TestType"

            print(f"\nB discovered A's reader:")
            print(f"  GUID: {remote_reader.endpoint_guid}")
            print(f"  Topic: {remote_reader.topic_name}")
            print(f"  Type: {remote_reader.type_name}")

        finally:
            pa.stop()
            pb.stop()

    def test_bidirectional_endpoint_discovery(self):
        """Both participants have endpoints, both discover each other's."""

        prefix_a = generate_guid_prefix()
        prefix_b = generate_guid_prefix()

        pa = DomainParticipant(domain_id=0, participant_id=0, guid_prefix=prefix_a)
        pb = DomainParticipant(domain_id=0, participant_id=1, guid_prefix=prefix_b)

        try:
            pa.start()
            pb.start()

            # A creates a writer, B creates a reader on same topic
            topic_a = pa.create_topic("HelloWorldTopic", HelloWorldType.TYPE_NAME)
            writer_a = pa.create_writer(topic_a, QosPolicy(reliability=ReliabilityKind.BEST_EFFORT))

            topic_b = pb.create_topic("HelloWorldTopic", HelloWorldType.TYPE_NAME)
            reader_b = pb.create_reader(topic_b, QosPolicy(reliability=ReliabilityKind.BEST_EFFORT))

            # Exchange SPDP
            pa.announce_spdp()
            pb.announce_spdp()

            # Spin to let SPDP + SEDP complete
            deadline = time.time() + 10.0
            a_found_reader = False
            b_found_writer = False

            while time.time() < deadline:
                pa.spin_once(timeout=0.05)
                pb.spin_once(timeout=0.05)

                if pa.endpoint_db.remote_readers:
                    a_found_reader = True
                if pb.endpoint_db.remote_writers:
                    b_found_writer = True
                if a_found_reader and b_found_writer:
                    break

            assert b_found_writer, "B did not discover A's writer"
            assert a_found_reader, "A did not discover B's reader"

            # Verify matching
            remote_w = list(pb.endpoint_db.remote_writers.values())[0]
            remote_r = list(pa.endpoint_db.remote_readers.values())[0]

            assert remote_w.topic_name == "HelloWorldTopic"
            assert remote_r.topic_name == "HelloWorldTopic"

            print(f"\nBidirectional SEDP discovery complete:")
            print(f"  B found A's writer: {remote_w.endpoint_guid}")
            print(f"  A found B's reader: {remote_r.endpoint_guid}")

        finally:
            pa.stop()
            pb.stop()

    def test_data_exchange_after_sedp(self):
        """After SEDP, A publishes data that B receives."""

        prefix_a = generate_guid_prefix()
        prefix_b = generate_guid_prefix()

        pa = DomainParticipant(domain_id=0, participant_id=0, guid_prefix=prefix_a)
        pb = DomainParticipant(domain_id=0, participant_id=1, guid_prefix=prefix_b)

        try:
            pa.start()
            pb.start()

            # A creates a writer
            topic_a = pa.create_topic("HelloWorldTopic", HelloWorldType.TYPE_NAME)
            writer_a = pa.create_writer(topic_a, QosPolicy(reliability=ReliabilityKind.BEST_EFFORT))

            # B creates a reader
            topic_b = pb.create_topic("HelloWorldTopic", HelloWorldType.TYPE_NAME)
            reader_b = pb.create_reader(topic_b, QosPolicy(reliability=ReliabilityKind.BEST_EFFORT))

            # Exchange SPDP + SEDP
            pa.announce_spdp()
            pb.announce_spdp()

            deadline = time.time() + 10.0
            while time.time() < deadline:
                pa.spin_once(timeout=0.05)
                pb.spin_once(timeout=0.05)
                if pb.endpoint_db.remote_writers and pa.endpoint_db.remote_readers:
                    break

            # Now publish data
            payload = HelloWorldType.serialize("Hello from A!")
            writer_a.write(payload)

            # Spin to receive
            deadline = time.time() + 5.0
            received = False
            while time.time() < deadline:
                pa.spin_once(timeout=0.05)
                pb.spin_once(timeout=0.05)

                samples = reader_b.take()
                if samples:
                    for sample in samples:
                        msg = HelloWorldType.deserialize(sample)
                        print(f"\nB received: '{msg}'")
                        assert msg == "Hello from A!"
                        received = True
                    break

            assert received, "B did not receive data from A"

        finally:
            pa.stop()
            pb.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
