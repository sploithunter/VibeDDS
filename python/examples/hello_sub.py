#!/usr/bin/env python3
"""Subscribe to HelloWorld samples on domain 0.

Usage:
    python examples/hello_sub.py [--domain DOMAIN_ID]

Receives HelloWorld messages from any publisher on the domain.
"""

import sys
import os
import argparse
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibedds.participant import DomainParticipant
from vibedds.qos import QosPolicy, ReliabilityKind
from vibedds.type_support import HelloWorldType


def on_data(payload: bytes):
    try:
        message = HelloWorldType.deserialize(payload)
        print(f"Received: {message}")
    except Exception as e:
        print(f"Failed to deserialize: {e}")


def main():
    parser = argparse.ArgumentParser(description="HelloWorld Subscriber")
    parser.add_argument("--domain", type=int, default=0)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )

    dp = DomainParticipant(domain_id=args.domain)
    dp.start()

    topic = dp.create_topic("HelloWorldTopic", HelloWorldType.TYPE_NAME)
    reader = dp.create_reader(topic, QosPolicy(reliability=ReliabilityKind.BEST_EFFORT))
    reader.on_data(on_data)

    print(f"HelloWorld Subscriber started on domain {args.domain}")
    print(f"  GUID: {dp.guid_prefix}")
    print(f"  Topic: {topic.name}")
    print("Waiting for data... Press Ctrl+C to stop.\n")

    # Send initial SPDP announcement
    dp.announce_spdp()

    try:
        while True:
            dp.spin_once(timeout=0.1)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        dp.stop()


if __name__ == "__main__":
    main()
