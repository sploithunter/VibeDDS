#!/usr/bin/env python3
"""Inspect RTI PID 0x8021 TypeObject payloads.

Supports:
  - Extracting the 0x8021 blob from a sedp dump file.
  - Parsing the RTI header (kind, uncompressed_len, compressed_len).
  - Decompressing the zlib payload to raw XCDR2 TypeObject bytes.
  - Computing EquivalenceHash (first 14 bytes of MD5 of serialized TypeObject).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import textwrap
import zlib


def _clean_hex(value: str) -> str:
    value = value.strip()
    if value.startswith("0x") or value.startswith("0X"):
        value = value[2:]
    return "".join(ch for ch in value if ch in "0123456789abcdefABCDEF")


def _hex_bytes(value: str) -> bytes:
    cleaned = _clean_hex(value)
    if len(cleaned) % 2 != 0:
        cleaned = "0" + cleaned
    return bytes.fromhex(cleaned)


def _extract_from_sedp(path: str, topic: str | None) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()
    if topic:
        topic = topic.strip()
    for i, line in enumerate(lines):
        if topic:
            if f"TOPIC_NAME={topic}" not in line:
                continue
        for j in range(i, min(i + 80, len(lines))):
            if "0x8021=" in lines[j]:
                return lines[j].split("0x8021=")[1].split(" (len=")[0].strip()
    raise SystemExit("No 0x8021 payload found for the requested topic.")


def _parse_header(blob: bytes) -> tuple[int, int, int, bytes]:
    if len(blob) < 12:
        raise SystemExit("Blob too short for RTI 0x8021 header.")
    kind = int.from_bytes(blob[0:4], "little")
    uncompressed_len = int.from_bytes(blob[4:8], "little")
    compressed_len = int.from_bytes(blob[8:12], "little")
    return kind, uncompressed_len, compressed_len, blob[12:]


def _hex_preview(data: bytes, width: int = 32) -> str:
    return data[:width].hex()


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect RTI TypeObject PID 0x8021 payloads")
    parser.add_argument("--hex", help="Hex string for the 0x8021 payload")
    parser.add_argument("--sedp", help="Path to sedp dump text file")
    parser.add_argument("--topic", help="Topic name to find in sedp dump")
    parser.add_argument("--out", help="Write decompressed TypeObject bytes to file")
    parser.add_argument("--repack", help="Write a re-packed RTI payload to file")
    parser.add_argument("--dump", action="store_true", help="Print decompressed hex (wrapped)")
    args = parser.parse_args()

    if not args.hex and not args.sedp:
        parser.error("Provide --hex or --sedp.")
    if args.hex and args.sedp:
        parser.error("Provide only one of --hex or --sedp.")

    if args.hex:
        hex_payload = args.hex
    else:
        hex_payload = _extract_from_sedp(args.sedp, args.topic)

    blob = _hex_bytes(hex_payload)
    kind, uncompressed_len, compressed_len, compressed = _parse_header(blob)

    print(f"kind={kind} uncompressed_len={uncompressed_len} compressed_len={compressed_len}")
    print(f"compressed_bytes={len(compressed)} zlib_header={compressed[:2].hex()}")

    try:
        decompressed = zlib.decompress(compressed)
    except zlib.error as exc:
        raise SystemExit(f"zlib decompress failed: {exc}") from exc

    print(f"decompressed_len={len(decompressed)} prefix={_hex_preview(decompressed)}")
    if uncompressed_len and len(decompressed) != uncompressed_len:
        print("WARNING: decompressed length does not match header")
    if compressed_len and len(compressed) != compressed_len:
        print("WARNING: compressed length does not match header")

    md5 = hashlib.md5(decompressed).digest()
    equiv_hash = md5[:14]
    print(f"equivalence_hash_md5_14={equiv_hash.hex()}")

    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "wb") as fh:
            fh.write(decompressed)
        print(f"wrote decompressed bytes -> {args.out}")

    if args.repack:
        repacked = blob[:12] + zlib.compress(decompressed)
        os.makedirs(os.path.dirname(args.repack), exist_ok=True)
        with open(args.repack, "wb") as fh:
            fh.write(repacked)
        print(f"wrote repacked payload -> {args.repack}")

    if args.dump:
        print("decompressed_hex:")
        print("\n".join(textwrap.wrap(decompressed.hex(), 96)))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
