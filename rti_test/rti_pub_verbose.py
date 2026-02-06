#!/usr/bin/env python3
"""RTI writer ONLY with superverbose logging for interop debugging.

Tests ONLY the RTI-writer → VibeDDS-reader direction.
No RTI reader to avoid self-matching loopback.
"""

import time
import rti.connextdds as dds

# Enable RTI superverbose logging for discovery debugging
try:
    dds.Logger.instance.verbosity = dds.Verbosity.STATUS_LOCAL
except Exception as e:
    print(f"Note: could not set verbosity: {e}")
    try:
        dds.Logger.instance.verbosity = dds.Verbosity.WARNING
    except:
        pass

struct_type = dds.StructType("HelloWorld")
struct_type.add_member(dds.Member("message", dds.StringType()))

participant = dds.DomainParticipant(domain_id=0)
topic = dds.DynamicData.Topic(participant, "HelloWorld", struct_type)
publisher = dds.Publisher(participant)

# Use default (best-effort) QoS since VibeDDS reader is best-effort
writer_qos = dds.QosProvider.default.datawriter_qos
writer = dds.DynamicData.DataWriter(publisher, topic, writer_qos)

print(f"RTI Writer-Only Publisher (verbose) started")
print(f"  Writer reliability: {writer.qos.reliability.kind}")
print(f"  NO reader created (avoids self-matching loopback)")
print()

count = 0
while count < 10:
    # Check matched subscriptions (should be 0 until VibeDDS matches)
    try:
        matched = writer.matched_subscriptions
        print(f"\n[{count+1}] Matched subscriptions: {len(matched)}")
        for sub in matched:
            try:
                data = writer.matched_subscription_data(sub)
                print(f"    Matched: topic={data.topic_name}, type={data.type_name}")
            except Exception as e:
                print(f"    Matched: handle={sub}, error: {e}")
    except Exception as e:
        print(f"Error: {e}")

    # Check incompatible QoS
    try:
        status = writer.offered_incompatible_qos_status
        if status.total_count > 0:
            print(f"    INCOMPATIBLE QOS: count={status.total_count}, last_policy={status.last_policy_id}")
    except Exception:
        pass

    count += 1
    sample = dds.DynamicData(struct_type)
    msg = f"Hello from RTI #{count}"
    sample["message"] = msg
    writer.write(sample)
    print(f"Published: {msg}")
    time.sleep(2)

print("\nDone.")
