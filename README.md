# VibeDDS

A lightweight DDS (Data Distribution Service) implementation in Python and Rust.

VibeDDS implements the OMG DDS and RTPS (Real-Time Publish-Subscribe) protocols, enabling interoperability with other DDS implementations like RTI Connext, FastDDS, and CycloneDDS.

## Features

- **SPDP** (Simple Participant Discovery Protocol) - automatic participant discovery
- **SEDP** (Simple Endpoint Discovery Protocol) - automatic topic/endpoint discovery
- **CDR** (Common Data Representation) serialization
- **RTPS** wire protocol implementation
- **QoS** policies (reliability, durability, etc.)
- **Multicast** discovery on standard DDS ports
- **Interoperability** tested with RTI DDS Spy

## Project Structure

```
VibeDDS/
├── python/
│   ├── vibedds/          # Core library
│   │   ├── participant.py    # DomainParticipant
│   │   ├── spdp.py           # Participant discovery
│   │   ├── sedp.py           # Endpoint discovery
│   │   ├── cdr.py            # CDR serialization
│   │   ├── messages.py       # RTPS messages
│   │   ├── wire.py           # Wire protocol
│   │   ├── transport.py      # UDP transport
│   │   ├── qos.py            # QoS policies
│   │   └── ...
│   ├── examples/         # Example applications
│   └── tests/            # Test suite
├── rust/
│   └── vibedds/          # Rust implementation (WIP)
├── specs/                # DDS/RTPS specifications (markdown)
└── pdfs/                 # Original OMG specification PDFs
```

## Quick Start

### Publisher

```python
from vibedds.participant import DomainParticipant
from vibedds.qos import QosPolicy, ReliabilityKind
from vibedds.type_support import HelloWorldType

# Create participant on domain 0
dp = DomainParticipant(domain_id=0)
dp.start()

# Create topic and writer
topic = dp.create_topic("HelloWorldTopic", HelloWorldType.TYPE_NAME)
writer = dp.create_writer(topic, QosPolicy(reliability=ReliabilityKind.BEST_EFFORT))

# Publish data
payload = HelloWorldType.serialize("Hello DDS World!")
writer.write(payload)
```

### Subscriber

```python
from vibedds.participant import DomainParticipant
from vibedds.qos import QosPolicy, ReliabilityKind
from vibedds.type_support import HelloWorldType

def on_data(payload: bytes):
    message = HelloWorldType.deserialize(payload)
    print(f"Received: {message}")

dp = DomainParticipant(domain_id=0)
dp.start()

topic = dp.create_topic("HelloWorldTopic", HelloWorldType.TYPE_NAME)
reader = dp.create_reader(topic, QosPolicy(reliability=ReliabilityKind.BEST_EFFORT))
reader.on_data(on_data)

# Process incoming data
while True:
    dp.spin_once(timeout=0.1)
```

## Running Examples

```bash
# Terminal 1 - Start subscriber
python python/examples/hello_sub.py

# Terminal 2 - Start publisher
python python/examples/hello_pub.py
```

## Testing with RTI DDS Spy

VibeDDS is interoperable with RTI Connext DDS. Run `rtiddsspy` to monitor traffic:

```bash
rtiddsspy -domainId 0
```

## Requirements

- Python 3.8+
- No external dependencies for core functionality

## Running Tests

```bash
cd python
python -m pytest tests/
```

## Specifications

The `specs/` directory contains markdown versions of the OMG DDS specifications for reference:

- DDS 1.4 - Data Distribution Service
- DDSI-RTPS 2.5 - Real-Time Publish-Subscribe Wire Protocol
- DDS-XTypes 1.3 - Extensible Types
- DDS-Security 1.2 - Security
- OMG IDL 4.2 - Interface Definition Language

## Status

This is an early-stage implementation. Current status:

- [x] SPDP participant discovery
- [x] SEDP endpoint discovery
- [x] Basic CDR serialization
- [x] Best-effort reliability
- [ ] Reliable reliability (NACK/heartbeat)
- [ ] Full QoS support
- [ ] Rust implementation

## License

MIT
