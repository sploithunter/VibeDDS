# VibeDDS RTI Interop Debug Progress

## Date: 2026-01-29

## Summary of Issues Fixed

### 1. ReliabilityKind Enum Values (FIXED)
- **Problem**: VibeDDS used BEST_EFFORT=1, RELIABLE=2 (OMG IDL spec values)
- **Fix**: Changed to wire format values BEST_EFFORT=0, RELIABLE=1
- **File**: `vibedds/qos.py` line 13-16

### 2. RTPX Magic (FIXED)
- **Problem**: RTI sends some packets with "RTPX" magic instead of "RTPS"
- **Fix**: Added RTPX_MAGIC constant and updated parser to accept both
- **Files**:
  - `vibedds/constants.py` - added `RTPX_MAGIC = b'RTPX'`
  - `vibedds/wire.py` - updated parser to accept both RTPS and RTPX

### 3. SEDP Profile Format (VERIFIED CORRECT)
- The "rti" profile produces correct DATA_REPRESENTATION (12 bytes) and TYPE_CONSISTENCY (8 bytes)
- Use `VIBEDDS_SEDP_PROFILE=rti` for RTI interop

## Current Blocking Issue

### VibeDDS Metatraffic Socket Not Receiving RTI Packets

**Symptom**: VibeDDS's metatraffic socket (bound to `192.168.8.151:7420`) receives NO packets from RTI.

**Evidence**:
1. Raw socket monitoring shows 0 packets received
2. VibeDDS discovers RTI's participant via SPDP multicast (works)
3. VibeDDS sends SEDP to RTI (confirmed by logging)
4. But RTI never sends SEDP publications back to VibeDDS's metatraffic port
5. RTI shows 0 matched subscriptions

**Key Log Output**:
```
VibeDDS metatraffic socket bound to: ('192.168.8.151', 7420)
=== Raw packet monitoring for 5 seconds ===
[i=0] No packet received
[i=1] No packet received
...
```

**Basic UDP Test Passed**:
A simple Python test sending from port 7410 to 7420 works fine, proving the network/socket layer is functional.

## Root Cause Hypothesis

RTI is either:
1. Not receiving VibeDDS's SPDP announcement correctly (missing/wrong metatraffic locators)
2. Not sending SEDP publications to VibeDDS because of a validation failure
3. Sending to the wrong address (e.g., localhost instead of 192.168.8.151)

## Next Steps to Debug

### Step 1: Verify VibeDDS's SPDP Announcement
Check that VibeDDS's SPDP includes correct metatraffic locators:
- PID_METATRAFFIC_UNICAST_LOCATOR should contain 192.168.8.151:7420
- Verify the Locator serialization format matches RTI's expectations

### Step 2: Use Wireshark/tcpdump to Capture Traffic
Need to run with sudo to capture:
```bash
sudo tcpdump -i any 'udp portrange 7400-7450' -w /tmp/capture.pcap
```
Then analyze what RTI is actually sending and where.

### Step 3: Check RTI's Discovery of VibeDDS
Use RTI's verbosity/logging to see if RTI discovers VibeDDS's participant and what metatraffic address it's using.

### Step 4: Try Binding to INADDR_ANY
Currently VibeDDS binds metatraffic to specific IP. Try binding to "" (INADDR_ANY) instead:
- File: `vibedds/transport.py` line 126
- Change: `sock.bind((bind_addr, self._metatraffic_unicast_port))`
- Try: `sock.bind(("", self._metatraffic_unicast_port))`

### Step 5: Compare SPDP with Working RTI-to-RTI
Capture RTI-to-RTI SPDP exchange and compare locator encoding with VibeDDS.

## Test Files Created

- `test_rti_match.py` - Basic reliability enum and SEDP format tests
- `test_sedp_format.py` - SEDP payload format verification for different profiles
- `test_rti_profile_match.py` - Full RTI-VibeDDS matching test

## Key Code Locations

- **Transport**: `vibedds/transport.py` - Socket binding and recv
- **SPDP Writer**: `vibedds/spdp.py:88-147` - SPDP announcement building
- **SEDP**: `vibedds/sedp.py` - SEDP protocol and payload building
- **Participant**: `vibedds/participant.py` - Message dispatch and handling

## Quick Resume Commands

```bash
cd /Users/jason/Documents/VibeDDS/python
source ../.venv-rti/bin/activate
export VIBEDDS_SEDP_PROFILE=rti

# Run the test
python test_rti_profile_match.py

# Or run with debug logging
python -c "
import os, logging
os.environ['VIBEDDS_SEDP_PROFILE'] = 'rti'
logging.basicConfig(level=logging.DEBUG)
# ... rest of test
"
```

## Interop Experiments Documentation

See also:
- `specs/interop-experiments.md` - Full experiment log
- `specs/interop-sedp-matrix.md` - SEDP format differences between implementations
