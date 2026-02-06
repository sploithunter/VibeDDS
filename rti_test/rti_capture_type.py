#!/usr/bin/env python3
"""Check if RTI reader can match VibeDDS writer, and vice versa."""

import time
import rti.connextdds as dds

struct_type = dds.StructType("HelloWorld")
struct_type.add_member(dds.Member("message", dds.StringType()))

participant = dds.DomainParticipant(domain_id=0)

topic = dds.DynamicData.Topic(participant, "HelloWorld", struct_type)
publisher = dds.Publisher(participant)
subscriber = dds.Subscriber(participant)

# Create writer with reliable QoS
writer_qos = dds.QosProvider.default.datawriter_qos
writer_qos << dds.Reliability.reliable()
writer = dds.DynamicData.DataWriter(publisher, topic, writer_qos)

# Create reader with reliable QoS (matching VibeDDS hello_sub)
reader_qos = dds.QosProvider.default.datareader_qos
reader_qos << dds.Reliability.reliable()
reader = dds.DynamicData.DataReader(subscriber, topic, reader_qos)

print("RTI Type Matching Test")
print(f"Topic: {topic.name}, Type: {topic.type_name}")
print()

# Check matches every 2 seconds for 16 seconds
for i in range(8):
    w_matched = writer.matched_subscriptions
    r_matched = reader.matched_publications
    print(f"[{i*2}s] Writer matched subs: {len(w_matched)}, Reader matched pubs: {len(r_matched)}")

    for h in w_matched:
        try:
            info = writer.matched_subscription_data(h)
            print(f"  Writer matched sub: {info}")
        except:
            print(f"  Writer matched sub handle: {h}")

    for h in r_matched:
        try:
            info = reader.matched_publication_data(h)
            print(f"  Reader matched pub: {info}")
        except:
            print(f"  Reader matched pub handle: {h}")

    # Try reading data
    try:
        samples = reader.take()
        for s in samples:
            if s.info.valid:
                try:
                    print(f"  ** RECEIVED: {s.data['message']}")
                except:
                    print(f"  ** RECEIVED data (could not read message field)")
    except Exception as e:
        pass

    time.sleep(2)

print("\nDone.")
