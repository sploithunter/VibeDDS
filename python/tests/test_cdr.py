"""Tests for CDR serialization/deserialization."""

import math
import struct
import pytest

from vibedds.cdr import (
    CdrSerializer,
    CdrDeserializer,
    ParameterListBuilder,
    ParameterListParser,
    PID_SENTINEL,
    CDR_BE,
    CDR_LE,
    PL_CDR_BE,
    PL_CDR_LE,
    encapsulation_header,
    parse_encapsulation_header,
)


# -- Primitive round-trip tests (Little Endian) --

class TestPrimitivesLE:
    def _roundtrip(self, write_method, read_method, value, endian="<"):
        ser = CdrSerializer(endian)
        getattr(ser, write_method)(value)
        de = CdrDeserializer(ser.getvalue(), endian)
        return getattr(de, read_method)()

    def test_bool_true(self):
        assert self._roundtrip("write_bool", "read_bool", True) is True

    def test_bool_false(self):
        assert self._roundtrip("write_bool", "read_bool", False) is False

    def test_uint8(self):
        for v in [0, 1, 127, 255]:
            assert self._roundtrip("write_uint8", "read_uint8", v) == v

    def test_int8(self):
        for v in [-128, -1, 0, 1, 127]:
            assert self._roundtrip("write_int8", "read_int8", v) == v

    def test_uint16(self):
        for v in [0, 1, 256, 65535]:
            assert self._roundtrip("write_uint16", "read_uint16", v) == v

    def test_int16(self):
        for v in [-32768, -1, 0, 1, 32767]:
            assert self._roundtrip("write_int16", "read_int16", v) == v

    def test_uint32(self):
        for v in [0, 1, 0x12345678, 0xFFFFFFFF]:
            assert self._roundtrip("write_uint32", "read_uint32", v) == v

    def test_int32(self):
        for v in [-2147483648, -1, 0, 1, 2147483647]:
            assert self._roundtrip("write_int32", "read_int32", v) == v

    def test_uint64(self):
        for v in [0, 1, 0x123456789ABCDEF0, 0xFFFFFFFFFFFFFFFF]:
            assert self._roundtrip("write_uint64", "read_uint64", v) == v

    def test_int64(self):
        for v in [-(2**63), -1, 0, 1, 2**63 - 1]:
            assert self._roundtrip("write_int64", "read_int64", v) == v

    def test_float32(self):
        for v in [0.0, 1.0, -1.0, 3.14]:
            result = self._roundtrip("write_float32", "read_float32", v)
            assert abs(result - v) < 1e-6

    def test_float32_special(self):
        result = self._roundtrip("write_float32", "read_float32", float('inf'))
        assert math.isinf(result) and result > 0

    def test_float64(self):
        for v in [0.0, 1.0, -1.0, 3.141592653589793, 1e300]:
            assert self._roundtrip("write_float64", "read_float64", v) == v


# -- Primitive round-trip tests (Big Endian) --

class TestPrimitivesBE:
    def _roundtrip(self, write_method, read_method, value):
        ser = CdrSerializer(">")
        getattr(ser, write_method)(value)
        de = CdrDeserializer(ser.getvalue(), ">")
        return getattr(de, read_method)()

    def test_uint32(self):
        assert self._roundtrip("write_uint32", "read_uint32", 0x12345678) == 0x12345678

    def test_int32(self):
        assert self._roundtrip("write_int32", "read_int32", -42) == -42

    def test_uint64(self):
        assert self._roundtrip("write_uint64", "read_uint64", 0xDEADBEEFCAFEBABE) == 0xDEADBEEFCAFEBABE

    def test_float64(self):
        assert self._roundtrip("write_float64", "read_float64", 2.718281828) == 2.718281828

    def test_string(self):
        ser = CdrSerializer(">")
        ser.write_string("hello")
        de = CdrDeserializer(ser.getvalue(), ">")
        assert de.read_string() == "hello"


# -- Known-byte tests --

class TestKnownBytes:
    def test_uint32_le(self):
        ser = CdrSerializer("<")
        ser.write_uint32(0x12345678)
        assert ser.getvalue() == b'\x78\x56\x34\x12'

    def test_uint32_be(self):
        ser = CdrSerializer(">")
        ser.write_uint32(0x12345678)
        assert ser.getvalue() == b'\x12\x34\x56\x78'

    def test_uint16_le(self):
        ser = CdrSerializer("<")
        ser.write_uint16(0xABCD)
        assert ser.getvalue() == b'\xCD\xAB'

    def test_bool_bytes(self):
        ser = CdrSerializer("<")
        ser.write_bool(True)
        ser.write_bool(False)
        assert ser.getvalue() == b'\x01\x00'


# -- Alignment tests --

class TestAlignment:
    def test_u8_then_u32_le(self):
        """u8 at offset 0, then u32 needs 4-byte alignment → 3 padding bytes."""
        ser = CdrSerializer("<")
        ser.write_uint8(0xAA)
        ser.write_uint32(0x12345678)
        data = ser.getvalue()
        # byte 0: 0xAA, bytes 1-3: padding, bytes 4-7: u32 LE
        assert data == b'\xAA\x00\x00\x00\x78\x56\x34\x12'
        assert len(data) == 8

    def test_u8_then_u64_le(self):
        """u8 at offset 0, then u64 needs 8-byte alignment → 7 padding bytes."""
        ser = CdrSerializer("<")
        ser.write_uint8(0xBB)
        ser.write_uint64(0x0102030405060708)
        data = ser.getvalue()
        assert data[0] == 0xBB
        assert data[1:8] == b'\x00' * 7  # 7 padding bytes
        assert len(data) == 16

    def test_u8_then_u16(self):
        """u8 then u16 needs 2-byte alignment → 1 padding byte."""
        ser = CdrSerializer("<")
        ser.write_uint8(0xFF)
        ser.write_uint16(0x1234)
        data = ser.getvalue()
        assert data == b'\xFF\x00\x34\x12'

    def test_u32_then_u32_no_padding(self):
        """Two u32s back to back — no padding needed."""
        ser = CdrSerializer("<")
        ser.write_uint32(1)
        ser.write_uint32(2)
        data = ser.getvalue()
        assert len(data) == 8

    def test_alignment_roundtrip(self):
        """Write mixed types and read them back."""
        ser = CdrSerializer("<")
        ser.write_uint8(42)
        ser.write_uint32(1000)
        ser.write_uint8(7)
        ser.write_uint64(9999999999)

        de = CdrDeserializer(ser.getvalue(), "<")
        assert de.read_uint8() == 42
        assert de.read_uint32() == 1000
        assert de.read_uint8() == 7
        assert de.read_uint64() == 9999999999

    def test_set_origin(self):
        """set_origin resets alignment base."""
        ser = CdrSerializer("<")
        ser.write_uint8(0xAA)  # offset 0
        ser.write_uint8(0xBB)  # offset 1
        ser.set_origin()  # origin = 2
        # Now u32 alignment is relative to origin=2, so offset 2 is already
        # 4-byte aligned relative to origin (offset - origin = 0)
        ser.write_uint32(0x12345678)
        data = ser.getvalue()
        # 0xAA, 0xBB, then u32 immediately (no padding since 0 % 4 == 0)
        assert data == b'\xAA\xBB\x78\x56\x34\x12'

    def test_deserializer_set_origin(self):
        """Deserializer set_origin works symmetrically."""
        data = b'\xAA\xBB\x78\x56\x34\x12'
        de = CdrDeserializer(data, "<")
        assert de.read_uint8() == 0xAA
        assert de.read_uint8() == 0xBB
        de.set_origin()
        assert de.read_uint32() == 0x12345678


# -- String tests --

class TestStrings:
    def test_empty_string(self):
        ser = CdrSerializer("<")
        ser.write_string("")
        de = CdrDeserializer(ser.getvalue(), "<")
        assert de.read_string() == ""

    def test_ascii_string(self):
        ser = CdrSerializer("<")
        ser.write_string("Hello, DDS!")
        de = CdrDeserializer(ser.getvalue(), "<")
        assert de.read_string() == "Hello, DDS!"

    def test_utf8_multibyte(self):
        ser = CdrSerializer("<")
        ser.write_string("日本語テスト")
        de = CdrDeserializer(ser.getvalue(), "<")
        assert de.read_string() == "日本語テスト"

    def test_string_wire_format(self):
        """Verify exact bytes: u32 length (incl NUL) + chars + NUL."""
        ser = CdrSerializer("<")
        ser.write_string("Hi")
        data = ser.getvalue()
        # length = 3 (H, i, NUL)
        assert data[0:4] == struct.pack("<I", 3)
        assert data[4:7] == b'Hi\x00'

    def test_string_then_u32_alignment(self):
        """String followed by u32: u32 must be 4-byte aligned."""
        ser = CdrSerializer("<")
        ser.write_string("Hi")  # 4 (len) + 3 (Hi\0) = 7 bytes
        ser.write_uint32(42)  # needs alignment to offset 8
        data = ser.getvalue()
        # 7 bytes for string, 1 padding, 4 bytes for u32 = 12 total
        assert len(data) == 12
        de = CdrDeserializer(data, "<")
        assert de.read_string() == "Hi"
        assert de.read_uint32() == 42


# -- Sequence tests --

class TestSequences:
    def test_sequence_uint32(self):
        ser = CdrSerializer("<")
        ser.write_sequence(
            [10, 20, 30],
            lambda s, v: s.write_uint32(v),
        )
        de = CdrDeserializer(ser.getvalue(), "<")
        result = de.read_sequence(lambda d: d.read_uint32())
        assert result == [10, 20, 30]

    def test_empty_sequence(self):
        ser = CdrSerializer("<")
        ser.write_sequence([], lambda s, v: s.write_uint32(v))
        de = CdrDeserializer(ser.getvalue(), "<")
        result = de.read_sequence(lambda d: d.read_uint32())
        assert result == []


# -- ParameterList tests --

class TestParameterList:
    def test_build_and_parse(self):
        """Build 3 parameters + sentinel, parse back, verify."""
        builder = ParameterListBuilder("<")
        builder.add_parameter(0x0015, struct.pack("<BB", 2, 5))  # protocol version
        builder.add_parameter(0x0016, struct.pack("<BB", 0xFF, 0x01))  # vendor id
        builder.add_parameter(0x0050, b'\x01' * 16)  # GUID (16 bytes)
        data = builder.finalize()

        params = list(ParameterListParser(data, "<"))
        assert len(params) == 3

        pid0, val0 = params[0]
        assert pid0 == 0x0015
        # Value is padded to 4 bytes
        assert len(val0) == 4
        assert val0[0] == 2  # major
        assert val0[1] == 5  # minor

        pid1, val1 = params[1]
        assert pid1 == 0x0016
        assert val1[0] == 0xFF
        assert val1[1] == 0x01

        pid2, val2 = params[2]
        assert pid2 == 0x0050
        assert len(val2) == 16
        assert val2 == b'\x01' * 16

    def test_single_param(self):
        builder = ParameterListBuilder("<")
        builder.add_parameter(0x0077, b'\xDE\xAD')
        data = builder.finalize()

        params = list(ParameterListParser(data, "<"))
        assert len(params) == 1
        assert params[0][0] == 0x0077
        assert params[0][1][:2] == b'\xDE\xAD'

    def test_empty_param_list(self):
        """Just a sentinel, no parameters."""
        builder = ParameterListBuilder("<")
        data = builder.finalize()
        params = list(ParameterListParser(data, "<"))
        assert len(params) == 0

    def test_padding_to_4_bytes(self):
        """Value of 3 bytes is padded to 4."""
        builder = ParameterListBuilder("<")
        builder.add_parameter(0x0010, b'\x01\x02\x03')
        data = builder.finalize()

        # Header: 2 (pid) + 2 (len) + 4 (padded value) + 4 (sentinel) = 12
        assert len(data) == 12

    def test_big_endian_param_list(self):
        builder = ParameterListBuilder(">")
        builder.add_parameter(0x0015, struct.pack(">BB", 2, 5))
        data = builder.finalize()

        params = list(ParameterListParser(data, ">"))
        assert len(params) == 1
        assert params[0][0] == 0x0015


# -- Encapsulation header tests --

class TestEncapsulation:
    def test_cdr_le_header(self):
        hdr = encapsulation_header(CDR_LE)
        assert hdr == b'\x00\x01\x00\x00'

    def test_cdr_be_header(self):
        hdr = encapsulation_header(CDR_BE)
        assert hdr == b'\x00\x00\x00\x00'

    def test_pl_cdr_le_header(self):
        hdr = encapsulation_header(PL_CDR_LE)
        assert hdr == b'\x00\x03\x00\x00'

    def test_pl_cdr_be_header(self):
        hdr = encapsulation_header(PL_CDR_BE)
        assert hdr == b'\x00\x02\x00\x00'

    def test_parse_roundtrip(self):
        for scheme in [CDR_LE, CDR_BE, PL_CDR_LE, PL_CDR_BE]:
            hdr = encapsulation_header(scheme)
            parsed_scheme, remaining = parse_encapsulation_header(hdr + b'\xDE\xAD')
            assert parsed_scheme == scheme
            assert remaining == b'\xDE\xAD'

    def test_parse_too_short(self):
        with pytest.raises(ValueError):
            parse_encapsulation_header(b'\x00\x01')


# -- Error handling --

class TestErrors:
    def test_buffer_underflow(self):
        de = CdrDeserializer(b'\x01\x02', "<")
        de.read_uint8()
        de.read_uint8()
        with pytest.raises(ValueError, match="Buffer underflow"):
            de.read_uint8()

    def test_invalid_endian(self):
        with pytest.raises(ValueError):
            CdrSerializer("!")
        with pytest.raises(ValueError):
            CdrDeserializer(b'', "!")
