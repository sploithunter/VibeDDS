#!/usr/bin/env python3
"""Interop diagnostic: send SPDP announcements and capture what RTI sends back.

Run this script and rtiddsspy simultaneously:
  Terminal 1:  python tests/test_interop_rtiddsspy.py
  Terminal 2:  rtiddsspy -domainId 0 -transport 1
"""

import sys
import os
import time
import socket
import struct
import select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibedds.participant import DomainParticipant, generate_guid_prefix
from vibedds.spdp import SPDPWriter, SPDPReader, DiscoveredParticipant
from vibedds.wire import RtpsMessageParser
from vibedds.messages import DataSubmessage
from vibedds.constants import SPDP_MULTICAST_ADDRESS, spdp_multicast_port


def hexdump(data: bytes, prefix: str = "  ") -> str:
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        hex_part = ' '.join(f'{b:02x}' for b in chunk)
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        lines.append(f"{prefix}{i:04x}  {hex_part:<48s}  {ascii_part}")
    return '\n'.join(lines)


def main():
    prefix = generate_guid_prefix()
    print(f"Our GUID prefix: {prefix}")

    dp = DomainParticipant(domain_id=0, participant_id=0, guid_prefix=prefix)
    dp.start()

    discovered = []
    def on_discovered(p: DiscoveredParticipant):
        discovered.append(p)
        print(f"\n=== Discovered participant ===")
        print(f"  GUID prefix: {p.guid_prefix}")
        if p.protocol_version:
            print(f"  Protocol version: {p.protocol_version.major}.{p.protocol_version.minor}")
        if p.vendor_id:
            print(f"  Vendor ID: 0x{p.vendor_id.vendor[0]:02x}{p.vendor_id.vendor[1]:02x}")
        if p.lease_duration:
            print(f"  Lease: {p.lease_duration.to_seconds()}s")
        for loc in p.default_unicast_locators:
            print(f"  Default unicast: {loc.ipv4_str}:{loc.port}")
        for loc in p.metatraffic_unicast_locators:
            print(f"  Metatraffic unicast: {loc.ipv4_str}:{loc.port}")
        print(f"  Builtin endpoints: 0x{p.builtin_endpoints:08x}")

    dp.on_participant_discovered(on_discovered)

    # Build and examine our SPDP announcement
    announcement = dp._spdp_writer.build_announcement()
    print(f"\nOur SPDP announcement ({len(announcement)} bytes):")
    print(hexdump(announcement))

    # Parse our own announcement to verify
    parsed = SPDPReader.parse_announcement(announcement)
    if parsed:
        print(f"\nSelf-parse OK:")
        print(f"  Protocol: {parsed.protocol_version.major}.{parsed.protocol_version.minor}")
        print(f"  Vendor: 0x{parsed.vendor_id.vendor[0]:02x}{parsed.vendor_id.vendor[1]:02x}")
        print(f"  Locators: {len(parsed.default_unicast_locators)} default, "
              f"{len(parsed.metatraffic_unicast_locators)} metatraffic")

    print(f"\nSending SPDP announcements every 2s for 20s...")
    print(f"Listening on multicast {SPDP_MULTICAST_ADDRESS}:{spdp_multicast_port(0)}")
    print(f"Waiting for rtiddsspy or other participants...\n")

    # Also set up a raw socket to capture all incoming multicast traffic
    raw_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    raw_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    raw_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    raw_sock.bind(("", 7400))
    mreq = struct.pack("4s4s",
                        socket.inet_aton(SPDP_MULTICAST_ADDRESS),
                        socket.inet_aton("0.0.0.0"))
    raw_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    raw_sock.setblocking(False)

    start = time.time()
    announce_count = 0

    while time.time() - start < 20:
        # Announce every 2 seconds
        elapsed = time.time() - start
        if announce_count == 0 or elapsed > announce_count * 2:
            dp.announce_spdp()
            announce_count += 1
            print(f"[{elapsed:.1f}s] Sent SPDP announcement #{announce_count}")

        dp.spin_once(timeout=0.1)

        # Also check raw socket for any incoming traffic
        try:
            data, (addr, port) = raw_sock.recvfrom(65536)
            if data[:4] == b'RTPS':
                # Don't print our own
                try:
                    msg = RtpsMessageParser.parse(data)
                    if msg.header.guid_prefix != prefix:
                        print(f"\n[{elapsed:.1f}s] Received RTPS from {addr}:{port} "
                              f"({len(data)} bytes):")
                        print(f"  GUID prefix: {msg.header.guid_prefix}")
                        print(f"  Version: {msg.header.version.major}.{msg.header.version.minor}")
                        print(f"  Vendor: 0x{msg.header.vendor_id.vendor[0]:02x}"
                              f"{msg.header.vendor_id.vendor[1]:02x}")
                        print(f"  Submessages: {len(msg.submessages)}")
                        for i, sm in enumerate(msg.submessages):
                            print(f"    [{i}] {type(sm).__name__}")
                except Exception as e:
                    print(f"  Parse error: {e}")
                    print(hexdump(data[:64]))
            elif data[:4] == b'RTPX':
                # RTI extension
                pass  # ignore silently
        except BlockingIOError:
            pass

    raw_sock.close()
    dp.stop()

    if discovered:
        print(f"\nTotal discovered: {len(discovered)} participants")
    else:
        print("\nNo participants discovered. Is rtiddsspy running?")


if __name__ == "__main__":
    main()
