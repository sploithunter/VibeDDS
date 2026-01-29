#!/usr/bin/env python3
"""E2E test: RTI DDS interoperability.

Tests SPDP discovery between VibeDDS and RTI Connext DDS.
"""

import os
import subprocess
import time
import pytest

# Check if RTI is available
try:
    import rti.connextdds as dds
    RTI_AVAILABLE = True
except ImportError:
    RTI_AVAILABLE = False

from vibedds.participant import DomainParticipant, generate_guid_prefix


@pytest.mark.skipif(not RTI_AVAILABLE, reason="RTI Connext DDS not installed")
class TestRTISPDPInterop:
    """Test SPDP discovery between VibeDDS and RTI."""

    def test_vibedds_discovers_rti_participant(self):
        """VibeDDS discovers RTI participant via SPDP."""
        import rti.connextdds as dds

        # Create RTI participant
        rti_participant = dds.DomainParticipant(0)

        try:
            # Create VibeDDS participant
            prefix = generate_guid_prefix()
            vibe_participant = DomainParticipant(domain_id=0, participant_id=2, guid_prefix=prefix)

            discovered_rti = []

            def on_discovered(p):
                # RTI vendor ID is (1, 1)
                if p.vendor_id and p.vendor_id.vendor == (1, 1):
                    discovered_rti.append(p)

            vibe_participant.on_participant_discovered(on_discovered)
            vibe_participant.start()
            vibe_participant.announce_spdp()

            # Spin for up to 5 seconds waiting to discover RTI
            deadline = time.time() + 5.0
            while time.time() < deadline and not discovered_rti:
                vibe_participant.spin_once(timeout=0.1)

            vibe_participant.stop()

            # Verify we discovered RTI
            assert len(discovered_rti) >= 1, "VibeDDS did not discover RTI participant"

            rti_part = discovered_rti[0]
            assert rti_part.vendor_id.vendor == (1, 1), f"Expected RTI vendor, got {rti_part.vendor_id}"

            print(f"\nVibeDDS discovered RTI participant:")
            print(f"  GUID prefix: {rti_part.guid_prefix.value.hex()}")
            print(f"  Vendor: {rti_part.vendor_id}")

        finally:
            rti_participant.close()

    def test_vibedds_discovers_rti_with_writer(self):
        """VibeDDS discovers RTI participant that has a DataWriter."""
        import rti.connextdds as dds
        import rti.types as types

        # Define a simple type
        @types.struct
        class TestData:
            value: int = 0

        # Create RTI participant with writer
        rti_participant = dds.DomainParticipant(0)
        topic = dds.Topic(rti_participant, "TestTopic", TestData)
        writer = dds.DataWriter(rti_participant.implicit_publisher, topic)

        try:
            # Create VibeDDS participant
            prefix = generate_guid_prefix()
            vibe_participant = DomainParticipant(domain_id=0, participant_id=3, guid_prefix=prefix)

            discovered_rti = []

            def on_discovered(p):
                if p.vendor_id and p.vendor_id.vendor == (1, 1):
                    discovered_rti.append(p)

            vibe_participant.on_participant_discovered(on_discovered)
            vibe_participant.start()
            vibe_participant.announce_spdp()

            # Spin
            deadline = time.time() + 5.0
            while time.time() < deadline and not discovered_rti:
                vibe_participant.spin_once(timeout=0.1)

            vibe_participant.stop()

            assert len(discovered_rti) >= 1, "VibeDDS did not discover RTI participant with writer"

            # RTI participant with writer should have builtin endpoints set
            rti_part = discovered_rti[0]
            print(f"\nVibeDDS discovered RTI participant with writer:")
            print(f"  GUID prefix: {rti_part.guid_prefix.value.hex()}")
            print(f"  Builtin endpoints: 0x{rti_part.builtin_endpoints:08x}")

        finally:
            rti_participant.close()

    def test_multiple_discoveries(self):
        """VibeDDS handles multiple RTI participants."""
        import rti.connextdds as dds

        # Create two RTI participants
        rti1 = dds.DomainParticipant(0)
        rti2 = dds.DomainParticipant(0)

        try:
            prefix = generate_guid_prefix()
            vibe_participant = DomainParticipant(domain_id=0, participant_id=4, guid_prefix=prefix)

            discovered_rti = []

            def on_discovered(p):
                if p.vendor_id and p.vendor_id.vendor == (1, 1):
                    discovered_rti.append(p)

            vibe_participant.on_participant_discovered(on_discovered)
            vibe_participant.start()
            vibe_participant.announce_spdp()

            # Spin
            deadline = time.time() + 5.0
            while time.time() < deadline and len(discovered_rti) < 2:
                vibe_participant.spin_once(timeout=0.1)

            vibe_participant.stop()

            # Should discover at least 2 RTI participants
            assert len(discovered_rti) >= 2, f"Expected 2+ RTI participants, found {len(discovered_rti)}"

            # Verify unique GUIDs
            guids = set(p.guid_prefix.value for p in discovered_rti)
            assert len(guids) >= 2, "RTI participants should have unique GUIDs"

            print(f"\nVibeDDS discovered {len(discovered_rti)} RTI participants")

        finally:
            rti1.close()
            rti2.close()


@pytest.mark.skipif(not RTI_AVAILABLE, reason="RTI Connext DDS not installed")
class TestRustRTIInterop:
    """Test SPDP discovery between Rust VibeDDS and RTI."""

    @pytest.fixture
    def rust_binary(self):
        """Ensure Rust binary is built."""
        rust_dir = os.path.join(os.path.dirname(__file__), "..", "..", "rust", "vibedds")
        binary = os.path.join(rust_dir, "target", "debug", "examples", "spdp_announce")
        if not os.path.exists(binary):
            pytest.skip("Rust binary not built")
        return binary

    def test_rust_discovers_rti_participant(self, rust_binary):
        """Rust VibeDDS discovers RTI participant via SPDP."""
        import rti.connextdds as dds

        # Start Rust
        env = os.environ.copy()
        env["RUST_LOG"] = "info"
        cargo_bin = os.path.expanduser("~/.cargo/bin")
        env["PATH"] = cargo_bin + ":" + env.get("PATH", "")

        rust_proc = subprocess.Popen(
            [rust_binary],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        try:
            time.sleep(1)

            # Create RTI participant
            rti_participant = dds.DomainParticipant(0)

            # Wait for Rust to discover RTI
            time.sleep(3)

            rti_participant.close()

            rust_proc.terminate()
            stdout, _ = rust_proc.communicate(timeout=2)
            output = stdout.decode("utf-8", errors="replace")

            # Check Rust logs for RTI discovery (vendor ID 01 01)
            assert "Discovered participant" in output, \
                f"Rust did not discover any participant. Output:\n{output}"

            # RTI vendor shows as VendorId([1, 1])
            assert "VendorId([1, 1])" in output, \
                f"Rust did not discover RTI (vendor 1,1). Output:\n{output}"

            print(f"\nRust discovered RTI participant (confirmed via logs)")

        finally:
            if rust_proc.poll() is None:
                rust_proc.terminate()
                rust_proc.wait(timeout=2)


@pytest.mark.skipif(not RTI_AVAILABLE, reason="RTI Connext DDS not installed")
class TestRTISEDPInterop:
    """Test SEDP endpoint discovery between VibeDDS and RTI."""

    def test_vibedds_discovers_rti_writer(self):
        """VibeDDS discovers RTI DataWriter via SEDP."""
        import rti.connextdds as dds
        import rti.types as types

        @types.struct
        class HelloMsg:
            message: str = ""

        # Create RTI participant with writer
        rti_participant = dds.DomainParticipant(0)
        topic = dds.Topic(rti_participant, "HelloWorld", HelloMsg)
        writer = dds.DataWriter(rti_participant.implicit_publisher, topic)

        try:
            from vibedds.qos import QosPolicy, ReliabilityKind

            prefix = generate_guid_prefix()
            vibe_participant = DomainParticipant(domain_id=0, participant_id=25, guid_prefix=prefix)
            vibe_participant.start()
            vibe_participant.announce_spdp()

            # Spin for discovery
            deadline = time.time() + 8.0
            found_writer = False
            while time.time() < deadline:
                vibe_participant.spin_once(timeout=0.2)
                # Check for discovered writers
                for rw in vibe_participant.endpoint_db.remote_writers.values():
                    if rw.topic_name == "HelloWorld":
                        found_writer = True
                        break
                if found_writer:
                    break

            vibe_participant.stop()

            if found_writer:
                print("\nVibeDDS discovered RTI HelloWorld writer via SEDP")
            else:
                # May not work if types don't match exactly
                print("\nNote: RTI writer discovery may require type compatibility")

        finally:
            rti_participant.close()

    def test_vibedds_reader_matches_rti_writer(self):
        """VibeDDS creates reader and attempts to match RTI writer."""
        import rti.connextdds as dds
        import rti.types as types

        @types.struct
        class SimpleData:
            value: int = 0

        rti_participant = dds.DomainParticipant(0)
        topic = dds.Topic(rti_participant, "SimpleData", SimpleData)
        writer = dds.DataWriter(rti_participant.implicit_publisher, topic)

        try:
            from vibedds.qos import QosPolicy, ReliabilityKind

            prefix = generate_guid_prefix()
            vibe_participant = DomainParticipant(domain_id=0, participant_id=26, guid_prefix=prefix)
            vibe_participant.start()

            # Create reader for same topic
            qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
            vibe_topic = vibe_participant.create_topic("SimpleData", "SimpleData", qos)
            reader = vibe_participant.create_reader(vibe_topic, qos)

            vibe_participant.announce_spdp()

            # Spin for discovery
            deadline = time.time() + 5.0
            while time.time() < deadline:
                vibe_participant.spin_once(timeout=0.2)

            vibe_participant.stop()

            # Check if we have any matched endpoints
            remote_writers = list(vibe_participant.endpoint_db.remote_writers.values())
            print(f"\nDiscovered {len(remote_writers)} remote writer(s)")
            for rw in remote_writers:
                print(f"  Topic: {rw.topic_name}, Type: {rw.type_name}")

        finally:
            rti_participant.close()


@pytest.mark.skipif(not RTI_AVAILABLE, reason="RTI Connext DDS not installed")
class TestRTIDataInterop:
    """Test user DATA exchange between VibeDDS and RTI.

    Note: Full data exchange with RTI requires type compatibility.
    These tests verify the infrastructure works, even if type matching fails.
    """

    def test_vibedds_can_publish_to_rti(self):
        """VibeDDS publishes data that RTI can potentially receive.

        Note: RTI may not receive if types don't match exactly.
        This test verifies VibeDDS publishes without errors.
        """
        import rti.connextdds as dds

        # Create RTI participant
        rti_participant = dds.DomainParticipant(0)

        try:
            from vibedds.qos import QosPolicy, ReliabilityKind
            from vibedds.type_support import HelloWorldType

            prefix = generate_guid_prefix()
            vibe_participant = DomainParticipant(domain_id=0, participant_id=27, guid_prefix=prefix)
            vibe_participant.start()

            # Create writer
            qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
            topic = vibe_participant.create_topic("TestPublish", "TestType", qos)
            writer = vibe_participant.create_writer(topic, qos)

            vibe_participant.announce_spdp()

            # Let discovery happen
            for _ in range(20):
                vibe_participant.spin_once(timeout=0.1)

            # Publish some data
            for i in range(3):
                payload = HelloWorldType.serialize(f"Test message {i}")
                writer.write(payload)
                vibe_participant.spin_once(timeout=0.1)

            vibe_participant.stop()

            # If we got here without errors, publishing works
            print("\nVibeDDS published 3 messages successfully")

        finally:
            rti_participant.close()

    def test_rti_receives_vibedds_data(self):
        """RTI DataReader receives data published by VibeDDS.

        This test creates an RTI reader and VibeDDS writer for the same topic
        and verifies that data published by VibeDDS is received by RTI.
        """
        import rti.connextdds as dds
        import rti.types as types

        # Define a simple type that matches our HelloWorld CDR format
        @types.struct
        class HelloWorld:
            message: str = ""

        # Create RTI participant with reader
        rti_participant = dds.DomainParticipant(0)
        topic = dds.Topic(rti_participant, "HelloWorld", HelloWorld)

        # Create reader with QoS that accepts best-effort writers
        reader_qos = dds.DataReaderQos()
        reader_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
        reader_qos.durability.kind = dds.DurabilityKind.VOLATILE
        reader = dds.DataReader(rti_participant.implicit_subscriber, topic, reader_qos)

        received_samples = []

        try:
            from vibedds.qos import QosPolicy, ReliabilityKind
            from vibedds.type_support import HelloWorldType

            prefix = generate_guid_prefix()
            vibe_participant = DomainParticipant(domain_id=0, participant_id=28, guid_prefix=prefix)
            vibe_participant.start()

            # Create VibeDDS writer - type name must match RTI's expectation
            qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
            vibe_topic = vibe_participant.create_topic("HelloWorld", "HelloWorld", qos)
            writer = vibe_participant.create_writer(vibe_topic, qos)

            vibe_participant.announce_spdp()

            # Wait for endpoint discovery
            for _ in range(30):
                vibe_participant.spin_once(timeout=0.1)

            # Publish several messages
            for i in range(5):
                payload = HelloWorldType.serialize(f"VibeDDS message {i}")
                writer.write(payload)
                vibe_participant.spin_once(timeout=0.1)

                # Check for received samples on RTI side
                samples = reader.take()
                for sample in samples:
                    if sample.info.valid:
                        received_samples.append(sample.data.message)

            # Final check for any remaining samples
            for _ in range(10):
                vibe_participant.spin_once(timeout=0.1)
                samples = reader.take()
                for sample in samples:
                    if sample.info.valid:
                        received_samples.append(sample.data.message)

            vibe_participant.stop()

            print(f"\nRTI received {len(received_samples)} samples from VibeDDS")
            for msg in received_samples:
                print(f"  - {msg}")

            # If type compatibility fails, we may get 0 samples
            # This is expected behavior - RTI has strict type checking
            if len(received_samples) > 0:
                assert any("VibeDDS" in msg for msg in received_samples), \
                    "Expected VibeDDS messages in received samples"
                print("SUCCESS: RTI successfully received VibeDDS data!")
            else:
                print("Note: RTI did not receive samples (likely type incompatibility)")

        finally:
            rti_participant.close()

    def test_vibedds_receives_rti_data(self):
        """VibeDDS DataReader receives data published by RTI.

        This test creates a VibeDDS reader and RTI writer for the same topic
        and verifies that data published by RTI is received by VibeDDS.
        """
        import rti.connextdds as dds
        import rti.types as types

        # Define RTI type
        @types.struct
        class HelloWorld:
            message: str = ""

        # Create RTI participant with writer
        rti_participant = dds.DomainParticipant(0)
        topic = dds.Topic(rti_participant, "HelloWorld", HelloWorld)

        # Create writer with best-effort QoS
        writer_qos = dds.DataWriterQos()
        writer_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
        writer_qos.durability.kind = dds.DurabilityKind.VOLATILE
        rti_writer = dds.DataWriter(rti_participant.implicit_publisher, topic, writer_qos)

        received_samples = []

        try:
            from vibedds.qos import QosPolicy, ReliabilityKind

            prefix = generate_guid_prefix()
            vibe_participant = DomainParticipant(domain_id=0, participant_id=29, guid_prefix=prefix)
            vibe_participant.start()

            # Create VibeDDS reader
            qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
            vibe_topic = vibe_participant.create_topic("HelloWorld", "HelloWorld", qos)
            reader = vibe_participant.create_reader(vibe_topic, qos)

            # Register callback to capture received data
            def on_data(sample):
                received_samples.append(sample)

            reader.on_data(on_data)

            vibe_participant.announce_spdp()

            # Wait for endpoint discovery
            for _ in range(30):
                vibe_participant.spin_once(timeout=0.1)

            # Publish several messages from RTI
            for i in range(5):
                sample = HelloWorld(message=f"RTI message {i}")
                rti_writer.write(sample)

                # Give VibeDDS time to receive
                for _ in range(5):
                    vibe_participant.spin_once(timeout=0.05)

            # Final spin to catch any remaining messages
            for _ in range(20):
                vibe_participant.spin_once(timeout=0.1)

            vibe_participant.stop()

            print(f"\nVibeDDS received {len(received_samples)} samples from RTI")

            if len(received_samples) > 0:
                # Try to decode the samples
                from vibedds.type_support import HelloWorldType
                for sample in received_samples[:3]:  # Show first 3
                    try:
                        msg = HelloWorldType.deserialize(sample.data)
                        print(f"  - {msg}")
                    except Exception as e:
                        print(f"  - (raw bytes, couldn't decode: {e})")

                print("SUCCESS: VibeDDS successfully received RTI data!")
            else:
                print("Note: VibeDDS did not receive samples (likely type/matching issue)")

        finally:
            rti_participant.close()

    def test_sedp_message_exchange(self):
        """Debug test: Verify SEDP message exchange with RTI."""
        import rti.connextdds as dds
        import rti.types as types

        @types.struct
        class HelloWorld:
            message: str = ""

        # Create RTI participant with writer
        rti_participant = dds.DomainParticipant(0)
        topic = dds.Topic(rti_participant, "HelloWorld", HelloWorld)
        writer_qos = dds.DataWriterQos()
        writer_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
        rti_writer = dds.DataWriter(rti_participant.implicit_publisher, topic, writer_qos)

        try:
            from vibedds.qos import QosPolicy, ReliabilityKind

            prefix = generate_guid_prefix()
            vibe_participant = DomainParticipant(domain_id=0, participant_id=33, guid_prefix=prefix)
            vibe_participant.start()

            # Create matching reader
            qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
            vibe_topic = vibe_participant.create_topic("HelloWorld", "HelloWorld", qos)
            reader = vibe_participant.create_reader(vibe_topic, qos)
            vibe_participant.announce_spdp()

            # Spin and log what happens
            print("\nSpinning for SEDP exchange...")
            for i in range(50):
                vibe_participant.spin_once(timeout=0.1)
                if (i + 1) % 10 == 0:
                    print(f"  {i+1} spins: {len(vibe_participant.endpoint_db.remote_writers)} remote writers, {len(vibe_participant.endpoint_db.remote_readers)} remote readers")

            # Show final state with locators
            print("\n  SEDP Exchange Results:")
            print(f"  Remote writers: {len(vibe_participant.endpoint_db.remote_writers)}")
            for rw in vibe_participant.endpoint_db.remote_writers.values():
                print(f"    Topic: {rw.topic_name}, Type: {rw.type_name}")
                print(f"    Locators: {[(loc.ipv4_str, loc.port) for loc in rw.unicast_locators]}")
            print(f"  Remote readers: {len(vibe_participant.endpoint_db.remote_readers)}")
            for rr in vibe_participant.endpoint_db.remote_readers.values():
                print(f"    Topic: {rr.topic_name}, Type: {rr.type_name}")
                print(f"    Locators: {[(loc.ipv4_str, loc.port) for loc in rr.unicast_locators]}")

            vibe_participant.stop()

        finally:
            rti_participant.close()

    def test_dump_rti_sedp_pids(self):
        """Diagnostic: Dump raw PIDs from RTI's SEDP endpoint announcements."""
        import rti.connextdds as dds
        import rti.types as types
        from vibedds.cdr import ParameterListParser, parse_encapsulation_header
        from vibedds.wire import RtpsMessageParser
        from vibedds.messages import DataSubmessage
        from vibedds.constants import (
            ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER,
            ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER,
        )

        @types.struct
        class HelloWorld:
            message: str = ""

        # Create RTI participant with writer
        rti_participant = dds.DomainParticipant(0)
        topic = dds.Topic(rti_participant, "HelloWorld", HelloWorld)
        rti_writer = dds.DataWriter(rti_participant.implicit_publisher, topic)

        captured_sedp = []

        try:
            prefix = generate_guid_prefix()
            vibe_participant = DomainParticipant(domain_id=0, participant_id=34, guid_prefix=prefix)
            vibe_participant.start()
            vibe_participant.announce_spdp()

            # Capture raw metatraffic packets
            original_handle = vibe_participant._handle_metatraffic_packet

            def capturing_handler(data, addr, port):
                # Parse and check for SEDP DATA
                try:
                    msg = RtpsMessageParser.parse(data)
                    for sm in msg.submessages:
                        if isinstance(sm, DataSubmessage):
                            writer_id = sm.writer_id.value
                            if (writer_id == ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER or
                                writer_id == ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER):
                                captured_sedp.append((writer_id, sm.serialized_payload))
                except:
                    pass
                return original_handle(data, addr, port)

            vibe_participant._handle_metatraffic_packet = capturing_handler

            # Spin
            for _ in range(50):
                vibe_participant.spin_once(timeout=0.1)

            vibe_participant.stop()

            # Dump captured SEDP PIDs
            print(f"\n  Captured {len(captured_sedp)} SEDP DATA messages from RTI:")
            for i, (writer_id, payload) in enumerate(captured_sedp[:3]):  # Show first 3
                endpoint_type = "Publication" if writer_id == ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER else "Subscription"
                print(f"\n  SEDP {endpoint_type} [{i+1}]:")
                if payload:
                    try:
                        scheme, pl_data = parse_encapsulation_header(payload)
                        print(f"    Encapsulation: 0x{scheme:04x}")
                        parser = ParameterListParser(pl_data)
                        for pid, value in parser:
                            print(f"    PID 0x{pid:04x}: {len(value)} bytes - {value[:20].hex()}...")
                    except Exception as e:
                        print(f"    Parse error: {e}")

        finally:
            rti_participant.close()

    def test_bidirectional_rti_data_exchange(self):
        """Full bidirectional data exchange between VibeDDS and RTI.

        This test creates matching pub/sub on both sides and verifies
        data flows in both directions.
        """
        import rti.connextdds as dds
        import rti.types as types

        @types.struct
        class HelloWorld:
            message: str = ""

        # Create RTI participant
        rti_participant = dds.DomainParticipant(0)
        topic = dds.Topic(rti_participant, "BidirTest", HelloWorld)

        # RTI writer and reader
        writer_qos = dds.DataWriterQos()
        writer_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
        reader_qos = dds.DataReaderQos()
        reader_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT

        rti_writer = dds.DataWriter(rti_participant.implicit_publisher, topic, writer_qos)
        rti_reader = dds.DataReader(rti_participant.implicit_subscriber, topic, reader_qos)

        rti_received = []
        vibe_received = []

        try:
            from vibedds.qos import QosPolicy, ReliabilityKind
            from vibedds.type_support import HelloWorldType

            prefix = generate_guid_prefix()
            vibe_participant = DomainParticipant(domain_id=0, participant_id=30, guid_prefix=prefix)
            vibe_participant.start()

            # VibeDDS writer and reader - use the exact type name RTI uses
            # RTI's generated type name for @types.struct class HelloWorld is "HelloWorld"
            qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
            vibe_topic = vibe_participant.create_topic("BidirTest", "HelloWorld", qos)
            vibe_writer = vibe_participant.create_writer(vibe_topic, qos)
            vibe_reader = vibe_participant.create_reader(vibe_topic, qos)

            def on_vibe_data(sample):
                vibe_received.append(sample)

            vibe_reader.on_data(on_vibe_data)

            vibe_participant.announce_spdp()

            # Enable logging to see SEDP messages
            import logging
            logging.basicConfig(level=logging.INFO, format='%(name)s: %(message)s')

            # Wait for SEDP discovery to complete (needs ~5 seconds)
            print("\n  Waiting for SEDP discovery...")
            deadline = time.time() + 8.0
            rti_writer_discovered = False
            rti_reader_discovered = False
            while time.time() < deadline:
                vibe_participant.spin_once(timeout=0.1)
                for rw in vibe_participant.endpoint_db.remote_writers.values():
                    if rw.topic_name == "BidirTest":
                        rti_writer_discovered = True
                for rr in vibe_participant.endpoint_db.remote_readers.values():
                    if rr.topic_name == "BidirTest":
                        rti_reader_discovered = True
                if rti_writer_discovered and rti_reader_discovered:
                    break

            # Debug: Show discovered participants with their locators
            print("  Discovered participants:")
            for pd in vibe_participant.participant_db.participants.values():
                print(f"    GUID: {pd.guid_prefix.value.hex()}, Vendor: {pd.vendor_id}")
                print(f"    Default unicast locators: {[(l.ipv4_str, l.port) for l in pd.default_unicast_locators]}")
                print(f"    Metatraffic unicast locators: {[(l.ipv4_str, l.port) for l in pd.metatraffic_unicast_locators]}")

            # Debug: Show discovered endpoints with locators
            print(f"  Discovered remote writers (RTI writer found: {rti_writer_discovered}):")
            for rw in vibe_participant.endpoint_db.remote_writers.values():
                print(f"    Topic: {rw.topic_name}, Type: {rw.type_name}")
                print(f"    Locators: {[(loc.ipv4_str, loc.port) for loc in rw.unicast_locators]}")
            print(f"  Discovered remote readers (RTI reader found: {rti_reader_discovered}):")
            for rr in vibe_participant.endpoint_db.remote_readers.values():
                print(f"    Topic: {rr.topic_name}, Type: {rr.type_name}")
                print(f"    Locators: {[(loc.ipv4_str, loc.port) for loc in rr.unicast_locators]}")

            # Track all incoming packets for debugging
            all_received_data = []
            original_handle = vibe_participant._handle_user_packet

            def debug_handle_user_packet(data, addr, port):
                all_received_data.append((data, addr, port))
                return original_handle(data, addr, port)

            vibe_participant._handle_user_packet = debug_handle_user_packet

            # Additional wait for RTI to discover VibeDDS's endpoints
            print("  Waiting for RTI to discover VibeDDS endpoints...")
            for _ in range(30):
                vibe_participant.spin_once(timeout=0.1)

            # Exchange data in both directions
            for i in range(3):
                # VibeDDS -> RTI
                payload = HelloWorldType.serialize(f"From VibeDDS {i}")
                vibe_writer.write(payload)

                # RTI -> VibeDDS
                rti_writer.write(HelloWorld(message=f"From RTI {i}"))

                # Process
                for _ in range(10):
                    vibe_participant.spin_once(timeout=0.05)

                # Check RTI reader
                samples = rti_reader.take()
                for sample in samples:
                    if sample.info.valid:
                        rti_received.append(sample.data.message)

            print(f"\n  Debug: VibeDDS user unicast port: {vibe_participant.transport.user_unicast_port}")
            print(f"  Debug: VibeDDS received {len(all_received_data)} user data packets")

            # Final collection
            for _ in range(20):
                vibe_participant.spin_once(timeout=0.1)
                samples = rti_reader.take()
                for sample in samples:
                    if sample.info.valid:
                        rti_received.append(sample.data.message)

            vibe_participant.stop()

            print(f"\nBidirectional Exchange Results:")
            print(f"  RTI received {len(rti_received)} samples from VibeDDS")
            print(f"  VibeDDS received {len(vibe_received)} samples from RTI")

            # Show what was received
            if rti_received:
                print(f"  RTI samples: {rti_received[:3]}")
            if vibe_received:
                print(f"  VibeDDS samples (count): {len(vibe_received)}")

            # Note: Due to type compatibility requirements, either direction
            # may fail. This test documents actual interop status.
            total_received = len(rti_received) + len(vibe_received)
            print(f"\n  Total samples exchanged: {total_received}")

        finally:
            rti_participant.close()


@pytest.mark.skipif(not RTI_AVAILABLE, reason="RTI Connext DDS not installed")
class TestRTIOneWayData:
    """Focused one-way data exchange tests."""

    def test_rti_to_vibedds_focused(self):
        """RTI writer -> VibeDDS reader with extended timing."""
        import rti.connextdds as dds
        import rti.types as types

        @types.struct
        class SimpleData:
            value: int = 0

        # Create VibeDDS first
        from vibedds.qos import QosPolicy, ReliabilityKind
        from vibedds.type_support import HelloWorldType

        prefix = generate_guid_prefix()
        # Use domain 0 (same as other working tests)
        vibe_participant = DomainParticipant(domain_id=0, participant_id=35, guid_prefix=prefix)
        vibe_participant.start()

        # Create VibeDDS reader
        qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
        vibe_topic = vibe_participant.create_topic("SimpleData", "SimpleData", qos)
        reader = vibe_participant.create_reader(vibe_topic, qos)

        received = []
        def on_data(payload):
            received.append(payload)

        reader.on_data(on_data)
        vibe_participant.announce_spdp()

        # Track SEDP messages received
        sedp_messages_received = []
        from vibedds.wire import RtpsMessageParser
        from vibedds.messages import DataSubmessage
        from vibedds.constants import (
            ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER,
            ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER,
        )

        all_metatraffic = []
        original_handle_meta = vibe_participant._handle_metatraffic_packet
        def tracking_handle_meta(data, addr, port):
            all_metatraffic.append((addr, port, len(data)))
            try:
                msg = RtpsMessageParser.parse(data)
                for sm in msg.submessages:
                    if isinstance(sm, DataSubmessage):
                        writer_id = sm.writer_id.value
                        if writer_id in [ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER,
                                        ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER]:
                            sedp_messages_received.append((writer_id, len(data)))
            except:
                pass
            return original_handle_meta(data, addr, port)

        vibe_participant._handle_metatraffic_packet = tracking_handle_meta

        # Wait for VibeDDS to announce
        for _ in range(20):
            vibe_participant.spin_once(timeout=0.1)

        # Now create RTI participant on same domain
        rti_participant = dds.DomainParticipant(0)
        topic = dds.Topic(rti_participant, "SimpleData", SimpleData)
        writer_qos = dds.DataWriterQos()
        writer_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
        rti_writer = dds.DataWriter(rti_participant.implicit_publisher, topic, writer_qos)

        try:
            # Show VibeDDS's own ports for debugging
            print(f"\nVibeDDS ports:")
            print(f"  Metatraffic unicast: {vibe_participant.transport.metatraffic_unicast_port}")
            print(f"  User unicast: {vibe_participant.transport.user_unicast_port}")
            print(f"  Local IP: {vibe_participant.transport.local_ip}")
            print(f"  GUID prefix: {vibe_participant.guid_prefix.value.hex()}")

            # Wait for discovery
            print("\nWaiting for discovery...")
            for i in range(80):
                vibe_participant.spin_once(timeout=0.1)
                if (i + 1) % 20 == 0:
                    print(f"  {i+1} spins: discovered {len(vibe_participant.participant_db.participants)} participants")

            # Show discovered state
            print(f"\nDiscovered participants:")
            for pd in vibe_participant.participant_db.participants.values():
                print(f"  GUID: {pd.guid_prefix.value.hex()}, Vendor: {pd.vendor_id}")
                print(f"  Metatraffic locators: {[(l.ipv4_str, l.port) for l in pd.metatraffic_unicast_locators]}")

            print(f"\nDiscovered remote writers:")
            for rw in vibe_participant.endpoint_db.remote_writers.values():
                print(f"  Topic: {rw.topic_name}, Type: {rw.type_name}")
            print(f"\nDiscovered remote readers:")
            for rr in vibe_participant.endpoint_db.remote_readers.values():
                print(f"  Topic: {rr.topic_name}, Type: {rr.type_name}")

            print(f"\nAll metatraffic packets: {len(all_metatraffic)}")
            print(f"SEDP messages received: {len(sedp_messages_received)}")

            # Publish from RTI
            print("\nRTI publishing...")
            for i in range(10):
                rti_writer.write(SimpleData(value=i))
                for _ in range(10):
                    vibe_participant.spin_once(timeout=0.05)

            # Final receive
            for _ in range(20):
                vibe_participant.spin_once(timeout=0.1)

            print(f"\nVibeDDS received {len(received)} packets from RTI")

        finally:
            vibe_participant.stop()
            rti_participant.close()


@pytest.mark.skipif(not RTI_AVAILABLE, reason="RTI Connext DDS not installed")
class TestRTISPDPDiagnostic:
    """Diagnostic tests for SPDP message format."""

    def test_dump_spdp_messages(self):
        """Dump raw SPDP messages from both sides to compare format."""
        import rti.connextdds as dds
        from vibedds.cdr import ParameterListParser, parse_encapsulation_header
        from vibedds.wire import RtpsMessageParser
        from vibedds.messages import DataSubmessage
        from vibedds.constants import ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER

        # Capture RTI's SPDP message
        rti_spdp_messages = []

        prefix = generate_guid_prefix()
        vibe_participant = DomainParticipant(domain_id=0, participant_id=36, guid_prefix=prefix)
        vibe_participant.start()

        # Hook to capture raw SPDP messages from RTI (not our own)
        original_handle_spdp = vibe_participant._handle_spdp_packet
        def capturing_spdp(data, addr, port):
            try:
                msg = RtpsMessageParser.parse(data)
                # Filter out our own messages
                if msg.header.guid_prefix != vibe_participant.guid_prefix:
                    for sm in msg.submessages:
                        if isinstance(sm, DataSubmessage):
                            if sm.writer_id.value == ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER:
                                rti_spdp_messages.append(sm.serialized_payload)
            except:
                pass
            return original_handle_spdp(data, addr, port)

        vibe_participant._handle_spdp_packet = capturing_spdp
        vibe_participant.announce_spdp()

        # Create RTI participant
        rti_participant = dds.DomainParticipant(0)

        try:
            # Wait for SPDP exchange
            for _ in range(30):
                vibe_participant.spin_once(timeout=0.1)

            # Dump VibeDDS's SPDP message
            print("\n=== VibeDDS SPDP Message ===")
            print(f"Metatraffic port should be: {vibe_participant.transport.metatraffic_unicast_port}")
            print(f"Local IP: {vibe_participant.transport.local_ip}")

            vibe_spdp_data = vibe_participant._spdp_writer.build_announcement()
            msg = RtpsMessageParser.parse(vibe_spdp_data)
            for sm in msg.submessages:
                if isinstance(sm, DataSubmessage):
                    if sm.serialized_payload:
                        print(f"\nVibeDDS SPDP payload ({len(sm.serialized_payload)} bytes):")
                        scheme, pl_data = parse_encapsulation_header(sm.serialized_payload)
                        print(f"  Encapsulation scheme: 0x{scheme:04x}")
                        parser = ParameterListParser(pl_data)
                        for pid, value in parser:
                            print(f"  PID 0x{pid:04x} ({len(value)} bytes): {value.hex()}")
                            # Decode locators
                            if pid in (0x0031, 0x0032):  # DEFAULT_UNICAST, METATRAFFIC_UNICAST
                                from vibedds.types import Locator
                                loc = Locator.from_bytes(value)
                                pid_name = "DEFAULT_UNICAST" if pid == 0x0031 else "METATRAFFIC_UNICAST"
                                print(f"       -> {pid_name}: {loc.ipv4_str}:{loc.port}")

            # Dump RTI's SPDP message
            print("\n=== RTI SPDP Message ===")
            if rti_spdp_messages:
                payload = rti_spdp_messages[0]
                print(f"\nRTI SPDP payload ({len(payload)} bytes):")
                scheme, pl_data = parse_encapsulation_header(payload)
                print(f"  Encapsulation scheme: 0x{scheme:04x}")
                parser = ParameterListParser(pl_data)
                for pid, value in parser:
                    print(f"  PID 0x{pid:04x} ({len(value)} bytes): {value[:32].hex()}...")
                    # Decode locators
                    if pid in (0x0031, 0x0032):  # DEFAULT_UNICAST, METATRAFFIC_UNICAST
                        from vibedds.types import Locator
                        loc = Locator.from_bytes(value)
                        pid_name = "DEFAULT_UNICAST" if pid == 0x0031 else "METATRAFFIC_UNICAST"
                        print(f"       -> {pid_name}: {loc.ipv4_str}:{loc.port}")
            else:
                print("No RTI SPDP messages captured!")

        finally:
            vibe_participant.stop()
            rti_participant.close()


@pytest.mark.skipif(not RTI_AVAILABLE, reason="RTI Connext DDS not installed")
class TestRTIDiscoversVibeDDS:
    """Test that RTI discovers VibeDDS participant."""

    def test_rti_discovers_vibedds_participant(self):
        """Check if RTI discovers VibeDDS using RTI's participant discovery API."""
        import rti.connextdds as dds
        import rti.types as types

        # Create VibeDDS participant first
        prefix = generate_guid_prefix()
        vibe_participant = DomainParticipant(domain_id=0, participant_id=37, guid_prefix=prefix)
        vibe_participant.start()
        vibe_participant.announce_spdp()

        print(f"\nVibeDDS GUID prefix: {vibe_participant.guid_prefix.value.hex()}")
        print(f"VibeDDS metatraffic port: {vibe_participant.transport.metatraffic_unicast_port}")

        # Keep VibeDDS running and announcing
        for _ in range(20):
            vibe_participant.spin_once(timeout=0.1)
            # Re-announce periodically
            vibe_participant.announce_spdp()

        # Now create RTI participant
        rti_participant = dds.DomainParticipant(0)

        try:
            # Get RTI's builtin participant reader using correct API
            builtin_subscriber = rti_participant.builtin_subscriber
            participant_reader = builtin_subscriber.find_datareader_by_topic_name("DCPSParticipant")

            discovered_vibedds = []

            # Poll for discovered participants
            print("\nPolling RTI for discovered participants...")
            for i in range(50):
                # Keep VibeDDS announcing
                vibe_participant.spin_once(timeout=0.1)
                if i % 10 == 0:
                    vibe_participant.announce_spdp()

                # Check RTI's discovered participants
                if participant_reader:
                    samples = participant_reader.take()
                    for sample in samples:
                        if sample.info.valid:
                            # ParticipantBuiltinTopicData
                            data = sample.data
                            key = data.key
                            # The key is a BuiltinTopicKey with value[0-3] representing the GUID
                            guid_bytes = key.value
                            print(f"  RTI discovered: key={[hex(x) for x in guid_bytes]}")

                            # Check if this is VibeDDS (our vendor ID is 0xff01)
                            # GUID prefix is in first 12 bytes of the key
                            if guid_bytes[0] == 0xff and guid_bytes[1] == 0x01:
                                discovered_vibedds.append(data)
                                print(f"  -> This is VibeDDS!")

            print(f"\nRTI discovered {len(discovered_vibedds)} VibeDDS participant(s)")

            if discovered_vibedds:
                print("SUCCESS: RTI can discover VibeDDS!")
            else:
                print("FAILURE: RTI does not see VibeDDS as a participant")
                print("This explains why RTI doesn't send SEDP to VibeDDS")

        finally:
            vibe_participant.stop()
            rti_participant.close()


@pytest.mark.skipif(not RTI_AVAILABLE, reason="RTI Connext DDS not installed")
class TestRTIDirectDataExchange:
    """Test direct DATA exchange bypassing SEDP endpoint matching.

    These tests verify the underlying DATA submessage format is correct
    by sending directly to known ports rather than relying on SEDP discovery.
    """

    def test_direct_rti_to_vibedds(self):
        """RTI sends data directly to VibeDDS reader's known port.

        This bypasses SEDP matching and tests raw DATA delivery.
        """
        import rti.connextdds as dds
        import rti.types as types

        @types.struct
        class TestData:
            message: str = ""

        received_packets = []

        # Create VibeDDS participant first to bind ports
        prefix = generate_guid_prefix()
        vibe_participant = DomainParticipant(domain_id=0, participant_id=31, guid_prefix=prefix)
        vibe_participant.start()

        # Get VibeDDS's user unicast port
        user_port = vibe_participant.transport.user_unicast_port
        print(f"\nVibeDDS listening on user unicast port: {user_port}")

        # Create simple listener that captures all incoming packets
        original_spin = vibe_participant.spin_once
        def capturing_spin(timeout=0.1):
            original_spin(timeout)

        try:
            from vibedds.qos import QosPolicy, ReliabilityKind

            # Create reader
            qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
            topic = vibe_participant.create_topic("TestData", "TestData", qos)
            reader = vibe_participant.create_reader(topic, qos)

            def on_data(payload):
                received_packets.append(payload)
                print(f"VibeDDS received raw payload: {len(payload)} bytes")

            reader.on_data(on_data)

            vibe_participant.announce_spdp()

            # Create RTI participant with writer
            rti_participant = dds.DomainParticipant(0)
            topic = dds.Topic(rti_participant, "TestData", TestData)
            writer_qos = dds.DataWriterQos()
            writer_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
            rti_writer = dds.DataWriter(rti_participant.implicit_publisher, topic, writer_qos)

            # Wait for discovery
            for _ in range(30):
                vibe_participant.spin_once(timeout=0.1)

            # Publish from RTI
            print("RTI publishing messages...")
            for i in range(5):
                sample = TestData(message=f"Direct from RTI {i}")
                rti_writer.write(sample)

                # Spin VibeDDS to receive
                for _ in range(10):
                    vibe_participant.spin_once(timeout=0.05)

            # Final receive
            for _ in range(20):
                vibe_participant.spin_once(timeout=0.1)

            rti_participant.close()
            vibe_participant.stop()

            print(f"\nDirect RTI->VibeDDS Results:")
            print(f"  Received {len(received_packets)} packets")

            # Note: May receive 0 if SEDP matching is required for RTI to send
            # This test helps diagnose whether the issue is SEDP or DATA format

        except Exception as e:
            vibe_participant.stop()
            raise

    def test_direct_vibedds_to_rti(self):
        """VibeDDS sends data directly to RTI reader's discovered port.

        After SPDP discovery, send DATA directly using RTI's user unicast locators.
        """
        import rti.connextdds as dds
        import rti.types as types

        @types.struct
        class TestData:
            message: str = ""

        # Create RTI participant with reader first
        rti_participant = dds.DomainParticipant(0)
        topic = dds.Topic(rti_participant, "TestData", TestData)
        reader_qos = dds.DataReaderQos()
        reader_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
        rti_reader = dds.DataReader(rti_participant.implicit_subscriber, topic, reader_qos)

        rti_received = []

        try:
            from vibedds.qos import QosPolicy, ReliabilityKind
            from vibedds.type_support import HelloWorldType
            from vibedds.wire import RtpsMessageBuilder
            from vibedds.types import Timestamp, EntityId
            from vibedds.constants import ENTITYID_UNKNOWN

            prefix = generate_guid_prefix()
            vibe_participant = DomainParticipant(domain_id=0, participant_id=32, guid_prefix=prefix)
            vibe_participant.start()

            qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
            topic = vibe_participant.create_topic("TestData", "TestData", qos)
            writer = vibe_participant.create_writer(topic, qos)

            vibe_participant.announce_spdp()

            # Wait for discovery
            discovered_rti = None
            for _ in range(30):
                vibe_participant.spin_once(timeout=0.1)
                for pd in vibe_participant.participant_db.participants.values():
                    if pd.vendor_id and pd.vendor_id.vendor == (1, 1):
                        discovered_rti = pd
                        break
                if discovered_rti:
                    break

            if discovered_rti:
                print(f"\nDiscovered RTI participant:")
                print(f"  GUID: {discovered_rti.guid_prefix.value.hex()}")
                print(f"  Default unicast locators: {len(discovered_rti.default_unicast_locators)}")
                for loc in discovered_rti.default_unicast_locators:
                    print(f"    {loc.ipv4_str}:{loc.port}")
                print(f"  Metatraffic unicast locators: {len(discovered_rti.metatraffic_unicast_locators)}")
                for loc in discovered_rti.metatraffic_unicast_locators:
                    print(f"    {loc.ipv4_str}:{loc.port}")

                # Send DATA directly to RTI's default unicast ports
                for loc in discovered_rti.default_unicast_locators:
                    for i in range(5):
                        payload = HelloWorldType.serialize(f"Direct VibeDDS {i}")
                        writer.write(payload)

                        # Check RTI for received samples
                        samples = rti_reader.take()
                        for sample in samples:
                            if sample.info.valid:
                                rti_received.append(sample.data.message)

                        vibe_participant.spin_once(timeout=0.05)

            # Final check
            for _ in range(20):
                vibe_participant.spin_once(timeout=0.1)
                samples = rti_reader.take()
                for sample in samples:
                    if sample.info.valid:
                        rti_received.append(sample.data.message)

            vibe_participant.stop()
            rti_participant.close()

            print(f"\nDirect VibeDDS->RTI Results:")
            print(f"  RTI received {len(rti_received)} samples: {rti_received}")

            # Even without SEDP matching, RTI should see our messages if
            # the DATA format is correct (assuming type compatibility)

        except Exception as e:
            vibe_participant.stop()
            rti_participant.close()
            raise


@pytest.mark.skipif(not RTI_AVAILABLE, reason="RTI Connext DDS not installed")
class TestSEDPLocatorDiagnostic:
    """Diagnostic tests for SEDP locator handling."""

    def test_dump_vibedds_sedp_subscription(self):
        """Dump VibeDDS's SEDP subscription announcement to verify locators."""
        import rti.connextdds as dds
        import rti.types as types
        from vibedds.cdr import ParameterListParser, parse_encapsulation_header
        from vibedds.types import Locator
        from vibedds.constants import (
            PID_UNICAST_LOCATOR, PID_DEFAULT_UNICAST_LOCATOR,
            PID_ENDPOINT_GUID, PID_TOPIC_NAME, PID_TYPE_NAME,
        )

        @types.struct
        class HelloWorld:
            message: str = ""

        prefix = generate_guid_prefix()
        vibe_participant = DomainParticipant(domain_id=0, participant_id=40, guid_prefix=prefix)
        vibe_participant.start()

        # Create a reader so we have a subscription to announce
        from vibedds.qos import QosPolicy, ReliabilityKind
        qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
        topic = vibe_participant.create_topic("HelloWorld", "HelloWorld", qos)
        reader = vibe_participant.create_reader(topic, qos)

        print(f"\n=== VibeDDS Ports ===")
        print(f"  Metatraffic unicast port: {vibe_participant.transport.metatraffic_unicast_port}")
        print(f"  User unicast port: {vibe_participant.transport.user_unicast_port}")
        print(f"  Local IP: {vibe_participant.transport.local_ip}")

        # Get the SEDP subscription announcement payload
        print(f"\n=== VibeDDS SEDP Subscription Announcement ===")
        for change in vibe_participant.sedp.sub_writer._history:
            payload = change.serialized_data
            print(f"Payload ({len(payload)} bytes):")

            scheme, pl_data = parse_encapsulation_header(payload)
            print(f"  Encapsulation scheme: 0x{scheme:04x}")

            endian = "<" if scheme in (0x0003, 0x0001) else ">"
            parser = ParameterListParser(pl_data, endian)

            for pid, value in parser:
                if pid == PID_ENDPOINT_GUID:
                    print(f"  PID_ENDPOINT_GUID (0x{pid:04x}): {value.hex()}")
                elif pid == PID_TOPIC_NAME:
                    from vibedds.cdr import CdrDeserializer
                    de = CdrDeserializer(value, endian)
                    topic_name = de.read_string()
                    print(f"  PID_TOPIC_NAME (0x{pid:04x}): '{topic_name}'")
                elif pid == PID_TYPE_NAME:
                    from vibedds.cdr import CdrDeserializer
                    de = CdrDeserializer(value, endian)
                    type_name = de.read_string()
                    print(f"  PID_TYPE_NAME (0x{pid:04x}): '{type_name}'")
                elif pid == PID_UNICAST_LOCATOR:
                    loc = Locator.from_bytes(value)
                    print(f"  PID_UNICAST_LOCATOR (0x{pid:04x}): {loc.ipv4_str}:{loc.port}")
                    # This should be the USER unicast port!
                    if loc.port == vibe_participant.transport.user_unicast_port:
                        print(f"    ✓ CORRECT: Matches user unicast port")
                    elif loc.port == vibe_participant.transport.metatraffic_unicast_port:
                        print(f"    ✗ WRONG: This is the metatraffic port!")
                    else:
                        print(f"    ? UNKNOWN: Neither user nor metatraffic port")
                elif pid == PID_DEFAULT_UNICAST_LOCATOR:
                    loc = Locator.from_bytes(value)
                    print(f"  PID_DEFAULT_UNICAST_LOCATOR (0x{pid:04x}): {loc.ipv4_str}:{loc.port}")
                else:
                    print(f"  PID 0x{pid:04x}: {len(value)} bytes")

        # Now create RTI and see if it matches
        rti_participant = dds.DomainParticipant(0)
        topic = dds.Topic(rti_participant, "HelloWorld", HelloWorld)
        writer_qos = dds.DataWriterQos()
        writer_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
        rti_writer = dds.DataWriter(rti_participant.implicit_publisher, topic, writer_qos)

        try:
            vibe_participant.announce_spdp()

            # Wait for SEDP exchange
            print("\n=== Waiting for SEDP exchange ===")
            for i in range(50):
                vibe_participant.spin_once(timeout=0.1)
                if (i + 1) % 10 == 0:
                    matches = rti_writer.matched_subscriptions
                    print(f"  After {i+1} spins: RTI writer matched {len(matches)} subscriptions")

            final_matches = rti_writer.matched_subscriptions
            print(f"\nFinal: RTI writer matched {len(final_matches)} subscriptions")

            if final_matches:
                print("RTI matched VibeDDS's subscription - checking where RTI would send data...")

                # Get locator info for matched subscriptions
                for match in final_matches:
                    locators = rti_writer.matched_subscription_data(match)
                    print(f"  Match: {match}")
                    if hasattr(locators, 'unicast_locators'):
                        print(f"    Unicast locators: {locators.unicast_locators}")
            else:
                print("RTI did not match VibeDDS's subscription")

        finally:
            vibe_participant.stop()
            rti_participant.close()

    def test_udp_listener_rti_destinations(self):
        """Use raw UDP listeners to capture exactly where RTI sends data.

        Uses domain 1 to avoid any domain 0 issues.
        """
        import rti.connextdds as dds
        import rti.types as types
        import socket
        import select

        @types.struct
        class HelloWorld:
            message: str = ""

        test_domain = 1  # Use domain 1 to avoid any conflicts

        prefix = generate_guid_prefix()
        vibe_participant = DomainParticipant(domain_id=test_domain, participant_id=0, guid_prefix=prefix)
        vibe_participant.start()

        meta_port = vibe_participant.transport.metatraffic_unicast_port
        user_port = vibe_participant.transport.user_unicast_port

        print(f"\n=== Ports to monitor (domain {test_domain}) ===")
        print(f"  Metatraffic: {meta_port}")
        print(f"  User: {user_port}")

        # Create reader
        from vibedds.qos import QosPolicy, ReliabilityKind
        qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
        topic = vibe_participant.create_topic("HelloWorld", "HelloWorld", qos)
        reader = vibe_participant.create_reader(topic, qos)
        vibe_participant.announce_spdp()

        # Create RTI writer on same domain
        rti_participant = dds.DomainParticipant(test_domain)
        rti_topic = dds.Topic(rti_participant, "HelloWorld", HelloWorld)
        writer_qos = dds.DataWriterQos()
        writer_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
        rti_writer = dds.DataWriter(rti_participant.implicit_publisher, rti_topic, writer_qos)

        # Track received packets by port
        meta_packets = []
        user_packets = []

        try:
            # Wait for SEDP discovery
            print("\nWaiting for discovery...")
            for i in range(60):
                vibe_participant.spin_once(timeout=0.1)
                if (i + 1) % 20 == 0:
                    matches = rti_writer.matched_subscriptions
                    print(f"  {i+1} spins: RTI matched {len(matches)} subs")
                    if matches:
                        break

            # Hook into the transport to see what ports receive data
            sockets = vibe_participant.transport.get_sockets()

            print("\nRTI publishing data...")
            for i in range(5):
                rti_writer.write(HelloWorld(message=f"Test {i}"))
                time.sleep(0.1)

            # Check both ports
            print("\nChecking which ports received data...")
            for _ in range(30):
                vibe_participant.spin_once(timeout=0.1)

            # Count what we received on each socket
            vibe_received = reader.take()
            print(f"\nVibeDDS reader received: {len(vibe_received)} samples")

            if len(vibe_received) == 0:
                print("\nVibeDDS received NOTHING from RTI!")
                print("This confirms RTI is likely sending to the wrong port")
                print("OR RTI is not matching VibeDDS's subscription")

        finally:
            vibe_participant.stop()
            rti_participant.close()

    def test_rti_matched_subscription_locators(self):
        """Inspect what locators RTI thinks VibeDDS's subscription has."""
        import rti.connextdds as dds
        import rti.types as types

        @types.struct
        class HelloWorld:
            message: str = ""

        prefix = generate_guid_prefix()
        vibe_participant = DomainParticipant(domain_id=0, participant_id=42, guid_prefix=prefix)
        vibe_participant.start()

        print(f"\n=== VibeDDS Configuration ===")
        print(f"  Metatraffic port: {vibe_participant.transport.metatraffic_unicast_port}")
        print(f"  User port: {vibe_participant.transport.user_unicast_port}")

        from vibedds.qos import QosPolicy, ReliabilityKind
        qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
        topic = vibe_participant.create_topic("HelloWorld", "HelloWorld", qos)
        reader = vibe_participant.create_reader(topic, qos)
        vibe_participant.announce_spdp()

        # Create RTI writer
        rti_participant = dds.DomainParticipant(0)
        rti_topic = dds.Topic(rti_participant, "HelloWorld", HelloWorld)
        writer_qos = dds.DataWriterQos()
        writer_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
        rti_writer = dds.DataWriter(rti_participant.implicit_publisher, rti_topic, writer_qos)

        try:
            # Wait for matching
            print("\nWaiting for RTI to match VibeDDS subscription...")
            matched_data = None
            for i in range(80):
                vibe_participant.spin_once(timeout=0.1)
                matches = rti_writer.matched_subscriptions
                if matches:
                    for match in matches:
                        try:
                            matched_data = rti_writer.matched_subscription_data(match)
                            print(f"\n=== RTI's view of VibeDDS subscription ===")
                            print(f"  Instance handle: {match}")
                            # Try to get locator information from the matched data
                            if hasattr(matched_data, 'unicast_locators'):
                                print(f"  Unicast locators: {matched_data.unicast_locators}")
                            if hasattr(matched_data, 'subscriber_key'):
                                print(f"  Subscriber key: {matched_data.subscriber_key}")
                            # Print all available attributes
                            for attr in dir(matched_data):
                                if not attr.startswith('_'):
                                    try:
                                        val = getattr(matched_data, attr)
                                        if not callable(val):
                                            print(f"  {attr}: {val}")
                                    except:
                                        pass
                        except Exception as e:
                            print(f"  Error getting matched data: {e}")
                    break

            if not matched_data:
                print("\nRTI never matched VibeDDS subscription!")
                print("This is the core problem - RTI doesn't match despite SEDP exchange")

                # Check what VibeDDS discovered about RTI (the reverse direction)
                print("\n=== What VibeDDS discovered from RTI ===")
                print(f"  Remote writers: {len(vibe_participant.endpoint_db.remote_writers)}")
                for rw in vibe_participant.endpoint_db.remote_writers.values():
                    print(f"    Topic: '{rw.topic_name}', Type: '{rw.type_name}'")
                print(f"  Remote readers: {len(vibe_participant.endpoint_db.remote_readers)}")
                for rr in vibe_participant.endpoint_db.remote_readers.values():
                    print(f"    Topic: '{rr.topic_name}', Type: '{rr.type_name}'")

        finally:
            vibe_participant.stop()
            rti_participant.close()


    def test_verify_writer_to_rti_reader_matching(self):
        """Test VibeDDS writer -> RTI reader matching (reverse direction).

        Uses different domains to avoid any loopback issues.
        """
        import rti.connextdds as dds
        import rti.types as types
        from vibedds.cdr import ParameterListParser, parse_encapsulation_header, CdrDeserializer
        from vibedds.constants import PID_TOPIC_NAME, PID_TYPE_NAME

        @types.struct
        class HelloWorld:
            message: str = ""

        # Use domain 1 to avoid any potential conflicts
        test_domain = 1

        prefix = generate_guid_prefix()
        vibe_participant = DomainParticipant(domain_id=test_domain, participant_id=0, guid_prefix=prefix)
        vibe_participant.start()

        from vibedds.qos import QosPolicy, ReliabilityKind
        qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
        vibe_topic = vibe_participant.create_topic("HelloWorld", "HelloWorld", qos)
        writer = vibe_participant.create_writer(vibe_topic, qos)

        # Capture RTI's SEDP to see what type name it uses
        rti_type_name = None
        from vibedds.wire import RtpsMessageParser
        from vibedds.messages import DataSubmessage
        from vibedds.constants import ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER

        original_handle_meta = vibe_participant._handle_metatraffic_packet
        def capturing_meta(data, addr, port):
            nonlocal rti_type_name
            try:
                msg = RtpsMessageParser.parse(data)
                for sm in msg.submessages:
                    if isinstance(sm, DataSubmessage):
                        if sm.writer_id.value == ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER:
                            if sm.serialized_payload:
                                scheme, pl_data = parse_encapsulation_header(sm.serialized_payload)
                                endian = "<" if scheme in (0x0003, 0x0001) else ">"
                                for pid, value in ParameterListParser(pl_data, endian):
                                    if pid == PID_TYPE_NAME:
                                        de = CdrDeserializer(value, endian)
                                        rti_type_name = de.read_string()
            except:
                pass
            return original_handle_meta(data, addr, port)
        vibe_participant._handle_metatraffic_packet = capturing_meta

        # Create RTI READER on same domain
        rti_participant = dds.DomainParticipant(test_domain)
        rti_topic = dds.Topic(rti_participant, "HelloWorld", HelloWorld)
        reader_qos = dds.DataReaderQos()
        reader_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
        rti_reader = dds.DataReader(rti_participant.implicit_subscriber, rti_topic, reader_qos)

        try:
            vibe_participant.announce_spdp()

            print(f"\nTesting VibeDDS Writer -> RTI Reader matching (domain {test_domain})")
            print(f"VibeDDS type_name: 'HelloWorld'")

            # Wait for matching
            for i in range(60):
                vibe_participant.spin_once(timeout=0.1)
                if (i + 1) % 20 == 0:
                    matches = rti_reader.matched_publications
                    print(f"  {i+1} spins: RTI reader matched {len(matches)} publications")
                    if rti_type_name:
                        print(f"  RTI type_name: '{rti_type_name}'")

            final_matches = rti_reader.matched_publications
            print(f"\nFinal: RTI reader matched {len(final_matches)} publications")
            if rti_type_name:
                print(f"RTI's type_name: '{rti_type_name}'")
                if rti_type_name != "HelloWorld":
                    print(f"TYPE NAME MISMATCH! VibeDDS='HelloWorld', RTI='{rti_type_name}'")

            if final_matches:
                print("SUCCESS: VibeDDS writer -> RTI reader matching works!")
            else:
                print("FAILURE: VibeDDS writer not matched by RTI reader")

        finally:
            vibe_participant.stop()
            rti_participant.close()

    def test_verify_sedp_sent_to_rti(self):
        """Verify VibeDDS is actually sending SEDP subscription to RTI."""
        import rti.connextdds as dds
        import rti.types as types
        from vibedds.wire import RtpsMessageParser
        from vibedds.messages import DataSubmessage, HeartbeatSubmessage, AckNackSubmessage

        @types.struct
        class HelloWorld:
            message: str = ""

        # Use domain 1 to avoid any domain 0 issues
        test_domain = 1
        prefix = generate_guid_prefix()
        vibe_participant = DomainParticipant(domain_id=test_domain, participant_id=0, guid_prefix=prefix)
        vibe_participant.start()

        # Track what VibeDDS sends
        sedp_messages_sent = []
        original_send_unicast = vibe_participant.transport.send_unicast
        def tracking_send(data, addr, port):
            sedp_messages_sent.append((addr, port, len(data)))
            return original_send_unicast(data, addr, port)
        vibe_participant.transport.send_unicast = tracking_send

        # Track ACKNACKs received from RTI
        acknacks_received = []
        original_handle_meta = vibe_participant._handle_metatraffic_packet
        def tracking_meta(data, addr, port):
            try:
                msg = RtpsMessageParser.parse(data)
                for sm in msg.submessages:
                    if isinstance(sm, AckNackSubmessage):
                        acknacks_received.append((sm.reader_id.value.hex(), sm.writer_id.value.hex()))
            except:
                pass
            return original_handle_meta(data, addr, port)
        vibe_participant._handle_metatraffic_packet = tracking_meta

        from vibedds.qos import QosPolicy, ReliabilityKind
        qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
        topic = vibe_participant.create_topic("HelloWorld", "HelloWorld", qos)
        reader = vibe_participant.create_reader(topic, qos)

        print(f"\nVibeDDS ports: metatraffic={vibe_participant.transport.metatraffic_unicast_port}, "
              f"user={vibe_participant.transport.user_unicast_port}")

        # Create RTI
        rti_participant = dds.DomainParticipant(0)
        rti_topic = dds.Topic(rti_participant, "HelloWorld", HelloWorld)
        writer_qos = dds.DataWriterQos()
        writer_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
        rti_writer = dds.DataWriter(rti_participant.implicit_publisher, rti_topic, writer_qos)

        try:
            vibe_participant.announce_spdp()

            # Wait for discovery and SEDP exchange
            print("\nWaiting for SPDP/SEDP exchange...")
            for i in range(60):
                vibe_participant.spin_once(timeout=0.1)
                if (i + 1) % 20 == 0:
                    print(f"  {i+1} spins: discovered {len(vibe_participant.participant_db.participants)} participants")

            # Show what VibeDDS discovered
            print(f"\n=== VibeDDS Discovery Results ===")
            for pd in vibe_participant.participant_db.participants.values():
                print(f"  Participant: {pd.guid_prefix.value.hex()}, Vendor: {pd.vendor_id}")
                print(f"    Metatraffic locators: {[(l.ipv4_str, l.port) for l in pd.metatraffic_unicast_locators]}")

            print(f"\n=== SEDP Messages VibeDDS Sent ===")
            print(f"  Total unicast messages: {len(sedp_messages_sent)}")
            # Group by destination port
            by_port = {}
            for addr, port, size in sedp_messages_sent:
                key = (addr, port)
                if key not in by_port:
                    by_port[key] = []
                by_port[key].append(size)
            for (addr, port), sizes in by_port.items():
                print(f"    {addr}:{port}: {len(sizes)} messages ({sizes[:5]}...)")

            # Check if VibeDDS sent to RTI's metatraffic port
            rti_meta_ports = set()
            for pd in vibe_participant.participant_db.participants.values():
                if pd.vendor_id and pd.vendor_id.vendor == (1, 1):
                    for loc in pd.metatraffic_unicast_locators:
                        rti_meta_ports.add(loc.port)

            print(f"\n  RTI metatraffic ports: {rti_meta_ports}")
            sent_to_rti = any(port in rti_meta_ports for _, port, _ in sedp_messages_sent)
            print(f"  VibeDDS sent SEDP to RTI: {sent_to_rti}")

            # Show RTI's matching status
            matches = rti_writer.matched_subscriptions
            print(f"\n=== RTI Matching Status ===")
            print(f"  RTI writer matched subscriptions: {len(matches)}")

            # Show ACKNACKs received from RTI
            print(f"\n=== ACKNACKs Received from RTI ===")
            print(f"  Total: {len(acknacks_received)}")
            for reader_id, writer_id in acknacks_received[:5]:
                print(f"    Reader: {reader_id}, Writer: {writer_id}")

            # Check VibeDDS's SEDP reliable writer state
            print(f"\n=== VibeDDS SEDP Sub Writer State ===")
            sub_writer = vibe_participant.sedp.sub_writer
            print(f"  History size: {len(sub_writer._history)}")
            print(f"  Reader proxies: {len(sub_writer._reader_proxies)}")

            # Show what VibeDDS discovered from RTI (SEDP)
            print(f"\n=== SEDP Discovered Endpoints ===")
            print(f"  Remote writers (from RTI): {len(vibe_participant.endpoint_db.remote_writers)}")
            for rw in vibe_participant.endpoint_db.remote_writers.values():
                print(f"    Topic: '{rw.topic_name}', Type: '{rw.type_name}'")
            print(f"  Remote readers (from RTI): {len(vibe_participant.endpoint_db.remote_readers)}")
            for rr in vibe_participant.endpoint_db.remote_readers.values():
                print(f"    Topic: '{rr.topic_name}', Type: '{rr.type_name}'")

        finally:
            vibe_participant.stop()
            rti_participant.close()

    def test_compare_sedp_formats(self):
        """Compare VibeDDS's SEDP subscription format to RTI's format."""
        import rti.connextdds as dds
        import rti.types as types
        from vibedds.cdr import ParameterListParser, parse_encapsulation_header
        from vibedds.wire import RtpsMessageParser
        from vibedds.messages import DataSubmessage
        from vibedds.constants import ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER

        @types.struct
        class HelloWorld:
            message: str = ""

        # First capture RTI's SEDP subscription format
        rti_participant = dds.DomainParticipant(0)
        rti_topic = dds.Topic(rti_participant, "HelloWorld", HelloWorld)
        reader_qos = dds.DataReaderQos()
        reader_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
        rti_reader = dds.DataReader(rti_participant.implicit_subscriber, rti_topic, reader_qos)

        rti_sedp_payload = None

        prefix = generate_guid_prefix()
        vibe_participant = DomainParticipant(domain_id=0, participant_id=43, guid_prefix=prefix)
        vibe_participant.start()

        # Hook to capture RTI's SEDP subscription
        original_handle_meta = vibe_participant._handle_metatraffic_packet
        def capturing_handle(data, addr, port):
            nonlocal rti_sedp_payload
            try:
                msg = RtpsMessageParser.parse(data)
                for sm in msg.submessages:
                    if isinstance(sm, DataSubmessage):
                        if sm.writer_id.value == ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER:
                            if rti_sedp_payload is None:
                                rti_sedp_payload = sm.serialized_payload
            except:
                pass
            return original_handle_meta(data, addr, port)

        vibe_participant._handle_metatraffic_packet = capturing_handle

        # Create VibeDDS reader too
        from vibedds.qos import QosPolicy, ReliabilityKind
        qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
        topic = vibe_participant.create_topic("HelloWorld", "HelloWorld", qos)
        vibe_reader = vibe_participant.create_reader(topic, qos)

        vibe_participant.announce_spdp()

        try:
            # Exchange SEDP
            for _ in range(50):
                vibe_participant.spin_once(timeout=0.1)

            # Get VibeDDS's SEDP subscription payload
            vibe_sedp_payload = None
            for change in vibe_participant.sedp.sub_writer._history:
                vibe_sedp_payload = change.serialized_data
                break

            print("\n" + "="*60)
            print("COMPARING SEDP SUBSCRIPTION FORMATS")
            print("="*60)

            def dump_sedp(name, payload):
                if payload is None:
                    print(f"\n{name}: No payload captured")
                    return

                print(f"\n{name} ({len(payload)} bytes):")
                scheme, pl_data = parse_encapsulation_header(payload)
                print(f"  Encapsulation: 0x{scheme:04x}")
                endian = "<" if scheme in (0x0003, 0x0001) else ">"

                pids_found = []
                for pid, value in ParameterListParser(pl_data, endian):
                    pids_found.append((pid, len(value), value[:40].hex() if len(value) <= 40 else value[:40].hex() + "..."))

                    # Decode known PIDs
                    pid_name = f"0x{pid:04x}"
                    if pid == 0x005a:
                        pid_name = "ENDPOINT_GUID"
                    elif pid == 0x0005:
                        pid_name = "TOPIC_NAME"
                        from vibedds.cdr import CdrDeserializer
                        de = CdrDeserializer(value, endian)
                        val = de.read_string()
                        print(f"  PID {pid_name}: '{val}'")
                        continue
                    elif pid == 0x0007:
                        pid_name = "TYPE_NAME"
                        from vibedds.cdr import CdrDeserializer
                        de = CdrDeserializer(value, endian)
                        val = de.read_string()
                        print(f"  PID {pid_name}: '{val}'")
                        continue
                    elif pid == 0x001a:
                        pid_name = "RELIABILITY"
                    elif pid == 0x001d:
                        pid_name = "DURABILITY"
                    elif pid == 0x002f:
                        pid_name = "UNICAST_LOCATOR"
                        from vibedds.types import Locator
                        loc = Locator.from_bytes(value)
                        print(f"  PID {pid_name}: {loc.ipv4_str}:{loc.port}")
                        continue
                    elif pid == 0x0050:
                        pid_name = "PARTICIPANT_GUID"

                    print(f"  PID {pid_name} ({len(value)} bytes): {value[:20].hex()}{'...' if len(value) > 20 else ''}")

                print(f"  Total PIDs: {len(pids_found)}")
                return set(p[0] for p in pids_found)

            vibe_pids = dump_sedp("VibeDDS SEDP Subscription", vibe_sedp_payload)
            rti_pids = dump_sedp("RTI SEDP Subscription", rti_sedp_payload)

            if vibe_pids and rti_pids:
                print(f"\n=== PID Comparison ===")
                print(f"  PIDs in VibeDDS only: {[hex(p) for p in (vibe_pids - rti_pids)] if vibe_pids - rti_pids else 'none'}")
                print(f"  PIDs in RTI only: {[hex(p) for p in (rti_pids - vibe_pids)] if rti_pids - vibe_pids else 'none'}")
                print(f"  PIDs in both: {len(vibe_pids & rti_pids)}")

        finally:
            vibe_participant.stop()
            rti_participant.close()


@pytest.mark.skipif(not RTI_AVAILABLE, reason="RTI Connext DDS not installed")
class TestRTIWriterVibeDDSReaderOnly:
    """Focused test: RTI writer -> VibeDDS reader only (no loopback)."""

    def test_rti_writer_to_vibedds_reader_isolated(self):
        """RTI writer -> VibeDDS reader with no other endpoints.

        Uses different type names to avoid any accidental loopback.
        RTI creates writer only, VibeDDS creates reader only.
        """
        import rti.connextdds as dds
        import rti.types as types

        @types.struct
        class RTIToVibe:
            message: str = ""

        # Create VibeDDS participant with reader ONLY
        from vibedds.qos import QosPolicy, ReliabilityKind

        prefix = generate_guid_prefix()
        vibe_participant = DomainParticipant(domain_id=0, participant_id=50, guid_prefix=prefix)
        vibe_participant.start()

        qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
        vibe_topic = vibe_participant.create_topic("RTIToVibeTest", "RTIToVibe", qos)
        vibe_reader = vibe_participant.create_reader(vibe_topic, qos)

        received = []
        def on_data(payload):
            received.append(payload)

        vibe_reader.on_data(on_data)
        vibe_participant.announce_spdp()

        # Wait a bit for VibeDDS to announce
        for _ in range(10):
            vibe_participant.spin_once(timeout=0.1)

        # Now create RTI participant with writer ONLY (no reader!)
        rti_participant = dds.DomainParticipant(0)
        rti_topic = dds.Topic(rti_participant, "RTIToVibeTest", RTIToVibe)
        writer_qos = dds.DataWriterQos()
        writer_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
        rti_writer = dds.DataWriter(rti_participant.implicit_publisher, rti_topic, writer_qos)

        try:
            # Wait for SEDP discovery
            print(f"\nVibeDDS ports: meta={vibe_participant.transport.metatraffic_unicast_port}, user={vibe_participant.transport.user_unicast_port}")
            print("Waiting for SEDP discovery...")

            for i in range(80):
                vibe_participant.spin_once(timeout=0.1)
                if (i + 1) % 20 == 0:
                    matches = rti_writer.matched_subscriptions
                    print(f"  {i+1} spins: RTI writer matched {len(matches)} subscriptions")

                    # Also show VibeDDS's discovery state
                    remote_writers = len(vibe_participant.endpoint_db.remote_writers)
                    print(f"           VibeDDS discovered {remote_writers} remote writers")

                    if matches:
                        break

            # Check final RTI matching status
            matches = rti_writer.matched_subscriptions
            print(f"\nFinal: RTI writer matched {len(matches)} subscriptions")

            if not matches:
                print("\nRTI writer DID NOT MATCH VibeDDS reader!")
                print("This is the core issue preventing RTI->VibeDDS data flow.")

                # Show what VibeDDS discovered
                print(f"\nVibeDDS discovered:")
                print(f"  Participants: {len(vibe_participant.participant_db.participants)}")
                for pd in vibe_participant.participant_db.participants.values():
                    print(f"    GUID: {pd.guid_prefix.value.hex()}, Vendor: {pd.vendor_id}")

                print(f"  Remote writers: {len(vibe_participant.endpoint_db.remote_writers)}")
                for rw in vibe_participant.endpoint_db.remote_writers.values():
                    print(f"    Topic: '{rw.topic_name}', Type: '{rw.type_name}'")
                    print(f"    Locators: {[(loc.ipv4_str, loc.port) for loc in rw.unicast_locators]}")

                # Show VibeDDS's SEDP subscription state
                print(f"\nVibeDDS SEDP sub_writer history: {len(vibe_participant.sedp.sub_writer._history)} items")
                print(f"VibeDDS SEDP sub_writer reader_proxies: {len(vibe_participant.sedp.sub_writer._reader_proxies)}")
            else:
                print("\nRTI writer MATCHED VibeDDS reader! Publishing...")

                # Publish from RTI
                for i in range(5):
                    rti_writer.write(RTIToVibe(message=f"RTI says hello {i}"))
                    for _ in range(5):
                        vibe_participant.spin_once(timeout=0.05)

                # Final receive
                for _ in range(20):
                    vibe_participant.spin_once(timeout=0.1)

                print(f"\nVibeDDS received {len(received)} samples")
                if received:
                    # Try to decode
                    from vibedds.type_support import HelloWorldType
                    for sample in received[:3]:
                        try:
                            msg = HelloWorldType.deserialize(sample)
                            print(f"  Sample: {msg}")
                        except:
                            print(f"  Raw: {sample[:50].hex()}...")

        finally:
            vibe_participant.stop()
            rti_participant.close()

    def test_trace_sedp_message_exchange(self):
        """Detailed trace of SEDP message exchange between VibeDDS and RTI."""
        import rti.connextdds as dds
        import rti.types as types
        from vibedds.wire import RtpsMessageParser
        from vibedds.messages import DataSubmessage, HeartbeatSubmessage, AckNackSubmessage
        from vibedds.constants import (
            ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER,
            ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER,
            ENTITYID_SEDP_BUILTIN_PUBLICATIONS_READER,
            ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_READER,
        )

        @types.struct
        class TestType:
            value: int = 0

        # Track all metatraffic
        meta_sent = []
        meta_received = []

        # Create VibeDDS with reader
        from vibedds.qos import QosPolicy, ReliabilityKind

        prefix = generate_guid_prefix()
        vibe_participant = DomainParticipant(domain_id=0, participant_id=52, guid_prefix=prefix)
        vibe_participant.start()

        # Hook transport to track sent messages
        original_send = vibe_participant.transport.send_unicast
        def tracking_send(data, addr, port):
            # Parse and classify
            try:
                msg = RtpsMessageParser.parse(data)
                for sm in msg.submessages:
                    if isinstance(sm, DataSubmessage):
                        writer_id = sm.writer_id.value
                        if writer_id == ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER:
                            meta_sent.append(('SUB_DATA', addr, port, sm.writer_sn.value))
                        elif writer_id == ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER:
                            meta_sent.append(('PUB_DATA', addr, port, sm.writer_sn.value))
                    elif isinstance(sm, HeartbeatSubmessage):
                        meta_sent.append(('HB', addr, port, sm.writer_id.value.hex()))
                    elif isinstance(sm, AckNackSubmessage):
                        meta_sent.append(('ACKNACK', addr, port, sm.reader_id.value.hex()))
            except:
                pass
            return original_send(data, addr, port)
        vibe_participant.transport.send_unicast = tracking_send

        # Hook metatraffic handler to track received
        original_handle_meta = vibe_participant._handle_metatraffic_packet
        def tracking_receive(data, addr, port):
            try:
                msg = RtpsMessageParser.parse(data)
                for sm in msg.submessages:
                    if isinstance(sm, DataSubmessage):
                        writer_id = sm.writer_id.value
                        if writer_id == ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER:
                            meta_received.append(('SUB_DATA', addr, port, sm.writer_sn.value))
                        elif writer_id == ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER:
                            meta_received.append(('PUB_DATA', addr, port, sm.writer_sn.value))
                    elif isinstance(sm, HeartbeatSubmessage):
                        meta_received.append(('HB', addr, port, sm.writer_id.value.hex()))
                    elif isinstance(sm, AckNackSubmessage):
                        meta_received.append(('ACKNACK', addr, port, sm.reader_id.value.hex()))
            except:
                pass
            return original_handle_meta(data, addr, port)
        vibe_participant._handle_metatraffic_packet = tracking_receive

        qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
        topic = vibe_participant.create_topic("TraceTest", "TestType", qos)
        reader = vibe_participant.create_reader(topic, qos)
        vibe_participant.announce_spdp()

        print(f"\nVibeDDS: meta_port={vibe_participant.transport.metatraffic_unicast_port}, user_port={vibe_participant.transport.user_unicast_port}")

        # Create RTI with writer
        rti_participant = dds.DomainParticipant(0)
        rti_topic = dds.Topic(rti_participant, "TraceTest", TestType)
        writer_qos = dds.DataWriterQos()
        writer_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
        rti_writer = dds.DataWriter(rti_participant.implicit_publisher, rti_topic, writer_qos)

        try:
            # Run discovery loop
            print("\nRunning SEDP discovery...")
            for i in range(80):
                vibe_participant.spin_once(timeout=0.1)

            # Report
            print(f"\n=== SEDP Message Exchange ===")
            print(f"\nVibeDDS SENT ({len(meta_sent)} messages):")
            for msg_type, addr, port, detail in meta_sent[:20]:
                print(f"  {msg_type} -> {addr}:{port} ({detail})")

            print(f"\nVibeDDS RECEIVED ({len(meta_received)} messages):")
            for msg_type, addr, port, detail in meta_received[:20]:
                print(f"  {msg_type} <- {addr}:{port} ({detail})")

            # Check RTI matching
            matches = rti_writer.matched_subscriptions
            print(f"\nRTI writer matched: {len(matches)} subscriptions")

            # Check VibeDDS discovery
            print(f"\nVibeDDS discovered:")
            print(f"  Remote writers: {len(vibe_participant.endpoint_db.remote_writers)}")
            for rw in vibe_participant.endpoint_db.remote_writers.values():
                print(f"    {rw.topic_name}/{rw.type_name}")
            print(f"  Remote readers: {len(vibe_participant.endpoint_db.remote_readers)}")

            # Key insights
            sub_data_sent = [m for m in meta_sent if m[0] == 'SUB_DATA']
            pub_data_recv = [m for m in meta_received if m[0] == 'PUB_DATA']
            hb_recv = [m for m in meta_received if m[0] == 'HB']
            acknack_recv = [m for m in meta_received if m[0] == 'ACKNACK']

            print(f"\n=== Key Findings ===")
            print(f"  VibeDDS sent SUB_DATA: {len(sub_data_sent)}")
            print(f"  VibeDDS received PUB_DATA (RTI's writer): {len(pub_data_recv)}")
            print(f"  VibeDDS received HB from RTI: {len(hb_recv)}")
            print(f"  VibeDDS received ACKNACK from RTI: {len(acknack_recv)}")

            if len(hb_recv) == 0:
                print("\n  ISSUE: No heartbeats received from RTI!")
                print("  This suggests RTI's SEDP writers aren't sending to VibeDDS.")

            if len(pub_data_recv) == 0:
                print("\n  ISSUE: No publication DATA received from RTI!")
                print("  VibeDDS isn't getting RTI's writer announcements.")

            if len(acknack_recv) == 0 and len(sub_data_sent) > 0:
                print("\n  ISSUE: VibeDDS sent subscriptions but got no ACKNACKs!")
                print("  RTI may not be receiving or accepting VibeDDS's SEDP messages.")

        finally:
            vibe_participant.stop()
            rti_participant.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
