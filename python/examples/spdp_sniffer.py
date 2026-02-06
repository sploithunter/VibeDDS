#!/usr/bin/env python3
"""Sniff SPDP multicast packets and display details."""

import sys
sys.path.insert(0, "/Users/jason/Documents/VibeDDS/python")

import socket
import struct
import time

SPDP_MULTICAST_ADDRESS = "239.255.0.1"
SPDP_PORT = 7400

def sniff_spdp(duration: float = 10.0):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.bind(("", SPDP_PORT))

    # Join multicast
    mreq = struct.pack("4s4s",
                       socket.inet_aton(SPDP_MULTICAST_ADDRESS),
                       socket.inet_aton("0.0.0.0"))
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.settimeout(1.0)

    print(f"Sniffing SPDP on {SPDP_MULTICAST_ADDRESS}:{SPDP_PORT} for {duration}s")

    end_time = time.time() + duration
    seen = {}

    while time.time() < end_time:
        try:
            data, (addr, port) = sock.recvfrom(65536)

            if len(data) >= 20:
                magic = data[0:4]
                vendor = data[6:8]
                prefix = data[8:20]

                key = prefix.hex()
                if key not in seen:
                    seen[key] = (addr, port, vendor.hex(), len(data), time.time())
                    vendor_name = "RTI" if vendor == b"\x01\x01" else "VibeDDS" if vendor == b"\xff\x01" else "Unknown"
                    print(f"[{time.time():.1f}] {vendor_name} ({vendor.hex()}) from {addr}:{port} - {len(data)} bytes - prefix={key}")
                    print(f"  First 40 bytes: {data[:40].hex()}")
        except socket.timeout:
            continue

    sock.close()
    print(f"\nTotal unique SPDP sources: {len(seen)}")
    for key, (addr, port, vendor, size, t) in seen.items():
        print(f"  {key}: {vendor} from {addr}:{port} ({size} bytes)")

if __name__ == "__main__":
    sniff_spdp(10.0)
