#!/usr/bin/env python3
"""Test 3: Rust VibeDDS publisher -> RTI subscriber.

Starts the Rust hello_pub example as a subprocess.
RTI subscribes and verifies it receives the correct content.
Confirms no loopback (RTI should NOT receive RTI's own messages).
"""

import sys
import os
import time
import subprocess
import signal

import rti.connextdds as dds

EXPECTED_PREFIX = "Hello DDS World"
RUST_PROJECT_DIR = os.path.join(os.path.dirname(__file__), "..", "rust", "vibedds")


def main():
    print("=" * 60)
    print("TEST 3: Rust VibeDDS Publisher -> RTI Subscriber")
    print("=" * 60)
    print()

    # --- Build Rust example first ---
    print("[SETUP] Building Rust hello_pub example...")
    build = subprocess.run(
        ["cargo", "build", "--example", "hello_pub"],
        cwd=RUST_PROJECT_DIR,
        capture_output=True,
        text=True,
    )
    if build.returncode != 0:
        print(f"[ERROR] Cargo build failed:\n{build.stderr}")
        return 1
    print("[SETUP] Build successful")

    # --- RTI subscriber ---
    struct_type = dds.StructType("HelloWorld")
    struct_type.add_member(dds.Member("message", dds.StringType()))

    rti_participant = dds.DomainParticipant(domain_id=0)
    rti_topic = dds.DynamicData.Topic(rti_participant, "HelloWorld", struct_type)

    rti_sub = dds.Subscriber(rti_participant)
    reader_qos = dds.DataReaderQos()
    reader_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
    rti_reader = dds.DynamicData.DataReader(rti_sub, rti_topic, reader_qos)
    print("[SETUP] RTI BEST_EFFORT reader created on topic 'HelloWorld'")

    # --- Start Rust publisher subprocess ---
    env = os.environ.copy()
    env["RUST_LOG"] = "info"
    rust_proc = subprocess.Popen(
        ["cargo", "run", "--example", "hello_pub"],
        cwd=RUST_PROJECT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    print(f"[SETUP] Rust hello_pub started (pid={rust_proc.pid})")
    print()

    # --- Run for up to 30 seconds ---
    rti_received = []
    start = time.time()

    try:
        while time.time() - start < 30:
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

            time.sleep(0.1)

            # Check if Rust process died
            if rust_proc.poll() is not None:
                print(f"[WARN] Rust process exited with code {rust_proc.returncode}")
                break

            # Stop early if we have enough samples
            if len(rti_received) >= 5:
                print("  [INFO] Got 5 samples, stopping early")
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

    # --- Results ---
    del rti_reader
    del rti_participant

    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"  RTI received: {len(rti_received)} messages")

    # Verify content
    correct = [m for m in rti_received if m.startswith(EXPECTED_PREFIX)]
    wrong = [m for m in rti_received if not m.startswith(EXPECTED_PREFIX)]

    print(f"  Correct messages ('{EXPECTED_PREFIX}...'): {len(correct)}")
    print(f"  Wrong/loopback messages: {len(wrong)}")

    if correct:
        print(f"  First: {correct[0]!r}")
        print(f"  Last:  {correct[-1]!r}")
    if wrong:
        for m in wrong:
            print(f"  UNEXPECTED: {m!r}")

    print()
    ok = len(correct) > 0 and len(wrong) == 0
    if ok:
        print("PASS - RTI received Rust VibeDDS messages, no loopback")
    else:
        if len(correct) == 0:
            print("FAIL - RTI received no messages from Rust VibeDDS")
        if len(wrong) > 0:
            print("FAIL - RTI received unexpected/loopback messages")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
