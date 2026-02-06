#!/usr/bin/env python3
"""Diagnostic test for RTI <-> VibeDDS matching.

This script tests whether RTI's DataWriter will match with VibeDDS's DataReader
using different SEDP profiles.
"""

import os
import sys
import time
import struct

# Add vibedds to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "python"))

def test_reliability_enum():
    """Verify ReliabilityKind enum has correct wire format values."""
    from vibedds.qos import ReliabilityKind, serialize_reliability_qos, QosPolicy

    print("=== Testing ReliabilityKind enum values ===")
    print(f"BEST_EFFORT = {int(ReliabilityKind.BEST_EFFORT)}")
    print(f"RELIABLE = {int(ReliabilityKind.RELIABLE)}")

    assert int(ReliabilityKind.BEST_EFFORT) == 0, "BEST_EFFORT should be 0 for wire format"
    assert int(ReliabilityKind.RELIABLE) == 1, "RELIABLE should be 1 for wire format"

    # Test serialization
    qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
    data = serialize_reliability_qos(qos, "<")
    kind = struct.unpack("<I", data[:4])[0]
    print(f"Serialized BEST_EFFORT reliability: {data.hex()}")
    print(f"  kind value: {kind}")
    assert kind == 0, "Serialized BEST_EFFORT kind should be 0"

    qos = QosPolicy(reliability=ReliabilityKind.RELIABLE)
    data = serialize_reliability_qos(qos, "<")
    kind = struct.unpack("<I", data[:4])[0]
    print(f"Serialized RELIABLE reliability: {data.hex()}")
    print(f"  kind value: {kind}")
    assert kind == 1, "Serialized RELIABLE kind should be 1"

    print("PASS: ReliabilityKind enum values are correct\n")


def test_sedp_profile_formats():
    """Compare SEDP payload formats between profiles."""
    from vibedds.qos import (
        serialize_data_representation_qos, serialize_data_representation_qos_rti,
        serialize_type_consistency_enforcement_qos,
        serialize_type_consistency_enforcement_qos_compact,
        DataRepresentationId, TypeConsistencyKind,
    )

    print("=== Testing SEDP profile formats ===")

    # Standard format
    std_datarep = serialize_data_representation_qos([DataRepresentationId.XCDR1])
    std_typecons = serialize_type_consistency_enforcement_qos()
    print(f"Standard DATA_REPRESENTATION ({len(std_datarep)} bytes): {std_datarep.hex()}")
    print(f"Standard TYPE_CONSISTENCY ({len(std_typecons)} bytes): {std_typecons.hex()}")

    # RTI format
    rti_datarep = serialize_data_representation_qos_rti([DataRepresentationId.XCDR1])
    rti_typecons = serialize_type_consistency_enforcement_qos_compact()
    print(f"RTI-style DATA_REPRESENTATION ({len(rti_datarep)} bytes): {rti_datarep.hex()}")
    print(f"RTI-style TYPE_CONSISTENCY ({len(rti_typecons)} bytes): {rti_typecons.hex()}")

    # Expected RTI values from pcap
    expected_datarep = bytes.fromhex("010000000000000007000000")
    expected_typecons = bytes.fromhex("0100010100000000")

    print(f"\nExpected RTI DATA_REPRESENTATION ({len(expected_datarep)} bytes): {expected_datarep.hex()}")
    print(f"Expected RTI TYPE_CONSISTENCY ({len(expected_typecons)} bytes): {expected_typecons.hex()}")

    if rti_datarep == expected_datarep:
        print("PASS: RTI DATA_REPRESENTATION matches expected")
    else:
        print(f"MISMATCH: RTI DATA_REPRESENTATION differs")

    if rti_typecons == expected_typecons:
        print("PASS: RTI TYPE_CONSISTENCY matches expected")
    else:
        print(f"MISMATCH: RTI TYPE_CONSISTENCY differs")

    print()


def test_rti_matching():
    """Test RTI DataWriter matching with VibeDDS DataReader."""
    import logging
    logging.basicConfig(level=logging.WARNING)

    try:
        import rti.connextdds as dds
    except ImportError:
        print("RTI Python API not available, skipping RTI matching test")
        return

    from vibedds.participant import DomainParticipant
    from vibedds.qos import QosPolicy, ReliabilityKind

    topic_name = "TestMatchTopic"
    type_name = "TestType"

    profiles = [
        ("default", {}),
        ("rti", {"VIBEDDS_SEDP_PROFILE": "rti"}),
        ("rti_strict", {"VIBEDDS_SEDP_PROFILE": "rti_strict"}),
    ]

    for profile_name, env_vars in profiles:
        print(f"\n=== Testing profile: {profile_name} ===")

        # Set env vars
        for key, value in env_vars.items():
            os.environ[key] = value

        # Clear any cached interop options
        try:
            from vibedds import sedp
            # Force re-read of env vars
            import importlib
            importlib.reload(sedp)
        except Exception:
            pass

        # Create RTI participant and writer
        rti_participant = dds.DomainParticipant(0)
        rti_topic = dds.DynamicData.Topic(
            rti_participant,
            topic_name,
            dds.DynamicType(
                dds.StructType(type_name, [
                    dds.Member("value", dds.Int32Type()),
                ])
            ),
        )
        rti_writer = dds.DynamicData.DataWriter(
            dds.Publisher(rti_participant),
            rti_topic,
            dds.DataWriterQos(),
        )

        # Create VibeDDS participant and reader
        vibe_participant = DomainParticipant(
            domain_id=0,
            participant_id=5,  # Avoid port conflicts
        )
        vibe_participant.create_reader(
            topic=topic_name,
            type_name=type_name,
            qos=QosPolicy(reliability=ReliabilityKind.BEST_EFFORT),
        )

        # Wait for matching
        print(f"Waiting for RTI/VibeDDS to discover each other...")
        matched = False
        for i in range(30):
            vibe_participant.spin_once(timeout=1.0)
            subs = list(rti_writer.matched_subscriptions)
            if subs:
                print(f"  RTI matched {len(subs)} subscription(s)")
                matched = True
                break
            if i % 5 == 0:
                print(f"  i={i} RTI matched: {len(subs)}")

        if matched:
            print(f"PASS: Profile '{profile_name}' achieved matching")
        else:
            print(f"FAIL: Profile '{profile_name}' did not achieve matching")

        # Cleanup
        vibe_participant.close()
        del rti_writer
        del rti_topic
        del rti_participant

        # Clear env vars
        for key in env_vars:
            if key in os.environ:
                del os.environ[key]

        time.sleep(1)  # Allow cleanup


if __name__ == "__main__":
    test_reliability_enum()
    test_sedp_profile_formats()
    test_rti_matching()
