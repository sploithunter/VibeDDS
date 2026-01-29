/// RTPS core types: GuidPrefix, EntityId, Guid, SequenceNumber, Locator, Timestamp, etc.

use std::fmt;
use std::io;

use crate::cdr::{CdrDeserializer, CdrSerializer};
use crate::constants::LOCATOR_KIND_UDPV4;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct ProtocolVersion {
    pub major: u8,
    pub minor: u8,
}

impl ProtocolVersion {
    pub fn new(major: u8, minor: u8) -> Self {
        Self { major, minor }
    }

    pub fn serialize(&self, ser: &mut CdrSerializer) {
        ser.write_u8(self.major);
        ser.write_u8(self.minor);
    }

    pub fn deserialize(de: &mut CdrDeserializer) -> io::Result<Self> {
        Ok(Self {
            major: de.read_u8()?,
            minor: de.read_u8()?,
        })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct VendorId(pub [u8; 2]);

impl VendorId {
    pub fn serialize(&self, ser: &mut CdrSerializer) {
        ser.write_bytes_raw(&self.0);
    }

    pub fn deserialize(de: &mut CdrDeserializer) -> io::Result<Self> {
        let b = de.read_bytes_raw(2)?;
        Ok(Self([b[0], b[1]]))
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Hash)]
pub struct GuidPrefix(pub [u8; 12]);

impl GuidPrefix {
    pub const UNKNOWN: Self = Self([0; 12]);

    pub fn serialize(&self, ser: &mut CdrSerializer) {
        ser.write_bytes_raw(&self.0);
    }

    pub fn deserialize(de: &mut CdrDeserializer) -> io::Result<Self> {
        let b = de.read_bytes_raw(12)?;
        let mut arr = [0u8; 12];
        arr.copy_from_slice(&b);
        Ok(Self(arr))
    }
}

impl fmt::Debug for GuidPrefix {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "GuidPrefix(")?;
        for b in &self.0 {
            write!(f, "{:02x}", b)?;
        }
        write!(f, ")")
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Hash)]
pub struct EntityId(pub [u8; 4]);

impl EntityId {
    pub const UNKNOWN: Self = Self([0; 4]);

    pub fn entity_key(&self) -> &[u8] {
        &self.0[..3]
    }

    pub fn entity_kind(&self) -> u8 {
        self.0[3]
    }

    pub fn serialize(&self, ser: &mut CdrSerializer) {
        ser.write_bytes_raw(&self.0);
    }

    pub fn deserialize(de: &mut CdrDeserializer) -> io::Result<Self> {
        let b = de.read_bytes_raw(4)?;
        let mut arr = [0u8; 4];
        arr.copy_from_slice(&b);
        Ok(Self(arr))
    }
}

impl fmt::Debug for EntityId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "EntityId(")?;
        for b in &self.0 {
            write!(f, "{:02x}", b)?;
        }
        write!(f, ")")
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Guid {
    pub prefix: GuidPrefix,
    pub entity_id: EntityId,
}

impl Guid {
    pub fn new(prefix: GuidPrefix, entity_id: EntityId) -> Self {
        Self { prefix, entity_id }
    }

    pub fn to_bytes(&self) -> [u8; 16] {
        let mut buf = [0u8; 16];
        buf[..12].copy_from_slice(&self.prefix.0);
        buf[12..16].copy_from_slice(&self.entity_id.0);
        buf
    }

    pub fn from_bytes(data: &[u8]) -> Self {
        let mut prefix = [0u8; 12];
        prefix.copy_from_slice(&data[..12]);
        let mut entity_id = [0u8; 4];
        entity_id.copy_from_slice(&data[12..16]);
        Self {
            prefix: GuidPrefix(prefix),
            entity_id: EntityId(entity_id),
        }
    }

    pub fn serialize(&self, ser: &mut CdrSerializer) {
        self.prefix.serialize(ser);
        self.entity_id.serialize(ser);
    }

    pub fn deserialize(de: &mut CdrDeserializer) -> io::Result<Self> {
        Ok(Self {
            prefix: GuidPrefix::deserialize(de)?,
            entity_id: EntityId::deserialize(de)?,
        })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct SequenceNumber {
    pub high: i32,
    pub low: u32,
}

impl SequenceNumber {
    pub const ZERO: Self = Self { high: 0, low: 0 };

    pub fn from_value(value: i64) -> Self {
        Self {
            high: (value >> 32) as i32,
            low: value as u32,
        }
    }

    pub fn value(&self) -> i64 {
        ((self.high as i64) << 32) | (self.low as i64)
    }

    pub fn increment(&self) -> Self {
        Self::from_value(self.value() + 1)
    }

    pub fn serialize(&self, ser: &mut CdrSerializer) {
        ser.write_i32(self.high);
        ser.write_u32(self.low);
    }

    pub fn deserialize(de: &mut CdrDeserializer) -> io::Result<Self> {
        Ok(Self {
            high: de.read_i32()?,
            low: de.read_u32()?,
        })
    }
}

impl PartialOrd for SequenceNumber {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.value().cmp(&other.value()))
    }
}

impl Ord for SequenceNumber {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        self.value().cmp(&other.value())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SequenceNumberSet {
    pub base: SequenceNumber,
    pub num_bits: u32,
    pub bitmap: Vec<u32>,
}

impl SequenceNumberSet {
    /// Create a new empty SequenceNumberSet with the given base.
    pub fn new(base: SequenceNumber) -> Self {
        Self {
            base,
            num_bits: 0,
            bitmap: Vec::new(),
        }
    }

    pub fn serialize(&self, ser: &mut CdrSerializer) {
        self.base.serialize(ser);
        ser.write_u32(self.num_bits);
        for &word in &self.bitmap {
            ser.write_u32(word);
        }
    }

    pub fn deserialize(de: &mut CdrDeserializer) -> io::Result<Self> {
        let base = SequenceNumber::deserialize(de)?;
        let num_bits = de.read_u32()?;
        let num_words = ((num_bits + 31) / 32) as usize;
        let mut bitmap = Vec::with_capacity(num_words);
        for _ in 0..num_words {
            bitmap.push(de.read_u32()?);
        }
        Ok(Self {
            base,
            num_bits,
            bitmap,
        })
    }

    pub fn missing_sequence_numbers(&self) -> Vec<SequenceNumber> {
        let mut result = Vec::new();
        for i in 0..self.num_bits {
            let word_idx = (i / 32) as usize;
            let bit_idx = 31 - (i % 32);
            if word_idx < self.bitmap.len() && (self.bitmap[word_idx] & (1 << bit_idx)) != 0 {
                result.push(SequenceNumber::from_value(self.base.value() + i as i64));
            }
        }
        result
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Locator {
    pub kind: i32,
    pub port: u32,
    pub address: [u8; 16],
}

impl Locator {
    pub const INVALID: Self = Self {
        kind: -1,
        port: 0,
        address: [0; 16],
    };

    pub fn from_ipv4(ip: &str, port: u32) -> Self {
        let mut address = [0u8; 16];
        let parts: Vec<u8> = ip.split('.').map(|p| p.parse().unwrap_or(0)).collect();
        if parts.len() == 4 {
            address[12] = parts[0];
            address[13] = parts[1];
            address[14] = parts[2];
            address[15] = parts[3];
        }
        Self {
            kind: LOCATOR_KIND_UDPV4,
            port,
            address,
        }
    }

    pub fn ipv4_str(&self) -> Option<String> {
        if self.kind != LOCATOR_KIND_UDPV4 {
            return None;
        }
        Some(format!(
            "{}.{}.{}.{}",
            self.address[12], self.address[13], self.address[14], self.address[15]
        ))
    }

    pub fn to_bytes(&self) -> [u8; 24] {
        let mut buf = [0u8; 24];
        buf[0..4].copy_from_slice(&self.kind.to_le_bytes());
        buf[4..8].copy_from_slice(&self.port.to_le_bytes());
        buf[8..24].copy_from_slice(&self.address);
        buf
    }

    pub fn from_bytes(data: &[u8]) -> Self {
        let kind = i32::from_le_bytes([data[0], data[1], data[2], data[3]]);
        let port = u32::from_le_bytes([data[4], data[5], data[6], data[7]]);
        let mut address = [0u8; 16];
        address.copy_from_slice(&data[8..24]);
        Self {
            kind,
            port,
            address,
        }
    }

    pub fn serialize(&self, ser: &mut CdrSerializer) {
        ser.write_i32(self.kind);
        ser.write_u32(self.port);
        ser.write_bytes_raw(&self.address);
    }

    pub fn deserialize(de: &mut CdrDeserializer) -> io::Result<Self> {
        Ok(Self {
            kind: de.read_i32()?,
            port: de.read_u32()?,
            address: {
                let b = de.read_bytes_raw(16)?;
                let mut arr = [0u8; 16];
                arr.copy_from_slice(&b);
                arr
            },
        })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Timestamp {
    pub seconds: i32,
    pub fraction: u32,
}

impl Timestamp {
    pub const ZERO: Self = Self {
        seconds: 0,
        fraction: 0,
    };
    pub const INVALID: Self = Self {
        seconds: -1,
        fraction: 0xFFFFFFFF,
    };

    pub fn from_seconds(secs: f64) -> Self {
        let s = secs as i32;
        let f = ((secs - s as f64) * (1u64 << 32) as f64) as u32;
        Self {
            seconds: s,
            fraction: f,
        }
    }

    /// Get the current time as a Timestamp.
    pub fn now() -> Self {
        use std::time::{SystemTime, UNIX_EPOCH};
        let duration = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default();
        Self {
            seconds: duration.as_secs() as i32,
            fraction: ((duration.subsec_nanos() as u64 * (1u64 << 32)) / 1_000_000_000) as u32,
        }
    }

    pub fn to_bytes_le(&self) -> [u8; 8] {
        let mut buf = [0u8; 8];
        buf[0..4].copy_from_slice(&self.seconds.to_le_bytes());
        buf[4..8].copy_from_slice(&self.fraction.to_le_bytes());
        buf
    }

    pub fn from_bytes_le(data: &[u8]) -> Self {
        Self {
            seconds: i32::from_le_bytes([data[0], data[1], data[2], data[3]]),
            fraction: u32::from_le_bytes([data[4], data[5], data[6], data[7]]),
        }
    }

    pub fn serialize(&self, ser: &mut CdrSerializer) {
        ser.write_i32(self.seconds);
        ser.write_u32(self.fraction);
    }

    pub fn deserialize(de: &mut CdrDeserializer) -> io::Result<Self> {
        Ok(Self {
            seconds: de.read_i32()?,
            fraction: de.read_u32()?,
        })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Duration {
    pub seconds: i32,
    pub fraction: u32,
}

impl Duration {
    pub const ZERO: Self = Self {
        seconds: 0,
        fraction: 0,
    };
    pub const INFINITE: Self = Self {
        seconds: 0x7FFFFFFF,
        fraction: 0xFFFFFFFF,
    };

    pub fn to_bytes_le(&self) -> [u8; 8] {
        let mut buf = [0u8; 8];
        buf[0..4].copy_from_slice(&self.seconds.to_le_bytes());
        buf[4..8].copy_from_slice(&self.fraction.to_le_bytes());
        buf
    }

    pub fn serialize(&self, ser: &mut CdrSerializer) {
        ser.write_i32(self.seconds);
        ser.write_u32(self.fraction);
    }

    pub fn deserialize(de: &mut CdrDeserializer) -> io::Result<Self> {
        Ok(Self {
            seconds: de.read_i32()?,
            fraction: de.read_u32()?,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cdr::{CdrSerializer, CdrDeserializer, Endian};

    #[test]
    fn test_guid_prefix_roundtrip() {
        let prefix = GuidPrefix([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);
        let mut ser = CdrSerializer::new(Endian::Little);
        prefix.serialize(&mut ser);
        let mut de = CdrDeserializer::new(ser.buffer(), Endian::Little);
        assert_eq!(GuidPrefix::deserialize(&mut de).unwrap(), prefix);
    }

    #[test]
    fn test_entity_id_roundtrip() {
        let eid = EntityId([0x00, 0x01, 0x00, 0xC2]);
        let mut ser = CdrSerializer::new(Endian::Little);
        eid.serialize(&mut ser);
        let mut de = CdrDeserializer::new(ser.buffer(), Endian::Little);
        assert_eq!(EntityId::deserialize(&mut de).unwrap(), eid);
    }

    #[test]
    fn test_guid_roundtrip() {
        let guid = Guid::new(
            GuidPrefix([0xAA; 12]),
            EntityId([0xBB, 0xCC, 0xDD, 0xEE]),
        );
        let bytes = guid.to_bytes();
        assert_eq!(bytes.len(), 16);
        assert_eq!(Guid::from_bytes(&bytes), guid);
    }

    #[test]
    fn test_sequence_number() {
        let sn = SequenceNumber::from_value(1);
        assert_eq!(sn.high, 0);
        assert_eq!(sn.low, 1);
        assert_eq!(sn.value(), 1);
        assert_eq!(sn.increment().value(), 2);
    }

    #[test]
    fn test_sequence_number_large() {
        let sn = SequenceNumber::from_value(0x100000001);
        assert_eq!(sn.high, 1);
        assert_eq!(sn.low, 1);
    }

    #[test]
    fn test_sequence_number_ordering() {
        let sn1 = SequenceNumber::from_value(1);
        let sn2 = SequenceNumber::from_value(2);
        assert!(sn1 < sn2);
        assert!(sn2 > sn1);
    }

    #[test]
    fn test_locator_ipv4() {
        let loc = Locator::from_ipv4("192.168.1.100", 7400);
        assert_eq!(loc.kind, LOCATOR_KIND_UDPV4);
        assert_eq!(loc.port, 7400);
        assert_eq!(loc.ipv4_str().unwrap(), "192.168.1.100");
    }

    #[test]
    fn test_locator_roundtrip() {
        let loc = Locator::from_ipv4("10.0.0.1", 7411);
        let bytes = loc.to_bytes();
        assert_eq!(Locator::from_bytes(&bytes), loc);
    }

    #[test]
    fn test_timestamp() {
        let ts = Timestamp::from_seconds(1.5);
        assert_eq!(ts.seconds, 1);
        assert!(ts.fraction > 0);
    }

    #[test]
    fn test_duration_infinite() {
        assert_eq!(Duration::INFINITE.seconds, 0x7FFFFFFF);
        assert_eq!(Duration::INFINITE.fraction, 0xFFFFFFFF);
    }

    #[test]
    fn test_sequence_number_set_missing() {
        let snset = SequenceNumberSet {
            base: SequenceNumber::from_value(1),
            num_bits: 32,
            bitmap: vec![0b11000000_00000000_00000000_00000000],
        };
        let missing = snset.missing_sequence_numbers();
        assert_eq!(missing.len(), 2);
        assert_eq!(missing[0].value(), 1);
        assert_eq!(missing[1].value(), 2);
    }
}
