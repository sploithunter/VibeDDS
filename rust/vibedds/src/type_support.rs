/// Type support helpers for common DDS data types.
///
/// These provide serialization/deserialization for HelloWorld and ShapeType,
/// commonly used in DDS interoperability testing.

use crate::cdr::{encapsulation_header, CdrDeserializer, CdrSerializer, Endian};
use crate::constants::CDR_LE;

/// HelloWorld type: a simple string message.
///
/// IDL equivalent:
/// ```idl
/// struct HelloWorld {
///     string message;
/// };
/// ```
pub struct HelloWorldType;

impl HelloWorldType {
    pub const TYPE_NAME: &'static str = "HelloWorld";

    /// Serialize a HelloWorld sample to CDR LE with encapsulation header.
    pub fn serialize(message: &str) -> Vec<u8> {
        let mut ser = CdrSerializer::new(Endian::Little);
        ser.write_string(message);

        let mut result = encapsulation_header(CDR_LE).to_vec();
        result.extend(ser.buffer());
        result
    }

    /// Deserialize a HelloWorld sample from CDR with encapsulation header.
    ///
    /// Returns the message string.
    pub fn deserialize(data: &[u8]) -> Result<String, std::io::Error> {
        if data.len() < 4 {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "Data too short for encapsulation header",
            ));
        }

        // Skip 4-byte encapsulation header
        let mut de = CdrDeserializer::new(&data[4..], Endian::Little);
        de.read_string()
    }
}

/// ShapeType: used by RTI Shapes Demo and rtiddsspy.
///
/// IDL equivalent:
/// ```idl
/// struct ShapeType {
///     string color;  // @key
///     long x;
///     long y;
///     long shapesize;
/// };
/// ```
pub struct ShapeType;

/// A ShapeType sample.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Shape {
    pub color: String,
    pub x: i32,
    pub y: i32,
    pub shapesize: i32,
}

impl ShapeType {
    pub const TYPE_NAME: &'static str = "ShapeType";

    /// Serialize a ShapeType sample to CDR LE with encapsulation header.
    pub fn serialize(color: &str, x: i32, y: i32, shapesize: i32) -> Vec<u8> {
        let mut ser = CdrSerializer::new(Endian::Little);
        ser.write_string(color);
        ser.write_i32(x);
        ser.write_i32(y);
        ser.write_i32(shapesize);

        let mut result = encapsulation_header(CDR_LE).to_vec();
        result.extend(ser.buffer());
        result
    }

    /// Serialize a Shape struct to CDR LE with encapsulation header.
    pub fn serialize_shape(shape: &Shape) -> Vec<u8> {
        Self::serialize(&shape.color, shape.x, shape.y, shape.shapesize)
    }

    /// Deserialize a ShapeType sample from CDR with encapsulation header.
    pub fn deserialize(data: &[u8]) -> Result<Shape, std::io::Error> {
        if data.len() < 4 {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "Data too short for encapsulation header",
            ));
        }

        // Skip 4-byte encapsulation header
        let mut de = CdrDeserializer::new(&data[4..], Endian::Little);
        Ok(Shape {
            color: de.read_string()?,
            x: de.read_i32()?,
            y: de.read_i32()?,
            shapesize: de.read_i32()?,
        })
    }
}

/// PingType: used by RTI ddsping.
///
/// IDL equivalent:
/// ```idl
/// struct PingType {
///     long count;
/// };
/// ```
pub struct PingType;

impl PingType {
    pub const TYPE_NAME: &'static str = "PingType";

    /// Serialize a PingType sample to CDR LE with encapsulation header.
    pub fn serialize(count: i32) -> Vec<u8> {
        let mut ser = CdrSerializer::new(Endian::Little);
        ser.write_i32(count);

        let mut result = encapsulation_header(CDR_LE).to_vec();
        result.extend(ser.buffer());
        result
    }

    /// Deserialize a PingType sample from CDR with encapsulation header.
    pub fn deserialize(data: &[u8]) -> Result<i32, std::io::Error> {
        if data.len() < 4 {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "Data too short for encapsulation header",
            ));
        }

        let mut de = CdrDeserializer::new(&data[4..], Endian::Little);
        de.read_i32()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hello_world_roundtrip() {
        let message = "Hello, DDS World!";
        let bytes = HelloWorldType::serialize(message);
        let decoded = HelloWorldType::deserialize(&bytes).unwrap();
        assert_eq!(decoded, message);
    }

    #[test]
    fn test_hello_world_empty_string() {
        let bytes = HelloWorldType::serialize("");
        let decoded = HelloWorldType::deserialize(&bytes).unwrap();
        assert_eq!(decoded, "");
    }

    #[test]
    fn test_hello_world_utf8() {
        let message = "Hello, 世界! 🌍";
        let bytes = HelloWorldType::serialize(message);
        let decoded = HelloWorldType::deserialize(&bytes).unwrap();
        assert_eq!(decoded, message);
    }

    #[test]
    fn test_hello_world_known_bytes() {
        // Known CDR encoding for "Hi"
        // Encapsulation: 00 01 00 00 (CDR_LE)
        // String length: 03 00 00 00 (3, including NUL)
        // String: "Hi\0"
        let bytes = HelloWorldType::serialize("Hi");

        // Check encapsulation header
        assert_eq!(&bytes[0..4], &[0x00, 0x01, 0x00, 0x00]);

        // Check string length (u32 LE = 3)
        assert_eq!(&bytes[4..8], &[0x03, 0x00, 0x00, 0x00]);

        // Check string content
        assert_eq!(&bytes[8..11], b"Hi\x00");
    }

    #[test]
    fn test_shape_type_roundtrip() {
        let shape = Shape {
            color: "BLUE".to_string(),
            x: 100,
            y: 200,
            shapesize: 30,
        };

        let bytes = ShapeType::serialize_shape(&shape);
        let decoded = ShapeType::deserialize(&bytes).unwrap();

        assert_eq!(decoded, shape);
    }

    #[test]
    fn test_shape_type_known_bytes() {
        let bytes = ShapeType::serialize("RED", 50, 75, 25);

        // Check encapsulation header
        assert_eq!(&bytes[0..4], &[0x00, 0x01, 0x00, 0x00]);

        // Verify we can round-trip
        let decoded = ShapeType::deserialize(&bytes).unwrap();
        assert_eq!(decoded.color, "RED");
        assert_eq!(decoded.x, 50);
        assert_eq!(decoded.y, 75);
        assert_eq!(decoded.shapesize, 25);
    }

    #[test]
    fn test_ping_type_roundtrip() {
        for count in [0, 1, 100, 1000000, -1, i32::MAX, i32::MIN] {
            let bytes = PingType::serialize(count);
            let decoded = PingType::deserialize(&bytes).unwrap();
            assert_eq!(decoded, count);
        }
    }

    #[test]
    fn test_ping_type_known_bytes() {
        // Ping with count=42
        let bytes = PingType::serialize(42);

        // Check encapsulation header
        assert_eq!(&bytes[0..4], &[0x00, 0x01, 0x00, 0x00]);

        // Check count (i32 LE = 42 = 0x2A)
        assert_eq!(&bytes[4..8], &[0x2A, 0x00, 0x00, 0x00]);
    }
}
