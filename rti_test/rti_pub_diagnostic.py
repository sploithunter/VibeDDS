#!/usr/bin/env python3
"""RTI publisher with comprehensive diagnostic logging for interop debugging."""

import time
import rti.connextdds as dds

# Enable RTI logging for discovery debugging
try:
    dds.Logger.instance.verbosity = dds.Verbosity.WARNING
except Exception:
    pass

struct_type = dds.StructType("HelloWorld")
struct_type.add_member(dds.Member("message", dds.StringType()))

participant = dds.DomainParticipant(domain_id=0)
topic = dds.DynamicData.Topic(participant, "HelloWorld", struct_type)
publisher = dds.Publisher(participant)

# Use best-effort to match VibeDDS best-effort reader
writer_qos = dds.QosProvider.default.datawriter_qos
writer = dds.DynamicData.DataWriter(publisher, topic, writer_qos)

print(f"RTI HelloWorld Publisher (diagnostic) started")
print(f"  Writer QoS reliability: {writer.qos.reliability.kind}")
print()

# Also create a subscriber to see if we can discover VibeDDS's writer
subscriber = dds.Subscriber(participant)
reader_qos = dds.QosProvider.default.datareader_qos
reader = dds.DynamicData.DataReader(subscriber, topic, reader_qos)
print(f"  Reader QoS reliability: {reader.qos.reliability.kind}")

count = 0
while count < 15:
    # Check writer matched subscriptions
    try:
        w_matched = writer.matched_subscriptions
        print(f"\n--- Iteration {count+1} ---")
        print(f"Writer matched subscriptions: {len(w_matched)}")
        for sub in w_matched:
            try:
                data = writer.matched_subscription_data(sub)
                print(f"  Matched sub: topic={data.topic_name}, type={data.type_name}")
            except Exception as e:
                print(f"  Matched sub: handle={sub}, error: {e}")
    except Exception as e:
        print(f"Error getting writer matches: {e}")

    # Check reader matched publications
    try:
        r_matched = reader.matched_publications
        print(f"Reader matched publications: {len(r_matched)}")
        for pub in r_matched:
            try:
                data = reader.matched_publication_data(pub)
                print(f"  Matched pub: topic={data.topic_name}, type={data.type_name}")
            except Exception as e:
                print(f"  Matched pub: handle={pub}, error: {e}")
    except Exception as e:
        print(f"Error getting reader matches: {e}")

    # Check incompatible QoS
    try:
        offered_incomp = writer.offered_incompatible_qos_status
        if offered_incomp.total_count > 0:
            print(f"  WRITER INCOMPATIBLE QOS: total_count={offered_incomp.total_count}, "
                  f"last_policy_id={offered_incomp.last_policy_id}")
    except Exception as e:
        pass

    try:
        requested_incomp = reader.requested_incompatible_qos_status
        if requested_incomp.total_count > 0:
            print(f"  READER INCOMPATIBLE QOS: total_count={requested_incomp.total_count}, "
                  f"last_policy_id={requested_incomp.last_policy_id}")
    except Exception as e:
        pass

    # Publish distinct message
    count += 1
    sample = dds.DynamicData(struct_type)
    msg = f"Hello from RTI #{count}"
    sample["message"] = msg
    writer.write(sample)
    print(f"Published: {msg}")

    # Read any data
    try:
        samples = reader.take()
        for s in samples:
            if s.info.valid:
                print(f"RECEIVED: {s.data['message']}")
    except Exception:
        pass

    time.sleep(2)

print("\nDone.")
