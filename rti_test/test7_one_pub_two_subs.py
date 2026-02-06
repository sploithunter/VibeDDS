#!/usr/bin/env python3
"""Test 7: One publisher, two subscribers from different libraries.

Python VibeDDS publishes "Hello World from Python VibeDDS" messages.
RTI Connext DDS subscribes (inline via RTI Python API).
Rust VibeDDS subscribes (subprocess, hello_sub example).
Verifies BOTH subscribers receive correct messages and no loopback.
"""

import sys
import os
import time
import subprocess
import signal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import rti.connextdds as dds
from vibedds.participant import DomainParticipant
from vibedds.qos import QosPolicy, ReliabilityKind
from vibedds.type_support import HelloWorldType

EXPECTED_PREFIX = "Hello World from Python VibeDDS"
RUST_PROJECT_DIR = os.path.join(os.path.dirname(__file__), "..", "rust", "vibedds")


def main():
    print("=" * 60)
    print("TEST 7: One Publisher -> Two Subscribers (3 Libraries)")
    print("  Publisher:    Python VibeDDS")
    print("  Subscriber 1: RTI Connext DDS")
    print("  Subscriber 2: Rust VibeDDS")
    print("=" * 60)
    print()

    # --- Build Rust example first ---
    print("[SETUP] Building Rust hello_sub example...")
    build = subprocess.run(
        ["cargo", "build", "--example", "hello_sub"],
        cwd=RUST_PROJECT_DIR,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": os.path.expanduser("~/.cargo/bin") + ":" + os.environ["PATH"]},
    )
    if build.returncode != 0:
        print(f"[ERROR] Cargo build failed:\n{build.stderr}")
        return 1
    print("[SETUP] Build successful")

    # --- RTI Connext DDS subscriber ---
    struct_type = dds.StructType("HelloWorld")
    struct_type.add_member(dds.Member("message", dds.StringType()))

    rti_participant = dds.DomainParticipant(domain_id=0)
    rti_topic = dds.DynamicData.Topic(rti_participant, "HelloWorld", struct_type)

    rti_sub = dds.Subscriber(rti_participant)
    reader_qos = dds.DataReaderQos()
    reader_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
    rti_reader = dds.DynamicData.DataReader(rti_sub, rti_topic, reader_qos)
    print("[SETUP] RTI Connext BEST_EFFORT reader created on topic 'HelloWorld'")

    # --- Rust VibeDDS subscriber (subprocess) ---
    rust_binary = os.path.join(RUST_PROJECT_DIR, "target", "debug", "examples", "hello_sub")
    env = os.environ.copy()
    env["RUST_LOG"] = "info"
    rust_proc = subprocess.Popen(
        [rust_binary],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    print(f"[SETUP] Rust hello_sub started (pid={rust_proc.pid})")

    # Give Rust a moment to start
    time.sleep(1)

    # --- Python VibeDDS publisher ---
    dp = DomainParticipant(domain_id=0, participant_id=7)
    dp.start()
    topic = dp.create_topic("HelloWorld", HelloWorldType.TYPE_NAME)
    qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
    writer = dp.create_writer(topic, qos)
    print("[SETUP] Python VibeDDS BEST_EFFORT writer created on topic 'HelloWorld'")
    print()

    dp.announce_spdp()

    # --- Run for up to 30 seconds, spinning continuously ---
    rti_received = []
    publish_count = 0
    start = time.time()
    last_publish = 0

    try:
        while time.time() - start < 30:
            dp.spin_once(timeout=0.05)

            # Publish from Python VibeDDS every 2 seconds
            elapsed = time.time() - start
            if int(elapsed) % 2 == 0 and int(elapsed) != last_publish and int(elapsed) > 0:
                last_publish = int(elapsed)
                publish_count += 1
                msg = f"{EXPECTED_PREFIX} #{publish_count}"
                payload = HelloWorldType.serialize(msg)
                writer.write(payload)
                print(f"  [Python TX] {msg}")

            # Read RTI samples
            try:
                samples = rti_reader.take()
                for s in samples:
                    if s.info.valid:
                        msg = s.data["message"]
                        rti_received.append(msg)
                        print(f"  [RTI    RX] {msg}")
            except Exception:
                pass

            # Check if Rust process died
            if rust_proc.poll() is not None:
                print(f"[WARN] Rust process exited with code {rust_proc.returncode}")
                break

            # Stop early after enough publishes
            if publish_count >= 8:
                # Keep spinning for a few more seconds to let messages arrive
                wait_start = time.time()
                while time.time() - wait_start < 5:
                    dp.spin_once(timeout=0.05)
                    try:
                        samples = rti_reader.take()
                        for s in samples:
                            if s.info.valid:
                                msg = s.data["message"]
                                rti_received.append(msg)
                                print(f"  [RTI    RX] {msg}")
                    except Exception:
                        pass
                break

    finally:
        # Kill Rust process
        try:
            rust_proc.send_signal(signal.SIGTERM)
            rust_proc.wait(timeout=5)
        except Exception:
            rust_proc.kill()
            rust_proc.wait()
        print(f"[CLEANUP] Rust process terminated")

    # --- Parse Rust stdout for received messages ---
    stdout_data = rust_proc.stdout.read().decode("utf-8", errors="replace")
    stderr_data = rust_proc.stderr.read().decode("utf-8", errors="replace")

    rust_received = []
    for line in stdout_data.splitlines():
        if "Received:" in line:
            idx = line.index("Received:") + len("Received: ")
            msg = line[idx:].strip()
            # Strip trailing metadata like "(from ..., sn=...)"
            if " (from " in msg:
                msg = msg[:msg.index(" (from ")].strip()
            rust_received.append(msg)

    # --- Cleanup ---
    dp.stop()
    del rti_reader
    del rti_participant

    # --- Results ---
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"  Python VibeDDS published: {publish_count} messages")
    print()

    # RTI results
    rti_correct = [m for m in rti_received if m.startswith(EXPECTED_PREFIX)]
    rti_wrong = [m for m in rti_received if not m.startswith(EXPECTED_PREFIX)]
    print(f"  RTI Connext received:     {len(rti_received)} messages")
    print(f"    Correct ('{EXPECTED_PREFIX}...'): {len(rti_correct)}")
    print(f"    Wrong/loopback:         {len(rti_wrong)}")
    if rti_correct:
        print(f"    First: {rti_correct[0]!r}")
        print(f"    Last:  {rti_correct[-1]!r}")
    if rti_wrong:
        for m in rti_wrong:
            print(f"    UNEXPECTED: {m!r}")

    print()

    # Rust results
    rust_correct = [m for m in rust_received if m.startswith(EXPECTED_PREFIX)]
    rust_wrong = [m for m in rust_received if not m.startswith(EXPECTED_PREFIX)]
    print(f"  Rust VibeDDS received:    {len(rust_received)} messages")
    print(f"    Correct ('{EXPECTED_PREFIX}...'): {len(rust_correct)}")
    print(f"    Wrong/loopback:         {len(rust_wrong)}")
    if rust_correct:
        print(f"    First: {rust_correct[0]!r}")
        print(f"    Last:  {rust_correct[-1]!r}")
    if rust_wrong:
        for m in rust_wrong:
            print(f"    UNEXPECTED: {m!r}")

    # Show Rust stderr if no messages received
    if len(rust_received) == 0 and stderr_data:
        print()
        print("  Rust stderr (last 20 lines):")
        for line in stderr_data.splitlines()[-20:]:
            print(f"    {line}")

    # --- Pass/Fail ---
    print()
    rti_ok = len(rti_correct) > 0 and len(rti_wrong) == 0
    rust_ok = len(rust_correct) > 0 and len(rust_wrong) == 0

    if rti_ok and rust_ok:
        print("PASS - Both RTI and Rust received Python VibeDDS messages, no loopback")
    else:
        if not rti_ok:
            if len(rti_correct) == 0:
                print("FAIL - RTI Connext received no messages from Python VibeDDS")
            if len(rti_wrong) > 0:
                print("FAIL - RTI Connext received unexpected/loopback messages")
        if not rust_ok:
            if len(rust_correct) == 0:
                print("FAIL - Rust VibeDDS received no messages from Python VibeDDS")
            if len(rust_wrong) > 0:
                print("FAIL - Rust VibeDDS received unexpected/loopback messages")

    return 0 if (rti_ok and rust_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
