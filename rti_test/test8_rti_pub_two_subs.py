#!/usr/bin/env python3
"""Test 8: RTI publishes, Python VibeDDS and Rust VibeDDS both subscribe.

RTI Connext DDS publishes "Hello World from RTI" messages.
Python VibeDDS subscribes (inline via callback).
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

EXPECTED_PREFIX = "Hello World from RTI"
RUST_PROJECT_DIR = os.path.join(os.path.dirname(__file__), "..", "rust", "vibedds")


def main():
    print("=" * 60)
    print("TEST 8: RTI Publisher -> Two Subscribers (3 Libraries)")
    print("  Publisher:    RTI Connext DDS")
    print("  Subscriber 1: Python VibeDDS")
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

    # --- RTI Connext DDS publisher ---
    struct_type = dds.StructType("HelloWorld")
    struct_type.add_member(dds.Member("message", dds.StringType()))

    rti_participant = dds.DomainParticipant(domain_id=0)
    rti_topic = dds.DynamicData.Topic(rti_participant, "HelloWorld", struct_type)

    rti_pub = dds.Publisher(rti_participant)
    writer_qos = dds.DataWriterQos()
    writer_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
    rti_writer = dds.DynamicData.DataWriter(rti_pub, rti_topic, writer_qos)
    print("[SETUP] RTI Connext BEST_EFFORT writer created on topic 'HelloWorld'")

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

    # --- Python VibeDDS subscriber ---
    dp = DomainParticipant(domain_id=0, participant_id=7)
    dp.start()
    topic = dp.create_topic("HelloWorld", HelloWorldType.TYPE_NAME)
    qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
    reader = dp.create_reader(topic, qos)

    python_received = []

    def on_data(payload: bytes):
        try:
            message = HelloWorldType.deserialize(payload)
            python_received.append(message)
            print(f"  [Python RX] {message}")
        except Exception as e:
            print(f"  [Python RX] Deserialize error: {e}")

    reader.on_data(on_data)
    print("[SETUP] Python VibeDDS BEST_EFFORT reader created on topic 'HelloWorld'")
    print()

    dp.announce_spdp()

    # --- Run for up to 30 seconds ---
    publish_count = 0
    start = time.time()
    last_publish = 0

    try:
        while time.time() - start < 30:
            dp.spin_once(timeout=0.05)

            # Publish from RTI every 2 seconds
            elapsed = time.time() - start
            if int(elapsed) % 2 == 0 and int(elapsed) != last_publish and int(elapsed) > 0:
                last_publish = int(elapsed)
                publish_count += 1
                sample = dds.DynamicData(struct_type)
                msg = f"{EXPECTED_PREFIX} #{publish_count}"
                sample["message"] = msg
                rti_writer.write(sample)
                print(f"  [RTI    TX] {msg}")

            # Check if Rust process died
            if rust_proc.poll() is not None:
                print(f"[WARN] Rust process exited with code {rust_proc.returncode}")
                break

            # Stop early after enough publishes
            if publish_count >= 8:
                wait_start = time.time()
                while time.time() - wait_start < 5:
                    dp.spin_once(timeout=0.05)
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
            if " (from " in msg:
                msg = msg[:msg.index(" (from ")].strip()
            rust_received.append(msg)

    # --- Cleanup ---
    dp.stop()
    del rti_writer
    del rti_participant

    # --- Results ---
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"  RTI Connext published:    {publish_count} messages")
    print()

    # Python results
    py_correct = [m for m in python_received if m.startswith(EXPECTED_PREFIX)]
    py_wrong = [m for m in python_received if not m.startswith(EXPECTED_PREFIX)]
    print(f"  Python VibeDDS received:  {len(python_received)} messages")
    print(f"    Correct ('{EXPECTED_PREFIX}...'): {len(py_correct)}")
    print(f"    Wrong/loopback:         {len(py_wrong)}")
    if py_correct:
        print(f"    First: {py_correct[0]!r}")
        print(f"    Last:  {py_correct[-1]!r}")
    if py_wrong:
        for m in py_wrong:
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
    py_ok = len(py_correct) > 0 and len(py_wrong) == 0
    rust_ok = len(rust_correct) > 0 and len(rust_wrong) == 0

    if py_ok and rust_ok:
        print("PASS - Both Python and Rust received RTI messages, no loopback")
    else:
        if not py_ok:
            if len(py_correct) == 0:
                print("FAIL - Python VibeDDS received no messages from RTI")
            if len(py_wrong) > 0:
                print("FAIL - Python VibeDDS received unexpected/loopback messages")
        if not rust_ok:
            if len(rust_correct) == 0:
                print("FAIL - Rust VibeDDS received no messages from RTI")
            if len(rust_wrong) > 0:
                print("FAIL - Rust VibeDDS received unexpected/loopback messages")

    return 0 if (py_ok and rust_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
