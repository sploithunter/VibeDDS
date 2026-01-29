"""Type support helpers for common DDS types.

Provides CDR serialization/deserialization for well-known types
like HelloWorld and ShapeType, so users don't need an IDL compiler.
"""

from __future__ import annotations

import os

from vibedds.cdr import CdrSerializer, CdrDeserializer, encapsulation_header, CDR_LE


class HelloWorldType:
    """CDR support for: struct HelloWorld { string message; };"""

    TYPE_NAME = "HelloWorld"

    @staticmethod
    def serialize(message: str) -> bytes:
        """Serialize a HelloWorld sample to CDR LE with encapsulation header."""
        ser = CdrSerializer("<")
        ser.write_string(message)
        return encapsulation_header(CDR_LE) + ser.getvalue()

    @staticmethod
    def deserialize(data: bytes) -> str:
        """Deserialize a HelloWorld sample from CDR with encapsulation header."""
        # Skip 4-byte encapsulation header
        de = CdrDeserializer(data[4:], "<")
        return de.read_string()


class ShapeType:
    """CDR support for: struct ShapeType { string color; long x; long y; long shapesize; FillKind fillKind; long angle; };"""

    TYPE_NAME = "ShapeType"

    @staticmethod
    def serialize(
        color: str,
        x: int,
        y: int,
        shapesize: int,
        fill_kind: int = 0,
        angle: int = 0,
    ) -> bytes:
        """Serialize a ShapeType sample to CDR LE with encapsulation header."""
        ser = CdrSerializer("<")
        ser.write_string(color)
        ser.write_int32(x)
        ser.write_int32(y)
        ser.write_int32(shapesize)
        ser.write_int32(fill_kind)
        ser.write_int32(angle)
        return encapsulation_header(CDR_LE) + ser.getvalue()

    @staticmethod
    def deserialize(data: bytes) -> dict:
        """Deserialize a ShapeType sample. Returns dict with color, x, y, shapesize, fillKind, angle."""
        de = CdrDeserializer(data[4:], "<")
        result = {
            "color": de.read_string(),
            "x": de.read_int32(),
            "y": de.read_int32(),
            "shapesize": de.read_int32(),
        }
        if de.remaining >= 4:
            result["fillKind"] = de.read_int32()
        if de.remaining >= 4:
            result["angle"] = de.read_int32()
        return result


class PingType:
    """CDR support for: struct PingType { long count; };"""

    TYPE_NAME = "PingType"

    @staticmethod
    def serialize(count: int) -> bytes:
        """Serialize a PingType sample to CDR LE with encapsulation header."""
        ser = CdrSerializer("<")
        ser.write_int32(count)
        return encapsulation_header(CDR_LE) + ser.getvalue()

    @staticmethod
    def deserialize(data: bytes) -> int:
        """Deserialize a PingType sample from CDR with encapsulation header."""
        de = CdrDeserializer(data[4:], "<")
        return de.read_int32()


# XTypes TypeInformation (serialized) captured from OpenDDS 3.34 for interop.
HELLOWORLD_TYPE_INFORMATION = bytes.fromhex(
    "5400000001100040280000002400000014000000f1b171dd17cc21f1"
    "d56aa6e08ff86a0028000000ffffffff040000000000000002100040"
    "1c000000180000000800000000000000000000000000000004000000"
    "00000000"
)
SHAPETYPE_TYPE_INFORMATION = bytes.fromhex(
    "5400000001100040280000002400000014000000f139b4f2ccabb48b"
    "ad086c66d05df10057000000ffffffff040000000000000002100040"
    "1c000000180000000800000000000000000000000000000004000000"
    "00000000"
)
PINGTYPE_TYPE_INFORMATION = bytes.fromhex(
    "5400000001100040280000002400000014000000f1ebfe38b8cbf57e"
    "d81be0408006740027000000ffffffff040000000000000002100040"
    "1c000000180000000800000000000000000000000000000004000000"
    "00000000"
)

TYPE_INFORMATION_BY_NAME = {
    HelloWorldType.TYPE_NAME: HELLOWORLD_TYPE_INFORMATION,
    ShapeType.TYPE_NAME: SHAPETYPE_TYPE_INFORMATION,
    PingType.TYPE_NAME: PINGTYPE_TYPE_INFORMATION,
}

# RTI TypeObject (PID 0x8021) payload captured on 2026-01-29.
HELLOWORLD_TYPE_OBJECT = bytes.fromhex(
    "0100000078010000b100000078da63ace76000011f46060626308b85410c4832"
    "02c53981f412281b0414c0a41898fca5fff40a7755f63f6e20db233527273f3c"
    "bf282705a296116c0a0480f82968fc54901e101bc96c1506041086d215577dd2"
    "2c99b6548254e4a6161727a6a76298cf548fc0205161a899203d2548e6eb80d4"
    "424d86992b0a6417971465e6a5c71b999ac627672416252697a416c1dc89cb1f"
    "3c40980a9501899f808aff47720f4cbf003cc4106106920700a6e82fe3000000"
)

SHAPETYPE_TYPE_OBJECT = bytes.fromhex(
    "01000000100400009201000078da63ace760008127cc0c0c2c60160b83189064048a7302"
    "e92f503608688049313079b9ba83ad4142c35908c80ece482c480da92c4875ad2849cd4b"
    "494d81ea6164809909e183c405e02630301c7dbdf1deb190bf9920b95420bf05889930ec"
    "8398c107653f39fda031f9d7157e90dbd2327372bc33f35218b0d8c7548f3047022ac60a"
    "c49c40c806a413f3d2735271e88361f4b0f0604498a9801416307f702187059e3040e683d"
    "4bd818ac1cc5601b1a16a84a1f455d35fd3d66d9b08767b727e4e7e11013f8bc0ec00fb9"
    "b151cae1544ea6142d25349408f0c548c19aa071406c5a03028ceac22267c85a16a40a695"
    "2085810ed81dc2287e1705995d529499971e6f6864119f9c915894985c925ac44020ac798"
    "030152a03123f01156f6040750b1f541e944e2ea0c5072c05c2d21f1f2caedd1089109f1b"
    "1490e2bb00490d37c81c7f1f4f9778374f1f1f487c0902714890a35f70806390ab5f085406"
    "122fa014e7e11fe419e5ef17e2e813efe118e2ec0153c00c8dc330d7a0104f675459983f6"
    "16e44ce87b0bc0c920700162a831a0000"
)

TYPE_OBJECT_BY_NAME = {
    HelloWorldType.TYPE_NAME: HELLOWORLD_TYPE_OBJECT,
    ShapeType.TYPE_NAME: SHAPETYPE_TYPE_OBJECT,
}

_DEFAULT_KEYED_TYPES = {
    ShapeType.TYPE_NAME,
}


def _keyed_types_from_env() -> set[str]:
    raw = os.getenv("VIBEDDS_KEYED_TYPES")
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def is_keyed_type(type_name: str) -> bool:
    """Return True if the type name is keyed (has @key fields)."""
    if type_name in _DEFAULT_KEYED_TYPES:
        return True
    return type_name in _keyed_types_from_env()


def type_information_for(type_name: str) -> bytes | None:
    """Return serialized XTypes TypeInformation for a known type name."""
    return TYPE_INFORMATION_BY_NAME.get(type_name)


def _sanitize_type_name_for_env(type_name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in type_name).upper()


def type_object_for(type_name: str) -> bytes | None:
    """Return serialized XTypes TypeObject (PID 0x8021) for a known type name."""
    override = os.getenv("VIBEDDS_SEDP_TYPE_OBJECT_HEX")
    if override:
        return bytes.fromhex("".join(ch for ch in override if ch in "0123456789abcdefABCDEF"))
    env_key = f"VIBEDDS_SEDP_TYPE_OBJECT_HEX_{_sanitize_type_name_for_env(type_name)}"
    override = os.getenv(env_key)
    if override:
        return bytes.fromhex("".join(ch for ch in override if ch in "0123456789abcdefABCDEF"))
    return TYPE_OBJECT_BY_NAME.get(type_name)
