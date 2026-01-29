#!/usr/bin/env python3
"""Dump the SEDP subscription payload in hex for analysis."""

import struct
from vibedds.participant import DomainParticipant
from vibedds.qos import QosPolicy, ReliabilityKind
from vibedds.sedp import _build_endpoint_data, LocalEndpoint
from vibedds.types import Guid, GuidPrefix, EntityId, Locator
from vibedds.cdr import parse_encapsulation_header, ParameterListParser, PL_CDR_LE, encapsulation_header

# PID names for pretty printing
PID_NAMES = {
    0x0001: "SENTINEL",
    0x0002: "PARTICIPANT_LEASE_DURATION",
    0x0005: "TOPIC_NAME",
    0x0007: "TYPE_NAME",
    0x000F: "DOMAIN_ID",
    0x0015: "PROTOCOL_VERSION",
    0x0016: "VENDORID",
    0x001A: "RELIABILITY",
    0x001B: "LIVELINESS",
    0x001D: "DURABILITY",
    0x001F: "OWNERSHIP",
    0x0023: "DEADLINE",
    0x0025: "DESTINATION_ORDER",
    0x0029: "PARTITION",
    0x0040: "HISTORY",
    0x0041: "RESOURCE_LIMITS",
    0x002f: "UNICAST_LOCATOR",
    0x0030: "MULTICAST_LOCATOR",
    0x0031: "DEFAULT_UNICAST_LOCATOR",
    0x0032: "METATRAFFIC_UNICAST_LOCATOR",
    0x0043: "EXPECTS_INLINE_QOS",
    0x0050: "PARTICIPANT_GUID",
    0x0053: "TYPE_CONSISTENCY_ENFORCEMENT",
    0x005A: "ENDPOINT_GUID",
    0x0058: "BUILTIN_ENDPOINT_SET",
    0x0073: "DATA_REPRESENTATION",
    0x8021: "TYPE_OBJECT",
}

def hex_dump(data: bytes, prefix: str = "  ") -> str:
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{prefix}{i:04x}: {hex_part:<48} {ascii_part}")
    return "\n".join(lines)

def main():
    # Create a fake local endpoint
    guid_prefix = GuidPrefix(bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c]))
    entity_id = EntityId(bytes([0x00, 0x00, 0x01, 0x07]))  # Reader entity
    guid = Guid(guid_prefix, entity_id)

    qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)

    endpoint = LocalEndpoint(
        guid=guid,
        topic_name="HelloWorld",
        type_name="HelloWorld",
        qos=qos,
        is_writer=False,  # Subscription
        unicast_locators=[Locator.from_ipv4("192.168.8.151", 7411)],
    )

    # Build the SEDP payload
    pl_data = _build_endpoint_data(endpoint)
    full_payload = encapsulation_header(PL_CDR_LE) + pl_data

    print("=" * 60)
    print("VibeDDS SEDP SUBSCRIPTION PAYLOAD")
    print("=" * 60)
    print(f"\nTotal length: {len(full_payload)} bytes")
    print(f"\nEncapsulation header: {full_payload[:4].hex()}")

    print("\n--- Raw hex dump ---")
    print(hex_dump(full_payload))

    print("\n--- Parsed parameters ---")
    scheme, pl_bytes = parse_encapsulation_header(full_payload)
    endian = "<" if scheme in (0x0003, 0x0001) else ">"

    for pid, value in ParameterListParser(pl_bytes, endian):
        pid_name = PID_NAMES.get(pid, f"UNKNOWN_0x{pid:04x}")
        print(f"\nPID 0x{pid:04x} ({pid_name}): {len(value)} bytes")
        print(hex_dump(value, "    "))

if __name__ == "__main__":
    main()
