#!/usr/bin/env python3
"""Debug script to capture and analyze SPDP packets from both VibeDDS and RTI."""

import sys
sys.path.insert(0, "/Users/jason/Documents/VibeDDS/python")

import socket
import struct
import time
import threading
from vibedds.constants import SPDP_MULTICAST_ADDRESS, spdp_multicast_port
from vibedds.types import GuidPrefix, Locator
from vibedds.spdp import SPDPWriter, SPDPReader
from vibedds.cdr import ParameterListParser, parse_encapsulation_header

# PID constants for display
PID_NAMES = {
    0x0015: "PROTOCOL_VERSION",
    0x0016: "VENDORID",
    0x0050: "PARTICIPANT_GUID",
    0x0002: "PARTICIPANT_LEASE_DURATION",
    0x002F: "UNICAST_LOCATOR",  # Endpoint-level
    0x0030: "MULTICAST_LOCATOR",  # Endpoint-level
    0x0031: "DEFAULT_UNICAST_LOCATOR",  # Participant-level
    0x0032: "METATRAFFIC_UNICAST_LOCATOR",
    0x0033: "METATRAFFIC_MULTICAST_LOCATOR",
    0x0048: "DEFAULT_MULTICAST_LOCATOR",
    0x0058: "BUILTIN_ENDPOINT_SET",
    0x000F: "DOMAIN_ID",
    0x0059: "DOMAIN_TAG",
    0x0062: "PARTICIPANT_SECURITY_INFO",
    0x0001: "SENTINEL",
    0x0044: "PARTICIPANT_BUILTIN_ENDPOINTS",
    0x0027: "PROPERTY_LIST",
    0x0073: "TYPE_INFORMATION",
    0x8000: "RTI_VENDOR_SPECIFIC_8000",
    0x8001: "RTI_VENDOR_SPECIFIC_8001",
    0x800F: "RTI_VENDOR_SPECIFIC_800F",
    0x8010: "RTI_VENDOR_SPECIFIC_8010",
}


def format_locator(data: bytes) -> str:
    """Format locator bytes for display."""
    if len(data) < 24:
        return data.hex()
    kind = struct.unpack("<i", data[0:4])[0]
    port = struct.unpack("<I", data[4:8])[0]
    addr = data[8:24]
    if kind == 1:  # UDPv4
        ip = ".".join(str(b) for b in addr[12:16])
        return f"UDPv4 {ip}:{port}"
    return f"kind={kind} port={port} addr={addr.hex()}"


def analyze_spdp_payload(data: bytes, source: str) -> None:
    """Parse and display SPDP payload details."""
    print(f"\n{'='*60}")
    print(f"SPDP from {source}")
    print(f"Total length: {len(data)} bytes")
    print(f"{'='*60}")

    # Parse RTPS header
    if len(data) < 20:
        print(f"Too short for RTPS header")
        return

    magic = data[0:4]
    version = data[4:6]
    vendor = data[6:8]
    guid_prefix = data[8:20]

    print(f"RTPS magic: {magic}")
    print(f"Version: {version[0]}.{version[1]}")
    print(f"Vendor ID: {vendor.hex()}")
    print(f"GUID prefix: {guid_prefix.hex()}")

    # Find DATA submessage (ID=0x15)
    offset = 20
    while offset < len(data):
        if offset + 4 > len(data):
            break
        sm_id = data[offset]
        sm_flags = data[offset + 1]
        sm_len = struct.unpack("<H", data[offset+2:offset+4])[0]

        print(f"\nSubmessage: id=0x{sm_id:02x} flags=0x{sm_flags:02x} len={sm_len}")

        if sm_id == 0x15:  # DATA
            # Parse DATA submessage
            sm_data = data[offset+4:offset+4+sm_len]
            if len(sm_data) >= 20:
                extra_flags = struct.unpack("<H", sm_data[0:2])[0]
                octets_to_inline_qos = struct.unpack("<H", sm_data[2:4])[0]
                reader_id = sm_data[4:8]
                writer_id = sm_data[8:12]
                seq_num = struct.unpack("<q", sm_data[12:20])[0]

                print(f"  Extra flags: 0x{extra_flags:04x}")
                print(f"  Octets to inline QoS: {octets_to_inline_qos}")
                print(f"  Reader ID: {reader_id.hex()}")
                print(f"  Writer ID: {writer_id.hex()}")
                print(f"  Sequence number: {seq_num}")

                # Payload starts after fixed fields
                payload_start = 20
                if sm_flags & 0x02:  # Q flag - inline QoS present
                    # Skip inline QoS (find sentinel)
                    qos_offset = payload_start
                    while qos_offset + 4 <= len(sm_data):
                        pid = struct.unpack("<H", sm_data[qos_offset:qos_offset+2])[0]
                        plen = struct.unpack("<H", sm_data[qos_offset+2:qos_offset+4])[0]
                        if pid == 0x0001:  # Sentinel
                            payload_start = qos_offset + 4
                            break
                        qos_offset += 4 + plen

                if sm_flags & 0x04:  # D flag - data present
                    payload = sm_data[payload_start:]
                    analyze_parameter_list(payload)

        offset += 4 + sm_len


def analyze_parameter_list(payload: bytes) -> None:
    """Analyze the PL_CDR payload."""
    if len(payload) < 4:
        print(f"  Payload too short: {payload.hex()}")
        return

    encap = struct.unpack("<H", payload[0:2])[0]
    options = struct.unpack("<H", payload[2:4])[0]
    print(f"\n  Encapsulation: 0x{encap:04x} options=0x{options:04x}")

    pl_data = payload[4:]
    offset = 0
    param_count = 0

    while offset + 4 <= len(pl_data):
        pid = struct.unpack("<H", pl_data[offset:offset+2])[0]
        plen = struct.unpack("<H", pl_data[offset+2:offset+4])[0]

        if pid == 0x0001:  # Sentinel
            print(f"  [{param_count}] SENTINEL")
            break

        if offset + 4 + plen > len(pl_data):
            print(f"  [{param_count}] PID=0x{pid:04x} len={plen} - TRUNCATED")
            break

        value = pl_data[offset+4:offset+4+plen]
        pid_name = PID_NAMES.get(pid, f"UNKNOWN_0x{pid:04x}")

        # Format value based on PID type
        if pid in (0x002F, 0x0030, 0x0031, 0x0032, 0x0033, 0x0048):  # Locators
            value_str = format_locator(value)
        elif pid == 0x0050:  # GUID
            value_str = value.hex()
        elif pid == 0x0058:  # BUILTIN_ENDPOINT_SET
            be = struct.unpack("<I", value[:4])[0]
            value_str = f"0x{be:08x}"
        elif pid == 0x0016:  # VENDORID
            value_str = f"{value[0]:02x}{value[1]:02x}"
        elif pid == 0x0015:  # PROTOCOL_VERSION
            value_str = f"{value[0]}.{value[1]}"
        elif pid == 0x000F:  # DOMAIN_ID
            value_str = str(struct.unpack("<I", value[:4])[0])
        elif pid == 0x0002:  # LEASE_DURATION
            secs = struct.unpack("<i", value[:4])[0]
            frac = struct.unpack("<I", value[4:8])[0]
            value_str = f"{secs}s + {frac} frac"
        else:
            value_str = value.hex() if len(value) <= 32 else value[:32].hex() + "..."

        print(f"  [{param_count}] {pid_name}: {value_str}")
        param_count += 1
        offset += 4 + plen


def capture_spdp_multicast(duration: float = 10.0) -> None:
    """Capture SPDP packets from multicast for analysis."""
    domain_id = 0
    port = spdp_multicast_port(domain_id)

    print(f"Listening on {SPDP_MULTICAST_ADDRESS}:{port} for {duration} seconds...")
    print("Start RTI publisher and VibeDDS subscriber to capture SPDP packets")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.bind(("", port))

    # Join multicast
    mreq = struct.pack("4s4s",
                       socket.inet_aton(SPDP_MULTICAST_ADDRESS),
                       socket.inet_aton("0.0.0.0"))
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.settimeout(1.0)

    seen_prefixes = set()
    end_time = time.time() + duration

    try:
        while time.time() < end_time:
            try:
                data, (addr, src_port) = sock.recvfrom(65536)

                # Extract GUID prefix for dedup
                if len(data) >= 20:
                    prefix = data[8:20]
                    vendor = data[6:8]

                    key = (prefix, vendor.hex())
                    if key not in seen_prefixes:
                        seen_prefixes.add(key)

                        # Identify source
                        if vendor == bytes([0x01, 0x01]):
                            source = f"RTI ({addr}:{src_port})"
                        elif vendor == bytes([0xFF, 0x01]):
                            source = f"VibeDDS ({addr}:{src_port})"
                        else:
                            source = f"Unknown vendor {vendor.hex()} ({addr}:{src_port})"

                        analyze_spdp_payload(data, source)

            except socket.timeout:
                continue
    finally:
        sock.close()

    print(f"\nCaptured {len(seen_prefixes)} unique SPDP announcements")


def generate_vibedds_spdp() -> None:
    """Generate and display a VibeDDS SPDP packet."""
    import os
    guid_prefix = GuidPrefix(os.urandom(12))

    writer = SPDPWriter(
        guid_prefix=guid_prefix,
        local_ip="192.168.1.100",  # Example IP
        metatraffic_unicast_port=7410,
        user_unicast_port=7411,
        domain_id=0,
    )

    packet = writer.build_announcement()
    print("\nGenerated VibeDDS SPDP packet:")
    analyze_spdp_payload(packet, "VibeDDS (local)")

    print(f"\nRaw hex ({len(packet)} bytes):")
    for i in range(0, len(packet), 32):
        print(f"  {packet[i:i+32].hex()}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true", help="Capture SPDP from network")
    parser.add_argument("--generate", action="store_true", help="Generate VibeDDS SPDP")
    parser.add_argument("--duration", type=float, default=10.0, help="Capture duration in seconds")
    args = parser.parse_args()

    if args.capture:
        capture_spdp_multicast(args.duration)
    elif args.generate:
        generate_vibedds_spdp()
    else:
        # Default: do both
        generate_vibedds_spdp()
        print("\n" + "="*60)
        print("Now capturing from network...")
        print("="*60)
        capture_spdp_multicast(args.duration)
