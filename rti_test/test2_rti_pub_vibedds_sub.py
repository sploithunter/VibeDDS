#!/usr/bin/env python3
"""Test 2: RTI publisher -> VibeDDS subscriber.

RTI publishes "Hello World from RTI" messages.
VibeDDS subscribes and verifies it receives the correct content.
Confirms no loopback (VibeDDS should NOT receive VibeDDS's own messages).
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import rti.connextdds as dds
from vibedds.participant import DomainParticipant
from vibedds.qos import QosPolicy, ReliabilityKind
from vibedds.type_support import HelloWorldType

EXPECTED_PREFIX = "Hello World from RTI"


def main():
    print("=" * 60)
    print("TEST 2: RTI Publisher -> VibeDDS Subscriber")
    print("=" * 60)
    print()

    # --- RTI publisher ---
    struct_type = dds.StructType("HelloWorld")
    struct_type.add_member(dds.Member("message", dds.StringType()))

    rti_participant = dds.DomainParticipant(domain_id=0)
    rti_topic = dds.DynamicData.Topic(rti_participant, "HelloWorld", struct_type)

    rti_pub = dds.Publisher(rti_participant)
    writer_qos = dds.DataWriterQos()
    writer_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
    rti_writer = dds.DynamicData.DataWriter(rti_pub, rti_topic, writer_qos)
    print("[SETUP] RTI BEST_EFFORT writer created on topic 'HelloWorld'")

    # --- VibeDDS subscriber ---
    dp = DomainParticipant(domain_id=0, participant_id=3)
    dp.start()
    topic = dp.create_topic("HelloWorld", HelloWorldType.TYPE_NAME)
    qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
    reader = dp.create_reader(topic, qos)

    vibe_received = []

    def on_data(payload: bytes):
        try:
            message = HelloWorldType.deserialize(payload)
            vibe_received.append(message)
            print(f"  [VibeDDS RX] {message}")
        except Exception as e:
            print(f"  [VibeDDS RX] Deserialize error: {e}")

    reader.on_data(on_data)
    print("[SETUP] VibeDDS BEST_EFFORT reader created on topic 'HelloWorld'")
    print()

    dp.announce_spdp()

    # --- Run for up to 20 seconds ---
    publish_count = 0
    start = time.time()
    last_publish = 0

    while time.time() - start < 20:
        dp.spin_once(timeout=0.05)

        # Publish from RTI every 2 seconds
        elapsed = time.time() - start
        if int(elapsed) % 2 == 0 and int(elapsed) != last_publish and int(elapsed) > 0:
            last_publish = int(elapsed)
            publish_count += 1
            sample = dds.DynamicData(struct_type)
            msg = f"{EXPECTED_PREFIX} #{publish_count}"
            sample["message"] = msg
            rti_writer.write(sample)
            print(f"  [RTI    TX] {msg}")

    # --- Results ---
    dp.stop()
    del rti_writer
    del rti_participant

    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"  RTI published: {publish_count} messages")
    print(f"  VibeDDS received: {len(vibe_received)} messages")

    # Verify content
    correct = [m for m in vibe_received if m.startswith(EXPECTED_PREFIX)]
    wrong = [m for m in vibe_received if not m.startswith(EXPECTED_PREFIX)]

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
        print("PASS - VibeDDS received RTI messages, no loopback")
    else:
        if len(correct) == 0:
            print("FAIL - VibeDDS received no messages from RTI")
        if len(wrong) > 0:
            print("FAIL - VibeDDS received unexpected/loopback messages")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
