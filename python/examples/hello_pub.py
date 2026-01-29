#!/usr/bin/env python3
"""Publish HelloWorld samples on domain 0.

Usage:
    python examples/hello_pub.py [--domain DOMAIN_ID] [--count COUNT]

rtiddsspy should display the published samples.
"""

import sys
import os
import time
import argparse
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibedds.participant import DomainParticipant
from vibedds.qos import QosPolicy, ReliabilityKind
from vibedds.type_support import HelloWorldType


def main():
    parser = argparse.ArgumentParser(description="HelloWorld Publisher")
    parser.add_argument("--domain", type=int, default=0)
    parser.add_argument("--participant", type=int, default=0, help="Participant ID (default: 0)")
    parser.add_argument("--count", type=int, default=0, help="0 = infinite")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--topic", default="HelloWorldTopic", help="DDS topic name")
    parser.add_argument(
        "--partition",
        default="",
        help="DDS partition name(s), comma-separated (empty = default)",
    )
    parser.add_argument(
        "--reliable",
        action="store_true",
        help="Offer RELIABLE reliability (default: BEST_EFFORT)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )

    dp = DomainParticipant(domain_id=args.domain, participant_id=args.participant)
    dp.start()

    topic = dp.create_topic(args.topic, HelloWorldType.TYPE_NAME)
    reliability = ReliabilityKind.RELIABLE if args.reliable else ReliabilityKind.BEST_EFFORT
    qos = QosPolicy(reliability=reliability)
    if args.partition:
        qos.partition = [p for p in (part.strip() for part in args.partition.split(",")) if p]
    writer = dp.create_writer(topic, qos)

    print(f"HelloWorld Publisher started on domain {args.domain}")
    print(f"  GUID: {dp.guid_prefix}")
    print(f"  Topic: {topic.name}")
    print("Press Ctrl+C to stop.\n")

    # Send initial SPDP announcement
    dp.announce_spdp()

    try:
        n = 0
        last_write = 0.0
        while True:
            dp.spin_once(timeout=0.05)

            now = time.time()
            if now - last_write >= args.interval:
                n += 1
                message = f"Hello DDS World #{n}"
                payload = HelloWorldType.serialize(message)
                writer.write(payload)
                print(f"Published: {message}")
                last_write = now

                if args.count > 0 and n >= args.count:
                    break
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        dp.stop()


if __name__ == "__main__":
    main()
