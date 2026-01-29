#!/usr/bin/env python3
"""Subscribe to ShapeType samples on a topic (e.g. Square) for RTI interop testing."""

import sys
import os
import argparse
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibedds.participant import DomainParticipant
from vibedds.qos import QosPolicy, ReliabilityKind
from vibedds.type_support import ShapeType


def on_data(payload: bytes):
    try:
        data = ShapeType.deserialize(payload)
        fill = data.get("fillKind")
        angle = data.get("angle")
        extra = ""
        if fill is not None or angle is not None:
            extra = f" fillKind={fill} angle={angle}"
        print(
            f"Received: color={data['color']} x={data['x']} y={data['y']} size={data['shapesize']}{extra}"
        )
    except Exception as e:
        print(f"Failed to deserialize: {e}")


def main():
    parser = argparse.ArgumentParser(description="ShapeType Subscriber")
    parser.add_argument("--domain", type=int, default=0)
    parser.add_argument("--participant", type=int, default=0, help="Participant ID (default: 0)")
    parser.add_argument("--topic", default="Square", help="RTI Shapes topic name (Square/Circle/Triangle)")
    parser.add_argument(
        "--partition",
        default="*",
        help="DDS partition name(s), comma-separated (default: *)",
    )
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
    reader = dp.create_reader(topic, qos)
    reader.on_data(on_data)

    print(f"ShapeType Subscriber started on domain {args.domain}")
    print(f"  GUID: {dp.guid_prefix}")
    print(f"  Topic: {topic.name}")
    print("Waiting for data... Press Ctrl+C to stop.\n")

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
