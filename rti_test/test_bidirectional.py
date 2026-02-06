#!/usr/bin/env python3
"""Comprehensive bidirectional test: RTI <-> VibeDDS data exchange.

Tests:
1. RTI writer → VibeDDS reader (with "Hello from RTI #N" messages)
2. VibeDDS writer → RTI reader (with "Hello from VibeDDS #N" messages)
3. Loopback detection: VibeDDS reader must NOT receive VibeDDS's own messages
4. Message content validation: ensures each direction receives the correct prefix

Requires: RTI Connext DDS Python API (rti.connextdds)
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
logger = logging.getLogger("bidir_test")


def main():
    print("=" * 70)
    print("BIDIRECTIONAL TEST: RTI <-> VibeDDS with loopback detection")
    print("=" * 70)
    print()

    # Kill stale processes that might hold ports
    os.system("pkill -f 'hello_sub\\|hello_pub\\|spdp_announce\\|sedp_announce' 2>/dev/null")
    time.sleep(0.5)

    # === RTI SIDE ===
    # Create RTI participant, writer, and reader on "HelloWorld" topic
    struct_type = dds.StructType("HelloWorld")
    struct_type.add_member(dds.Member("message", dds.StringType()))

    rti_participant = dds.DomainParticipant(domain_id=0)
    rti_topic = dds.DynamicData.Topic(rti_participant, "HelloWorld", struct_type)

    # RTI BEST_EFFORT writer (sends TO VibeDDS)
    rti_pub = dds.Publisher(rti_participant)
    rti_writer_qos = dds.DataWriterQos()
    rti_writer_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
    rti_writer = dds.DynamicData.DataWriter(rti_pub, rti_topic, rti_writer_qos)

    # RTI BEST_EFFORT reader (receives FROM VibeDDS)
    rti_sub = dds.Subscriber(rti_participant)
    rti_reader_qos = dds.DataReaderQos()
    rti_reader_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
    rti_reader = dds.DynamicData.DataReader(rti_sub, rti_topic, rti_reader_qos)

    print("[SETUP] RTI participant created with BEST_EFFORT writer + reader")

    # === VibeDDS SIDE ===
    # Use participant_id=3 to avoid port conflicts with RTI (which uses pid 0)
    dp = DomainParticipant(domain_id=0, participant_id=3)
    dp.start()

    topic = dp.create_topic("HelloWorld", HelloWorldType.TYPE_NAME)
    qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)

    vibe_writer = dp.create_writer(topic, qos)
    vibe_reader = dp.create_reader(topic, qos)

    # Track received samples with source identification
    vibe_received = []  # Messages received by VibeDDS reader

    def on_vibe_data(payload: bytes):
        try:
            message = HelloWorldType.deserialize(payload)
            vibe_received.append(message)
            print(f"  [VibeDDS RX] {message!r}")
        except Exception as e:
            print(f"  [VibeDDS RX] Deserialize error: {e}")

    vibe_reader.on_data(on_vibe_data)

    print(f"[SETUP] VibeDDS participant created with BEST_EFFORT writer + reader")
    print(f"  VibeDDS GUID prefix: {dp.guid_prefix}")
    print(f"  Metatraffic port: {dp.transport.metatraffic_unicast_port}")
    print(f"  User data port: {dp.transport.user_unicast_port}")
    print()

    # Initial SPDP
    dp.announce_spdp()

    # === EVENT LOOP ===
    DURATION = 30
    print(f"Running for {DURATION} seconds...")
    print()

    start = time.time()
    rti_publish_count = 0
    vibe_publish_count = 0
    last_rti_publish = 0
    last_vibe_publish = 0
    last_status = -1

    milestones = {
        "spdp_discovered": False,
        "sedp_rti_writer_found": False,
        "sedp_rti_reader_found": False,
        "rti_matched_vibe_reader": False,
        "rti_matched_vibe_writer": False,
        "rti_to_vibe_data": False,
        "vibe_to_rti_data": False,
    }

    rti_received = []  # Messages received by RTI reader

    while time.time() - start < DURATION:
        dp.spin_once(timeout=0.05)
        elapsed = time.time() - start

        # Publish from RTI every 2 seconds (distinct prefix)
        if int(elapsed) % 2 == 0 and int(elapsed) != last_rti_publish and int(elapsed) > 0:
            last_rti_publish = int(elapsed)
            rti_publish_count += 1
            sample = dds.DynamicData(struct_type)
            msg = f"Hello from RTI #{rti_publish_count}"
            sample["message"] = msg
            rti_writer.write(sample)

        # Publish from VibeDDS every 2 seconds (offset by 1s, distinct prefix)
        if int(elapsed) % 2 == 1 and int(elapsed) != last_vibe_publish and int(elapsed) > 1:
            last_vibe_publish = int(elapsed)
            vibe_publish_count += 1
            msg = f"Hello from VibeDDS #{vibe_publish_count}"
            payload = HelloWorldType.serialize(msg)
            vibe_writer.write(payload)

        # Read RTI samples
        try:
            samples = rti_reader.take()
            for sample_info in samples:
                if sample_info.info.valid:
                    msg = sample_info.data["message"]
                    rti_received.append(msg)
                    print(f"  [RTI RX] {msg!r}")
        except Exception:
            pass

        # Periodic status check every 5 seconds
        check = int(elapsed)
        if check % 5 == 0 and check > 0 and check != last_status:
            last_status = check

            # SPDP
            n_part = len(list(dp.participant_db.participants.values()))
            if n_part > 0 and not milestones["spdp_discovered"]:
                milestones["spdp_discovered"] = True
                print(f"[t={check}s] SPDP: Discovered {n_part} participant(s)")

            # SEDP - remote writers/readers
            n_rw = len(dp.endpoint_db.remote_writers)
            n_rr = len(dp.endpoint_db.remote_readers)
            if n_rw > 0 and not milestones["sedp_rti_writer_found"]:
                milestones["sedp_rti_writer_found"] = True
                for key, ep in dp.endpoint_db.remote_writers.items():
                    print(f"[t={check}s] SEDP: Found RTI writer: topic={ep.topic_name} type={ep.type_name}")
            if n_rr > 0 and not milestones["sedp_rti_reader_found"]:
                milestones["sedp_rti_reader_found"] = True
                for key, ep in dp.endpoint_db.remote_readers.items():
                    print(f"[t={check}s] SEDP: Found RTI reader: topic={ep.topic_name} type={ep.type_name}")

            # RTI matched subscriptions (VibeDDS reader matched by RTI writer)
            try:
                matched_subs = rti_writer.matched_subscriptions
                if len(matched_subs) > 0 and not milestones["rti_matched_vibe_reader"]:
                    milestones["rti_matched_vibe_reader"] = True
                    print(f"[t={check}s] RTI writer matched {len(matched_subs)} subscription(s)")
            except Exception:
                pass

            # RTI matched publications (VibeDDS writer matched by RTI reader)
            try:
                matched_pubs = rti_reader.matched_publications
                if len(matched_pubs) > 0 and not milestones["rti_matched_vibe_writer"]:
                    milestones["rti_matched_vibe_writer"] = True
                    print(f"[t={check}s] RTI reader matched {len(matched_pubs)} publication(s)")
            except Exception:
                pass

            # Data received
            if vibe_received and not milestones["rti_to_vibe_data"]:
                rti_msgs = [m for m in vibe_received if m.startswith("Hello from RTI")]
                if rti_msgs:
                    milestones["rti_to_vibe_data"] = True
                    print(f"[t={check}s] RTI->VibeDDS: {len(rti_msgs)} sample(s) received")
            if rti_received and not milestones["vibe_to_rti_data"]:
                vibe_msgs = [m for m in rti_received if m.startswith("Hello from VibeDDS")]
                if vibe_msgs:
                    milestones["vibe_to_rti_data"] = True
                    print(f"[t={check}s] VibeDDS->RTI: {len(vibe_msgs)} sample(s) received")

            # Show pending milestones
            remaining = [k for k, v in milestones.items() if not v]
            if remaining:
                print(f"[t={check}s] Waiting for: {remaining}")

    # === RESULTS ===
    print()
    print("=" * 70)
    print("RESULTS")
    print("=" * 70)
    print()

    # Milestone summary
    all_pass = True
    for key, value in milestones.items():
        status = "PASS" if value else "FAIL"
        if not value:
            all_pass = False
        print(f"  [{status}] {key}")

    # Direction 1: RTI -> VibeDDS
    print()
    print("--- Direction 1: RTI -> VibeDDS ---")
    rti_to_vibe = [m for m in vibe_received if m.startswith("Hello from RTI")]
    print(f"  RTI published: {rti_publish_count} samples")
    print(f"  VibeDDS received from RTI: {len(rti_to_vibe)} samples")
    if rti_to_vibe:
        print(f"  First: {rti_to_vibe[0]!r}")
        print(f"  Last:  {rti_to_vibe[-1]!r}")

    # Direction 2: VibeDDS -> RTI
    print()
    print("--- Direction 2: VibeDDS -> RTI ---")
    vibe_to_rti = [m for m in rti_received if m.startswith("Hello from VibeDDS")]
    print(f"  VibeDDS published: {vibe_publish_count} samples")
    print(f"  RTI received from VibeDDS: {len(vibe_to_rti)} samples")
    if vibe_to_rti:
        print(f"  First: {vibe_to_rti[0]!r}")
        print(f"  Last:  {vibe_to_rti[-1]!r}")

    # LOOPBACK CHECK: VibeDDS reader should NOT receive VibeDDS's own messages
    print()
    print("--- Loopback Check ---")
    loopback_msgs = [m for m in vibe_received if m.startswith("Hello from VibeDDS")]
    if loopback_msgs:
        print(f"  WARNING: VibeDDS reader received {len(loopback_msgs)} of its OWN messages (loopback detected!)")
        for m in loopback_msgs[:5]:
            print(f"    Loopback: {m!r}")
        loopback_ok = False
    else:
        print(f"  OK: VibeDDS reader received 0 loopback messages")
        loopback_ok = True

    # Also check if RTI reader received RTI's own messages (RTI handles this internally)
    rti_loopback = [m for m in rti_received if m.startswith("Hello from RTI")]
    if rti_loopback:
        print(f"  NOTE: RTI reader received {len(rti_loopback)} of RTI's own messages (RTI loopback)")
    else:
        print(f"  OK: RTI reader received 0 loopback messages")

    # Unknown messages
    vibe_unknown = [m for m in vibe_received if not m.startswith("Hello from RTI") and not m.startswith("Hello from VibeDDS")]
    rti_unknown = [m for m in rti_received if not m.startswith("Hello from RTI") and not m.startswith("Hello from VibeDDS")]
    if vibe_unknown:
        print(f"  WARNING: VibeDDS received {len(vibe_unknown)} unknown messages: {vibe_unknown[:3]}")
    if rti_unknown:
        print(f"  WARNING: RTI received {len(rti_unknown)} unknown messages: {rti_unknown[:3]}")

    # Cleanup
    dp.stop()
    del rti_writer
    del rti_reader
    del rti_participant

    # Final verdict
    print()
    print("=" * 70)
    data_ok = len(rti_to_vibe) > 0 and len(vibe_to_rti) > 0
    if all_pass and data_ok and loopback_ok:
        print("ALL TESTS PASSED - Bidirectional interop confirmed, no loopback")
    elif all_pass and data_ok and not loopback_ok:
        print("DATA EXCHANGE WORKS - But loopback detected (VibeDDS receives own messages)")
    else:
        print("SOME TESTS FAILED")
        if not data_ok:
            print(f"  RTI->VibeDDS: {'OK' if rti_to_vibe else 'FAILED'}")
            print(f"  VibeDDS->RTI: {'OK' if vibe_to_rti else 'FAILED'}")
    print("=" * 70)

    return 0 if (all_pass and data_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
