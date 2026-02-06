#!/usr/bin/env python3
"""RTI Connext DDS publisher for HelloWorld topic.

Used to test RTI -> VibeDDS data exchange.
Publishes a simple string message on topic "HelloWorld" with type "HelloWorld".
"""

import time
import rti.connextdds as dds

# Create a DynamicType matching VibeDDS HelloWorld:
# struct HelloWorld { string message; };
struct_type = dds.StructType("HelloWorld")
struct_type.add_member(dds.Member("message", dds.StringType()))

# Create participant on domain 0
participant = dds.DomainParticipant(domain_id=0)

# Create topic
topic = dds.DynamicData.Topic(participant, "HelloWorld", struct_type)

# Create publisher and writer with BEST_EFFORT QoS (matches VibeDDS default)
publisher = dds.Publisher(participant)
writer_qos = dds.DataWriterQos()
writer_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
writer = dds.DynamicData.DataWriter(publisher, topic, writer_qos)

print("RTI HelloWorld Publisher started")
print("Publishing on topic='HelloWorld', type='HelloWorld'")
print("Press Ctrl+C to stop")
print()

count = 0
try:
    while True:
        count += 1
        sample = dds.DynamicData(struct_type)
        msg = f"Hello from RTI #{count}"
        sample["message"] = msg
        writer.write(sample)
        print(f"Published: {msg}")
        time.sleep(2)
except KeyboardInterrupt:
    print("\nStopping...")
