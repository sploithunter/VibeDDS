#!/usr/bin/env python3
"""Parse RTPS packets from a pcap file and summarize SPDP/SEDP payloads."""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from typing import Iterable

# scapy is used for pcap parsing
from scapy.all import rdpcap, UDP

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
    PID_MULTICAST_LOCATOR,
    PID_DOMAIN_ID,
)
from vibedds.wire import RtpsMessageParser
from vibedds.types import Locator, Guid
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


def _decode_pid(pid: int, value: bytes, endian: str) -> str:
    if pid in (PID_TOPIC_NAME, PID_TYPE_NAME):
        s = _read_string(value, endian)
        return s if s is not None else value.hex()
    if pid in (PID_ENDPOINT_GUID, PID_PARTICIPANT_GUID):
        return _format_guid(value)
    if pid in (
        PID_UNICAST_LOCATOR,
        PID_DEFAULT_UNICAST_LOCATOR,
        PID_MULTICAST_LOCATOR,
        PID_DEFAULT_MULTICAST_LOCATOR,
        PID_METATRAFFIC_UNICAST_LOCATOR,
        PID_METATRAFFIC_MULTICAST_LOCATOR,
    ):
        try:
            loc = Locator.from_bytes(value)
            return f"{loc.kind} {loc.ipv4_str}:{loc.port}"
        except Exception:
            return value.hex()
    if pid == PID_PROTOCOL_VERSION and len(value) >= 2:
        return f"{value[0]}.{value[1]}"
    if pid == PID_VENDORID and len(value) >= 2:
        return f"{value[0]:02x}{value[1]:02x}"
    return value.hex()


def _parse_parameter_list(payload: bytes) -> tuple[str, list[tuple[int, str, int]]]:
    scheme, pl_data = parse_encapsulation_header(payload)
    endian = "<" if scheme in (PL_CDR_LE, CDR_LE) else ">"
    items: list[tuple[int, str, int]] = []
    for pid, value in ParameterListParser(pl_data, endian):
        name = PID_NAMES.get(pid, f"0x{pid:04x}")
        decoded = _decode_pid(pid, value, endian)
        items.append((pid, f"{name}={decoded}", len(value)))
    if scheme == PL_CDR_LE:
        enc = "PL_CDR_LE"
    elif scheme == PL_CDR_BE:
        enc = "PL_CDR_BE"
    else:
        enc = "CDR"
    return enc, items


def _log_header(out, ts: float, addr: str, port: int, info: str) -> None:
    t = dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    out.write(f"[{t}] {addr}:{port} {info}\n")


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


def main() -> int:
    parser = argparse.ArgumentParser(description="RTPS pcap parser for SPDP/SEDP")
    parser.add_argument("pcap", help="Path to pcap/pcapng file")
    parser.add_argument("--ports", default="", help="Optional UDP port filter (e.g. 7400,7410-7420)")
    parser.add_argument("--output", default=None, help="Log file path")
    args = parser.parse_args()

    ports = set(parse_ports(args.ports)) if args.ports else None

    out = sys.stdout
    if args.output:
        out = open(args.output, "w", encoding="utf-8")

    out.write("# RTPS pcap dump\n")
    out.write(f"# pcap={args.pcap}\n")
    if ports:
        out.write(f"# ports={sorted(ports)}\n")

    packets = rdpcap(args.pcap)
    for pkt in packets:
        if UDP not in pkt:
            continue
        udp = pkt[UDP]
        if ports and udp.dport not in ports and udp.sport not in ports:
            continue
        payload = bytes(udp.payload)
        if not payload.startswith(b"RTPS"):
            continue

        ip = pkt.getlayer("IP") or pkt.getlayer("IPv6")
        src = ip.src if ip is not None else "?"
        ts = float(getattr(pkt, "time", 0.0))

        try:
            msg = RtpsMessageParser.parse(payload)
        except Exception:
            continue

        prefix = msg.header.guid_prefix.value.hex()
        _log_header(out, ts, src, int(udp.sport), f"RTPS guid_prefix={prefix}")

        for sm in msg.submessages:
            if isinstance(sm, DataSubmessage):
                writer = sm.writer_id.value.hex()
                reader = sm.reader_id.value.hex()
                if not sm.serialized_payload:
                    continue
                try:
                    enc, items = _parse_parameter_list(sm.serialized_payload)
                except Exception:
                    out.write(f"  DATA writer={writer} reader={reader} enc=PARSE_ERROR\n")
                    continue
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

    if out is not sys.stdout:
        out.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
