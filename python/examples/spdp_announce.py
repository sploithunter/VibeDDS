#!/usr/bin/env python3
"""Standalone SPDP announcer — sends participant announcements via multicast.

Usage:
    python examples/spdp_announce.py [--domain DOMAIN_ID]

Announce a VibeDDS participant on the DDS domain. Other DDS implementations
(e.g., rtiddsspy) should see this participant appear.
"""

import sys
import os
import time
import argparse
import logging

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibedds.participant import DomainParticipant


def main():
    parser = argparse.ArgumentParser(description="SPDP Announcer")
    parser.add_argument("--domain", type=int, default=0, help="DDS domain ID")
    parser.add_argument("--interval", type=float, default=5.0,
                        help="Announce interval in seconds")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )

    participant = DomainParticipant(domain_id=args.domain)
    participant._spdp_announce_interval = args.interval
    participant.start()

    print(f"SPDP Announcer started on domain {args.domain}")
    print(f"  GUID Prefix: {participant.guid_prefix}")
    print(f"  Local IP: {participant.transport.local_ip}")
    print(f"  Metatraffic port: {participant.transport.metatraffic_unicast_port}")
    print(f"  User data port: {participant.transport.user_unicast_port}")
    print(f"  Announce interval: {args.interval}s")
    print("Press Ctrl+C to stop.\n")

    # Send first announcement immediately
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
