#!/usr/bin/env python3
"""VibeDDS subscriber for RTI SimpleType interop testing.

Topic: "Example SimpleType"
Type: "SimpleType" (struct with message, x, y, count)
"""

import sys
import struct
sys.path.insert(0, "/Users/jason/Documents/VibeDDS/python")

import logging
from vibedds.participant import DomainParticipant
from vibedds.topic import Topic
from vibedds.qos import QosPolicy, ReliabilityKind, DurabilityKind

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def decode_simpletype(data: bytes) -> dict:
    """Decode CDR-encoded SimpleType: string<64> message, long x, long y, long count."""
    if len(data) < 4:
        return {"raw": data.hex()}

    offset = 0
    # CDR encapsulation header (4 bytes): kind(2) + options(2)
    # Usually 0x0001 0x0000 for little-endian
    encap = data[0:4]
    offset = 4

    result = {"encapsulation": encap.hex()}

    try:
        # String: 4-byte length (including null) + chars + null + padding
        if offset + 4 <= len(data):
            str_len = struct.unpack_from("<I", data, offset)[0]
            offset += 4
            if offset + str_len <= len(data):
                message = data[offset:offset + str_len - 1].decode("utf-8", errors="replace")
                offset += str_len
                # Align to 4 bytes
                offset = (offset + 3) & ~3
                result["message"] = message

        # long x
        if offset + 4 <= len(data):
            result["x"] = struct.unpack_from("<i", data, offset)[0]
            offset += 4

        # long y
        if offset + 4 <= len(data):
            result["y"] = struct.unpack_from("<i", data, offset)[0]
            offset += 4

        # long count
        if offset + 4 <= len(data):
            result["count"] = struct.unpack_from("<i", data, offset)[0]
            offset += 4

    except Exception as e:
        result["decode_error"] = str(e)
        result["raw"] = data.hex()

    return result

def on_data_received(data: bytes):
    """Callback when data is received."""
    decoded = decode_simpletype(data)
    logger.info("RECEIVED SimpleType: %s", decoded)
    print(f"Data received: {decoded}")

def main():
    logger.info("Starting VibeDDS SimpleType subscriber...")

    # Create participant on domain 0
    # Use participant_id=1 to avoid port conflicts with rtiddsspy/other participants
    dp = DomainParticipant(domain_id=0, participant_id=1)

    # Create topic matching RTI's "Example SimpleType" with type "SimpleType"
    topic = Topic(
        name="Example SimpleType",
        type_name="SimpleType",
        keyed=True,  # message field is marked as @key
    )

    # Create reader with BEST_EFFORT QoS for simpler data flow
    qos = QosPolicy(
        reliability=ReliabilityKind.BEST_EFFORT,
        durability=DurabilityKind.VOLATILE,
    )
    reader = dp.create_reader(topic, qos)
    reader.on_data_available = on_data_received

    logger.info("Subscribed to topic '%s' type '%s'", topic.name, topic.type_name)

    # Run the event loop
    try:
        dp.start()
        logger.info("Running for 30 seconds...")
        dp.spin(duration=30.0)
    except KeyboardInterrupt:
        logger.info("Stopping...")
    finally:
        dp.stop()
        logger.info("VibeDDS test completed")

if __name__ == "__main__":
    main()
