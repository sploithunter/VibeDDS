#!/usr/bin/env python3
"""Test 1: VibeDDS publisher -> RTI subscriber.

VibeDDS publishes "Hello World from VibeDDS" messages.
RTI subscribes and verifies it receives the correct content.
Confirms no loopback (RTI should NOT receive RTI's own messages).
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import rti.connextdds as dds
from vibedds.participant import DomainParticipant
from vibedds.qos import QosPolicy, ReliabilityKind
from vibedds.type_support import HelloWorldType

EXPECTED_PREFIX = "Hello World from VibeDDS"


def main():
    print("=" * 60)
    print("TEST 1: VibeDDS Publisher -> RTI Subscriber")
    print("=" * 60)
    print()

    # --- RTI subscriber ---
    struct_type = dds.StructType("HelloWorld")
    struct_type.add_member(dds.Member("message", dds.StringType()))

    rti_participant = dds.DomainParticipant(domain_id=0)
    rti_topic = dds.DynamicData.Topic(rti_participant, "HelloWorld", struct_type)

    rti_sub = dds.Subscriber(rti_participant)
    reader_qos = dds.DataReaderQos()
    reader_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
    rti_reader = dds.DynamicData.DataReader(rti_sub, rti_topic, reader_qos)
    print("[SETUP] RTI BEST_EFFORT reader created on topic 'HelloWorld'")

    # --- VibeDDS publisher ---
    dp = DomainParticipant(domain_id=0, participant_id=3)
    dp.start()
    topic = dp.create_topic("HelloWorld", HelloWorldType.TYPE_NAME)
    qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
    writer = dp.create_writer(topic, qos)
    print("[SETUP] VibeDDS BEST_EFFORT writer created on topic 'HelloWorld'")
    print()

    dp.announce_spdp()

    # --- Run for up to 20 seconds ---
    rti_received = []
    publish_count = 0
    start = time.time()
    last_publish = 0

    while time.time() - start < 20:
        dp.spin_once(timeout=0.05)

        # Publish from VibeDDS every 2 seconds
        elapsed = time.time() - start
        if int(elapsed) % 2 == 0 and int(elapsed) != last_publish and int(elapsed) > 0:
            last_publish = int(elapsed)
            publish_count += 1
            msg = f"{EXPECTED_PREFIX} #{publish_count}"
            payload = HelloWorldType.serialize(msg)
            writer.write(payload)
            print(f"  [VibeDDS TX] {msg}")

        # Read RTI samples
        try:
            samples = rti_reader.take()
            for s in samples:
                if s.info.valid:
                    msg = s.data["message"]
                    rti_received.append(msg)
                    print(f"  [RTI    RX] {msg}")
        except Exception:
            pass

    # --- Results ---
    dp.stop()
    del rti_reader
    del rti_participant

    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"  VibeDDS published: {publish_count} messages")
    print(f"  RTI received: {len(rti_received)} messages")

    # Verify content
    correct = [m for m in rti_received if m.startswith(EXPECTED_PREFIX)]
    wrong = [m for m in rti_received if not m.startswith(EXPECTED_PREFIX)]

    print(f"  Correct messages ('{EXPECTED_PREFIX}...'): {len(correct)}")
    print(f"  Wrong/loopback messages: {len(wrong)}")

    if correct:
        print(f"  First: {correct[0]!r}")
        print(f"  Last:  {correct[-1]!r}")
    if wrong:
        for m in wrong:
            print(f"  UNEXPECTED: {m!r}")

    print()
    ok = len(correct) > 0 and len(wrong) == 0
    if ok:
        print("PASS - RTI received VibeDDS messages, no loopback")
    else:
        if len(correct) == 0:
            print("FAIL - RTI received no messages from VibeDDS")
        if len(wrong) > 0:
            print("FAIL - RTI received unexpected/loopback messages")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
