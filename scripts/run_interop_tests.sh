#!/bin/bash
# Run VibeDDS interoperability tests between Python, Rust, and RTI
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "============================================"
echo "VibeDDS Interoperability Test Suite"
echo "============================================"
echo ""

PASSED=0
FAILED=0
SKIPPED=0

run_test() {
    local name="$1"
    local cmd="$2"
    echo -e "${BLUE}Running: $name${NC}"
    if eval "$cmd" 2>&1; then
        echo -e "${GREEN}✓ PASSED: $name${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ FAILED: $name${NC}"
        ((FAILED++))
    fi
    echo ""
}

skip_test() {
    local name="$1"
    local reason="$2"
    echo -e "${YELLOW}⚠ SKIPPED: $name ($reason)${NC}"
    ((SKIPPED++))
    echo ""
}

# Build Rust first
echo -e "${YELLOW}Building Rust implementation...${NC}"
cd "$PROJECT_ROOT/rust/vibedds"
cargo build --examples 2>&1 | tail -3
echo ""

# ============================================
# Wire Compatibility Tests
# ============================================
echo -e "${YELLOW}=== Wire Compatibility Tests ===${NC}"
echo ""

# Python wire format tests
run_test "Python wire format verification" \
    "cd $PROJECT_ROOT/python && python3 -m pytest tests/test_wire_compat.py -v --tb=short"

# Rust parses Python SPDP
run_test "Rust parses Python SPDP bytes" \
    "cd $PROJECT_ROOT/rust/vibedds && cargo test test_parse_python_generated_spdp --no-fail-fast"

# ============================================
# Python ↔ Rust SPDP Interop
# ============================================
echo -e "${YELLOW}=== Python ↔ Rust SPDP Interop ===${NC}"
echo ""

run_test "Python discovers Rust participant" \
    "cd $PROJECT_ROOT/python && python3 -m pytest tests/test_e2e_rust_interop.py::TestRustPythonSPDPInterop::test_python_discovers_rust_participant -v --tb=short"

run_test "Rust discovers Python participant" \
    "cd $PROJECT_ROOT/python && python3 -m pytest tests/test_e2e_rust_interop.py::TestRustPythonSPDPInterop::test_rust_discovers_python_participant -v --tb=short"

run_test "Bidirectional SPDP discovery" \
    "cd $PROJECT_ROOT/python && python3 -m pytest tests/test_e2e_rust_interop.py::TestRustPythonSPDPInterop::test_bidirectional_discovery -v --tb=short"

# ============================================
# RTI Interop (if available)
# ============================================
echo -e "${YELLOW}=== RTI Interop Tests ===${NC}"
echo ""

if python3 -c "import rti.connextdds" 2>/dev/null; then
    run_test "Python discovers RTI participant" \
        "cd $PROJECT_ROOT/python && python3 -m pytest tests/test_e2e_rti_interop.py::TestRTISPDPInterop::test_vibedds_discovers_rti_participant -v --tb=short"

    run_test "Python discovers RTI with writer" \
        "cd $PROJECT_ROOT/python && python3 -m pytest tests/test_e2e_rti_interop.py::TestRTISPDPInterop::test_vibedds_discovers_rti_with_writer -v --tb=short"

    run_test "Rust discovers RTI participant" \
        "cd $PROJECT_ROOT/python && python3 -m pytest tests/test_e2e_rti_interop.py::TestRustRTIInterop::test_rust_discovers_rti_participant -v --tb=short"

    # Manual SEDP test with rtiddsspy
    if [ -x "/Applications/rti_connext_dds-7.3.0/bin/rtiddsspy" ]; then
        echo -e "${BLUE}Running: Rust SEDP → rtiddsspy${NC}"
        cd "$PROJECT_ROOT/rust/vibedds"
        timeout 8 cargo run --example sedp_announce 2>&1 &
        RUST_PID=$!
        sleep 2

        OUTPUT=$(timeout 4 /Applications/rti_connext_dds-7.3.0/bin/rtiddsspy -domainId 0 2>&1 || true)

        wait $RUST_PID 2>/dev/null || true

        if echo "$OUTPUT" | grep -q "New writer.*HelloWorld"; then
            echo -e "${GREEN}✓ PASSED: Rust SEDP → rtiddsspy${NC}"
            ((PASSED++))
        else
            echo -e "${RED}✗ FAILED: Rust SEDP → rtiddsspy${NC}"
            echo "Output was: $OUTPUT"
            ((FAILED++))
        fi
        echo ""
    else
        skip_test "Rust SEDP → rtiddsspy" "rtiddsspy not found"
    fi
else
    skip_test "Python discovers RTI" "RTI Connext DDS not installed"
    skip_test "Rust discovers RTI" "RTI Connext DDS not installed"
    skip_test "Rust SEDP → rtiddsspy" "RTI Connext DDS not installed"
fi

# ============================================
# Summary
# ============================================
echo "============================================"
echo "Summary"
echo "============================================"
echo -e "Passed:  ${GREEN}$PASSED${NC}"
echo -e "Failed:  ${RED}$FAILED${NC}"
echo -e "Skipped: ${YELLOW}$SKIPPED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All interop tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some interop tests failed${NC}"
    exit 1
fi
