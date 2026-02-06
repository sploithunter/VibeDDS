#!/usr/bin/env python3
"""Systematic diagnostic: figure out WHY RTI writer doesn't match VibeDDS reader.

Tests multiple SEDP configurations to narrow down the issue.
Runs VibeDDS reader + RTI writer in same process (no loopback risk:
RTI only has writer, VibeDDS only has reader).

Usage:
    cd /Users/jason/Documents/VibeDDS
    python rti_test/diagnose_matching.py
"""

import sys
import os
import time
import struct
import threading
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import rti.connextdds as dds
from vibedds.participant import DomainParticipant
from vibedds.sedp import SedpInteropOptions, _build_endpoint_data, LocalEndpoint
from vibedds.qos import QosPolicy, ReliabilityKind, DurabilityKind
from vibedds.type_support import HelloWorldType, HELLOWORLD_TYPE_INFORMATION, HELLOWORLD_TYPE_OBJECT
from vibedds.types import Guid, GuidPrefix, EntityId, Locator
from vibedds.cdr import ParameterListParser, parse_encapsulation_header
from vibedds.constants import (
    PID_ENDPOINT_GUID, PID_TOPIC_NAME, PID_TYPE_NAME,
    PID_RELIABILITY, PID_DURABILITY, PID_UNICAST_LOCATOR,
    PID_DEFAULT_UNICAST_LOCATOR, PID_DATA_REPRESENTATION,
    PID_TYPE_CONSISTENCY_ENFORCEMENT, PID_TYPE_INFORMATION,
    PID_TYPE_OBJECT, PID_PARTICIPANT_GUID, PID_PARTITION,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)
logger = logging.getLogger("diagnose")


def dump_sedp_payload(endpoint: LocalEndpoint, interop: SedpInteropOptions):
    """Build and hex-dump the SEDP subscription announcement."""
    pl_data = _build_endpoint_data(endpoint, interop)

    PID_NAMES = {
        PID_ENDPOINT_GUID: "ENDPOINT_GUID",
        PID_TOPIC_NAME: "TOPIC_NAME",
        PID_TYPE_NAME: "TYPE_NAME",
        PID_RELIABILITY: "RELIABILITY",
        PID_DURABILITY: "DURABILITY",
        PID_UNICAST_LOCATOR: "UNICAST_LOCATOR",
        PID_DEFAULT_UNICAST_LOCATOR: "DEFAULT_UNICAST_LOCATOR",
        PID_DATA_REPRESENTATION: "DATA_REPRESENTATION",
        PID_TYPE_CONSISTENCY_ENFORCEMENT: "TYPE_CONSISTENCY_ENFORCEMENT",
        PID_TYPE_INFORMATION: "TYPE_INFORMATION",
        PID_TYPE_OBJECT: "TYPE_OBJECT",
        PID_PARTICIPANT_GUID: "PARTICIPANT_GUID",
        PID_PARTITION: "PARTITION",
        0x001a: "OWNERSHIP",
        0x001b: "LIVELINESS",
        0x001d: "DESTINATION_ORDER",
        0x0023: "DEADLINE",
        0x0040: "HISTORY",
        0x0015: "PROTOCOL_VERSION",
        0x0016: "VENDORID",
        0x0025: "EXPECTS_INLINE_QOS",
        0x0029: "GROUP_ENTITY_ID",
        0x8000: "RTI_VENDOR_8000",
        0x8002: "RTI_VENDOR_8002",
        0x8004: "RTI_VENDOR_8004",
        0x8009: "RTI_VENDOR_8009",
        0x8015: "RTI_VENDOR_8015",
        0x0013: "RTI_VENDOR_0013",
        0x0018: "RTI_VENDOR_0018",
        0x0060: "RTI_VENDOR_0060",
    }

    print(f"\n  SEDP Parameter List ({len(pl_data)} bytes):")
    for pid, value in ParameterListParser(pl_data, "<"):
        name = PID_NAMES.get(pid, f"0x{pid:04x}")
        if len(value) <= 24:
            print(f"    PID {name} ({len(value)} bytes): {value.hex()}")
        else:
            print(f"    PID {name} ({len(value)} bytes): {value[:24].hex()}...")

    # Specifically show reliability encoding
    for pid, value in ParameterListParser(pl_data, "<"):
        if pid == PID_RELIABILITY:
            kind = struct.unpack("<I", value[:4])[0]
            print(f"\n  >> RELIABILITY kind on wire = {kind} (0=BEST_EFFORT(DDS), 1=RELIABLE(DDS), RTPS: 1=BE, 2=REL)")

    return pl_data


def make_rti_writer():
    """Create an RTI writer-only (no reader to avoid loopback)."""
    struct_type = dds.StructType("HelloWorld")
    struct_type.add_member(dds.Member("message", dds.StringType()))

    participant = dds.DomainParticipant(domain_id=0)
    topic = dds.DynamicData.Topic(participant, "HelloWorld", struct_type)
    publisher = dds.Publisher(participant)
    writer_qos = dds.QosProvider.default.datawriter_qos
    writer = dds.DynamicData.DataWriter(publisher, topic, writer_qos)
    return participant, writer, struct_type


def test_config(name, sedp_options, participant_id=3, timeout=20):
    """Test a specific SEDP configuration against RTI writer.

    Returns number of matched subscriptions RTI sees.
    """
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")

    # Create RTI writer
    rti_participant, rti_writer, struct_type = make_rti_writer()
    print(f"  RTI writer created (reliability: {rti_writer.qos.reliability.kind})")

    # Create VibeDDS participant + reader
    dp = DomainParticipant(
        domain_id=0,
        participant_id=participant_id,
        sedp_options=sedp_options,
    )
    dp.start()
    topic = dp.create_topic("HelloWorld", HelloWorldType.TYPE_NAME)
    qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
    reader = dp.create_reader(topic, qos)

    print(f"  VibeDDS reader created (guid: {dp.guid_prefix})")
    print(f"  VibeDDS user_unicast_port: {dp.transport.user_unicast_port}")

    # Dump the SEDP subscription announcement
    local_ep = LocalEndpoint(
        guid=reader.guid,
        topic_name="HelloWorld",
        type_name="HelloWorld",
        qos=qos,
        is_writer=False,
        unicast_locators=[
            Locator.from_ipv4(dp.transport.local_ip, dp.transport.user_unicast_port),
        ],
        type_information=topic.type_information,
        type_object=topic.type_object,
    )
    dump_sedp_payload(local_ep, sedp_options)

    # Send initial SPDP
    dp.announce_spdp()

    # Run discovery loop
    matched = 0
    start = time.time()
    publish_count = 0
    while time.time() - start < timeout:
        dp.spin_once(timeout=0.1)

        # Publish from RTI periodically
        if int(time.time() - start) > publish_count:
            publish_count = int(time.time() - start)
            sample = dds.DynamicData(struct_type)
            sample["message"] = f"Hello from RTI #{publish_count}"
            rti_writer.write(sample)

        # Check RTI matched subscriptions
        try:
            m = rti_writer.matched_subscriptions
            if len(m) != matched:
                matched = len(m)
                print(f"\n  >>> RTI matched_subscriptions changed to {matched} at t={time.time()-start:.1f}s")
                for sub in m:
                    try:
                        data = rti_writer.matched_subscription_data(sub)
                        print(f"      Matched: topic={data.topic_name}, type={data.type_name}")
                    except Exception as e:
                        print(f"      Matched: handle={sub}, error: {e}")
        except:
            pass

        # Check RTI incompatible QoS
        try:
            status = rti_writer.offered_incompatible_qos_status
            if status.total_count > 0:
                print(f"  >>> RTI INCOMPATIBLE QOS: count={status.total_count}, last_policy={status.last_policy_id}")
        except:
            pass

        # Early exit if matched
        if matched > 0:
            # Wait a bit more to see if data arrives
            time.sleep(2)
            break

    # Check if VibeDDS received any data
    print(f"\n  Result: RTI matched_subscriptions = {matched}")

    # Cleanup
    dp.stop()
    del rti_writer
    del rti_participant
    time.sleep(1)  # Let sockets release

    return matched


def main():
    print("RTI→VibeDDS Matching Diagnostic")
    print("================================")
    print("Testing different SEDP configurations to find what RTI needs.\n")

    results = {}

    # Test 1: Default "full" profile (current behavior)
    opts1 = SedpInteropOptions()
    opts1.profile = "full"
    results["full (default)"] = test_config("Full profile (default)", opts1)

    # Test 2: No TYPE_INFORMATION (skip XTypes type checking)
    opts2 = SedpInteropOptions()
    opts2.include_type_information = False
    results["no TYPE_INFO"] = test_config("No TYPE_INFORMATION", opts2, participant_id=4)

    # Test 3: No TYPE_INFORMATION, no DATA_REPRESENTATION, no TYPE_CONSISTENCY
    opts3 = SedpInteropOptions()
    opts3.include_type_information = False
    opts3.include_data_representation = False
    opts3.include_type_consistency = False
    results["no XTypes"] = test_config("No XTypes PIDs at all", opts3, participant_id=5)

    # Test 4: With TYPE_OBJECT (RTI's own TypeObject blob)
    opts4 = SedpInteropOptions()
    opts4.include_type_object = True
    results["with TYPE_OBJECT"] = test_config("Full + TYPE_OBJECT", opts4, participant_id=6)

    # Test 5: RTI profile (all RTI-specific PIDs)
    opts5 = SedpInteropOptions()
    opts5.profile = "rti"
    # Apply rti profile settings
    opts5.include_participant_guid = True
    opts5.include_protocol_vendor = True
    opts5.include_extended_qos = True
    opts5.include_partition = True
    opts5.include_unicast_locator = True
    opts5.locator_pid = "endpoint"
    opts5.include_data_representation = True
    opts5.include_type_consistency = True
    opts5.include_type_information = True
    opts5.include_type_object = True
    opts5.xtypes_format = "rti"
    opts5.data_representation_raw = bytes.fromhex("010000000000000007000000")
    opts5.type_consistency_raw = bytes.fromhex("0100010100000000")
    opts5.include_rti_vendor_pids = True
    opts5.include_rti_pid_8002_guid = True
    opts5.rti_pid_8000 = bytes.fromhex("07030005")
    opts5.rti_pid_8009 = bytes.fromhex("00000000")
    opts5.rti_pid_8015 = bytes.fromhex("0100000000000000")
    opts5.rti_pid_0018 = bytes.fromhex("ffffffff")
    results["rti profile"] = test_config("RTI profile (vendor PIDs)", opts5, participant_id=7)

    # Test 6: Minimal - just the basics
    opts6 = SedpInteropOptions()
    opts6.profile = "minimal"
    opts6.include_participant_guid = False
    opts6.include_protocol_vendor = False
    opts6.include_extended_qos = False
    opts6.include_partition = False
    opts6.include_data_representation = False
    opts6.include_type_consistency = False
    opts6.include_type_information = False
    opts6.include_type_object = False
    results["minimal"] = test_config("Minimal (endpoint_guid + topic + type + reliability + durability + locator)", opts6, participant_id=8)

    # Summary
    print(f"\n\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for name, matched in results.items():
        status = "MATCHED" if matched > 0 else "NO MATCH"
        print(f"  {name:30s} → {status} ({matched})")

    print("\nDone.")


if __name__ == "__main__":
    main()
