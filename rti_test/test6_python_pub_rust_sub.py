#!/usr/bin/env python3
"""Test 6: Python VibeDDS publisher -> Rust VibeDDS subscriber.

Python VibeDDS publishes "Hello World from Python VibeDDS" messages.
Starts the Rust hello_sub example as a subprocess.
Verifies Rust receives the correct content by checking stdout.
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

EXPECTED_PREFIX = "Hello World from Python VibeDDS"
RUST_PROJECT_DIR = os.path.join(os.path.dirname(__file__), "..", "rust", "vibedds")


def main():
    print("=" * 60)
    print("TEST 6: Python VibeDDS Publisher -> Rust VibeDDS Subscriber")
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

    # --- Start Rust subscriber subprocess ---
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
    dp = DomainParticipant(domain_id=0, participant_id=6)
    dp.start()
    topic = dp.create_topic("HelloWorld", HelloWorldType.TYPE_NAME)
    qos = QosPolicy(reliability=ReliabilityKind.BEST_EFFORT)
    writer = dp.create_writer(topic, qos)
    print("[SETUP] Python VibeDDS BEST_EFFORT writer created on topic 'HelloWorld'")
    print()

    dp.announce_spdp()

    # --- Run for up to 30 seconds, spinning continuously ---
    publish_count = 0
    start = time.time()
    last_publish = 0

    try:
        while time.time() - start < 30:
            dp.spin_once(timeout=0.1)

            # Publish from Python VibeDDS every 2 seconds
            elapsed = time.time() - start
            if int(elapsed) % 2 == 0 and int(elapsed) != last_publish and int(elapsed) > 0:
                last_publish = int(elapsed)
                publish_count += 1
                msg = f"{EXPECTED_PREFIX} #{publish_count}"
                payload = HelloWorldType.serialize(msg)
                writer.write(payload)
                print(f"  [Python TX] {msg}")

            # Check if Rust process died
            if rust_proc.poll() is not None:
                print(f"[WARN] Rust process exited with code {rust_proc.returncode}")
                break

            # Stop early after enough publishes
            if publish_count >= 8:
                # Keep spinning for a few more seconds to let messages arrive
                wait_start = time.time()
                while time.time() - wait_start < 5:
                    dp.spin_once(timeout=0.1)
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
        # hello_sub prints "Received: <message>" or "[buffer] Received: <message> (...)"
        if "Received:" in line:
            idx = line.index("Received:") + len("Received: ")
            msg = line[idx:].strip()
            # Strip trailing metadata like "(from ..., sn=...)"
            if " (from " in msg:
                msg = msg[:msg.index(" (from ")].strip()
            rust_received.append(msg)

    # --- Cleanup ---
    dp.stop()

    # --- Results ---
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"  Python published: {publish_count} messages")
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
        print("PASS - Rust VibeDDS received Python VibeDDS messages, no loopback")
    else:
        if len(correct) == 0:
            print("FAIL - Rust VibeDDS received no messages from Python VibeDDS")
        if len(wrong) > 0:
            print("FAIL - Rust VibeDDS received unexpected/loopback messages")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
