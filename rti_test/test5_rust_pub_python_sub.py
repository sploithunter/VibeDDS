#!/usr/bin/env python3
"""Test 5: Rust VibeDDS publisher -> Python VibeDDS subscriber.

Starts the Rust hello_pub example as a subprocess.
Python VibeDDS subscribes and verifies it receives the correct content.
Confirms no loopback.
"""

import sys
import os
import time
import subprocess
import signal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from vibedds.participant import DomainParticipant
from vibedds.qos import QosPolicy, ReliabilityKind
from vibedds.type_support import HelloWorldType

EXPECTED_PREFIX = "Hello DDS World"
RUST_PROJECT_DIR = os.path.join(os.path.dirname(__file__), "..", "rust", "vibedds")


def main():
    print("=" * 60)
    print("TEST 5: Rust VibeDDS Publisher -> Python VibeDDS Subscriber")
    print("=" * 60)
    print()

    # --- Build Rust example first ---
    print("[SETUP] Building Rust hello_pub example...")
    build = subprocess.run(
        ["cargo", "build", "--example", "hello_pub"],
        cwd=RUST_PROJECT_DIR,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": os.path.expanduser("~/.cargo/bin") + ":" + os.environ["PATH"]},
    )
    if build.returncode != 0:
        print(f"[ERROR] Cargo build failed:\n{build.stderr}")
        return 1
    print("[SETUP] Build successful")

    # --- Python VibeDDS subscriber ---
    dp = DomainParticipant(domain_id=0, participant_id=3)
    dp.start()
    topic = dp.create_topic("HelloWorld", HelloWorldType.TYPE_NAME)
    qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
    reader = dp.create_reader(topic, qos)

    vibe_received = []

    def on_data(payload: bytes):
        try:
            message = HelloWorldType.deserialize(payload)
            vibe_received.append(message)
            print(f"  [Python RX] {message}")
        except Exception as e:
            print(f"  [Python RX] Deserialize error: {e}")

    reader.on_data(on_data)
    print("[SETUP] Python VibeDDS BEST_EFFORT reader created on topic 'HelloWorld'")

    dp.announce_spdp()

    # --- Start Rust publisher subprocess ---
    env = os.environ.copy()
    env["RUST_LOG"] = "info"
    env["PATH"] = os.path.expanduser("~/.cargo/bin") + ":" + env["PATH"]
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
    start = time.time()

    try:
        while time.time() - start < 30:
            dp.spin_once(timeout=0.05)

            time.sleep(0.05)

            # Check if Rust process died
            if rust_proc.poll() is not None:
                print(f"[WARN] Rust process exited with code {rust_proc.returncode}")
                break

            # Stop early if we have enough samples
            if len(vibe_received) >= 5:
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
    dp.stop()

    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"  Python received: {len(vibe_received)} messages")

    # Verify content
    correct = [m for m in vibe_received if m.startswith(EXPECTED_PREFIX)]
    wrong = [m for m in vibe_received if not m.startswith(EXPECTED_PREFIX)]

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
        print("PASS - Python VibeDDS received Rust VibeDDS messages, no loopback")
    else:
        if len(correct) == 0:
            print("FAIL - Python VibeDDS received no messages from Rust VibeDDS")
        if len(wrong) > 0:
            print("FAIL - Python VibeDDS received unexpected/loopback messages")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
