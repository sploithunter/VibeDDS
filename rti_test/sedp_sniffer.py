#!/usr/bin/env python3
"""Sniff SEDP packets on metatraffic unicast ports and decode parameter lists.

Captures what VibeDDS and RTI send as SEDP announcements,
allowing byte-by-byte comparison of subscription announcements.
"""

import socket
import struct
import sys
import time
import threading

# RTPS constants
RTPS_MAGIC = b"RTPS"
RTPX_MAGIC = b"RTPX"
SUBMSG_DATA = 0x15
SUBMSG_HEARTBEAT = 0x07
SUBMSG_ACKNACK = 0x06
SUBMSG_INFO_DST = 0x0E
SUBMSG_INFO_TS = 0x09

# SEDP entity IDs
SEDP_PUB_WRITER = bytes([0x00, 0x00, 0x03, 0xC2])
SEDP_PUB_READER = bytes([0x00, 0x00, 0x03, 0xC7])
SEDP_SUB_WRITER = bytes([0x00, 0x00, 0x04, 0xC2])
SEDP_SUB_READER = bytes([0x00, 0x00, 0x04, 0xC7])

# PIDs
PID_NAMES = {
    0x0000: "PAD",
    0x0001: "SENTINEL",
    0x0002: "PARTICIPANT_LEASE_DURATION",
    0x0004: "TIME_BASED_FILTER",
    0x0005: "TOPIC_NAME",
    0x0007: "TYPE_NAME",
    0x000a: "TOPIC_DATA",
    0x000c: "GROUP_DATA",
    0x0013: "RTI_0013 (coherent_set?)",
    0x0015: "PROTOCOL_VERSION",
    0x0016: "VENDOR_ID",
    0x0018: "RTI_0018 (expects_ack?)",
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
    0x0033: "METATRAFFIC_MULTICAST_LOCATOR",
    0x0040: "HISTORY",
    0x0044: "RESOURCE_LIMITS",
    0x0050: "PARTICIPANT_GUID",
    0x0053: "GROUP_ENTITY_ID",
    0x0058: "BUILTIN_ENDPOINT_SET",
    0x005a: "ENDPOINT_GUID",
    0x0060: "RTI_0060 (property?)",
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

RELIABILITY_KINDS = {1: "BEST_EFFORT", 2: "RELIABLE"}
DURABILITY_KINDS = {0: "VOLATILE", 1: "TRANSIENT_LOCAL", 2: "TRANSIENT", 3: "PERSISTENT"}


def hex_dump(data, prefix="    "):
    """Format bytes as hex dump."""
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        hex_str = " ".join(f"{b:02x}" for b in chunk)
        ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{prefix}{i:04x}: {hex_str:<48s}  {ascii_str}")
    return "\n".join(lines)


def decode_guid(data):
    """Decode a 16-byte GUID."""
    prefix = data[:12]
    entity = data[12:16]
    prefix_hex = "".join(f"{b:02x}" for b in prefix)
    entity_hex = "".join(f"{b:02x}" for b in entity)
    return f"Prefix({prefix_hex}):Entity({entity_hex})"


def decode_locator(data):
    """Decode a 24-byte RTPS locator."""
    if len(data) < 24:
        return f"<invalid locator, len={len(data)}>"
    kind = struct.unpack_from("<i", data, 0)[0]
    port = struct.unpack_from("<I", data, 4)[0]
    # IPv4 is in the last 4 bytes of the 16-byte address
    ip = f"{data[20]}.{data[21]}.{data[22]}.{data[23]}"
    return f"kind={kind} port={port} ip={ip}"


def decode_string(data):
    """Decode a CDR string (LE)."""
    if len(data) < 4:
        return "<too short>"
    length = struct.unpack_from("<I", data, 0)[0]
    if length == 0:
        return '""'
    s = data[4:4+length-1]  # -1 to strip null terminator
    try:
        return f'"{s.decode("utf-8")}"'
    except:
        return f"<{length} bytes>"


def decode_parameter(pid, value):
    """Decode a parameter value based on PID."""
    info = ""
    if pid == 0x005a:  # ENDPOINT_GUID
        if len(value) >= 16:
            info = decode_guid(value)
    elif pid == 0x0050:  # PARTICIPANT_GUID
        if len(value) >= 16:
            info = decode_guid(value)
    elif pid == 0x0005:  # TOPIC_NAME
        info = decode_string(value)
    elif pid == 0x0007:  # TYPE_NAME
        info = decode_string(value)
    elif pid == 0x001a:  # RELIABILITY
        if len(value) >= 12:
            kind = struct.unpack_from("<I", value, 0)[0]
            sec = struct.unpack_from("<i", value, 4)[0]
            frac = struct.unpack_from("<I", value, 8)[0]
            kind_name = RELIABILITY_KINDS.get(kind, f"UNKNOWN({kind})")
            info = f"kind={kind_name} max_blocking={sec}.{frac}"
    elif pid == 0x001d:  # DURABILITY
        if len(value) >= 4:
            kind = struct.unpack_from("<I", value, 0)[0]
            kind_name = DURABILITY_KINDS.get(kind, f"UNKNOWN({kind})")
            info = f"kind={kind_name}"
    elif pid == 0x001f:  # OWNERSHIP
        if len(value) >= 4:
            kind = struct.unpack_from("<I", value, 0)[0]
            info = f"kind={'SHARED' if kind == 0 else 'EXCLUSIVE' if kind == 1 else f'UNKNOWN({kind})'}"
    elif pid == 0x001b:  # LIVELINESS
        if len(value) >= 12:
            kind = struct.unpack_from("<I", value, 0)[0]
            sec = struct.unpack_from("<i", value, 4)[0]
            frac = struct.unpack_from("<I", value, 8)[0]
            kinds = {0: "AUTOMATIC", 1: "MANUAL_BY_PARTICIPANT", 2: "MANUAL_BY_TOPIC"}
            info = f"kind={kinds.get(kind, f'UNKNOWN({kind})')} lease={sec}.{frac}"
    elif pid == 0x0025:  # DESTINATION_ORDER
        if len(value) >= 4:
            kind = struct.unpack_from("<I", value, 0)[0]
            info = f"kind={'BY_RECEPTION' if kind == 0 else 'BY_SOURCE' if kind == 1 else f'UNKNOWN({kind})'}"
    elif pid == 0x0023:  # DEADLINE
        if len(value) >= 8:
            sec = struct.unpack_from("<i", value, 0)[0]
            frac = struct.unpack_from("<I", value, 4)[0]
            info = f"period={sec}.{frac}"
    elif pid == 0x0040:  # HISTORY
        if len(value) >= 8:
            kind = struct.unpack_from("<I", value, 0)[0]
            depth = struct.unpack_from("<I", value, 4)[0]
            info = f"kind={'KEEP_LAST' if kind == 0 else 'KEEP_ALL' if kind == 1 else f'UNKNOWN({kind})'} depth={depth}"
    elif pid == 0x0029:  # PARTITION
        if len(value) >= 4:
            count = struct.unpack_from("<I", value, 0)[0]
            info = f"count={count}"
    elif pid in (0x002f, 0x0031, 0x0032):  # Locators
        info = decode_locator(value)
    elif pid == 0x0015:  # PROTOCOL_VERSION
        if len(value) >= 2:
            info = f"v{value[0]}.{value[1]}"
    elif pid == 0x0016:  # VENDOR_ID
        if len(value) >= 2:
            info = f"[{value[0]:02x},{value[1]:02x}]"
            if value[0] == 0x01 and value[1] == 0x01:
                info += " (RTI)"
            elif value[0] == 0xff and value[1] == 0x01:
                info += " (VibeDDS)"
    elif pid == 0x0073:  # DATA_REPRESENTATION
        info = f"len={len(value)}"
    elif pid == 0x0074:  # TYPE_CONSISTENCY
        info = f"len={len(value)}"
    elif pid == 0x0075:  # TYPE_INFORMATION
        info = f"len={len(value)}"
    elif pid == 0x8021:  # TYPE_OBJECT
        info = f"len={len(value)}"
    elif pid == 0x0053:  # GROUP_ENTITY_ID
        if len(value) >= 4:
            info = f"{value[0]:02x}{value[1]:02x}{value[2]:02x}{value[3]:02x}"
    return info


def parse_parameter_list(data, endian="<"):
    """Parse a PL_CDR parameter list."""
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

        value = data[offset:offset+length]
        params.append((pid, value))
        offset += length
        # Align to 4 bytes
        offset = (offset + 3) & ~3

    return params


def identify_entity(entity_bytes):
    """Identify an SEDP entity ID."""
    if entity_bytes == SEDP_PUB_WRITER:
        return "SEDP_PUB_WRITER"
    elif entity_bytes == SEDP_PUB_READER:
        return "SEDP_PUB_READER"
    elif entity_bytes == SEDP_SUB_WRITER:
        return "SEDP_SUB_WRITER"
    elif entity_bytes == SEDP_SUB_READER:
        return "SEDP_SUB_READER"
    else:
        return f"Entity({entity_bytes.hex()})"


def parse_rtps_message(data, source_port, dest_port):
    """Parse an RTPS message and print SEDP details."""
    if len(data) < 20:
        return

    magic = data[0:4]
    if magic != RTPS_MAGIC and magic != RTPX_MAGIC:
        return

    version = f"{data[4]}.{data[5]}"
    vendor = f"{data[6]:02x}{data[7]:02x}"
    prefix = data[8:20]
    prefix_hex = "".join(f"{b:02x}" for b in prefix)

    vendor_name = ""
    if data[6] == 0x01 and data[7] == 0x01:
        vendor_name = " (RTI)"
    elif data[6] == 0xff and data[7] == 0x01:
        vendor_name = " (VibeDDS)"

    offset = 20
    submsg_idx = 0

    while offset + 4 <= len(data):
        submsg_id = data[offset]
        flags = data[offset + 1]
        submsg_len = struct.unpack_from("<H", data, offset + 2)[0]

        if submsg_id == SUBMSG_DATA and offset + 24 <= len(data):
            # Parse DATA submessage
            extra_flags = struct.unpack_from("<H", data, offset + 4)[0]
            octets_to_inline = struct.unpack_from("<H", data, offset + 6)[0]
            reader_id = data[offset + 8:offset + 12]
            writer_id = data[offset + 12:offset + 16]
            writer_sn_hi = struct.unpack_from("<i", data, offset + 16)[0]
            writer_sn_lo = struct.unpack_from("<I", data, offset + 20)[0]
            writer_sn = (writer_sn_hi << 32) | writer_sn_lo

            writer_name = identify_entity(writer_id)
            reader_name = identify_entity(reader_id)

            # Only show SEDP DATA (not SPDP)
            is_sedp = writer_id in (SEDP_PUB_WRITER, SEDP_SUB_WRITER)
            if is_sedp:
                kind = "PUBLICATION" if writer_id == SEDP_PUB_WRITER else "SUBSCRIPTION"
                print(f"\n{'='*80}")
                print(f"SEDP {kind} DATA from {prefix_hex}{vendor_name}")
                print(f"  src_port={source_port} dst_port={dest_port}")
                print(f"  writer={writer_name} reader={reader_name} sn={writer_sn}")

                # Parse serialized payload
                payload_offset = offset + 24
                if flags & 0x04:  # data present flag
                    if payload_offset + 4 <= offset + 4 + submsg_len:
                        # Encapsulation header
                        encap = struct.unpack_from(">H", data, payload_offset)[0]
                        encap_options = struct.unpack_from(">H", data, payload_offset + 2)[0]
                        encap_name = {0: "CDR_BE", 1: "CDR_LE", 2: "PL_CDR_BE", 3: "PL_CDR_LE"}.get(encap, f"0x{encap:04x}")
                        print(f"  encapsulation={encap_name}")

                        pl_data = data[payload_offset + 4:offset + 4 + submsg_len]
                        endian = "<" if encap in (1, 3) else ">"

                        params = parse_parameter_list(pl_data, endian)
                        print(f"  Parameters ({len(params)}):")
                        for pid, value in params:
                            pid_name = PID_NAMES.get(pid, f"0x{pid:04x}")
                            decoded = decode_parameter(pid, value)
                            print(f"    PID {pid_name} (0x{pid:04x}): len={len(value)} {decoded}")
                            if len(value) > 0 and len(value) <= 32:
                                print(f"      raw: {value.hex()}")
                            elif len(value) > 32:
                                print(f"      raw: {value[:32].hex()}... ({len(value)} bytes)")

                        # Also dump the full payload hex for comparison
                        full_payload = data[payload_offset:offset + 4 + submsg_len]
                        print(f"\n  Full SEDP payload ({len(full_payload)} bytes):")
                        print(hex_dump(full_payload))

        if submsg_len == 0:
            break
        offset += 4 + submsg_len
        # Align to 4 bytes
        offset = (offset + 3) & ~3
        submsg_idx += 1


def listen_on_port(port, label):
    """Listen on a specific UDP port and process incoming packets."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except AttributeError:
        pass
    sock.bind(("0.0.0.0", port))
    sock.settimeout(0.5)

    print(f"[{label}] Listening on port {port}")

    while True:
        try:
            data, addr = sock.recvfrom(65536)
            source_port = addr[1]
            parse_rtps_message(data, source_port, port)
        except socket.timeout:
            continue
        except Exception as e:
            print(f"[{label}] Error: {e}")
            continue


def main():
    # Metatraffic unicast ports for domain 0
    # participant 0: 7410, participant 1: 7412, etc.
    # Also listen on user data ports
    ports = {
        7410: "meta-p0",   # RTI participant (usually p0)
        7412: "meta-p1",   # VibeDDS hello_sub (p1)
        7401: "user-p0",   # User data port p0
        7403: "user-p1",   # User data port p1
    }

    # Allow custom ports from command line
    if len(sys.argv) > 1:
        ports = {}
        for arg in sys.argv[1:]:
            port = int(arg)
            ports[port] = f"port-{port}"

    print("SEDP Packet Sniffer")
    print("=" * 80)
    print("Listening for SEDP announcements...")
    print(f"Ports: {', '.join(f'{p} ({l})' for p, l in ports.items())}")
    print()

    threads = []
    for port, label in ports.items():
        t = threading.Thread(target=listen_on_port, args=(port, label), daemon=True)
        t.start()
        threads.append(t)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDone.")


if __name__ == "__main__":
    main()
