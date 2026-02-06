#!/usr/bin/env python3
"""End-to-end test: RTI writer → VibeDDS reader.

Creates an RTI DynamicData writer and a VibeDDS reader on the same topic,
then checks whether:
1. SPDP discovery completes (bidirectional)
2. SEDP discovery completes (VibeDDS discovers RTI writer)
3. RTI matches VibeDDS's subscription (matched_subscriptions > 0)
4. VibeDDS reader receives data from RTI writer
"""

import sys
import os
import time
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import rti.connextdds as dds
from vibedds.participant import DomainParticipant
from vibedds.qos import QosPolicy, ReliabilityKind
from vibedds.type_support import HelloWorldType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)
logger = logging.getLogger("e2e_test")


def main():
    print("=" * 60)
    print("END-TO-END TEST: RTI writer → VibeDDS reader")
    print("=" * 60)

    # Kill stale processes that might hold ports
    os.system("pkill -f 'hello_sub\\|hello_pub\\|spdp_announce\\|sedp_announce' 2>/dev/null")
    time.sleep(0.5)

    # --- Create RTI writer ---
    struct_type = dds.StructType("HelloWorld")
    struct_type.add_member(dds.Member("message", dds.StringType()))
    rti_participant = dds.DomainParticipant(domain_id=0)
    rti_topic = dds.DynamicData.Topic(rti_participant, "HelloWorld", struct_type)

    # Use BEST_EFFORT to match VibeDDS reader
    rti_writer_qos = dds.DataWriterQos()
    rti_writer_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
    rti_publisher = dds.Publisher(rti_participant)
    rti_writer = dds.DynamicData.DataWriter(rti_publisher, rti_topic, rti_writer_qos)
    print(f"[SETUP] RTI BEST_EFFORT writer created")

    # --- Create VibeDDS reader ---
    dp = DomainParticipant(domain_id=0, participant_id=3)
    dp.start()
    topic = dp.create_topic("HelloWorld", HelloWorldType.TYPE_NAME)
    qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
    reader = dp.create_reader(topic, qos)

    received_samples = []

    def on_data(payload: bytes):
        try:
            message = HelloWorldType.deserialize(payload)
            received_samples.append(message)
            print(f"[DATA] VibeDDS received: {message!r}")
        except Exception as e:
            print(f"[DATA] Deserialize error: {e}")

    reader.on_data(on_data)
    print(f"[SETUP] VibeDDS BEST_EFFORT reader created (meta_uc={dp.transport.metatraffic_unicast_port})")
    print()

    # Initial SPDP announcement
    dp.announce_spdp()

    # --- Run event loop ---
    DURATION = 25
    print(f"Running for {DURATION} seconds...")
    print()

    start = time.time()
    last_publish = 0
    last_check = -1
    last_spdp = start

    milestones = {
        "spdp_discovered": False,
        "sedp_remote_writer": False,
        "rti_matched": False,
        "data_received": False,
    }

    while time.time() - start < DURATION:
        dp.spin_once(timeout=0.1)
        elapsed = time.time() - start

        # Re-announce SPDP every 3 seconds for faster discovery
        if elapsed - (last_spdp - start) >= 3.0:
            dp.announce_spdp()
            last_spdp = time.time()

        # Publish from RTI every 2 seconds
        if int(elapsed) % 2 == 0 and int(elapsed) != last_publish:
            last_publish = int(elapsed)
            sample = dds.DynamicData(struct_type)
            sample["message"] = f"Hello from RTI #{last_publish}"
            rti_writer.write(sample)

        # Periodic status check
        check_interval = int(elapsed)
        if check_interval % 3 == 0 and check_interval > 0 and check_interval != last_check:
            last_check = check_interval

            # Check SPDP
            n_participants = len(dp.participant_db.participants.values())
            if n_participants > 0 and not milestones["spdp_discovered"]:
                milestones["spdp_discovered"] = True
                print(f"[t={check_interval}s] ✓ SPDP: Discovered {n_participants} participant(s)")

            # Check SEDP
            n_writers = len(dp.endpoint_db.remote_writers)
            n_readers = len(dp.endpoint_db.remote_readers)
            if n_writers > 0 and not milestones["sedp_remote_writer"]:
                milestones["sedp_remote_writer"] = True
                for key, ep in dp.endpoint_db.remote_writers.items():
                    print(f"[t={check_interval}s] ✓ SEDP: Discovered remote writer: {ep.endpoint_guid} topic={ep.topic_name}")

            # Check RTI matched subscriptions
            try:
                matched = rti_writer.matched_subscriptions
                if len(matched) > 0 and not milestones["rti_matched"]:
                    milestones["rti_matched"] = True
                    print(f"[t={check_interval}s] ✓ RTI matched_subscriptions: {len(matched)}")
                    for sub in matched:
                        try:
                            data = rti_writer.matched_subscription_data(sub)
                            print(f"           topic={data.topic_name} type={data.type_name}")
                        except Exception as e:
                            print(f"           (error reading: {e})")
            except Exception as e:
                pass

            # Check data received
            if received_samples and not milestones["data_received"]:
                milestones["data_received"] = True
                print(f"[t={check_interval}s] ✓ VibeDDS received {len(received_samples)} sample(s)")

            # Check RTI incompatible QoS
            try:
                status = rti_writer.offered_incompatible_qos_status
                if status.total_count > 0:
                    print(f"[t={check_interval}s] ⚠ RTI INCOMPATIBLE QOS: count={status.total_count} policy_id={status.last_policy_id}")
            except:
                pass

            # Print status summary
            if not all(milestones.values()):
                remaining = [k for k, v in milestones.items() if not v]
                print(f"[t={check_interval}s] Waiting for: {remaining}")

    # --- Final results ---
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)

    all_pass = True
    for key, value in milestones.items():
        status = "PASS" if value else "FAIL"
        if not value:
            all_pass = False
        print(f"  [{status}] {key}")

    print()
    print(f"Total samples received: {len(received_samples)}")
    if received_samples:
        print(f"First sample: {received_samples[0]!r}")
        print(f"Last sample: {received_samples[-1]!r}")

    # Extra diagnostics on failure
    if not milestones["rti_matched"]:
        print()
        print("--- Diagnostics for rti_matched failure ---")
        try:
            matched = rti_writer.matched_subscriptions
            print(f"RTI matched_subscriptions: {len(matched)}")
        except Exception as e:
            print(f"Error checking matched: {e}")

        try:
            discovered = rti_participant.discovered_participants()
            print(f"RTI discovered_participants: {len(discovered)}")
            for handle in discovered:
                try:
                    data = rti_participant.discovered_participant_data(handle)
                    key_bytes = bytes(data.key.value)
                    print(f"  Key: {key_bytes[:16].hex()}")
                except:
                    pass
        except Exception as e:
            print(f"Error checking participants: {e}")

        print(f"VibeDDS remote_writers: {len(dp.endpoint_db.remote_writers)}")
        print(f"VibeDDS remote_readers: {len(dp.endpoint_db.remote_readers)}")

    # Cleanup
    dp.stop()
    del rti_writer
    del rti_participant

    print()
    if all_pass:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
