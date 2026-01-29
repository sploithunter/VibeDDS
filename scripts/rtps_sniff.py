#!/usr/bin/env python3
"""Lightweight RTPS UDP sniffer for SPDP/SEDP parameter list comparison.

Captures UDP packets on selected ports, parses RTPS messages, and prints
normalized PID/value summaries for SPDP/SEDP discovery payloads.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import select
import socket
import struct
import sys
from typing import Iterable

# Allow running from repo root without install
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PYTHON_ROOT = os.path.join(REPO_ROOT, "python")
if PYTHON_ROOT not in sys.path:
    sys.path.insert(0, PYTHON_ROOT)

from vibedds.cdr import (
    CdrDeserializer,
    ParameterListParser,
    parse_encapsulation_header,
    PL_CDR_LE,
    PL_CDR_BE,
    CDR_LE,
    CDR_BE,
)
from vibedds.constants import (
    PID_ENDPOINT_GUID,
    PID_PARTICIPANT_GUID,
    PID_TOPIC_NAME,
    PID_TYPE_NAME,
    PID_RELIABILITY,
    PID_DURABILITY,
    PID_OWNERSHIP,
    PID_LIVELINESS,
    PID_DESTINATION_ORDER,
    PID_DEADLINE,
    PID_HISTORY,
    PID_PARTITION,
    PID_UNICAST_LOCATOR,
    PID_DEFAULT_UNICAST_LOCATOR,
    PID_PROTOCOL_VERSION,
    PID_VENDORID,
    PID_DATA_REPRESENTATION,
    PID_TYPE_CONSISTENCY_ENFORCEMENT,
    PID_TYPE_INFORMATION,
    PID_BUILTIN_ENDPOINT_SET,
    PID_METATRAFFIC_UNICAST_LOCATOR,
    PID_METATRAFFIC_MULTICAST_LOCATOR,
    PID_DEFAULT_MULTICAST_LOCATOR,
    PID_DEFAULT_UNICAST_LOCATOR,
    PID_MULTICAST_LOCATOR,
    PID_DOMAIN_ID,
)
from vibedds.wire import RtpsMessageParser
from vibedds.messages import (
    DataSubmessage,
    HeartbeatSubmessage,
    AckNackSubmessage,
    GapSubmessage,
    InfoTimestampSubmessage,
    InfoDestinationSubmessage,
    InfoSourceSubmessage,
    PadSubmessage,
)
from vibedds.types import Locator, Guid


PID_NAMES = {
    PID_ENDPOINT_GUID: "ENDPOINT_GUID",
    PID_PARTICIPANT_GUID: "PARTICIPANT_GUID",
    PID_TOPIC_NAME: "TOPIC_NAME",
    PID_TYPE_NAME: "TYPE_NAME",
    PID_RELIABILITY: "RELIABILITY",
    PID_DURABILITY: "DURABILITY",
    PID_OWNERSHIP: "OWNERSHIP",
    PID_LIVELINESS: "LIVELINESS",
    PID_DESTINATION_ORDER: "DESTINATION_ORDER",
    PID_DEADLINE: "DEADLINE",
    PID_HISTORY: "HISTORY",
    PID_PARTITION: "PARTITION",
    PID_UNICAST_LOCATOR: "UNICAST_LOCATOR",
    PID_DEFAULT_UNICAST_LOCATOR: "DEFAULT_UNICAST_LOCATOR",
    PID_MULTICAST_LOCATOR: "MULTICAST_LOCATOR",
    PID_DEFAULT_MULTICAST_LOCATOR: "DEFAULT_MULTICAST_LOCATOR",
    PID_PROTOCOL_VERSION: "PROTOCOL_VERSION",
    PID_VENDORID: "VENDORID",
    PID_DATA_REPRESENTATION: "DATA_REPRESENTATION",
    PID_TYPE_CONSISTENCY_ENFORCEMENT: "TYPE_CONSISTENCY_ENFORCEMENT",
    PID_TYPE_INFORMATION: "TYPE_INFORMATION",
    PID_BUILTIN_ENDPOINT_SET: "BUILTIN_ENDPOINT_SET",
    PID_METATRAFFIC_UNICAST_LOCATOR: "METATRAFFIC_UNICAST_LOCATOR",
    PID_METATRAFFIC_MULTICAST_LOCATOR: "METATRAFFIC_MULTICAST_LOCATOR",
    PID_DOMAIN_ID: "DOMAIN_ID",
}


def _format_guid(raw: bytes) -> str:
    if len(raw) < 16:
        return raw.hex()
    try:
        guid = Guid.from_bytes(raw[:16])
        return f"{guid.prefix.value.hex()}.{guid.entity_id.value.hex()}"
    except Exception:
        return raw[:16].hex()


def _read_string(value: bytes, endian: str) -> str | None:
    try:
        de = CdrDeserializer(value, endian)
        return de.read_string()
    except Exception:
        return None


def _format_locator(loc: Locator) -> str:
    ip = loc.ipv4_str or "?"
    return f"{loc.kind} {ip}:{loc.port}"


def _decode_pid(pid: int, value: bytes, endian: str) -> str:
    if pid in (PID_TOPIC_NAME, PID_TYPE_NAME):
        s = _read_string(value, endian)
        return s if s is not None else value.hex()
    if pid in (PID_ENDPOINT_GUID, PID_PARTICIPANT_GUID):
        return _format_guid(value)
    if pid in (PID_UNICAST_LOCATOR, PID_DEFAULT_UNICAST_LOCATOR, PID_MULTICAST_LOCATOR,
               PID_DEFAULT_MULTICAST_LOCATOR, PID_METATRAFFIC_UNICAST_LOCATOR,
               PID_METATRAFFIC_MULTICAST_LOCATOR):
        try:
            loc = Locator.from_bytes(value)
            return f"{loc.kind} {loc.ipv4_str}:{loc.port}"
        except Exception:
            return value.hex()
    if pid == PID_PROTOCOL_VERSION:
        if len(value) >= 2:
            return f"{value[0]}.{value[1]}"
    if pid == PID_VENDORID:
        if len(value) >= 2:
            return f"{value[0]:02x}{value[1]:02x}"
    if pid == PID_DOMAIN_ID and len(value) >= 4:
        return str(struct.unpack(endian + "I", value[:4])[0])
    # For QoS-like values, show hex to avoid accidental mis-decoding
    return value.hex()


def _parse_parameter_list(payload: bytes) -> tuple[str, list[tuple[int, str, int]]]:
    scheme, pl_data = parse_encapsulation_header(payload)
    endian = "<" if scheme in (PL_CDR_LE, CDR_LE) else ">"
    items: list[tuple[int, str, int]] = []
    for pid, value in ParameterListParser(pl_data, endian):
        name = PID_NAMES.get(pid, f"0x{pid:04x}")
        decoded = _decode_pid(pid, value, endian)
        items.append((pid, f"{name}={decoded}", len(value)))
    enc = "PL_CDR_LE" if scheme == PL_CDR_LE else "PL_CDR_BE" if scheme == PL_CDR_BE else "CDR"
    return enc, items


def _log_header(out, addr, port, info: str) -> None:
    ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out.write(f"[{ts}] {addr}:{port} {info}\n")


def parse_rtps_packet(packet: bytes, addr: str, port: int, out) -> None:
    try:
        msg = RtpsMessageParser.parse(packet)
    except Exception:
        return

    prefix = msg.header.guid_prefix.value.hex()
    _log_header(out, addr, port, f"RTPS guid_prefix={prefix}")

    for sm in msg.submessages:
        if isinstance(sm, DataSubmessage):
            writer = sm.writer_id.value.hex()
            reader = sm.reader_id.value.hex()
            payload = sm.serialized_payload
            if not payload:
                continue
            enc, items = _parse_parameter_list(payload)
            out.write(f"  DATA writer={writer} reader={reader} enc={enc}\n")
            for _, entry, length in items:
                out.write(f"    - {entry} (len={length})\n")
        elif isinstance(sm, InfoTimestampSubmessage):
            out.write("  INFO_TS\n")
        elif isinstance(sm, InfoDestinationSubmessage):
            out.write("  INFO_DST\n")
        elif isinstance(sm, InfoSourceSubmessage):
            out.write("  INFO_SRC\n")
        elif isinstance(sm, HeartbeatSubmessage):
            out.write("  HEARTBEAT\n")
        elif isinstance(sm, AckNackSubmessage):
            out.write("  ACKNACK\n")
        elif isinstance(sm, GapSubmessage):
            out.write("  GAP\n")
        elif isinstance(sm, PadSubmessage):
            out.write("  PAD\n")
        else:
            out.write(f"  SUBMSG type={type(sm).__name__}\n")


def parse_ports(spec: str) -> list[int]:
    ports: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start = int(start_s)
            end = int(end_s)
            ports.extend(range(start, end + 1))
        else:
            ports.append(int(part))
    return sorted(set(ports))


def open_sockets(ports: Iterable[int], multicast_group: str | None) -> list[socket.socket]:
    sockets: list[socket.socket] = []
    for port in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            sock.close()
            continue
        if multicast_group:
            mreq = struct.pack("4s4s", socket.inet_aton(multicast_group), socket.inet_aton("0.0.0.0"))
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            except OSError:
                pass
        sockets.append(sock)
    return sockets


def main() -> int:
    parser = argparse.ArgumentParser(description="RTPS UDP sniffer for SPDP/SEDP")
    parser.add_argument("--ports", default="7400,7410-7420", help="Comma/range ports to listen on")
    parser.add_argument("--multicast", default="239.255.0.1", help="Multicast group (SPDP)")
    parser.add_argument("--duration", type=float, default=0.0, help="Seconds to run (0 = forever)")
    parser.add_argument("--output", default=None, help="Log file path")
    args = parser.parse_args()

    ports = parse_ports(args.ports)
    sockets = open_sockets(ports, args.multicast if args.multicast else None)
    if not sockets:
        print("No sockets bound; check ports.")
        return 2

    out_path = args.output
    if not out_path:
        os.makedirs(os.path.join(REPO_ROOT, "logs"), exist_ok=True)
        ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        out_path = os.path.join(REPO_ROOT, "logs", f"rtps_sniff-{ts}.log")

    with open(out_path, "w", encoding="utf-8") as out:
        out.write(f"# RTPS sniff log\n# ports={ports}\n# multicast={args.multicast}\n")
        out.flush()
        start = dt.datetime.now().timestamp()
        while True:
            if args.duration and dt.datetime.now().timestamp() - start > args.duration:
                break
            rlist, _, _ = select.select(sockets, [], [], 0.5)
            for sock in rlist:
                try:
                    data, (addr, port) = sock.recvfrom(65535)
                except OSError:
                    continue
                parse_rtps_packet(data, addr, port, out)
                out.flush()

    print(f"Wrote log: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
