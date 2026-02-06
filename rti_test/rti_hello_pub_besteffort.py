#!/usr/bin/env python3
"""RTI publisher with best-effort QoS for interop testing."""

import time
import rti.connextdds as dds

struct_type = dds.StructType("HelloWorld")
struct_type.add_member(dds.Member("message", dds.StringType()))

participant = dds.DomainParticipant(domain_id=0)

topic = dds.DynamicData.Topic(participant, "HelloWorld", struct_type)
publisher = dds.Publisher(participant)

# Use best-effort QoS to match VibeDDS best-effort reader
writer_qos = dds.QosProvider.default.datawriter_qos
writer_qos << dds.Reliability.best_effort()
writer = dds.DynamicData.DataWriter(publisher, topic, writer_qos)

print("RTI HelloWorld Publisher (best-effort) started")
print()

count = 0
while count < 30:
    # Check matched subscriptions
    try:
        matched = writer.matched_subscriptions
        print(f"Matched subscriptions: {len(matched)}")
        for sub in matched:
            try:
                data = writer.matched_subscription_data(sub)
                print(f"  - handle={sub}")
            except Exception as e:
                print(f"  - handle={sub}, error: {e}")
    except Exception as e:
        print(f"Error getting matches: {e}")

    count += 1
    sample = dds.DynamicData(struct_type)
    msg = f"Hello from RTI #{count}"
    sample["message"] = msg
    writer.write(sample)
    print(f"Published: {msg}")
    time.sleep(2)
