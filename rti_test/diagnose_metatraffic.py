#!/usr/bin/env python3
"""Focused diagnostic: trace ALL metatraffic between VibeDDS and RTI.

Shows every RTPS submessage received on metatraffic port to identify
why RTI doesn't match VibeDDS's reader.

Usage:
    cd /Users/jason/Documents/VibeDDS
    python rti_test/diagnose_metatraffic.py
"""

import sys
import os
import time
import struct
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import rti.connextdds as dds
from vibedds.participant import DomainParticipant
from vibedds.qos import QosPolicy, ReliabilityKind
from vibedds.type_support import HelloWorldType

# Enable ALL debug logging for vibedds
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(name)-30s %(levelname)-5s: %(message)s",
)
# But suppress overly noisy modules
logging.getLogger("vibedds.reliability").setLevel(logging.INFO)

logger = logging.getLogger("diagnose")


def main():
    print("=" * 60)
    print("METATRAFFIC DIAGNOSTIC: VibeDDS reader + RTI writer")
    print("=" * 60)
    print()

    # Create RTI writer ONLY (no reader - avoid loopback)
    struct_type = dds.StructType("HelloWorld")
    struct_type.add_member(dds.Member("message", dds.StringType()))
    rti_participant = dds.DomainParticipant(domain_id=0)
    rti_topic = dds.DynamicData.Topic(rti_participant, "HelloWorld", struct_type)
    rti_publisher = dds.Publisher(rti_participant)
    rti_writer_qos = dds.QosProvider.default.datawriter_qos
    rti_writer = dds.DynamicData.DataWriter(rti_publisher, rti_topic, rti_writer_qos)
    print(f"RTI writer created (reliability: {rti_writer.qos.reliability.kind})")

    # Create VibeDDS participant + reader
    dp = DomainParticipant(domain_id=0, participant_id=3)
    dp.start()
    topic = dp.create_topic("HelloWorld", HelloWorldType.TYPE_NAME)
    qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
    reader = dp.create_reader(topic, qos)

    print(f"VibeDDS reader created")
    print(f"  GUID: {dp.guid_prefix}")
    print(f"  Metatraffic unicast port: {dp.transport.metatraffic_unicast_port}")
    print(f"  User unicast port: {dp.transport.user_unicast_port}")
    print()

    # Send initial SPDP
    dp.announce_spdp()

    # Publish from RTI
    sample = dds.DynamicData(struct_type)
    sample["message"] = "Hello from RTI #0"
    rti_writer.write(sample)

    # Run for 30 seconds with full debug logging
    print("Running for 30 seconds with full metatraffic debug logging...")
    print("Look for: SEDP DATA submessages, heartbeats, ACKNACKs")
    print()

    start = time.time()
    pub_count = 0
    while time.time() - start < 30:
        dp.spin_once(timeout=0.2)

        # Publish from RTI periodically
        elapsed = int(time.time() - start)
        if elapsed > pub_count:
            pub_count = elapsed
            if pub_count % 3 == 0:
                sample = dds.DynamicData(struct_type)
                sample["message"] = f"Hello from RTI #{pub_count}"
                rti_writer.write(sample)

        # Check RTI matching periodically
        if elapsed % 5 == 0 and elapsed > 0 and elapsed != getattr(main, '_last_check', -1):
            main._last_check = elapsed
            try:
                matched = rti_writer.matched_subscriptions
                print(f"\n>>> [t={elapsed}s] RTI matched_subscriptions: {len(matched)}")
                for sub in matched:
                    try:
                        data = rti_writer.matched_subscription_data(sub)
                        print(f"    Matched: topic={data.topic_name}, type={data.type_name}")
                    except Exception as e:
                        print(f"    Matched: error: {e}")
            except:
                pass

            # Check for received data
            print(f">>> [t={elapsed}s] VibeDDS endpoint_db:")
            print(f"    local_writers: {len(dp.endpoint_db.local_writers)}")
            print(f"    local_readers: {len(dp.endpoint_db.local_readers)}")
            print(f"    remote_writers: {len(dp.endpoint_db.remote_writers)}")
            print(f"    remote_readers: {len(dp.endpoint_db.remote_readers)}")
            for key, rw in dp.endpoint_db.remote_writers.items():
                print(f"    Remote writer: {rw.endpoint_guid} topic={rw.topic_name} type={rw.type_name}")

    print("\n" + "=" * 60)
    print("FINAL STATE")
    print("=" * 60)
    try:
        matched = rti_writer.matched_subscriptions
        print(f"RTI matched_subscriptions: {len(matched)}")
    except:
        pass
    print(f"VibeDDS remote_writers: {len(dp.endpoint_db.remote_writers)}")
    print(f"VibeDDS remote_readers: {len(dp.endpoint_db.remote_readers)}")
    print(f"VibeDDS participants: {len(dp.participant_db)}")

    for key, p in dp.participant_db.participants.items():
        print(f"  Participant: {p.guid_prefix} vendor={p.vendor_id}")
        print(f"    meta_uc: {[(l.ipv4_str, l.port) for l in p.metatraffic_unicast_locators]}")

    dp.stop()
    del rti_writer
    del rti_participant
    print("\nDone.")


if __name__ == "__main__":
    main()
