#!/usr/bin/env python3
"""Test RTI DataWriter matching with VibeDDS DataReader using rti profile."""

import os
import sys
import time
import logging

sys.path.insert(0, os.path.dirname(__file__))

# Set the rti profile BEFORE importing vibedds
os.environ["VIBEDDS_SEDP_PROFILE"] = "rti"

# Enable logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(name)s: %(message)s",
)

def main():
    try:
        import rti.connextdds as dds
    except ImportError:
        print("RTI Python API not available")
        return

    from vibedds.participant import DomainParticipant
    from vibedds.qos import QosPolicy, ReliabilityKind

    topic_name = "Example SimpleType"
    type_name = "SimpleType"

    print(f"=== RTI -> VibeDDS Matching Test ===")
    print(f"Profile: {os.environ.get('VIBEDDS_SEDP_PROFILE', 'default')}")
    print(f"Topic: '{topic_name}', Type: '{type_name}'")
    print()

    # Create RTI participant and writer
    print("Creating RTI DomainParticipant...")
    rti_participant = dds.DomainParticipant(0)

    # Create a simple type
    print("Creating RTI Topic and DataWriter...")
    simple_type = dds.StructType("SimpleType")
    simple_type.add_member(dds.Member("value", dds.Int32Type()))

    rti_topic = dds.DynamicData.Topic(
        rti_participant,
        topic_name,
        simple_type,
    )
    # Set BEST_EFFORT reliability to match VibeDDS reader
    writer_qos = dds.DataWriterQos()
    writer_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
    rti_writer = dds.DynamicData.DataWriter(
        dds.Publisher(rti_participant),
        rti_topic,
        writer_qos,
    )

    print(f"RTI Writer: reliability={rti_writer.qos.reliability.kind}")

    # Create VibeDDS participant and reader
    print("\nCreating VibeDDS DomainParticipant...")
    vibe_participant = DomainParticipant(
        domain_id=0,
        participant_id=5,  # Avoid port conflicts
    )
    print(f"VibeDDS GUID prefix: {vibe_participant.guid_prefix}")
    print(f"VibeDDS domain: {vibe_participant.domain_id}, participant_id: {vibe_participant.participant_id}")

    # Start the participant (opens transport, initializes protocols)
    print("Starting VibeDDS participant...")
    vibe_participant.start()

    print("\nCreating VibeDDS Topic and DataReader...")
    vibe_topic = vibe_participant.create_topic(
        name=topic_name,
        type_name=type_name,
        keyed=False,
    )
    vibe_reader = vibe_participant.create_reader(
        topic=vibe_topic,
        qos=QosPolicy(reliability=ReliabilityKind.BEST_EFFORT),
    )

    # Wait for matching
    print("\n--- Waiting for discovery and matching ---")
    samples_published = 0
    matched = False

    for i in range(40):
        # Spin VibeDDS
        vibe_participant.spin_once(timeout=0.5)

        # Check RTI matched subscriptions
        subs = list(rti_writer.matched_subscriptions)
        if subs and not matched:
            print(f"\n[i={i}] RTI matched {len(subs)} subscription(s)!")
            for s in subs:
                print(f"  - {s}")
            matched = True

        # Publish samples if matched
        if matched and samples_published < 5:
            sample = dds.DynamicData(simple_type)
            sample["value"] = samples_published
            rti_writer.write(sample)
            samples_published += 1
            print(f"[i={i}] Published sample {samples_published}: value={samples_published-1}")

        # Status every 10 iterations
        if i % 10 == 0:
            print(f"[i={i}] RTI matched: {len(subs)}, VibeDDS discovered writers: {len(vibe_participant._sedp._endpoint_db.remote_writers)}")

        time.sleep(0.5)

        # Check if VibeDDS received samples
        # (would need to check via callbacks, skip for now)

        if i > 30 and not matched:
            print("\nNo match after 15 seconds, stopping.")
            break

    print("\n--- Summary ---")
    print(f"RTI matched subscriptions: {len(list(rti_writer.matched_subscriptions))}")
    print(f"VibeDDS discovered remote writers: {len(vibe_participant._sedp._endpoint_db.remote_writers)}")

    if matched:
        print("\nSUCCESS: RTI DataWriter matched with VibeDDS DataReader!")
    else:
        print("\nFAILED: No match achieved.")

        # Dump diagnostics
        print("\n--- Diagnostics ---")
        for key, writer in vibe_participant._sedp._endpoint_db.remote_writers.items():
            print(f"Remote writer: {writer.endpoint_guid}")
            print(f"  topic: '{writer.topic_name}'")
            print(f"  type: '{writer.type_name}'")
            print(f"  reliability: {writer.reliability}")
            print(f"  durability: {writer.durability}")

    # Cleanup
    print("\nCleaning up...")
    try:
        vibe_participant.close()
    except AttributeError:
        vibe_participant._transport.close()
    del rti_writer
    del rti_topic
    del rti_participant


if __name__ == "__main__":
    main()
