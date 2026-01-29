"""CDR (Common Data Representation) serialization and deserialization.

Implements XCDR1 encoding with alignment rules per the OMG CDR specification.
Also provides ParameterList builder/parser for RTPS discovery data.
"""

import struct
from typing import Iterator

# Encapsulation scheme identifiers (2-byte big-endian)
CDR_BE = 0x0000
CDR_LE = 0x0001
PL_CDR_BE = 0x0002
PL_CDR_LE = 0x0003

# Sentinel PID for parameter lists
PID_SENTINEL = 0x0001
PID_PAD = 0x0000


def encapsulation_header(scheme: int) -> bytes:
    """Build a 4-byte CDR encapsulation header: [scheme_hi, scheme_lo, 0, 0]."""
    return struct.pack(">HH", scheme, 0)


def parse_encapsulation_header(data: bytes) -> tuple[int, bytes]:
    """Parse 4-byte encapsulation header. Returns (scheme, remaining_data)."""
    if len(data) < 4:
        raise ValueError("Encapsulation header requires at least 4 bytes")
    scheme = struct.unpack(">H", data[0:2])[0]
    # bytes 2-3 are options (ignored)
    return scheme, data[4:]


class CdrSerializer:
    """Serializes values into CDR format.

    Supports both little-endian and big-endian encoding.
    Tracks current offset for alignment calculations.
    """

    def __init__(self, endian: str = "<"):
        """Initialize serializer.

        Args:
            endian: '<' for little-endian, '>' for big-endian.
        """
        if endian not in ("<", ">"):
            raise ValueError("endian must be '<' or '>'")
        self._endian = endian
        self._buf = bytearray()
        self._origin = 0

    @property
    def buffer(self) -> bytearray:
        return self._buf

    def set_origin(self) -> None:
        """Reset alignment origin to current offset.

        Used when serializing parameter values so alignment is relative
        to the start of each parameter value, not the start of the stream.
        """
        self._origin = len(self._buf)

    def _align(self, n: int) -> None:
        """Pad to n-byte alignment relative to origin."""
        offset = len(self._buf) - self._origin
        remainder = offset % n
        if remainder != 0:
            self._buf.extend(b'\x00' * (n - remainder))

    def write_bool(self, value: bool) -> None:
        self._buf.append(1 if value else 0)

    def write_uint8(self, value: int) -> None:
        self._buf.append(value & 0xFF)

    def write_int8(self, value: int) -> None:
        self._buf.extend(struct.pack(self._endian + "b", value))

    def write_uint16(self, value: int) -> None:
        self._align(2)
        self._buf.extend(struct.pack(self._endian + "H", value))

    def write_int16(self, value: int) -> None:
        self._align(2)
        self._buf.extend(struct.pack(self._endian + "h", value))

    def write_uint32(self, value: int) -> None:
        self._align(4)
        self._buf.extend(struct.pack(self._endian + "I", value))

    def write_int32(self, value: int) -> None:
        self._align(4)
        self._buf.extend(struct.pack(self._endian + "i", value))

    def write_uint64(self, value: int) -> None:
        self._align(8)
        self._buf.extend(struct.pack(self._endian + "Q", value))

    def write_int64(self, value: int) -> None:
        self._align(8)
        self._buf.extend(struct.pack(self._endian + "q", value))

    def write_float32(self, value: float) -> None:
        self._align(4)
        self._buf.extend(struct.pack(self._endian + "f", value))

    def write_float64(self, value: float) -> None:
        self._align(8)
        self._buf.extend(struct.pack(self._endian + "d", value))

    def write_string(self, value: str) -> None:
        """Write a CDR string: u32 length (including NUL) + UTF-8 bytes + NUL.

        The length field includes the terminating NUL byte.
        No trailing padding after the NUL — that's handled by the next
        write's alignment.
        """
        encoded = value.encode("utf-8")
        length = len(encoded) + 1  # +1 for NUL terminator
        self.write_uint32(length)
        self._buf.extend(encoded)
        self._buf.append(0)  # NUL terminator

    def write_bytes_raw(self, data: bytes | bytearray) -> None:
        """Write raw bytes without any length prefix or alignment."""
        self._buf.extend(data)

    def write_sequence(self, items: list, write_fn) -> None:
        """Write a CDR sequence: u32 length followed by each element.

        Args:
            items: List of items to serialize.
            write_fn: Callable that takes (serializer, item) and writes one element.
        """
        self.write_uint32(len(items))
        for item in items:
            write_fn(self, item)

    def getvalue(self) -> bytes:
        """Return the serialized bytes."""
        return bytes(self._buf)


class CdrDeserializer:
    """Deserializes values from CDR format.

    Supports both little-endian and big-endian encoding.
    Tracks current offset for alignment calculations.
    """

    def __init__(self, data: bytes | bytearray | memoryview, endian: str = "<"):
        """Initialize deserializer.

        Args:
            data: Input bytes to deserialize.
            endian: '<' for little-endian, '>' for big-endian.
        """
        if endian not in ("<", ">"):
            raise ValueError("endian must be '<' or '>'")
        self._data = bytes(data)
        self._endian = endian
        self._pos = 0
        self._origin = 0

    @property
    def pos(self) -> int:
        return self._pos

    @property
    def remaining(self) -> int:
        return len(self._data) - self._pos

    def set_origin(self) -> None:
        """Reset alignment origin to current position."""
        self._origin = self._pos

    def _align(self, n: int) -> None:
        """Advance position to n-byte alignment relative to origin."""
        offset = self._pos - self._origin
        remainder = offset % n
        if remainder != 0:
            self._pos += n - remainder

    def _read(self, n: int) -> bytes:
        if self._pos + n > len(self._data):
            raise ValueError(
                f"Buffer underflow: need {n} bytes at offset {self._pos}, "
                f"but only {len(self._data) - self._pos} remain"
            )
        result = self._data[self._pos:self._pos + n]
        self._pos += n
        return result

    def read_bool(self) -> bool:
        return self._read(1)[0] != 0

    def read_uint8(self) -> int:
        return self._read(1)[0]

    def read_int8(self) -> int:
        return struct.unpack(self._endian + "b", self._read(1))[0]

    def read_uint16(self) -> int:
        self._align(2)
        return struct.unpack(self._endian + "H", self._read(2))[0]

    def read_int16(self) -> int:
        self._align(2)
        return struct.unpack(self._endian + "h", self._read(2))[0]

    def read_uint32(self) -> int:
        self._align(4)
        return struct.unpack(self._endian + "I", self._read(4))[0]

    def read_int32(self) -> int:
        self._align(4)
        return struct.unpack(self._endian + "i", self._read(4))[0]

    def read_uint64(self) -> int:
        self._align(8)
        return struct.unpack(self._endian + "Q", self._read(8))[0]

    def read_int64(self) -> int:
        self._align(8)
        return struct.unpack(self._endian + "q", self._read(8))[0]

    def read_float32(self) -> float:
        self._align(4)
        return struct.unpack(self._endian + "f", self._read(4))[0]

    def read_float64(self) -> float:
        self._align(8)
        return struct.unpack(self._endian + "d", self._read(8))[0]

    def read_string(self) -> str:
        """Read a CDR string: u32 length (incl NUL) + UTF-8 bytes + NUL."""
        length = self.read_uint32()
        if length == 0:
            return ""
        raw = self._read(length)
        # Strip the NUL terminator
        if raw[-1:] == b'\x00':
            raw = raw[:-1]
        return raw.decode("utf-8")

    def read_bytes_raw(self, n: int) -> bytes:
        """Read exactly n raw bytes."""
        return self._read(n)

    def read_sequence(self, read_fn) -> list:
        """Read a CDR sequence: u32 count followed by elements.

        Args:
            read_fn: Callable that takes (deserializer) and returns one element.
        """
        count = self.read_uint32()
        return [read_fn(self) for _ in range(count)]


class ParameterListBuilder:
    """Builds a CDR parameter list (PID + length + value) with PID_SENTINEL termination.

    Each parameter is: u16 pid + u16 length + value_bytes (padded to 4-byte multiple).
    """

    def __init__(self, endian: str = "<"):
        self._endian = endian
        self._buf = bytearray()

    def add_parameter(self, pid: int, value_bytes: bytes | bytearray) -> None:
        """Add a parameter with the given PID and serialized value.

        Value is padded to a 4-byte boundary.
        """
        # Pad value to 4-byte alignment
        padded_len = (len(value_bytes) + 3) & ~3
        padded_value = value_bytes + b'\x00' * (padded_len - len(value_bytes))

        self._buf.extend(struct.pack(self._endian + "HH", pid, padded_len))
        self._buf.extend(padded_value)

    def finalize(self) -> bytes:
        """Append PID_SENTINEL and return the complete parameter list bytes."""
        self._buf.extend(struct.pack(self._endian + "HH", PID_SENTINEL, 0))
        return bytes(self._buf)


class ParameterListParser:
    """Parses a CDR parameter list, yielding (pid, value_bytes) tuples.

    Stops at PID_SENTINEL or end of data.
    """

    def __init__(self, data: bytes | bytearray | memoryview, endian: str = "<"):
        self._data = bytes(data)
        self._endian = endian

    def __iter__(self) -> Iterator[tuple[int, bytes]]:
        pos = 0
        while pos + 4 <= len(self._data):
            pid, length = struct.unpack(
                self._endian + "HH", self._data[pos:pos + 4]
            )
            pos += 4
            if pid == PID_SENTINEL:
                return
            if pid == PID_PAD:
                pos += length
                continue
            if pos + length > len(self._data):
                raise ValueError(
                    f"Parameter length {length} at offset {pos - 4} "
                    f"exceeds remaining data ({len(self._data) - pos} bytes)"
                )
            value = self._data[pos:pos + length]
            yield pid, value
            pos += length
