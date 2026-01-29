# VibeDDS Project Context

## Overview

VibeDDS is a DDS (Data Distribution Service) implementation built from scratch, prototyped in Python and ported to Rust. The goal is full interoperability with RTI Connext DDS.

## Project Structure

```
/Users/jason/Documents/VibeDDS/
├── python/                 # Python prototype (complete)
│   ├── vibedds/           # Main library
│   └── tests/             # Unit + E2E tests
├── rust/vibedds/          # Rust implementation (in progress)
│   ├── src/               # Library modules
│   └── examples/          # Runnable examples
├── pdfs/                  # Original RTPS/DDS specs
└── specs/                 # Extracted markdown specs
```

## Implementation Stages

| Stage | Description | Python | Rust |
|-------|-------------|--------|------|
| 1 | CDR Serialization | Done | Done |
| 2 | RTPS Messages + Wire | Done | Done |
| 3 | SPDP Discovery | Done | Done |
| 4 | SEDP Endpoint Discovery | Done | Done |
| 5 | Pub/Sub Data Exchange | Done | **TODO** |

## RTI Interoperability Testing

### Tools

1. **rtiddsspy** - Shows discovered endpoints and samples
   ```bash
   /Applications/rti_connext_dds-7.3.0/bin/rtiddsspy -domainId 0 -printSample
   ```
   - Without `-printSample`: shows only endpoint discovery (writers/readers)
   - With `-printSample`: shows actual data samples being published

2. **RTI Python API** - For programmatic interop tests
   ```python
   import rti.connextdds as dds
   participant = dds.DomainParticipant(0)
   ```

3. **RTI Shapes Demo** - Visual pub/sub testing
   ```bash
   /Applications/rti_connext_dds-7.3.0/bin/rtishapesdemo
   ```

### What rtiddsspy Shows

- **SPDP only**: Nothing visible (rtiddsspy doesn't show raw participants)
- **SEDP complete**: Shows "New writer" / "New reader" lines
- **Data publishing**: Shows sample data with `-printSample` flag

### Testing Checklist

1. **SPDP Discovery**
   ```bash
   # Run VibeDDS
   cargo run --example spdp_announce
   # Check logs for "Discovered participant" with vendor (1,1) = RTI
   ```

2. **SEDP Endpoint Discovery**
   ```bash
   # Run VibeDDS with registered endpoints
   cargo run --example sedp_announce
   # Run rtiddsspy - should see "New writer/reader from <IP>"
   /Applications/rti_connext_dds-7.3.0/bin/rtiddsspy -domainId 0
   ```

3. **Data Exchange** (Stage 6e)
   ```bash
   # Run VibeDDS publisher
   cargo run --example hello_pub
   # Run rtiddsspy with samples
   /Applications/rti_connext_dds-7.3.0/bin/rtiddsspy -domainId 0 -printSample
   # Should see actual HelloWorld data
   ```

### Common Issues

1. **Ports**: Domain 0 uses ports 7400 (SPDP multicast), 7410+ (unicast)
2. **Multicast**: Ensure 239.255.0.1 is reachable
3. **Vendor ID**: VibeDDS uses 0xFF01 (experimental), RTI is 0x0101

## Key Files

### Rust

- `src/participant.rs` - DomainParticipant, main entry point
- `src/spdp.rs` - Participant discovery
- `src/sedp.rs` - Endpoint discovery
- `src/reliability.rs` - Reliable writer/reader state machines
- `src/qos.rs` - QoS policies
- `src/wire.rs` - RTPS message building/parsing
- `src/cdr.rs` - CDR serialization

### Examples

- `examples/spdp_announce.rs` - SPDP-only test
- `examples/sedp_announce.rs` - SEDP endpoint registration

## Building & Testing

```bash
cd /Users/jason/Documents/VibeDDS/rust/vibedds

# Build
cargo build

# Run all tests
cargo test

# Run specific example
cargo run --example sedp_announce

# With logging
RUST_LOG=debug cargo run --example sedp_announce
```

## Next Steps (Stage 6e)

1. Implement `DataWriter.write()` - serialize data, build DATA submessage, send
2. Implement `DataReader` - receive DATA, deserialize, deliver to callback
3. Add HelloWorld type support (CDR encoding)
4. Test with `rtiddsspy -printSample`

## Protocol Constants

- RTPS Version: 2.5
- Vendor ID: 0xFF01 (VibeDDS experimental)
- Default domain: 0
- SPDP multicast: 239.255.0.1:7400
- Entity kinds: 0x02 = writer, 0x07 = reader, 0xC2 = builtin writer, 0xC7 = builtin reader
