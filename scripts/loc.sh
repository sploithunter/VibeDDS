#!/usr/bin/env bash
# Lines of code counter for VibeDDS
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

count_and_display() {
    local label="$1"
    shift
    local total=0
    local files=0
    for f in "$@"; do
        if [ -f "$f" ]; then
            local n
            n=$(wc -l < "$f")
            total=$((total + n))
            files=$((files + 1))
        fi
    done
    printf "  %-40s %6d lines  (%d files)\n" "$label" "$total" "$files" >&2
    echo "$total"
}

echo "===== VibeDDS Lines of Code =====" >&2
echo "" >&2

grand_total=0

# --- Python ---
echo "Python Implementation" >&2
n=$(count_and_display "Library (vibedds/)" "$ROOT"/python/vibedds/*.py)
grand_total=$((grand_total + n))
n=$(count_and_display "Tests (tests/)" "$ROOT"/python/tests/*.py)
grand_total=$((grand_total + n))
n=$(count_and_display "Examples (examples/)" "$ROOT"/python/examples/*.py)
grand_total=$((grand_total + n))
echo "" >&2

# --- Rust ---
echo "Rust Implementation" >&2
n=$(count_and_display "Library (src/)" "$ROOT"/rust/vibedds/src/*.rs)
grand_total=$((grand_total + n))
n=$(count_and_display "Tests (tests/)" "$ROOT"/rust/vibedds/tests/*.rs)
grand_total=$((grand_total + n))
n=$(count_and_display "Examples (examples/)" "$ROOT"/rust/vibedds/examples/*.rs)
grand_total=$((grand_total + n))
echo "" >&2

# --- Other ---
echo "Other" >&2
n=$(count_and_display "Scripts (scripts/)" "$ROOT"/scripts/*.py "$ROOT"/scripts/*.sh)
grand_total=$((grand_total + n))
n=$(count_and_display "RTI test tools (rti_test/)" "$ROOT"/rti_test/*.py)
grand_total=$((grand_total + n))

# Config files
config_files=("$ROOT"/rust/vibedds/Cargo.toml)
[ -f "$ROOT/python/pyproject.toml" ] && config_files+=("$ROOT/python/pyproject.toml")
[ -f "$ROOT/python/setup.py" ] && config_files+=("$ROOT/python/setup.py")
[ -f "$ROOT/python/setup.cfg" ] && config_files+=("$ROOT/python/setup.cfg")
n=$(count_and_display "Config (Cargo.toml, etc.)" "${config_files[@]}")
grand_total=$((grand_total + n))

# Documentation - only project docs, not third_party/specs/venvs
doc_files=()
for f in "$ROOT"/*.md "$ROOT"/python/*.md; do
    [ -f "$f" ] && doc_files+=("$f")
done
if [ ${#doc_files[@]} -gt 0 ]; then
    n=$(count_and_display "Documentation (*.md)" "${doc_files[@]}")
    grand_total=$((grand_total + n))
fi
echo "" >&2

echo "---------------------------------------------" >&2
printf "  %-40s %6d lines\n" "TOTAL" "$grand_total" >&2
echo "" >&2

# --- Rust compiled library size ---
echo "Rust Compiled Library" >&2
RUST_DIR="$ROOT/rust/vibedds"
if [ -d "$RUST_DIR" ]; then
    if ! cargo build --release --manifest-path "$RUST_DIR/Cargo.toml" --quiet 2>/dev/null; then
        echo "  (cargo build --release failed, skipping)" >&2
    else
        lib_file=$(find "$RUST_DIR/target/release" -maxdepth 3 -name "libvibedds*.rlib" -o -name "libvibedds*.a" 2>/dev/null | head -1)
        if [ -n "$lib_file" ]; then
            size_bytes=$(stat -f%z "$lib_file" 2>/dev/null || stat -c%s "$lib_file" 2>/dev/null)
            if [ "$size_bytes" -ge 1048576 ]; then
                size_human="$(echo "scale=1; $size_bytes / 1048576" | bc) MB"
            else
                size_human="$(echo "scale=1; $size_bytes / 1024" | bc) KB"
            fi
            printf "  %-40s %s (%s)\n" "Release library" "$size_human" "$(basename "$lib_file")" >&2
        else
            echo "  (no .rlib or .a found in target/release)" >&2
        fi
    fi
fi
echo "=====================================" >&2
