#!/bin/bash
# Run all VibeDDS tests: unit, E2E, and interoperability
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "============================================"
echo "VibeDDS Full Test Suite"
echo "============================================"
echo ""

FAILED=0

# 1. Rust unit tests
echo -e "${YELLOW}[1/5] Running Rust unit tests...${NC}"
cd "$PROJECT_ROOT/rust/vibedds"
if cargo test 2>&1; then
    echo -e "${GREEN}✓ Rust unit tests passed${NC}"
else
    echo -e "${RED}✗ Rust unit tests failed${NC}"
    FAILED=1
fi
echo ""

# 2. Python unit tests
echo -e "${YELLOW}[2/5] Running Python unit tests...${NC}"
cd "$PROJECT_ROOT/python"
if python3 -m pytest tests/test_cdr.py tests/test_types.py tests/test_messages.py tests/test_spdp.py tests/test_sedp.py tests/test_wire_compat.py -v --tb=short 2>&1; then
    echo -e "${GREEN}✓ Python unit tests passed${NC}"
else
    echo -e "${RED}✗ Python unit tests failed${NC}"
    FAILED=1
fi
echo ""

# 3. Python E2E tests (no external deps)
echo -e "${YELLOW}[3/5] Running Python E2E tests...${NC}"
cd "$PROJECT_ROOT/python"
if python3 -m pytest tests/test_e2e_spdp.py tests/test_e2e_sedp.py tests/test_interop.py -v --tb=short 2>&1; then
    echo -e "${GREEN}✓ Python E2E tests passed${NC}"
else
    echo -e "${RED}✗ Python E2E tests failed${NC}"
    FAILED=1
fi
echo ""

# 4. Python ↔ Rust interop
echo -e "${YELLOW}[4/5] Running Python ↔ Rust interoperability tests...${NC}"
cd "$PROJECT_ROOT/python"
if python3 -m pytest tests/test_e2e_rust_interop.py -v --tb=short 2>&1; then
    echo -e "${GREEN}✓ Python ↔ Rust interop tests passed${NC}"
else
    echo -e "${RED}✗ Python ↔ Rust interop tests failed${NC}"
    FAILED=1
fi
echo ""

# 5. RTI interop (optional)
echo -e "${YELLOW}[5/5] Running RTI interoperability tests...${NC}"
cd "$PROJECT_ROOT/python"
if python3 -c "import rti.connextdds" 2>/dev/null; then
    if python3 -m pytest tests/test_e2e_rti_interop.py -v --tb=short 2>&1; then
        echo -e "${GREEN}✓ RTI interop tests passed${NC}"
    else
        echo -e "${RED}✗ RTI interop tests failed${NC}"
        FAILED=1
    fi
else
    echo -e "${YELLOW}⚠ RTI Connext DDS not installed, skipping RTI tests${NC}"
fi
echo ""

# Summary
echo "============================================"
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed${NC}"
    exit 1
fi
