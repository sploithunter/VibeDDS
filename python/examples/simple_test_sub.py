#!/usr/bin/env python3
"""Simple VibeDDS subscriber for discovery testing.

Uses participant_id=1 to avoid port conflicts with RTI (which uses id=0).
"""

import sys
sys.path.insert(0, "/Users/jason/Documents/VibeDDS/python")

import logging
import time
from vibedds.participant import DomainParticipant
from vibedds.topic import Topic
from vibedds.qos import QosPolicy, ReliabilityKind, DurabilityKind

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting VibeDDS test (participant_id=1, ports 7412/7413)")

    # Use participant_id=1 to avoid conflict with RTI (which uses 0)
    dp = DomainParticipant(domain_id=0, participant_id=1)

    # Reduce SPDP interval for faster discovery
    dp._spdp_announce_interval = 1.0

    topic = Topic(
        name="Example SimpleType",
        type_name="SimpleType",
        keyed=True,
    )

    qos = QosPolicy(
        reliability=ReliabilityKind.BEST_EFFORT,
        durability=DurabilityKind.VOLATILE,
    )
    reader = dp.create_reader(topic, qos)
    reader.on_data_available = lambda data: logger.info("Received data: %s", data[:50].hex())

    logger.info("Subscribed to topic '%s'", topic.name)

    try:
        dp.start()
        logger.info("Running for 20 seconds...")

        end_time = time.time() + 20
        while time.time() < end_time:
            dp.spin(duration=1.0)
            # Log discovered participants
            for prefix, p in dp._participant_db.participants.items():
                vendor = p.vendor_id.vendor if p.vendor_id else (0, 0)
                logger.info("Known participant: %s vendor=%02x%02x", prefix.hex(), vendor[0], vendor[1])
    except KeyboardInterrupt:
        logger.info("Interrupted")
    finally:
        dp.stop()
        logger.info("Done")

if __name__ == "__main__":
    main()
