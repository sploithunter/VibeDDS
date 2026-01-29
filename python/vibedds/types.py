"""RTPS core types: GuidPrefix, EntityId, Guid, SequenceNumber, Locator, Timestamp, etc.

All types are frozen dataclasses with serialize/deserialize class methods.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import ClassVar

from vibedds.cdr import CdrSerializer, CdrDeserializer
from vibedds.constants import LOCATOR_KIND_UDPv4, LOCATOR_KIND_INVALID


@dataclass(frozen=True)
class ProtocolVersion:
    major: int  # u8
    minor: int  # u8

    def serialize(self, ser: CdrSerializer) -> None:
        ser.write_uint8(self.major)
        ser.write_uint8(self.minor)

    @classmethod
    def deserialize(cls, de: CdrDeserializer) -> ProtocolVersion:
        return cls(major=de.read_uint8(), minor=de.read_uint8())

    def to_bytes(self) -> bytes:
        return bytes([self.major, self.minor])

    @classmethod
    def from_bytes(cls, data: bytes) -> ProtocolVersion:
        return cls(major=data[0], minor=data[1])


@dataclass(frozen=True)
class VendorId:
    vendor: tuple[int, int]  # 2 bytes

    def serialize(self, ser: CdrSerializer) -> None:
        ser.write_uint8(self.vendor[0])
        ser.write_uint8(self.vendor[1])

    @classmethod
    def deserialize(cls, de: CdrDeserializer) -> VendorId:
        return cls(vendor=(de.read_uint8(), de.read_uint8()))

    def to_bytes(self) -> bytes:
        return bytes(self.vendor)

    @classmethod
    def from_bytes(cls, data: bytes) -> VendorId:
        return cls(vendor=(data[0], data[1]))


@dataclass(frozen=True)
class GuidPrefix:
    """12-byte GUID prefix identifying a participant."""
    value: bytes  # exactly 12 bytes

    UNKNOWN: ClassVar[GuidPrefix]

    def __post_init__(self):
        if len(self.value) != 12:
            raise ValueError(f"GuidPrefix must be 12 bytes, got {len(self.value)}")

    def serialize(self, ser: CdrSerializer) -> None:
        ser.write_bytes_raw(self.value)

    @classmethod
    def deserialize(cls, de: CdrDeserializer) -> GuidPrefix:
        return cls(value=de.read_bytes_raw(12))

    def to_bytes(self) -> bytes:
        return self.value

    @classmethod
    def from_bytes(cls, data: bytes) -> GuidPrefix:
        return cls(value=bytes(data[:12]))

    def __repr__(self) -> str:
        return f"GuidPrefix({self.value.hex()})"


GuidPrefix.UNKNOWN = GuidPrefix(b'\x00' * 12)


@dataclass(frozen=True)
class EntityId:
    """4-byte entity identifier: 3-byte key + 1-byte kind."""
    value: bytes  # exactly 4 bytes

    UNKNOWN: ClassVar[EntityId]

    def __post_init__(self):
        if len(self.value) != 4:
            raise ValueError(f"EntityId must be 4 bytes, got {len(self.value)}")

    @property
    def entity_key(self) -> bytes:
        return self.value[:3]

    @property
    def entity_kind(self) -> int:
        return self.value[3]

    def serialize(self, ser: CdrSerializer) -> None:
        ser.write_bytes_raw(self.value)

    @classmethod
    def deserialize(cls, de: CdrDeserializer) -> EntityId:
        return cls(value=de.read_bytes_raw(4))

    def to_bytes(self) -> bytes:
        return self.value

    @classmethod
    def from_bytes(cls, data: bytes) -> EntityId:
        return cls(value=bytes(data[:4]))

    def __repr__(self) -> str:
        return f"EntityId({self.value.hex()})"


EntityId.UNKNOWN = EntityId(b'\x00\x00\x00\x00')


@dataclass(frozen=True)
class Guid:
    """16-byte globally unique identifier = GuidPrefix(12) + EntityId(4)."""
    prefix: GuidPrefix
    entity_id: EntityId

    def serialize(self, ser: CdrSerializer) -> None:
        self.prefix.serialize(ser)
        self.entity_id.serialize(ser)

    @classmethod
    def deserialize(cls, de: CdrDeserializer) -> Guid:
        return cls(
            prefix=GuidPrefix.deserialize(de),
            entity_id=EntityId.deserialize(de),
        )

    def to_bytes(self) -> bytes:
        return self.prefix.value + self.entity_id.value

    @classmethod
    def from_bytes(cls, data: bytes) -> Guid:
        return cls(
            prefix=GuidPrefix(data[:12]),
            entity_id=EntityId(data[12:16]),
        )

    def __repr__(self) -> str:
        return f"Guid({self.prefix.value.hex()}|{self.entity_id.value.hex()})"


@dataclass(frozen=True)
class SequenceNumber:
    """RTPS sequence number: i32 high + u32 low = 64-bit value."""
    high: int  # i32
    low: int   # u32

    ZERO: ClassVar[SequenceNumber]
    UNKNOWN: ClassVar[SequenceNumber]

    @classmethod
    def from_value(cls, value: int) -> SequenceNumber:
        high = (value >> 32) & 0xFFFFFFFF
        if high >= 0x80000000:
            high -= 0x100000000
        low = value & 0xFFFFFFFF
        return cls(high=high, low=low)

    @property
    def value(self) -> int:
        return ((self.high & 0xFFFFFFFF) << 32) | self.low

    def __add__(self, other: int) -> SequenceNumber:
        return SequenceNumber.from_value(self.value + other)

    def __sub__(self, other: SequenceNumber | int) -> int | SequenceNumber:
        if isinstance(other, SequenceNumber):
            return self.value - other.value
        return SequenceNumber.from_value(self.value - other)

    def __lt__(self, other: SequenceNumber) -> bool:
        return self.value < other.value

    def __le__(self, other: SequenceNumber) -> bool:
        return self.value <= other.value

    def __gt__(self, other: SequenceNumber) -> bool:
        return self.value > other.value

    def __ge__(self, other: SequenceNumber) -> bool:
        return self.value >= other.value

    def serialize(self, ser: CdrSerializer) -> None:
        ser.write_int32(self.high)
        ser.write_uint32(self.low)

    @classmethod
    def deserialize(cls, de: CdrDeserializer) -> SequenceNumber:
        return cls(high=de.read_int32(), low=de.read_uint32())


SequenceNumber.ZERO = SequenceNumber(0, 0)
SequenceNumber.UNKNOWN = SequenceNumber(-1, 0)


@dataclass(frozen=True)
class SequenceNumberSet:
    """Bitmap of sequence numbers: base + numBits + bitmap words."""
    base: SequenceNumber
    num_bits: int  # u32, 0..256
    bitmap: tuple[int, ...]  # u32 words, ceil(num_bits/32) entries

    def contains(self, sn: SequenceNumber) -> bool:
        offset = sn.value - self.base.value
        if offset < 0 or offset >= self.num_bits:
            return False
        word_idx = offset // 32
        bit_idx = 31 - (offset % 32)  # MSB first within each word
        return bool(self.bitmap[word_idx] & (1 << bit_idx))

    def missing_sequence_numbers(self) -> list[SequenceNumber]:
        """Return sequence numbers where bitmap bit is SET (= missing/requested)."""
        result = []
        for i in range(self.num_bits):
            word_idx = i // 32
            bit_idx = 31 - (i % 32)
            if self.bitmap[word_idx] & (1 << bit_idx):
                result.append(self.base + i)
        return result

    def serialize(self, ser: CdrSerializer) -> None:
        self.base.serialize(ser)
        ser.write_uint32(self.num_bits)
        for word in self.bitmap:
            ser.write_uint32(word)

    @classmethod
    def deserialize(cls, de: CdrDeserializer) -> SequenceNumberSet:
        base = SequenceNumber.deserialize(de)
        num_bits = de.read_uint32()
        num_words = (num_bits + 31) // 32
        bitmap = tuple(de.read_uint32() for _ in range(num_words))
        return cls(base=base, num_bits=num_bits, bitmap=bitmap)


@dataclass(frozen=True)
class Locator:
    """Network locator: kind (i32) + port (u32) + 16-byte address."""
    kind: int   # i32
    port: int   # u32
    address: bytes  # 16 bytes

    INVALID: ClassVar[Locator]

    def __post_init__(self):
        if len(self.address) != 16:
            raise ValueError(f"Locator address must be 16 bytes, got {len(self.address)}")

    @classmethod
    def from_ipv4(cls, ip: str, port: int) -> Locator:
        """Create a UDPv4 locator from dotted IP string and port."""
        parts = [int(p) for p in ip.split('.')]
        addr = b'\x00' * 12 + bytes(parts)
        return cls(kind=LOCATOR_KIND_UDPv4, port=port, address=addr)

    @property
    def ipv4_str(self) -> str | None:
        if self.kind != LOCATOR_KIND_UDPv4:
            return None
        return '.'.join(str(b) for b in self.address[12:16])

    def serialize(self, ser: CdrSerializer) -> None:
        ser.write_int32(self.kind)
        ser.write_uint32(self.port)
        ser.write_bytes_raw(self.address)

    @classmethod
    def deserialize(cls, de: CdrDeserializer) -> Locator:
        return cls(
            kind=de.read_int32(),
            port=de.read_uint32(),
            address=de.read_bytes_raw(16),
        )

    def to_bytes(self) -> bytes:
        return struct.pack("<iI", self.kind, self.port) + self.address

    @classmethod
    def from_bytes(cls, data: bytes) -> Locator:
        kind, port = struct.unpack("<iI", data[:8])
        return cls(kind=kind, port=port, address=bytes(data[8:24]))


Locator.INVALID = Locator(kind=LOCATOR_KIND_INVALID, port=0, address=b'\x00' * 16)


@dataclass(frozen=True)
class Timestamp:
    """RTPS Timestamp / Time_t: seconds (i32) + fraction (u32).

    Fraction represents fractions of a second as (fraction / 2^32).
    """
    seconds: int   # i32
    fraction: int  # u32

    ZERO: ClassVar[Timestamp]
    INVALID: ClassVar[Timestamp]

    def serialize(self, ser: CdrSerializer) -> None:
        ser.write_int32(self.seconds)
        ser.write_uint32(self.fraction)

    @classmethod
    def deserialize(cls, de: CdrDeserializer) -> Timestamp:
        return cls(seconds=de.read_int32(), fraction=de.read_uint32())

    def to_bytes(self, endian: str = "<") -> bytes:
        return struct.pack(endian + "iI", self.seconds, self.fraction)

    @classmethod
    def from_bytes(cls, data: bytes, endian: str = "<") -> Timestamp:
        s, f = struct.unpack(endian + "iI", data[:8])
        return cls(seconds=s, fraction=f)

    @classmethod
    def from_seconds(cls, secs: float) -> Timestamp:
        s = int(secs)
        f = int((secs - s) * (2**32))
        return cls(seconds=s, fraction=f)

    def to_seconds(self) -> float:
        return self.seconds + self.fraction / (2**32)


Timestamp.ZERO = Timestamp(0, 0)
Timestamp.INVALID = Timestamp(-1, 0xFFFFFFFF)


@dataclass(frozen=True)
class Duration:
    """RTPS Duration: seconds (i32) + fraction (u32). Same layout as Timestamp."""
    seconds: int   # i32
    fraction: int  # u32

    ZERO: ClassVar[Duration]
    INFINITE: ClassVar[Duration]

    def serialize(self, ser: CdrSerializer) -> None:
        ser.write_int32(self.seconds)
        ser.write_uint32(self.fraction)

    @classmethod
    def deserialize(cls, de: CdrDeserializer) -> Duration:
        return cls(seconds=de.read_int32(), fraction=de.read_uint32())

    def to_bytes(self, endian: str = "<") -> bytes:
        return struct.pack(endian + "iI", self.seconds, self.fraction)

    @classmethod
    def from_bytes(cls, data: bytes, endian: str = "<") -> Duration:
        s, f = struct.unpack(endian + "iI", data[:8])
        return cls(seconds=s, fraction=f)

    def to_seconds(self) -> float:
        return self.seconds + self.fraction / (2**32)

    @classmethod
    def from_seconds(cls, secs: float) -> Duration:
        s = int(secs)
        f = int((secs - s) * (2**32))
        return cls(seconds=s, fraction=f)


Duration.ZERO = Duration(0, 0)
Duration.INFINITE = Duration(0x7FFFFFFF, 0xFFFFFFFF)
