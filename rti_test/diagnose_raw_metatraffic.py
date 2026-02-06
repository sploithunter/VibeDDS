#!/usr/bin/env python3
"""Raw metatraffic diagnostic: dump every byte RTI sends to VibeDDS.

Shows:
1. Raw hex of every RTPS message from RTI (non-VibeDDS vendor)
2. Byte-by-byte submessage annotation
3. Whether any submessages are being silently dropped
4. The exact flags on DATA submessages

Usage:
    cd /Users/jason/Documents/VibeDDS
    python rti_test/diagnose_raw_metatraffic.py
"""

import sys
import os
import struct
import time
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import rti.connextdds as dds
from vibedds.participant import DomainParticipant
from vibedds.qos import QosPolicy, ReliabilityKind
from vibedds.type_support import HelloWorldType
from vibedds.constants import (
    RTPS_MAGIC, RTPX_MAGIC,
    SUBMSG_PAD, SUBMSG_ACKNACK, SUBMSG_HEARTBEAT, SUBMSG_GAP,
    SUBMSG_INFO_TS, SUBMSG_INFO_SRC, SUBMSG_INFO_DST, SUBMSG_DATA,
    SUBMSG_DATA_FRAG, SUBMSG_NACK_FRAG, SUBMSG_HEARTBEAT_FRAG,
    FLAG_ENDIAN, FLAG_DATA_Q, FLAG_DATA_D, FLAG_DATA_K,
)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(name)-30s %(levelname)-5s: %(message)s",
)
# Keep most modules at INFO to reduce noise
logging.getLogger("vibedds.reliability").setLevel(logging.INFO)
logging.getLogger("vibedds.sedp").setLevel(logging.INFO)
logging.getLogger("vibedds.spdp").setLevel(logging.INFO)
# But keep wire and participant at DEBUG to see dropped submessages
logging.getLogger("vibedds.wire").setLevel(logging.DEBUG)
logging.getLogger("vibedds.participant").setLevel(logging.DEBUG)

logger = logging.getLogger("diagnose")

SUBMSG_NAMES = {
    0x01: "PAD", 0x06: "ACKNACK", 0x07: "HEARTBEAT", 0x08: "GAP",
    0x09: "INFO_TS", 0x0C: "INFO_SRC", 0x0E: "INFO_DST", 0x0F: "INFO_REPLY",
    0x12: "NACK_FRAG", 0x13: "HEARTBEAT_FRAG", 0x15: "DATA", 0x16: "DATA_FRAG",
}

VIBEDDS_VENDOR = (0xFF, 0x01)


def dump_rtps_message(data: bytes, addr: str, port: int) -> dict:
    """Parse and dump an RTPS message at the byte level.

    Returns dict with parsed info.
    """
    if len(data) < 20:
        print(f"  [too short: {len(data)} bytes]")
        return {}

    magic = data[0:4]
    if magic not in (RTPS_MAGIC, RTPX_MAGIC):
        print(f"  [bad magic: {magic!r}]")
        return {}

    version_major = data[4]
    version_minor = data[5]
    vendor = (data[6], data[7])
    guid_prefix = data[8:20]

    is_vibedds = vendor == VIBEDDS_VENDOR
    vendor_name = "VibeDDS" if is_vibedds else f"vendor({vendor[0]:02x}.{vendor[1]:02x})"
    if vendor == (0x01, 0x01):
        vendor_name = "RTI"

    print(f"\n{'='*70}")
    print(f"RTPS from {addr}:{port} | {vendor_name} | guid={guid_prefix.hex()}")
    print(f"  magic={magic!r} version={version_major}.{version_minor} vendor=0x{vendor[0]:02x}{vendor[1]:02x}")
    print(f"  Raw header: {data[:20].hex()}")
    print(f"  Total message: {len(data)} bytes")

    # Parse submessages
    pos = 20
    sm_idx = 0
    submessages = []
    while pos < len(data):
        if pos + 4 > len(data):
            print(f"  [incomplete submessage header at offset {pos}]")
            break

        sm_id = data[pos]
        sm_flags = data[pos + 1]
        sm_length = struct.unpack_from("<H", data, pos + 2)[0]

        sm_name = SUBMSG_NAMES.get(sm_id, f"UNKNOWN(0x{sm_id:02x})")
        endian = "LE" if (sm_flags & FLAG_ENDIAN) else "BE"

        body_start = pos + 4
        if sm_length == 0 and body_start < len(data):
            # Last submessage - rest of message
            body = data[body_start:]
            body_end = len(data)
        else:
            body = data[body_start:body_start + sm_length]
            body_end = body_start + sm_length

        print(f"\n  --- Submessage #{sm_idx}: {sm_name} ---")
        print(f"  offset={pos} id=0x{sm_id:02x} flags=0x{sm_flags:02x}({endian}) length={sm_length}")
        print(f"  header bytes: {data[pos:pos+4].hex()}")

        # Detailed annotation based on type
        if sm_id == SUBMSG_DATA:
            _dump_data_submessage(sm_flags, body)
        elif sm_id == SUBMSG_HEARTBEAT:
            _dump_heartbeat_submessage(sm_flags, body)
        elif sm_id == SUBMSG_ACKNACK:
            _dump_acknack_submessage(sm_flags, body)
        elif sm_id == SUBMSG_INFO_DST:
            if len(body) >= 12:
                print(f"  dest_guid_prefix: {body[:12].hex()}")
        elif sm_id == SUBMSG_INFO_TS:
            if sm_flags & 0x02:
                print(f"  [timestamp invalidated]")
            elif len(body) >= 8:
                sec = struct.unpack_from("<I", body, 0)[0]
                frac = struct.unpack_from("<I", body, 4)[0]
                print(f"  timestamp: sec={sec} frac={frac}")
        else:
            if body:
                print(f"  body ({len(body)} bytes): {body[:60].hex()}{'...' if len(body) > 60 else ''}")

        submessages.append({
            "name": sm_name,
            "id": sm_id,
            "flags": sm_flags,
            "length": sm_length,
            "body": body,
        })

        sm_idx += 1
        pos = body_end

    return {
        "vendor": vendor,
        "guid_prefix": guid_prefix,
        "submessages": submessages,
    }


def _dump_data_submessage(flags: int, body: bytes):
    """Detailed dump of DATA submessage."""
    has_qos = bool(flags & FLAG_DATA_Q)
    has_data = bool(flags & FLAG_DATA_D)
    has_key = bool(flags & FLAG_DATA_K)
    print(f"  flags: E={flags & 0x01} Q={int(has_qos)} D={int(has_data)} K={int(has_key)}")

    if len(body) < 20:
        print(f"  [body too short: {len(body)} bytes, need 20]")
        print(f"  body hex: {body.hex()}")
        return

    endian = "<" if (flags & FLAG_ENDIAN) else ">"

    extra_flags = struct.unpack_from("<H", body, 0)[0]
    octets_to_iq = struct.unpack_from("<H", body, 2)[0]
    reader_id = body[4:8]
    writer_id = body[8:12]
    sn_high = struct.unpack_from(endian + "i", body, 12)[0]
    sn_low = struct.unpack_from(endian + "I", body, 16)[0]
    sn_value = (sn_high << 32) | sn_low

    print(f"  extraFlags=0x{extra_flags:04x} octetsToInlineQos={octets_to_iq}")
    print(f"  readerId={reader_id.hex()} writerId={writer_id.hex()}")
    print(f"  writerSN: high={sn_high} low={sn_low} (value={sn_value})")

    payload_offset = 4 + octets_to_iq
    print(f"  payload_offset={payload_offset} (4 + {octets_to_iq})")

    if has_qos:
        print(f"  [has inline QoS starting at offset {payload_offset}]")
        # Try to find PID_SENTINEL
        qos_hex = body[payload_offset:payload_offset + 60]
        print(f"  inline QoS hex: {qos_hex.hex()}")

    if has_data or has_key:
        payload = body[payload_offset:]
        print(f"  serialized payload: {len(payload)} bytes")
        if payload:
            print(f"  payload hex: {payload[:80].hex()}{'...' if len(payload) > 80 else ''}")
            if len(payload) >= 4:
                encap = struct.unpack_from(">H", payload, 0)[0]
                print(f"  encapsulation scheme: 0x{encap:04x} ({'PL_CDR_LE' if encap == 0x0003 else 'PL_CDR_BE' if encap == 0x0002 else 'CDR_LE' if encap == 0x0001 else 'unknown'})")
    else:
        remaining = body[payload_offset:]
        print(f"  [no D or K flag - no serialized payload expected]")
        if remaining:
            print(f"  BUT there are {len(remaining)} bytes after payload_offset!")
            print(f"  remaining hex: {remaining[:80].hex()}")


def _dump_heartbeat_submessage(flags: int, body: bytes):
    """Detailed dump of HEARTBEAT submessage."""
    is_final = bool(flags & 0x02)
    is_liveliness = bool(flags & 0x04)
    print(f"  flags: E={flags & 0x01} F={int(is_final)} L={int(is_liveliness)}")

    if len(body) < 28:
        print(f"  [body too short: {len(body)} bytes, need 28]")
        print(f"  body hex: {body.hex()}")
        return

    endian = "<" if (flags & FLAG_ENDIAN) else ">"
    reader_id = body[0:4]
    writer_id = body[4:8]
    first_high = struct.unpack_from(endian + "i", body, 8)[0]
    first_low = struct.unpack_from(endian + "I", body, 12)[0]
    last_high = struct.unpack_from(endian + "i", body, 16)[0]
    last_low = struct.unpack_from(endian + "I", body, 20)[0]
    count = struct.unpack_from(endian + "I", body, 24)[0]

    print(f"  readerId={reader_id.hex()} writerId={writer_id.hex()}")
    print(f"  firstSN: high={first_high} low={first_low}")
    print(f"  lastSN: high={last_high} low={last_low}")
    print(f"  count={count}")


def _dump_acknack_submessage(flags: int, body: bytes):
    """Detailed dump of ACKNACK submessage."""
    is_final = bool(flags & 0x02)
    print(f"  flags: E={flags & 0x01} F={int(is_final)}")

    if len(body) < 24:
        print(f"  [body too short: {len(body)} bytes]")
        print(f"  body hex: {body.hex()}")
        return

    reader_id = body[0:4]
    writer_id = body[4:8]
    print(f"  readerId={reader_id.hex()} writerId={writer_id.hex()}")
    print(f"  rest hex: {body[8:].hex()}")


def main():
    print("=" * 70)
    print("RAW METATRAFFIC DIAGNOSTIC: VibeDDS reader + RTI writer")
    print("=" * 70)

    # Kill any stale VibeDDS processes
    print("\nChecking for stale processes...")
    os.system("pkill -f 'hello_sub\\|hello_pub\\|spdp_announce\\|sedp_announce' 2>/dev/null")
    time.sleep(1)

    # Create RTI writer
    struct_type = dds.StructType("HelloWorld")
    struct_type.add_member(dds.Member("message", dds.StringType()))
    rti_participant = dds.DomainParticipant(domain_id=0)
    rti_topic = dds.DynamicData.Topic(rti_participant, "HelloWorld", struct_type)
    rti_publisher = dds.Publisher(rti_participant)
    rti_writer = dds.DynamicData.DataWriter(rti_publisher, rti_topic)
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

    # Monkey-patch the metatraffic handler to dump raw bytes
    original_handle = dp._handle_metatraffic_packet

    def patched_handle(data, addr, port):
        # Only dump non-VibeDDS traffic in detail
        if len(data) >= 8:
            vendor = (data[6], data[7])
            if vendor != VIBEDDS_VENDOR:
                dump_rtps_message(data, addr, port)
        original_handle(data, addr, port)

    dp._handle_metatraffic_packet = patched_handle

    # Also patch the SPDP multicast handler to catch RTI's metatraffic there
    original_spdp = dp._handle_spdp_packet

    def patched_spdp(data, addr, port):
        if len(data) >= 8:
            vendor = (data[6], data[7])
            if vendor != VIBEDDS_VENDOR:
                print(f"\n  [SPDP multicast from non-VibeDDS: vendor=0x{vendor[0]:02x}{vendor[1]:02x}]")
        return original_spdp(data, addr, port)

    dp._handle_spdp_packet = patched_spdp

    # Send initial SPDP
    dp.announce_spdp()

    # Publish from RTI
    sample = dds.DynamicData(struct_type)
    sample["message"] = "Hello from RTI #0"
    rti_writer.write(sample)

    print("\nRunning for 45 seconds with raw metatraffic dumping...")
    print("Looking for: HEARTBEATs from RTI, DATA flags, dropped submessages")
    print()

    start = time.time()
    pub_count = 0
    while time.time() - start < 45:
        dp.spin_once(timeout=0.2)

        elapsed = int(time.time() - start)
        if elapsed > pub_count:
            pub_count = elapsed
            if pub_count % 3 == 0:
                sample = dds.DynamicData(struct_type)
                sample["message"] = f"Hello from RTI #{pub_count}"
                rti_writer.write(sample)

        if elapsed % 10 == 0 and elapsed > 0 and elapsed != getattr(main, '_last', -1):
            main._last = elapsed
            try:
                matched = rti_writer.matched_subscriptions
                print(f"\n>>> [t={elapsed}s] RTI matched_subscriptions: {len(matched)}")
            except:
                pass

            # Check VibeDDS state
            print(f">>> [t={elapsed}s] VibeDDS endpoint_db:")
            print(f"    remote_writers: {len(dp.endpoint_db.remote_writers)}")
            print(f"    remote_readers: {len(dp.endpoint_db.remote_readers)}")
            for key, rw in dp.endpoint_db.remote_writers.items():
                print(f"    Remote writer: {rw.endpoint_guid} topic={rw.topic_name}")

            # Check reliability state
            print(f">>> [t={elapsed}s] SEDP reliability state:")
            pub_reader = dp.sedp.pub_reader
            for key, wp in pub_reader.writer_proxies.items():
                print(f"    pub_reader writer_proxy: {wp.remote_writer_guid} highest_received={wp.highest_received_sn} received={wp.received_sns}")
            sub_reader = dp.sedp.sub_reader
            for key, wp in sub_reader.writer_proxies.items():
                print(f"    sub_reader writer_proxy: {wp.remote_writer_guid} highest_received={wp.highest_received_sn} received={wp.received_sns}")

    print(f"\n\n{'='*70}")
    print("FINAL STATE")
    print(f"{'='*70}")
    try:
        matched = rti_writer.matched_subscriptions
        print(f"RTI matched_subscriptions: {len(matched)}")
    except:
        pass
    print(f"VibeDDS remote_writers: {len(dp.endpoint_db.remote_writers)}")
    print(f"VibeDDS remote_readers: {len(dp.endpoint_db.remote_readers)}")
    print(f"VibeDDS participants: {len(dp.participant_db)}")

    dp.stop()
    del rti_writer
    del rti_participant
    print("\nDone.")


if __name__ == "__main__":
    main()
