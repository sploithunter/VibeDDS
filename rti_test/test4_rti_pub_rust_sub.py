#!/usr/bin/env python3
"""Test 4: RTI publisher -> Rust VibeDDS subscriber.

RTI publishes "Hello World from RTI" messages.
Starts the Rust hello_sub example as a subprocess.
Verifies Rust receives the correct content by checking stdout.
Confirms no loopback (Rust should NOT receive Rust's own messages).
"""

import sys
import os
import time
import subprocess
import signal

import rti.connextdds as dds

EXPECTED_PREFIX = "Hello World from RTI"
RUST_PROJECT_DIR = os.path.join(os.path.dirname(__file__), "..", "rust", "vibedds")


def main():
    print("=" * 60)
    print("TEST 4: RTI Publisher -> Rust VibeDDS Subscriber")
    print("=" * 60)
    print()

    # --- Build Rust example first ---
    print("[SETUP] Building Rust hello_sub example...")
    build = subprocess.run(
        ["cargo", "build", "--example", "hello_sub"],
        cwd=RUST_PROJECT_DIR,
        capture_output=True,
        text=True,
    )
    if build.returncode != 0:
        print(f"[ERROR] Cargo build failed:\n{build.stderr}")
        return 1
    print("[SETUP] Build successful")

    # --- RTI publisher ---
    struct_type = dds.StructType("HelloWorld")
    struct_type.add_member(dds.Member("message", dds.StringType()))

    rti_participant = dds.DomainParticipant(domain_id=0)
    rti_topic = dds.DynamicData.Topic(rti_participant, "HelloWorld", struct_type)

    rti_pub = dds.Publisher(rti_participant)
    writer_qos = dds.DataWriterQos()
    writer_qos.reliability.kind = dds.ReliabilityKind.BEST_EFFORT
    rti_writer = dds.DynamicData.DataWriter(rti_pub, rti_topic, writer_qos)
    print("[SETUP] RTI BEST_EFFORT writer created on topic 'HelloWorld'")

    # --- Start Rust subscriber subprocess ---
    env = os.environ.copy()
    env["RUST_LOG"] = "info"
    rust_proc = subprocess.Popen(
        ["cargo", "run", "--example", "hello_sub"],
        cwd=RUST_PROJECT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    print(f"[SETUP] Rust hello_sub started (pid={rust_proc.pid})")
    print()

    # Give Rust subscriber time to start and discover
    time.sleep(3)

    # --- Run for up to 30 seconds ---
    publish_count = 0
    start = time.time()
    last_publish = 0

    try:
        while time.time() - start < 30:
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

            time.sleep(0.1)

            # Check if Rust process died
            if rust_proc.poll() is not None:
                print(f"[WARN] Rust process exited with code {rust_proc.returncode}")
                break

            # Stop early after enough publishes
            if publish_count >= 8:
                print("  [INFO] Published 8 messages, waiting 3s for delivery...")
                time.sleep(3)
                break

    finally:
        # Kill Rust process and capture output
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
        # hello_sub prints "Received: <message>" or "[buffer] Received: <message> (...)"
        if "Received:" in line:
            # Extract message after "Received: "
            idx = line.index("Received:") + len("Received: ")
            msg = line[idx:].strip()
            # Strip trailing metadata like "(from ..., sn=...)"
            if " (from " in msg:
                msg = msg[:msg.index(" (from ")].strip()
            rust_received.append(msg)

    # --- Cleanup RTI ---
    del rti_writer
    del rti_participant

    # --- Results ---
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"  RTI published: {publish_count} messages")
    print(f"  Rust received: {len(rust_received)} messages")

    if rust_received:
        for m in rust_received:
            print(f"    {m!r}")

    # Verify content
    correct = [m for m in rust_received if m.startswith(EXPECTED_PREFIX)]
    wrong = [m for m in rust_received if not m.startswith(EXPECTED_PREFIX)]

    print(f"  Correct messages ('{EXPECTED_PREFIX}...'): {len(correct)}")
    print(f"  Wrong/loopback messages: {len(wrong)}")

    if wrong:
        for m in wrong:
            print(f"  UNEXPECTED: {m!r}")

    # Show Rust stderr (logs) if no messages received
    if len(rust_received) == 0 and stderr_data:
        print()
        print("  Rust stderr (last 20 lines):")
        for line in stderr_data.splitlines()[-20:]:
            print(f"    {line}")

    print()
    ok = len(correct) > 0 and len(wrong) == 0
    if ok:
        print("PASS - Rust VibeDDS received RTI messages, no loopback")
    else:
        if len(correct) == 0:
            print("FAIL - Rust VibeDDS received no messages from RTI")
        if len(wrong) > 0:
            print("FAIL - Rust VibeDDS received unexpected/loopback messages")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
