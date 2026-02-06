#!/usr/bin/env python3
"""RTI publisher with type checking disabled."""

import time
import os
import rti.connextdds as dds

# Disable type checking by setting type_code/type_object limits to 0
os.environ.setdefault("NDDS_QOS_PROFILES",
    os.path.join(os.path.dirname(__file__), "USER_QOS_PROFILES_INTEROP.xml"))

struct_type = dds.StructType("HelloWorld")
struct_type.add_member(dds.Member("message", dds.StringType()))

# Try to create participant with relaxed type checking
qos_provider = dds.QosProvider(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "USER_QOS_PROFILES_INTEROP.xml")
)

participant = dds.DomainParticipant(domain_id=0)
topic = dds.DynamicData.Topic(participant, "HelloWorld", struct_type)
publisher = dds.Publisher(participant)

writer_qos = dds.QosProvider.default.datawriter_qos
writer_qos << dds.Reliability.reliable()
writer = dds.DynamicData.DataWriter(publisher, topic, writer_qos)

print("RTI HelloWorld Publisher (type-check disabled) started")
print()

count = 0
while count < 8:
    matched = writer.matched_subscriptions
    print(f"Matched subscriptions: {len(matched)}")

    count += 1
    sample = dds.DynamicData(struct_type)
    msg = f"Hello from RTI #{count}"
    sample["message"] = msg
    writer.write(sample)
    print(f"Published: {msg}")
    time.sleep(2)
