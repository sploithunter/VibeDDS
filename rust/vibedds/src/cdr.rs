/// CDR (Common Data Representation) serialization and deserialization.
///
/// Implements XCDR1 encoding with alignment rules.
/// Also provides ParameterList builder/parser.

use std::io;

use crate::constants::{PID_PAD, PID_SENTINEL};

/// Byte order for CDR encoding.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Endian {
    Little,
    Big,
}

/// CDR Serializer — writes values to an internal buffer with alignment.
pub struct CdrSerializer {
    buf: Vec<u8>,
    endian: Endian,
    origin: usize,
}

impl CdrSerializer {
    pub fn new(endian: Endian) -> Self {
        Self {
            buf: Vec::new(),
            endian,
            origin: 0,
        }
    }

    pub fn buffer(&self) -> &[u8] {
        &self.buf
    }

    pub fn into_bytes(self) -> Vec<u8> {
        self.buf
    }

    pub fn set_origin(&mut self) {
        self.origin = self.buf.len();
    }

    fn align(&mut self, n: usize) {
        let offset = self.buf.len() - self.origin;
        let remainder = offset % n;
        if remainder != 0 {
            let padding = n - remainder;
            self.buf.extend(std::iter::repeat(0u8).take(padding));
        }
    }

    pub fn write_bool(&mut self, value: bool) {
        self.buf.push(if value { 1 } else { 0 });
    }

    pub fn write_u8(&mut self, value: u8) {
        self.buf.push(value);
    }

    pub fn write_i8(&mut self, value: i8) {
        self.buf.push(value as u8);
    }

    pub fn write_u16(&mut self, value: u16) {
        self.align(2);
        match self.endian {
            Endian::Little => self.buf.extend_from_slice(&value.to_le_bytes()),
            Endian::Big => self.buf.extend_from_slice(&value.to_be_bytes()),
        }
    }

    pub fn write_i16(&mut self, value: i16) {
        self.align(2);
        match self.endian {
            Endian::Little => self.buf.extend_from_slice(&value.to_le_bytes()),
            Endian::Big => self.buf.extend_from_slice(&value.to_be_bytes()),
        }
    }

    pub fn write_u32(&mut self, value: u32) {
        self.align(4);
        match self.endian {
            Endian::Little => self.buf.extend_from_slice(&value.to_le_bytes()),
            Endian::Big => self.buf.extend_from_slice(&value.to_be_bytes()),
        }
    }

    pub fn write_i32(&mut self, value: i32) {
        self.align(4);
        match self.endian {
            Endian::Little => self.buf.extend_from_slice(&value.to_le_bytes()),
            Endian::Big => self.buf.extend_from_slice(&value.to_be_bytes()),
        }
    }

    pub fn write_u64(&mut self, value: u64) {
        self.align(8);
        match self.endian {
            Endian::Little => self.buf.extend_from_slice(&value.to_le_bytes()),
            Endian::Big => self.buf.extend_from_slice(&value.to_be_bytes()),
        }
    }

    pub fn write_i64(&mut self, value: i64) {
        self.align(8);
        match self.endian {
            Endian::Little => self.buf.extend_from_slice(&value.to_le_bytes()),
            Endian::Big => self.buf.extend_from_slice(&value.to_be_bytes()),
        }
    }

    pub fn write_f32(&mut self, value: f32) {
        self.align(4);
        match self.endian {
            Endian::Little => self.buf.extend_from_slice(&value.to_le_bytes()),
            Endian::Big => self.buf.extend_from_slice(&value.to_be_bytes()),
        }
    }

    pub fn write_f64(&mut self, value: f64) {
        self.align(8);
        match self.endian {
            Endian::Little => self.buf.extend_from_slice(&value.to_le_bytes()),
            Endian::Big => self.buf.extend_from_slice(&value.to_be_bytes()),
        }
    }

    /// Write a CDR string: u32 length (incl NUL) + UTF-8 bytes + NUL.
    pub fn write_string(&mut self, value: &str) {
        let encoded = value.as_bytes();
        let length = (encoded.len() + 1) as u32; // +1 for NUL
        self.write_u32(length);
        self.buf.extend_from_slice(encoded);
        self.buf.push(0); // NUL terminator
    }

    pub fn write_bytes_raw(&mut self, data: &[u8]) {
        self.buf.extend_from_slice(data);
    }
}

/// CDR Deserializer — reads values from a byte slice with alignment.
pub struct CdrDeserializer<'a> {
    data: &'a [u8],
    pos: usize,
    endian: Endian,
    origin: usize,
}

impl<'a> CdrDeserializer<'a> {
    pub fn new(data: &'a [u8], endian: Endian) -> Self {
        Self {
            data,
            pos: 0,
            endian,
            origin: 0,
        }
    }

    pub fn pos(&self) -> usize {
        self.pos
    }

    pub fn remaining(&self) -> usize {
        self.data.len().saturating_sub(self.pos)
    }

    pub fn set_origin(&mut self) {
        self.origin = self.pos;
    }

    fn align(&mut self, n: usize) {
        let offset = self.pos - self.origin;
        let remainder = offset % n;
        if remainder != 0 {
            self.pos += n - remainder;
        }
    }

    fn read_bytes(&mut self, n: usize) -> io::Result<&'a [u8]> {
        if self.pos + n > self.data.len() {
            return Err(io::Error::new(
                io::ErrorKind::UnexpectedEof,
                format!(
                    "Buffer underflow: need {} bytes at offset {}, {} remain",
                    n,
                    self.pos,
                    self.data.len() - self.pos
                ),
            ));
        }
        let result = &self.data[self.pos..self.pos + n];
        self.pos += n;
        Ok(result)
    }

    pub fn read_bool(&mut self) -> io::Result<bool> {
        let b = self.read_bytes(1)?;
        Ok(b[0] != 0)
    }

    pub fn read_u8(&mut self) -> io::Result<u8> {
        let b = self.read_bytes(1)?;
        Ok(b[0])
    }

    pub fn read_i8(&mut self) -> io::Result<i8> {
        let b = self.read_bytes(1)?;
        Ok(b[0] as i8)
    }

    pub fn read_u16(&mut self) -> io::Result<u16> {
        self.align(2);
        let b = self.read_bytes(2)?;
        Ok(match self.endian {
            Endian::Little => u16::from_le_bytes([b[0], b[1]]),
            Endian::Big => u16::from_be_bytes([b[0], b[1]]),
        })
    }

    pub fn read_i16(&mut self) -> io::Result<i16> {
        self.align(2);
        let b = self.read_bytes(2)?;
        Ok(match self.endian {
            Endian::Little => i16::from_le_bytes([b[0], b[1]]),
            Endian::Big => i16::from_be_bytes([b[0], b[1]]),
        })
    }

    pub fn read_u32(&mut self) -> io::Result<u32> {
        self.align(4);
        let b = self.read_bytes(4)?;
        Ok(match self.endian {
            Endian::Little => u32::from_le_bytes([b[0], b[1], b[2], b[3]]),
            Endian::Big => u32::from_be_bytes([b[0], b[1], b[2], b[3]]),
        })
    }

    pub fn read_i32(&mut self) -> io::Result<i32> {
        self.align(4);
        let b = self.read_bytes(4)?;
        Ok(match self.endian {
            Endian::Little => i32::from_le_bytes([b[0], b[1], b[2], b[3]]),
            Endian::Big => i32::from_be_bytes([b[0], b[1], b[2], b[3]]),
        })
    }

    pub fn read_u64(&mut self) -> io::Result<u64> {
        self.align(8);
        let b = self.read_bytes(8)?;
        Ok(match self.endian {
            Endian::Little => u64::from_le_bytes(b.try_into().unwrap()),
            Endian::Big => u64::from_be_bytes(b.try_into().unwrap()),
        })
    }

    pub fn read_i64(&mut self) -> io::Result<i64> {
        self.align(8);
        let b = self.read_bytes(8)?;
        Ok(match self.endian {
            Endian::Little => i64::from_le_bytes(b.try_into().unwrap()),
            Endian::Big => i64::from_be_bytes(b.try_into().unwrap()),
        })
    }

    pub fn read_f32(&mut self) -> io::Result<f32> {
        self.align(4);
        let b = self.read_bytes(4)?;
        Ok(match self.endian {
            Endian::Little => f32::from_le_bytes([b[0], b[1], b[2], b[3]]),
            Endian::Big => f32::from_be_bytes([b[0], b[1], b[2], b[3]]),
        })
    }

    pub fn read_f64(&mut self) -> io::Result<f64> {
        self.align(8);
        let b = self.read_bytes(8)?;
        Ok(match self.endian {
            Endian::Little => f64::from_le_bytes(b.try_into().unwrap()),
            Endian::Big => f64::from_be_bytes(b.try_into().unwrap()),
        })
    }

    pub fn read_string(&mut self) -> io::Result<String> {
        let length = self.read_u32()? as usize;
        if length == 0 {
            return Ok(String::new());
        }
        let raw = self.read_bytes(length)?;
        // Strip NUL terminator
        let s = if raw.last() == Some(&0) {
            &raw[..raw.len() - 1]
        } else {
            raw
        };
        String::from_utf8(s.to_vec())
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))
    }

    pub fn read_bytes_raw(&mut self, n: usize) -> io::Result<Vec<u8>> {
        let b = self.read_bytes(n)?;
        Ok(b.to_vec())
    }
}

/// Builds a CDR parameter list with PID_SENTINEL termination.
pub struct ParameterListBuilder {
    buf: Vec<u8>,
    endian: Endian,
}

impl ParameterListBuilder {
    pub fn new(endian: Endian) -> Self {
        Self {
            buf: Vec::new(),
            endian,
        }
    }

    pub fn add_parameter(&mut self, pid: u16, value: &[u8]) {
        let padded_len = (value.len() + 3) & !3;
        match self.endian {
            Endian::Little => {
                self.buf.extend_from_slice(&pid.to_le_bytes());
                self.buf.extend_from_slice(&(padded_len as u16).to_le_bytes());
            }
            Endian::Big => {
                self.buf.extend_from_slice(&pid.to_be_bytes());
                self.buf.extend_from_slice(&(padded_len as u16).to_be_bytes());
            }
        }
        self.buf.extend_from_slice(value);
        // Pad to 4-byte boundary
        let pad = padded_len - value.len();
        for _ in 0..pad {
            self.buf.push(0);
        }
    }

    pub fn finalize(mut self) -> Vec<u8> {
        match self.endian {
            Endian::Little => {
                self.buf.extend_from_slice(&PID_SENTINEL.to_le_bytes());
                self.buf.extend_from_slice(&0u16.to_le_bytes());
            }
            Endian::Big => {
                self.buf.extend_from_slice(&PID_SENTINEL.to_be_bytes());
                self.buf.extend_from_slice(&0u16.to_be_bytes());
            }
        }
        self.buf
    }
}

/// Parses a CDR parameter list, yielding (pid, value) pairs.
pub struct ParameterListParser<'a> {
    data: &'a [u8],
    pos: usize,
    endian: Endian,
}

impl<'a> ParameterListParser<'a> {
    pub fn new(data: &'a [u8], endian: Endian) -> Self {
        Self {
            data,
            pos: 0,
            endian,
        }
    }
}

impl<'a> Iterator for ParameterListParser<'a> {
    type Item = (u16, &'a [u8]);

    fn next(&mut self) -> Option<Self::Item> {
        if self.pos + 4 > self.data.len() {
            return None;
        }
        let pid = match self.endian {
            Endian::Little => u16::from_le_bytes([self.data[self.pos], self.data[self.pos + 1]]),
            Endian::Big => u16::from_be_bytes([self.data[self.pos], self.data[self.pos + 1]]),
        };
        let length = match self.endian {
            Endian::Little => {
                u16::from_le_bytes([self.data[self.pos + 2], self.data[self.pos + 3]]) as usize
            }
            Endian::Big => {
                u16::from_be_bytes([self.data[self.pos + 2], self.data[self.pos + 3]]) as usize
            }
        };
        self.pos += 4;

        if pid == PID_SENTINEL {
            return None;
        }
        if pid == PID_PAD {
            self.pos += length;
            return self.next();
        }
        if self.pos + length > self.data.len() {
            return None;
        }
        let value = &self.data[self.pos..self.pos + length];
        self.pos += length;
        Some((pid, value))
    }
}

/// Build a 4-byte CDR encapsulation header.
pub fn encapsulation_header(scheme: u16) -> [u8; 4] {
    let bytes = scheme.to_be_bytes();
    [bytes[0], bytes[1], 0, 0]
}

/// Parse a 4-byte encapsulation header. Returns (scheme, offset_of_data).
pub fn parse_encapsulation_header(data: &[u8]) -> io::Result<(u16, usize)> {
    if data.len() < 4 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "Encapsulation header requires at least 4 bytes",
        ));
    }
    let scheme = u16::from_be_bytes([data[0], data[1]]);
    Ok((scheme, 4))
}

#[cfg(test)]
mod tests {
    use super::*;

    // -- Primitive round-trips (LE) --

    #[test]
    fn test_bool_roundtrip() {
        let mut ser = CdrSerializer::new(Endian::Little);
        ser.write_bool(true);
        ser.write_bool(false);
        let mut de = CdrDeserializer::new(ser.buffer(), Endian::Little);
        assert!(de.read_bool().unwrap());
        assert!(!de.read_bool().unwrap());
    }

    #[test]
    fn test_u8_roundtrip() {
        for v in [0u8, 1, 127, 255] {
            let mut ser = CdrSerializer::new(Endian::Little);
            ser.write_u8(v);
            let mut de = CdrDeserializer::new(ser.buffer(), Endian::Little);
            assert_eq!(de.read_u8().unwrap(), v);
        }
    }

    #[test]
    fn test_u16_roundtrip() {
        for v in [0u16, 1, 256, 65535] {
            let mut ser = CdrSerializer::new(Endian::Little);
            ser.write_u16(v);
            let mut de = CdrDeserializer::new(ser.buffer(), Endian::Little);
            assert_eq!(de.read_u16().unwrap(), v);
        }
    }

    #[test]
    fn test_u32_roundtrip() {
        for v in [0u32, 1, 0x12345678, 0xFFFFFFFF] {
            let mut ser = CdrSerializer::new(Endian::Little);
            ser.write_u32(v);
            let mut de = CdrDeserializer::new(ser.buffer(), Endian::Little);
            assert_eq!(de.read_u32().unwrap(), v);
        }
    }

    #[test]
    fn test_i32_roundtrip() {
        for v in [i32::MIN, -1, 0, 1, i32::MAX] {
            let mut ser = CdrSerializer::new(Endian::Little);
            ser.write_i32(v);
            let mut de = CdrDeserializer::new(ser.buffer(), Endian::Little);
            assert_eq!(de.read_i32().unwrap(), v);
        }
    }

    #[test]
    fn test_u64_roundtrip() {
        for v in [0u64, 1, 0x123456789ABCDEF0, u64::MAX] {
            let mut ser = CdrSerializer::new(Endian::Little);
            ser.write_u64(v);
            let mut de = CdrDeserializer::new(ser.buffer(), Endian::Little);
            assert_eq!(de.read_u64().unwrap(), v);
        }
    }

    #[test]
    fn test_f32_roundtrip() {
        for v in [0.0f32, 1.0, -1.0, 3.14] {
            let mut ser = CdrSerializer::new(Endian::Little);
            ser.write_f32(v);
            let mut de = CdrDeserializer::new(ser.buffer(), Endian::Little);
            assert!((de.read_f32().unwrap() - v).abs() < 1e-6);
        }
    }

    #[test]
    fn test_f64_roundtrip() {
        for v in [0.0f64, 1.0, -1.0, std::f64::consts::PI] {
            let mut ser = CdrSerializer::new(Endian::Little);
            ser.write_f64(v);
            let mut de = CdrDeserializer::new(ser.buffer(), Endian::Little);
            assert_eq!(de.read_f64().unwrap(), v);
        }
    }

    // -- Big endian --

    #[test]
    fn test_u32_be() {
        let mut ser = CdrSerializer::new(Endian::Big);
        ser.write_u32(0x12345678);
        assert_eq!(ser.buffer(), &[0x12, 0x34, 0x56, 0x78]);
        let mut de = CdrDeserializer::new(ser.buffer(), Endian::Big);
        assert_eq!(de.read_u32().unwrap(), 0x12345678);
    }

    // -- Known bytes --

    #[test]
    fn test_u32_le_known_bytes() {
        let mut ser = CdrSerializer::new(Endian::Little);
        ser.write_u32(0x12345678);
        assert_eq!(ser.buffer(), &[0x78, 0x56, 0x34, 0x12]);
    }

    #[test]
    fn test_bool_known_bytes() {
        let mut ser = CdrSerializer::new(Endian::Little);
        ser.write_bool(true);
        ser.write_bool(false);
        assert_eq!(ser.buffer(), &[0x01, 0x00]);
    }

    // -- Alignment --

    #[test]
    fn test_u8_then_u32_alignment() {
        let mut ser = CdrSerializer::new(Endian::Little);
        ser.write_u8(0xAA);
        ser.write_u32(0x12345678);
        let buf = ser.buffer();
        assert_eq!(buf, &[0xAA, 0x00, 0x00, 0x00, 0x78, 0x56, 0x34, 0x12]);
    }

    #[test]
    fn test_u8_then_u64_alignment() {
        let mut ser = CdrSerializer::new(Endian::Little);
        ser.write_u8(0xBB);
        ser.write_u64(0x0102030405060708);
        let buf = ser.buffer();
        assert_eq!(buf[0], 0xBB);
        assert_eq!(&buf[1..8], &[0; 7]); // 7 padding bytes
        assert_eq!(buf.len(), 16);
    }

    #[test]
    fn test_u8_then_u16_alignment() {
        let mut ser = CdrSerializer::new(Endian::Little);
        ser.write_u8(0xFF);
        ser.write_u16(0x1234);
        assert_eq!(ser.buffer(), &[0xFF, 0x00, 0x34, 0x12]);
    }

    #[test]
    fn test_set_origin() {
        let mut ser = CdrSerializer::new(Endian::Little);
        ser.write_u8(0xAA);
        ser.write_u8(0xBB);
        ser.set_origin();
        ser.write_u32(0x12345678);
        assert_eq!(ser.buffer(), &[0xAA, 0xBB, 0x78, 0x56, 0x34, 0x12]);
    }

    #[test]
    fn test_alignment_roundtrip() {
        let mut ser = CdrSerializer::new(Endian::Little);
        ser.write_u8(42);
        ser.write_u32(1000);
        ser.write_u8(7);
        ser.write_u64(9999999999);

        let mut de = CdrDeserializer::new(ser.buffer(), Endian::Little);
        assert_eq!(de.read_u8().unwrap(), 42);
        assert_eq!(de.read_u32().unwrap(), 1000);
        assert_eq!(de.read_u8().unwrap(), 7);
        assert_eq!(de.read_u64().unwrap(), 9999999999);
    }

    // -- String tests --

    #[test]
    fn test_empty_string() {
        let mut ser = CdrSerializer::new(Endian::Little);
        ser.write_string("");
        let mut de = CdrDeserializer::new(ser.buffer(), Endian::Little);
        assert_eq!(de.read_string().unwrap(), "");
    }

    #[test]
    fn test_ascii_string() {
        let mut ser = CdrSerializer::new(Endian::Little);
        ser.write_string("Hello, DDS!");
        let mut de = CdrDeserializer::new(ser.buffer(), Endian::Little);
        assert_eq!(de.read_string().unwrap(), "Hello, DDS!");
    }

    #[test]
    fn test_utf8_string() {
        let mut ser = CdrSerializer::new(Endian::Little);
        ser.write_string("日本語テスト");
        let mut de = CdrDeserializer::new(ser.buffer(), Endian::Little);
        assert_eq!(de.read_string().unwrap(), "日本語テスト");
    }

    #[test]
    fn test_string_wire_format() {
        let mut ser = CdrSerializer::new(Endian::Little);
        ser.write_string("Hi");
        let buf = ser.buffer();
        // length = 3 (H, i, NUL) as u32 LE
        assert_eq!(&buf[0..4], &3u32.to_le_bytes());
        assert_eq!(&buf[4..7], b"Hi\0");
    }

    // -- ParameterList tests --

    #[test]
    fn test_parameter_list_build_parse() {
        let mut builder = ParameterListBuilder::new(Endian::Little);
        builder.add_parameter(0x0015, &[2, 5]);
        builder.add_parameter(0x0016, &[0xFF, 0x01]);
        builder.add_parameter(0x0050, &[0x01; 16]);
        let data = builder.finalize();

        let parser = ParameterListParser::new(&data, Endian::Little);
        let params: Vec<(u16, &[u8])> = parser.collect();
        assert_eq!(params.len(), 3);
        assert_eq!(params[0].0, 0x0015);
        assert_eq!(params[0].1[0], 2);
        assert_eq!(params[0].1[1], 5);
        assert_eq!(params[1].0, 0x0016);
        assert_eq!(params[2].0, 0x0050);
        assert_eq!(params[2].1.len(), 16);
    }

    #[test]
    fn test_empty_parameter_list() {
        let builder = ParameterListBuilder::new(Endian::Little);
        let data = builder.finalize();
        let parser = ParameterListParser::new(&data, Endian::Little);
        let params: Vec<_> = parser.collect();
        assert_eq!(params.len(), 0);
    }

    // -- Encapsulation header --

    #[test]
    fn test_encapsulation_header_cdr_le() {
        let hdr = encapsulation_header(crate::constants::CDR_LE);
        assert_eq!(hdr, [0x00, 0x01, 0x00, 0x00]);
    }

    #[test]
    fn test_encapsulation_header_pl_cdr_le() {
        let hdr = encapsulation_header(crate::constants::PL_CDR_LE);
        assert_eq!(hdr, [0x00, 0x03, 0x00, 0x00]);
    }

    #[test]
    fn test_parse_encapsulation_header() {
        let hdr = encapsulation_header(crate::constants::CDR_LE);
        let (scheme, offset) = parse_encapsulation_header(&hdr).unwrap();
        assert_eq!(scheme, crate::constants::CDR_LE);
        assert_eq!(offset, 4);
    }

    // -- Error handling --

    #[test]
    fn test_buffer_underflow() {
        let data = [1u8, 2];
        let mut de = CdrDeserializer::new(&data, Endian::Little);
        de.read_u8().unwrap();
        de.read_u8().unwrap();
        assert!(de.read_u8().is_err());
    }
}
