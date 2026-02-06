#!/usr/bin/env python3
"""Compare VibeDDS vs RTI SEDP subscription announcements byte-by-byte.

Creates both a VibeDDS reader and an RTI reader for the same topic,
captures what each sends as its SEDP subscription announcement,
and compares them.
"""

import os
import sys
import struct
import socket
import time
import threading

# Add the Python VibeDDS to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import rti.connextdds as dds

from vibedds.types import GuidPrefix, EntityId, Guid, Locator
from vibedds.qos import QosPolicy, ReliabilityKind
from vibedds.sedp import SedpInteropOptions, _build_endpoint_data, LocalEndpoint
from vibedds.cdr import encapsulation_header, PL_CDR_LE, ParameterListParser, parse_encapsulation_header


# PID names
PID_NAMES = {
    0x0001: "SENTINEL",
    0x0002: "PARTICIPANT_LEASE_DURATION",
    0x0004: "TIME_BASED_FILTER",
    0x0005: "TOPIC_NAME",
    0x0007: "TYPE_NAME",
    0x000a: "TOPIC_DATA",
    0x000c: "GROUP_DATA",
    0x0013: "RTI_0013",
    0x0015: "PROTOCOL_VERSION",
    0x0016: "VENDOR_ID",
    0x0018: "RTI_0018",
    0x001a: "RELIABILITY",
    0x001b: "LIVELINESS",
    0x001d: "DURABILITY",
    0x001f: "OWNERSHIP",
    0x0021: "PRESENTATION",
    0x0023: "DEADLINE",
    0x0025: "DESTINATION_ORDER",
    0x0027: "LATENCY_BUDGET",
    0x0029: "PARTITION",
    0x002b: "USER_DATA",
    0x002f: "UNICAST_LOCATOR",
    0x0030: "MULTICAST_LOCATOR",
    0x0031: "DEFAULT_UNICAST_LOCATOR",
    0x0032: "METATRAFFIC_UNICAST_LOCATOR",
    0x0040: "HISTORY",
    0x0044: "RESOURCE_LIMITS",
    0x0050: "PARTICIPANT_GUID",
    0x0053: "GROUP_ENTITY_ID",
    0x0058: "BUILTIN_ENDPOINT_SET",
    0x005a: "ENDPOINT_GUID",
    0x0060: "RTI_0060",
    0x0062: "ENTITY_NAME",
    0x0073: "DATA_REPRESENTATION",
    0x0074: "TYPE_CONSISTENCY_ENFORCEMENT",
    0x0075: "TYPE_INFORMATION",
    0x8000: "RTI_8000",
    0x8002: "RTI_8002",
    0x8004: "RTI_8004",
    0x8009: "RTI_8009",
    0x8015: "RTI_8015",
    0x8021: "TYPE_OBJECT",
}


SEDP_SUB_WRITER = bytes([0x00, 0x00, 0x04, 0xC2])
SEDP_SUB_READER = bytes([0x00, 0x00, 0x04, 0xC7])
SEDP_PUB_WRITER = bytes([0x00, 0x00, 0x03, 0xC2])


def parse_pl_cdr(payload):
    """Parse parameter list from an encapsulated payload."""
    if len(payload) < 4:
        return []
    scheme = struct.unpack_from(">H", payload, 0)[0]
    endian = "<" if scheme in (1, 3) else ">"
    data = payload[4:]

    params = []
    offset = 0
    while offset + 4 <= len(data):
        pid = struct.unpack_from(f"{endian}H", data, offset)[0]
        length = struct.unpack_from(f"{endian}H", data, offset + 2)[0]
        offset += 4
        if pid == 0x0001:  # SENTINEL
            params.append((pid, b""))
            break
        if offset + length > len(data):
            break
        value = data[offset:offset + length]
        params.append((pid, value))
        offset += length
        offset = (offset + 3) & ~3
    return params


def dump_params(params, label):
    """Pretty print parameter list."""
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")
    for pid, value in params:
        pid_name = PID_NAMES.get(pid, f"UNKNOWN_0x{pid:04x}")
        short_hex = value.hex() if len(value) <= 40 else value[:40].hex() + f"... ({len(value)}B)"
        print(f"  PID 0x{pid:04x} ({pid_name:30s}): len={len(value):3d}  {short_hex}")


def capture_rti_sedp(port, timeout=15):
    """Listen on a port and capture SEDP subscription DATA payloads from RTI."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except:
        pass
    sock.bind(("0.0.0.0", port))
    sock.settimeout(0.5)

    captured_sub = []
    captured_pub = []
    start = time.time()

    while time.time() - start < timeout:
        try:
            data, addr = sock.recvfrom(65536)
        except socket.timeout:
            continue

        if len(data) < 20 or data[:4] not in (b"RTPS", b"RTPX"):
            continue

        vendor = (data[6], data[7])
        # Only capture RTI packets
        if vendor != (0x01, 0x01):
            continue

        # Parse submessages to find SEDP DATA
        offset = 20
        while offset + 4 <= len(data):
            sm_id = data[offset]
            flags = data[offset + 1]
            sm_len = struct.unpack_from("<H", data, offset + 2)[0]

            if sm_id == 0x15 and offset + 24 <= len(data):  # DATA
                writer_id = data[offset + 12:offset + 16]
                payload_offset = offset + 24
                payload_end = offset + 4 + sm_len

                if writer_id == SEDP_SUB_WRITER and flags & 0x04:
                    payload = data[payload_offset:payload_end]
                    if payload not in captured_sub:
                        captured_sub.append(payload)
                        print(f"[Captured RTI SEDP subscription, {len(payload)} bytes from {addr}]")

                if writer_id == SEDP_PUB_WRITER and flags & 0x04:
                    payload = data[payload_offset:payload_end]
                    if payload not in captured_pub:
                        captured_pub.append(payload)
                        print(f"[Captured RTI SEDP publication, {len(payload)} bytes from {addr}]")

            if sm_len == 0:
                break
            offset += 4 + sm_len
            offset = (offset + 3) & ~3

    sock.close()
    return captured_sub, captured_pub


def build_vibedds_sub_payload(profile="full"):
    """Build VibeDDS SEDP subscription payload for comparison."""
    os.environ["VIBEDDS_SEDP_PROFILE"] = profile
    interop = SedpInteropOptions.from_env()

    guid_prefix = GuidPrefix(bytes([0xAA] * 12))
    entity_id = EntityId(bytes([0x00, 0x00, 0x01, 0x07]))  # Reader no-key
    guid = Guid(guid_prefix, entity_id)

    qos = QosPolicy(reliability=ReliabilityKind.RELIABLE)

    endpoint = LocalEndpoint(
        guid=guid,
        topic_name="HelloWorld",
        type_name="HelloWorld",
        qos=qos,
        is_writer=False,
        unicast_locators=[Locator.from_ipv4("192.168.1.12", 7403)],
    )

    pl_data = _build_endpoint_data(endpoint, interop)
    payload = encapsulation_header(PL_CDR_LE) + pl_data

    if "VIBEDDS_SEDP_PROFILE" in os.environ:
        del os.environ["VIBEDDS_SEDP_PROFILE"]

    return payload


def build_vibedds_pub_payload(profile="full"):
    """Build VibeDDS SEDP publication payload for comparison."""
    os.environ["VIBEDDS_SEDP_PROFILE"] = profile
    interop = SedpInteropOptions.from_env()

    guid_prefix = GuidPrefix(bytes([0xAA] * 12))
    entity_id = EntityId(bytes([0x00, 0x00, 0x01, 0x03]))  # Writer no-key
    guid = Guid(guid_prefix, entity_id)

    qos = QosPolicy(reliability=ReliabilityKind.RELIABLE)

    endpoint = LocalEndpoint(
        guid=guid,
        topic_name="HelloWorld",
        type_name="HelloWorld",
        qos=qos,
        is_writer=True,
        unicast_locators=[Locator.from_ipv4("192.168.1.12", 7401)],
    )

    pl_data = _build_endpoint_data(endpoint, interop)
    payload = encapsulation_header(PL_CDR_LE) + pl_data

    if "VIBEDDS_SEDP_PROFILE" in os.environ:
        del os.environ["VIBEDDS_SEDP_PROFILE"]

    return payload


def main():
    print("SEDP Subscription Announcement Comparison")
    print("=" * 70)

    # Step 1: Generate VibeDDS payloads
    for profile in ["full", "minimal", "rti"]:
        vibe_sub = build_vibedds_sub_payload(profile)
        vibe_pub = build_vibedds_pub_payload(profile)

        vibe_sub_params = parse_pl_cdr(vibe_sub)
        vibe_pub_params = parse_pl_cdr(vibe_pub)

        dump_params(vibe_sub_params, f"VibeDDS SUBSCRIPTION (profile={profile})")
        dump_params(vibe_pub_params, f"VibeDDS PUBLICATION (profile={profile})")

        # Show PIDs present in sub but not pub, and vice versa
        sub_pids = set(pid for pid, _ in vibe_sub_params)
        pub_pids = set(pid for pid, _ in vibe_pub_params)

        sub_only = sub_pids - pub_pids
        pub_only = pub_pids - sub_pids
        if sub_only:
            print(f"\n  PIDs only in SUB: {', '.join(PID_NAMES.get(p, f'0x{p:04x}') for p in sorted(sub_only))}")
        if pub_only:
            print(f"  PIDs only in PUB: {', '.join(PID_NAMES.get(p, f'0x{p:04x}') for p in sorted(pub_only))}")

    # Step 2: Capture RTI's SEDP announcements
    print("\n" + "=" * 70)
    print("Now starting RTI capture...")
    print("Creating RTI participant with reader and writer on HelloWorld...")
    print("Listening for RTI's SEDP announcements on port 7412...")
    print("(Waiting up to 15 seconds)")
    print("=" * 70)

    # Start capture in background
    capture_result = {"sub": [], "pub": []}

    def capture_thread():
        sub, pub = capture_rti_sedp(7412, timeout=15)
        capture_result["sub"] = sub
        capture_result["pub"] = pub

    t = threading.Thread(target=capture_thread, daemon=True)
    t.start()

    # Give socket time to bind
    time.sleep(0.5)

    # Create RTI participant with a reader
    struct_type = dds.StructType("HelloWorld")
    struct_type.add_member(dds.Member("message", dds.StringType()))

    participant = dds.DomainParticipant(domain_id=0)
    topic = dds.DynamicData.Topic(participant, "HelloWorld", struct_type)
    subscriber = dds.Subscriber(participant)
    publisher = dds.Publisher(participant)

    reader_qos = dds.QosProvider.default.datareader_qos
    reader_qos << dds.Reliability.reliable()
    reader = dds.DynamicData.DataReader(subscriber, topic, reader_qos)

    writer_qos = dds.QosProvider.default.datawriter_qos
    writer_qos << dds.Reliability.reliable()
    writer = dds.DynamicData.DataWriter(publisher, topic, writer_qos)

    print(f"RTI reader and writer created on topic '{topic.name}', type '{topic.type_name}'")
    print("Waiting for SEDP exchange...")

    # Wait for capture to complete
    t.join(timeout=20)

    # Analyze captured RTI payloads
    if capture_result["sub"]:
        for i, payload in enumerate(capture_result["sub"]):
            rti_params = parse_pl_cdr(payload)
            dump_params(rti_params, f"RTI SUBSCRIPTION #{i+1} (captured)")
    else:
        print("\n** WARNING: No RTI subscription announcements captured!")
        print("   This might be because SO_REUSEPORT didn't work for capture,")
        print("   or RTI sent to a different port.")

    if capture_result["pub"]:
        for i, payload in enumerate(capture_result["pub"]):
            rti_params = parse_pl_cdr(payload)
            dump_params(rti_params, f"RTI PUBLICATION #{i+1} (captured)")
    else:
        print("\n** WARNING: No RTI publication announcements captured!")

    # Step 3: Compare PIDs
    if capture_result["sub"]:
        print("\n" + "=" * 70)
        print("  COMPARISON: VibeDDS (full) vs RTI subscription")
        print("=" * 70)

        vibe_sub = build_vibedds_sub_payload("full")
        vibe_params = {pid: val for pid, val in parse_pl_cdr(vibe_sub)}
        rti_params = {pid: val for pid, val in parse_pl_cdr(capture_result["sub"][0])}

        all_pids = sorted(set(list(vibe_params.keys()) + list(rti_params.keys())))

        for pid in all_pids:
            pid_name = PID_NAMES.get(pid, f"0x{pid:04x}")
            in_vibe = pid in vibe_params
            in_rti = pid in rti_params

            if in_vibe and in_rti:
                vv = vibe_params[pid]
                rv = rti_params[pid]
                if vv == rv:
                    status = "MATCH"
                else:
                    status = "DIFFER"
                    print(f"  {pid_name:30s}: {status}")
                    print(f"    VibeDDS: {vv.hex()[:80]}")
                    print(f"    RTI:     {rv.hex()[:80]}")
                    continue
                print(f"  {pid_name:30s}: {status}")
            elif in_vibe and not in_rti:
                print(f"  {pid_name:30s}: VibeDDS ONLY  ({vibe_params[pid].hex()[:40]})")
            elif in_rti and not in_vibe:
                print(f"  {pid_name:30s}: RTI ONLY      ({rti_params[pid].hex()[:40]})")

    print("\nDone.")


if __name__ == "__main__":
    main()
