# VibeDDS Comprehensive Test Plan

## Current Test Status (Updated 2026-01-28)

**Total Tests: 324**
- **Rust**: 144 tests (133 unit + 11 wire_compat integration)
- **Python**: 180 tests

All tests passing ✅

## Testing Philosophy

Every component needs tests at multiple levels:
1. **Unit tests** - Test individual functions/methods in isolation
2. **Integration tests** - Test component interactions within a language
3. **E2E tests** - Test full protocol flows
4. **Wire compatibility tests** - Cross-language byte-level verification
5. **RTI interop tests** - Verify against reference implementation

## Test Matrix

### Unit Tests by Module

| Module | Rust Tests | Python Tests | Target | Notes |
|--------|------------|--------------|--------|-------|
| CDR serialization | 26 | 30 | 30+ | Need edge cases |
| Types | 12 | 28 | 30+ | Need error cases |
| Messages | 9 | 15 | 20+ | Need all submessage types |
| Wire builder/parser | 9 | 10 | 20+ | Need malformed input tests |
| SPDP | 12 | 12 | 20+ | Need error handling |
| SEDP | 18 | 10 | 25+ | Need all SEDP flows |
| QoS | 18 | 8 | 20+ | Need all QoS policies |
| Reliability | 10 | 8 | 25+ | Need retransmit, gap handling |
| Transport | 14 | 5 | 15+ | Need error conditions |
| Participant | 14 | 6 | 20+ | Need lifecycle tests |

### Wire Compatibility Tests

| Scenario | Status | Priority |
|----------|--------|----------|
| Rust parses Python SPDP | ✅ 6 tests | Done |
| Python parses Rust SPDP | ✅ 2 tests | Done |
| Rust parses Python SEDP | ✅ 3 tests | Done |
| Python parses Rust SEDP | ✅ 2 tests | Done |
| Rust parses Python DATA | ❌ Missing | HIGH (Stage 6e) |
| Python parses Rust DATA | ❌ Missing | HIGH (Stage 6e) |
| Python parses Rust HEARTBEAT | ✅ 1 test | Done |
| Both parse RTI SPDP | ❌ Missing | MEDIUM |
| Both parse RTI SEDP | ❌ Missing | MEDIUM |

### E2E Protocol Tests

| Scenario | Rust | Python | Status |
|----------|------|--------|--------|
| SPDP self-discovery | ✅ | ✅ | Done |
| SPDP lease expiry | ✅ | ✅ | Done |
| SEDP endpoint announce | ✅ | ✅ | Done |
| SEDP endpoint matching | ❌ | ✅ | Rust missing |
| Reliable writer heartbeat | ❌ | ✅ | Rust E2E missing |
| Reliable reader ACKNACK | ❌ | ✅ | Rust E2E missing |
| Data publish/subscribe | ❌ | ✅ | Stage 6e |
| QoS compatibility reject | ❌ | ✅ | Rust E2E missing |

### Interoperability Tests

| Scenario | Status | Priority |
|----------|--------|----------|
| Python ↔ Rust SPDP | ✅ 3 tests | Done |
| Python ↔ Rust SEDP | ❌ Missing | HIGH |
| Python ↔ Rust DATA | ❌ Missing | HIGH (Stage 6e) |
| Python ↔ RTI SPDP | ✅ 3 tests | Done |
| Python ↔ RTI SEDP | ❌ Missing | HIGH |
| Python ↔ RTI DATA | ❌ Missing | HIGH |
| Rust ↔ RTI SPDP | ✅ 1 test | Done |
| Rust ↔ RTI SEDP | ✅ rtiddsspy | Done (manual verified) |
| Rust ↔ RTI DATA | ❌ Missing | HIGH (Stage 6e) |

## Immediate Priorities

### Phase 1: Wire Compatibility ✅ DONE
1. ✅ Generate known-good bytes from Python, test Rust parsing
2. ✅ Generate known-good bytes from Rust, test Python parsing
3. ❌ Capture RTI bytes, test both parsing

### Phase 2: Cross-Language SEDP (Next)
1. Python registers writer, Rust discovers it
2. Rust registers writer, Python discovers it
3. Verify endpoint matching across languages

### Phase 3: RTI Automated Interop
1. ✅ Automate rtiddsspy verification (in run_interop_tests.sh)
2. ❌ RTI writer → VibeDDS reader
3. ❌ VibeDDS writer → RTI reader

### Phase 4: Error Handling & Edge Cases
1. Malformed RTPS messages
2. Invalid parameter lists
3. Network errors
4. Lease expiry edge cases

## Test File Organization

```
python/tests/
├── test_cdr.py              # CDR unit tests
├── test_types.py            # Type unit tests
├── test_messages.py         # Message unit tests
├── test_spdp.py             # SPDP unit tests
├── test_sedp.py             # SEDP unit tests
├── test_qos.py              # QoS unit tests
├── test_reliability.py      # Reliability unit tests
├── test_wire_compat.py      # Wire compatibility (bidirectional)
├── test_e2e_spdp.py         # SPDP E2E
├── test_e2e_sedp.py         # SEDP E2E
├── test_e2e_data.py         # Data E2E (Stage 6e)
├── test_e2e_rust_interop.py # Rust interop
├── test_e2e_rti_interop.py  # RTI interop
└── test_interop.py          # Type interop tests

rust/vibedds/src/
├── cdr.rs          # CDR tests inline
├── types.rs        # Type tests inline
├── messages.rs     # Message tests inline
├── wire.rs         # Wire tests inline
├── spdp.rs         # SPDP tests inline
├── sedp.rs         # SEDP tests inline
├── qos.rs          # QoS tests inline
├── reliability.rs  # Reliability tests inline
├── transport.rs    # Transport tests inline
└── participant.rs  # Participant tests inline

rust/vibedds/tests/
├── wire_compat.rs      # Wire compatibility (11 tests)
├── e2e_spdp.rs         # SPDP E2E (planned)
├── e2e_sedp.rs         # SEDP E2E (planned)
└── python_interop.rs   # Python interop (planned)

rust/vibedds/examples/
├── spdp_announce.rs    # SPDP example for interop
├── sedp_announce.rs    # SEDP example for interop
└── export_test_bytes.rs # Generate bytes for Python tests
```

## Running Tests

```bash
# Full test suite
cd /Users/jason/Documents/VibeDDS
bash scripts/run_all_tests.sh

# Interop tests only
bash scripts/run_interop_tests.sh

# Python only
cd python && pytest tests/ -v --tb=short

# Rust only
cd rust/vibedds && cargo test

# Specific test file
pytest tests/test_wire_compat.py -v
cargo test --test wire_compat
```

## CI/CD Checklist

- [x] All unit tests pass
- [x] All E2E tests pass
- [x] Wire compatibility verified (bidirectional)
- [x] RTI interop verified (SPDP + SEDP)
- [ ] No memory leaks (Rust)
- [ ] Code coverage > 80%
- [ ] Python ↔ Rust SEDP interop automated

## Next Steps for Stage 6e (Data Pub/Sub)

1. Implement DataWriter.write() in Rust
2. Implement data sample serialization
3. Add wire compat tests for DATA submessages
4. Add E2E tests for publish/subscribe
5. Add RTI data interop tests
