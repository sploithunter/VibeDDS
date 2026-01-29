"""Type support helpers for common DDS types.

Provides CDR serialization/deserialization for well-known types
like HelloWorld and ShapeType, so users don't need an IDL compiler.
"""

from __future__ import annotations

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
    """CDR support for: struct ShapeType { string color; long x; long y; long shapesize; };"""

    TYPE_NAME = "ShapeType"

    @staticmethod
    def serialize(color: str, x: int, y: int, shapesize: int) -> bytes:
        """Serialize a ShapeType sample to CDR LE with encapsulation header."""
        ser = CdrSerializer("<")
        ser.write_string(color)
        ser.write_int32(x)
        ser.write_int32(y)
        ser.write_int32(shapesize)
        return encapsulation_header(CDR_LE) + ser.getvalue()

    @staticmethod
    def deserialize(data: bytes) -> dict:
        """Deserialize a ShapeType sample. Returns dict with color, x, y, shapesize."""
        de = CdrDeserializer(data[4:], "<")
        return {
            "color": de.read_string(),
            "x": de.read_int32(),
            "y": de.read_int32(),
            "shapesize": de.read_int32(),
        }
