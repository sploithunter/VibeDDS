#!/usr/bin/env python3
"""Test SEDP payload format with different profiles."""

import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from vibedds.sedp import SedpInteropOptions, _build_endpoint_data, LocalEndpoint
from vibedds.types import GuidPrefix, EntityId, Guid, Locator
from vibedds.qos import QosPolicy, ReliabilityKind
from vibedds.cdr import ParameterListParser, parse_encapsulation_header
from vibedds.constants import (
    PID_DATA_REPRESENTATION, PID_TYPE_CONSISTENCY_ENFORCEMENT,
    PID_RELIABILITY, PID_TOPIC_NAME, PID_TYPE_NAME,
)

def test_profile(profile_name: str, env_overrides: dict):
    print(f"\n=== Profile: {profile_name} ===")

    # Set env vars
    for key, value in env_overrides.items():
        os.environ[key] = value

    # Create interop options from env
    opts = SedpInteropOptions.from_env()
    print(f"  xtypes_format: {opts.xtypes_format}")
    print(f"  include_data_representation: {opts.include_data_representation}")
    print(f"  include_type_consistency: {opts.include_type_consistency}")
    print(f"  data_representation_raw: {opts.data_representation_raw.hex() if opts.data_representation_raw else None}")
    print(f"  type_consistency_raw: {opts.type_consistency_raw.hex() if opts.type_consistency_raw else None}")

    # Build a mock reader endpoint
    guid_prefix = GuidPrefix(bytes(range(12)))
    entity_id = EntityId(bytes([0x00, 0x00, 0x01, 0x07]))  # reader
    endpoint = LocalEndpoint(
        guid=Guid(guid_prefix, entity_id),
        topic_name="TestTopic",
        type_name="TestType",
        qos=QosPolicy(reliability=ReliabilityKind.BEST_EFFORT),
        is_writer=False,
        unicast_locators=[Locator.from_ipv4("192.168.1.100", 7411)],
    )

    # Build SEDP payload
    payload = _build_endpoint_data(endpoint, opts)

    # Parse to extract PIDs
    print(f"\n  SEDP payload PIDs:")
    for pid, value in ParameterListParser(payload, "<"):
        if pid == PID_RELIABILITY:
            print(f"    PID_RELIABILITY ({len(value)} bytes): {value.hex()}")
            # Check reliability kind value
            import struct
            kind = struct.unpack("<I", value[:4])[0]
            print(f"      kind = {kind} (should be 0 for BEST_EFFORT)")
        elif pid == PID_DATA_REPRESENTATION:
            print(f"    PID_DATA_REPRESENTATION ({len(value)} bytes): {value.hex()}")
        elif pid == PID_TYPE_CONSISTENCY_ENFORCEMENT:
            print(f"    PID_TYPE_CONSISTENCY_ENFORCEMENT ({len(value)} bytes): {value.hex()}")
        elif pid == PID_TOPIC_NAME:
            print(f"    PID_TOPIC_NAME: present")
        elif pid == PID_TYPE_NAME:
            print(f"    PID_TYPE_NAME: present")

    # Clear env vars
    for key in env_overrides:
        if key in os.environ:
            del os.environ[key]


def main():
    # Test default profile
    test_profile("default (full)", {})

    # Test rti profile
    test_profile("rti", {"VIBEDDS_SEDP_PROFILE": "rti"})

    # Test rti_strict profile
    test_profile("rti_strict", {"VIBEDDS_SEDP_PROFILE": "rti_strict"})

    # Test minimal profile
    test_profile("minimal", {"VIBEDDS_SEDP_PROFILE": "minimal"})

    # Summary
    print("\n=== Expected RTI values (from pcap) ===")
    print(f"  DATA_REPRESENTATION: 010000000000000007000000 (12 bytes)")
    print(f"  TYPE_CONSISTENCY: 0100010100000000 (8 bytes)")
    print(f"  - kind=1 (ALLOW), ignore_seq_bounds=1, ignore_string_bounds=1, others=0")


if __name__ == "__main__":
    main()
