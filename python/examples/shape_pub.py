#!/usr/bin/env python3
"""Publish ShapeType samples on a topic (e.g. Square) for RTI interop testing."""

import sys
import os
import time
import argparse
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibedds.participant import DomainParticipant
from vibedds.qos import QosPolicy, ReliabilityKind
from vibedds.type_support import ShapeType


def main():
    parser = argparse.ArgumentParser(description="ShapeType Publisher")
    parser.add_argument("--domain", type=int, default=0)
    parser.add_argument("--participant", type=int, default=0, help="Participant ID (default: 0)")
    parser.add_argument("--count", type=int, default=0, help="0 = infinite")
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--topic", default="Square", help="RTI Shapes topic name (Square/Circle/Triangle)")
    parser.add_argument("--partition", default="*", help="DDS partition name(s), comma-separated")
    parser.add_argument("--color", default="BLUE", help="Shape color")
    parser.add_argument("--size", type=int, default=30, help="Shape size")
    parser.add_argument("--x", type=int, default=10, help="Start X")
    parser.add_argument("--y", type=int, default=10, help="Start Y")
    parser.add_argument("--dx", type=int, default=5, help="Delta X per sample")
    parser.add_argument("--dy", type=int, default=5, help="Delta Y per sample")
    parser.add_argument("--fill-kind", type=int, default=0, help="FillKind enum value (0=SOLID_FILL)")
    parser.add_argument("--angle", type=int, default=0, help="Angle value")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )

    dp = DomainParticipant(domain_id=args.domain, participant_id=args.participant)
    dp.start()

    topic = dp.create_topic(args.topic, ShapeType.TYPE_NAME)
    qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
    if args.partition:
        qos.partition = [p for p in (part.strip() for part in args.partition.split(",")) if p]
    writer = dp.create_writer(topic, qos)

    print(f"ShapeType Publisher started on domain {args.domain}")
    print(f"  GUID: {dp.guid_prefix}")
    print(f"  Topic: {topic.name}")
    print("Press Ctrl+C to stop.\n")

    dp.announce_spdp()

    x = args.x
    y = args.y
    count = 0
    try:
        while True:
            dp.spin_once(timeout=0.05)
            payload = ShapeType.serialize(
                args.color,
                x,
                y,
                args.size,
                fill_kind=args.fill_kind,
                angle=args.angle,
            )
            writer.write(payload)
            count += 1
            x += args.dx
            y += args.dy
            if args.count > 0 and count >= args.count:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        dp.stop()


if __name__ == "__main__":
    main()
