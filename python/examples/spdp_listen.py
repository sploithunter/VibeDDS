#!/usr/bin/env python3
"""Standalone SPDP listener — discovers DDS participants on the network.

Usage:
    python examples/spdp_listen.py [--domain DOMAIN_ID]

Listens for SPDP multicast announcements and prints discovered participants.
"""

import sys
import os
import argparse
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibedds.participant import DomainParticipant
from vibedds.spdp import DiscoveredParticipant


def on_discovered(participant: DiscoveredParticipant):
    print(f"\n--- Discovered Participant ---")
    print(f"  GUID Prefix: {participant.guid_prefix}")
    if participant.protocol_version:
        pv = participant.protocol_version
        print(f"  Protocol Version: {pv.major}.{pv.minor}")
    if participant.vendor_id:
        vid = participant.vendor_id.vendor
        print(f"  Vendor ID: 0x{vid[0]:02X}{vid[1]:02X}")
    if participant.lease_duration:
        print(f"  Lease Duration: {participant.lease_duration.to_seconds()}s")
    for loc in participant.default_unicast_locators:
        print(f"  Default Unicast: {loc.ipv4_str}:{loc.port}")
    for loc in participant.metatraffic_unicast_locators:
        print(f"  Metatraffic Unicast: {loc.ipv4_str}:{loc.port}")
    print(f"  Builtin Endpoints: 0x{participant.builtin_endpoints:08X}")


def on_lost(participant: DiscoveredParticipant):
    print(f"\n--- Lost Participant ---")
    print(f"  GUID Prefix: {participant.guid_prefix}")


def main():
    parser = argparse.ArgumentParser(description="SPDP Listener")
    parser.add_argument("--domain", type=int, default=0, help="DDS domain ID")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )

    participant = DomainParticipant(domain_id=args.domain)
    participant.on_participant_discovered(on_discovered)
    participant.on_participant_lost(on_lost)
    participant.start()

    print(f"SPDP Listener started on domain {args.domain}")
    print(f"  GUID Prefix: {participant.guid_prefix}")
    print("Waiting for participants... Press Ctrl+C to stop.\n")

    # Also announce ourselves so others can discover us
    participant.announce_spdp()

    try:
        while True:
            participant.spin_once(timeout=0.5)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        participant.stop()


if __name__ == "__main__":
    main()
