#!/usr/bin/env python3
"""UDP sniffer for RTPS traffic on domain 0.

Captures traffic on:
- Port 7400: SPDP multicast
- Ports 7410-7419: Metatraffic unicast (participant IDs 0-4)
- Ports 7411-7419: User unicast

Usage:
    sudo python scripts/udp_sniffer.py [--duration SECONDS]
"""

import socket
import struct
import sys
import time
import argparse
from datetime import datetime


SPDP_MC_PORT = 7400
META_UC_PORTS = range(7410, 7420)  # participant IDs 0-4


def parse_rtps_header(data: bytes) -> dict | None:
    """Parse RTPS header to extract basic info."""
    if len(data) < 20:
        return None
    if data[:4] != b'RTPS':
        return None

    version_major = data[4]
    version_minor = data[5]
    vendor_id = (data[6], data[7])
    guid_prefix = data[8:20].hex()

    return {
        "version": f"{version_major}.{version_minor}",
        "vendor": f"{vendor_id[0]:02x}{vendor_id[1]:02x}",
        "guid_prefix": guid_prefix,
    }


def parse_submessages(data: bytes) -> list[dict]:
    """Parse submessage headers."""
    if len(data) < 20:
        return []

    submessages = []
    offset = 20  # Skip RTPS header

    while offset + 4 <= len(data):
        sm_id = data[offset]
        sm_flags = data[offset + 1]
        sm_len = struct.unpack_from("<H", data, offset + 2)[0]

        # Map submessage IDs
        sm_names = {
            0x01: "PAD",
            0x06: "ACKNACK",
            0x07: "HEARTBEAT",
            0x08: "GAP",
            0x09: "INFO_TS",
            0x0c: "INFO_SRC",
            0x0d: "INFO_REPLY_IP4",
            0x0e: "INFO_DST",
            0x0f: "INFO_REPLY",
            0x12: "NACK_FRAG",
            0x13: "HEARTBEAT_FRAG",
            0x15: "DATA",
            0x16: "DATA_FRAG",
        }
        sm_name = sm_names.get(sm_id, f"0x{sm_id:02x}")

        # For DATA submessages, try to extract entityId
        entity_info = ""
        if sm_id == 0x15 and offset + 24 <= len(data):  # DATA
            # Skip to reader/writer entity IDs
            reader_eid = data[offset+8:offset+12] if offset+12 <= len(data) else b''
            writer_eid = data[offset+12:offset+16] if offset+16 <= len(data) else b''
            if reader_eid and writer_eid:
                entity_info = f" r={reader_eid.hex()} w={writer_eid.hex()}"

        submessages.append({
            "id": sm_id,
            "name": sm_name,
            "flags": sm_flags,
            "len": sm_len,
            "entity_info": entity_info,
        })

        if sm_len == 0:
            break
        offset += 4 + sm_len

    return submessages


def vendor_name(vendor_id: str) -> str:
    """Return human-readable vendor name."""
    vendors = {
        "0101": "RTI",
        "0102": "PrismTech",
        "0103": "OpenDDS",
        "ff01": "VibeDDS",
    }
    return vendors.get(vendor_id, vendor_id)


def main():
    parser = argparse.ArgumentParser(description="UDP sniffer for RTPS")
    parser.add_argument("--duration", type=int, default=30, help="Capture duration in seconds")
    parser.add_argument("--port", type=int, help="Specific port to listen on")
    parser.add_argument("--all-ports", action="store_true", help="Listen on all RTPS ports")
    args = parser.parse_args()

    # Use raw socket if available, otherwise bind to specific ports
    try:
        # Try raw socket (requires root)
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setblocking(False)
        raw_mode = True
        print("Using raw socket mode (requires sudo)")
    except PermissionError:
        print("Raw socket requires sudo. Using regular UDP sockets instead.")
        print("Note: Will only see packets destined for bound ports, not all traffic.")
        raw_mode = False

        # Create sockets for each port we want to monitor
        sockets = {}
        ports_to_monitor = [7400, 7410, 7411, 7412, 7413, 7414, 7415]

        for port in ports_to_monitor:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                if sys.platform == "darwin":
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                s.bind(("", port))

                # Join multicast for SPDP port
                if port == 7400:
                    mreq = struct.pack("4s4s",
                                      socket.inet_aton("239.255.0.1"),
                                      socket.inet_aton("0.0.0.0"))
                    s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

                s.setblocking(False)
                sockets[port] = s
                print(f"Listening on port {port}")
            except OSError as e:
                print(f"Could not bind to port {port}: {e}")

    print(f"\nCapturing for {args.duration} seconds...")
    print("-" * 80)

    start_time = time.time()
    packet_count = 0

    try:
        while time.time() - start_time < args.duration:
            if raw_mode:
                try:
                    data, addr = sock.recvfrom(65535)
                    # Raw socket includes IP header, skip it
                    ip_header_len = (data[0] & 0x0f) * 4
                    udp_start = ip_header_len
                    src_port = struct.unpack_from(">H", data, udp_start)[0]
                    dst_port = struct.unpack_from(">H", data, udp_start + 2)[0]
                    udp_data = data[udp_start + 8:]

                    # Filter for RTPS ports
                    if dst_port not in [7400] + list(range(7410, 7420)):
                        continue

                    source_addr = addr[0]
                except BlockingIOError:
                    time.sleep(0.01)
                    continue
            else:
                # Poll all sockets
                import select
                readable, _, _ = select.select(list(sockets.values()), [], [], 0.01)
                if not readable:
                    continue

                for sock in readable:
                    try:
                        data, (source_addr, src_port) = sock.recvfrom(65535)
                        dst_port = sock.getsockname()[1]
                        udp_data = data
                        break
                    except BlockingIOError:
                        continue
                else:
                    continue

            packet_count += 1
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]

            rtps = parse_rtps_header(udp_data)
            if rtps:
                vendor = vendor_name(rtps["vendor"])
                submessages = parse_submessages(udp_data)
                sm_summary = " ".join(f"{sm['name']}{sm['entity_info']}" for sm in submessages[:5])

                print(f"{ts} {source_addr}:{src_port} -> :{dst_port} "
                      f"[{vendor}] {rtps['guid_prefix'][:8]}... "
                      f"({len(udp_data)}B) {sm_summary}")
            else:
                print(f"{ts} {source_addr}:{src_port} -> :{dst_port} "
                      f"NON-RTPS ({len(udp_data)}B) {udp_data[:20].hex()}")

    except KeyboardInterrupt:
        print("\nInterrupted")

    print("-" * 80)
    print(f"Captured {packet_count} packets in {time.time() - start_time:.1f}s")


if __name__ == "__main__":
    main()
