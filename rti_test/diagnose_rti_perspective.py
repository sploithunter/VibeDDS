#!/usr/bin/env python3
"""Check exactly what RTI sees from VibeDDS.

This script:
1. Creates RTI writer + VibeDDS reader
2. Checks RTI's discovered_participants() to see if VibeDDS is visible
3. Dumps the SPDP data that RTI has for VibeDDS
4. Checks for any RTI error/warning status
5. Uses a raw socket sniffer on a SEPARATE port to monitor traffic
"""

import sys
import os
import socket
import struct
import select
import time
import logging
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import rti.connextdds as dds
from vibedds.participant import DomainParticipant
from vibedds.qos import QosPolicy, ReliabilityKind
from vibedds.type_support import HelloWorldType

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)
logger = logging.getLogger("diagnose")

# Also open a sniffer on port 7410 (RTI's metatraffic port) to see what VibeDDS sends
# And on port 7416 (VibeDDS's metatraffic port) to see what RTI sends

VIBEDDS_VENDOR = (0xFF, 0x01)
RTI_VENDOR = (0x01, 0x01)

SUBMSG_NAMES = {
    0x01: "PAD", 0x06: "ACKNACK", 0x07: "HEARTBEAT", 0x08: "GAP",
    0x09: "INFO_TS", 0x0C: "INFO_SRC", 0x0E: "INFO_DST", 0x0F: "INFO_REPLY",
    0x12: "NACK_FRAG", 0x13: "HEARTBEAT_FRAG", 0x15: "DATA", 0x16: "DATA_FRAG",
}


def sniff_port(port, label, duration=30):
    """Open a UDP socket on the given port and log all traffic."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if sys.platform == "darwin":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind(("", port))
        sock.setblocking(False)
    except Exception as e:
        print(f"[SNIFFER:{label}] Failed to bind port {port}: {e}")
        return

    print(f"[SNIFFER:{label}] Listening on port {port}")
    start = time.time()
    pkt_count = 0

    while time.time() - start < duration:
        try:
            readable, _, _ = select.select([sock], [], [], 0.5)
            if not readable:
                continue
            data, (addr, src_port) = sock.recvfrom(65536)
            pkt_count += 1

            if len(data) < 8:
                continue

            vendor = (data[6], data[7])
            guid_prefix = data[8:20].hex() if len(data) >= 20 else "?"

            vendor_name = "VibeDDS" if vendor == VIBEDDS_VENDOR else "RTI" if vendor == RTI_VENDOR else f"0x{vendor[0]:02x}{vendor[1]:02x}"

            # Count submessages
            sm_types = []
            pos = 20
            while pos + 4 <= len(data):
                sm_id = data[pos]
                sm_len = struct.unpack_from("<H", data, pos + 2)[0]
                sm_types.append(SUBMSG_NAMES.get(sm_id, f"0x{sm_id:02x}"))
                pos += 4 + (sm_len if sm_len > 0 else (len(data) - pos - 4))
                if sm_len == 0:
                    break

            print(f"[SNIFFER:{label}] {addr}:{src_port} -> :{port} | {vendor_name} guid={guid_prefix[:12]}... | {len(data)}B | submsg={sm_types}")

        except BlockingIOError:
            continue
        except Exception as e:
            print(f"[SNIFFER:{label}] Error: {e}")

    sock.close()
    print(f"[SNIFFER:{label}] Done. Total packets: {pkt_count}")


def main():
    print("=" * 70)
    print("RTI PERSPECTIVE DIAGNOSTIC")
    print("=" * 70)

    # Kill stale processes
    os.system("pkill -f 'hello_sub\\|hello_pub\\|spdp_announce\\|sedp_announce' 2>/dev/null")
    time.sleep(1)

    # Start sniffers in background threads
    t_rti = threading.Thread(target=sniff_port, args=(7410, "RTI_PORT", 35), daemon=True)
    t_vibe = threading.Thread(target=sniff_port, args=(7416, "VIBE_PORT", 35), daemon=True)
    t_rti.start()
    t_vibe.start()
    time.sleep(0.5)

    # Enable RTI logging
    try:
        dds.Logger.instance.verbosity = dds.Verbosity.WARNING
    except:
        pass

    # Create RTI writer
    struct_type = dds.StructType("HelloWorld")
    struct_type.add_member(dds.Member("message", dds.StringType()))
    rti_participant = dds.DomainParticipant(domain_id=0)
    rti_topic = dds.DynamicData.Topic(rti_participant, "HelloWorld", struct_type)
    rti_publisher = dds.Publisher(rti_participant)
    rti_writer = dds.DynamicData.DataWriter(rti_publisher, rti_topic)
    print(f"RTI writer created")

    # Create VibeDDS
    dp = DomainParticipant(domain_id=0, participant_id=3)
    dp.start()
    topic = dp.create_topic("HelloWorld", HelloWorldType.TYPE_NAME)
    qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
    reader = dp.create_reader(topic, qos)
    print(f"VibeDDS reader created (meta_uc={dp.transport.metatraffic_unicast_port})")

    dp.announce_spdp()

    # Publish
    sample = dds.DynamicData(struct_type)
    sample["message"] = "Hello #0"
    rti_writer.write(sample)

    print("\nRunning for 30 seconds...")
    print()

    start = time.time()
    seen_participants = set()
    last_check = -1

    while time.time() - start < 30:
        dp.spin_once(timeout=0.2)

        elapsed = int(time.time() - start)
        if elapsed % 5 == 0 and elapsed > 0 and elapsed != last_check:
            last_check = elapsed

            # Check RTI discovered participants
            try:
                discovered = rti_participant.discovered_participants()
                for handle in discovered:
                    if handle not in seen_participants:
                        seen_participants.add(handle)
                        try:
                            data = rti_participant.discovered_participant_data(handle)
                            key_bytes = bytes(data.key.value)
                            print(f"\n[t={elapsed}s] RTI discovered participant:")
                            print(f"  Key: {key_bytes[:16].hex()}")
                            try:
                                print(f"  Name: {data.participant_name.name}")
                            except:
                                pass
                        except Exception as e:
                            print(f"\n[t={elapsed}s] RTI discovered participant (error reading: {e})")
            except Exception as e:
                print(f"[t={elapsed}s] Error checking discovered: {e}")

            # Check RTI matched subscriptions
            try:
                matched = rti_writer.matched_subscriptions
                print(f"[t={elapsed}s] RTI matched_subscriptions: {len(matched)}")
                for sub in matched:
                    try:
                        data = rti_writer.matched_subscription_data(sub)
                        print(f"  Matched: topic={data.topic_name} type={data.type_name}")
                    except Exception as e:
                        print(f"  Matched: error={e}")
            except:
                pass

            # Check RTI incompatible QoS
            try:
                status = rti_writer.offered_incompatible_qos_status
                if status.total_count > 0:
                    print(f"[t={elapsed}s] RTI INCOMPATIBLE QOS: count={status.total_count} last_policy={status.last_policy_id}")
            except:
                pass

            # Check VibeDDS state
            print(f"[t={elapsed}s] VibeDDS remote_writers={len(dp.endpoint_db.remote_writers)} remote_readers={len(dp.endpoint_db.remote_readers)}")

            # Publish from RTI
            sample = dds.DynamicData(struct_type)
            sample["message"] = f"Hello #{elapsed}"
            rti_writer.write(sample)

    print(f"\n{'='*70}")
    print("FINAL STATE")
    print(f"{'='*70}")
    try:
        matched = rti_writer.matched_subscriptions
        print(f"RTI matched_subscriptions: {len(matched)}")
    except:
        pass
    print(f"RTI discovered_participants: {len(seen_participants)}")
    print(f"VibeDDS remote_writers: {len(dp.endpoint_db.remote_writers)}")
    print(f"VibeDDS remote_readers: {len(dp.endpoint_db.remote_readers)}")

    dp.stop()
    del rti_writer
    del rti_participant

    # Wait for sniffers
    t_rti.join(timeout=5)
    t_vibe.join(timeout=5)
    print("\nDone.")


if __name__ == "__main__":
    main()
