#!/usr/bin/env python3
"""Check what RTI sees: does it discover VibeDDS participant?
Does it discover VibeDDS's reader endpoint?

Uses RTI's builtin discovery APIs to check.
"""

import sys
import os
import time
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import rti.connextdds as dds

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rti_check")


def main():
    print("=" * 60)
    print("RTI Discovery Check")
    print("=" * 60)

    # Enable some RTI logging
    try:
        dds.Logger.instance.verbosity = dds.Verbosity.WARNING
    except:
        pass

    # Create participant
    participant = dds.DomainParticipant(domain_id=0)
    print(f"RTI participant created on domain 0")

    # Create writer
    struct_type = dds.StructType("HelloWorld")
    struct_type.add_member(dds.Member("message", dds.StringType()))
    topic = dds.DynamicData.Topic(participant, "HelloWorld", struct_type)
    publisher = dds.Publisher(participant)
    writer = dds.DynamicData.DataWriter(publisher, topic)

    print(f"RTI writer created (reliability: {writer.qos.reliability.kind})")
    print()

    # Monitor discovered participants and endpoints
    start = time.time()
    seen_participants = set()
    last_print = 0

    while time.time() - start < 45:
        time.sleep(0.5)

        # Check discovered participants using builtin reader
        try:
            discovered = participant.discovered_participants()
            for handle in discovered:
                if handle not in seen_participants:
                    seen_participants.add(handle)
                    try:
                        data = participant.discovered_participant_data(handle)
                        key_bytes = bytes(data.key.value)
                        print(f"\n[t={time.time()-start:.1f}s] NEW PARTICIPANT DISCOVERED:")
                        print(f"  Key (first 16 bytes): {key_bytes[:16].hex()}")
                        print(f"  Participant name: {data.participant_name.name if hasattr(data, 'participant_name') else 'N/A'}")
                    except Exception as e:
                        print(f"\n[t={time.time()-start:.1f}s] NEW PARTICIPANT: handle={handle}, error reading data: {e}")
        except Exception as e:
            pass

        # Check matched subscriptions
        elapsed = int(time.time() - start)
        if elapsed % 5 == 0 and elapsed > 0 and elapsed != last_print:
            last_print = elapsed
            try:
                matched = writer.matched_subscriptions
                print(f"\n[t={elapsed}s] Writer matched_subscriptions: {len(matched)}")
            except:
                pass

            # Check incompatible QoS
            try:
                status = writer.offered_incompatible_qos_status
                if status.total_count > 0:
                    print(f"  INCOMPATIBLE QOS: count={status.total_count}")
            except:
                pass

            # Publish a message
            sample = dds.DynamicData(struct_type)
            sample["message"] = f"Hello from RTI #{elapsed}"
            writer.write(sample)

    print(f"\nTotal participants discovered: {len(seen_participants)}")
    print(f"Writer matched subscriptions: {len(writer.matched_subscriptions)}")


if __name__ == "__main__":
    main()
