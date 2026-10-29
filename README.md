# DATS RF Simulator Console

Operator interface and control console for the DATS (Digital Advanced Telemetry Simulator) RF Simulator on AMD/Xilinx RFSoC.

The application communicates with the RFSoC bare-metal firmware (`rfsoc_eth_app`) over TCP/UDP, configuring up to 12 simultaneous carriers across a 100 MHz instantaneous bandwidth centered at 2.25 GHz.

---

## Overview

- **Frequency Band**: 2.20 GHz to 2.30 GHz (2.25 GHz nominal center, ±50 MHz offset)
- **Carriers**: Up to 12 independent channels with selectable modulation, power, and data rate
- **Supported Waveforms**: PCM/FSK, PCM/PSK, PCM/PSK/PM, CDMA, Arbitrary I/Q
- **Operating Modes**:
  - **Simulation**: Load Vivado ILA CSV or custom I/Q captures, inspect time-domain waveforms, FFT power spectrum, and constellations, and stream samples to any carrier.
  - **Radiation**: Over-the-air transmission via RFSoC DACs with safety confirmations for mode changes and RF start/stop.
- **Protocol**: Standard DATS Common Message Structure frame with ACK handshake.

---

## Getting Started

### Prerequisites
- Python 3.10+
- Modern web browser (Chrome, Edge, Firefox)

### Running on Windows
Double-click `start.bat` or run:
```cmd
py run.py
```
This automatically starts the FastAPI backend and serves the compiled UI at:  
**http://127.0.0.1:8765**

### Running on Linux / macOS
```bash
chmod +x start.sh
./start.sh
```

### Local Testing Without Hardware
If you don't have the RFSoC board connected, run the mock device in a separate terminal:
```cmd
py backend/mock_device.py --port 7000
```
In the web console, set IP to `127.0.0.1`, port to `7000`, and click **Connect**.

---

## Hardware Connection

| Setting | Default Value | Notes |
| :--- | :--- | :--- |
| **Board IP** | `192.168.1.10` | Static IP assigned to RFSoC PS GEM |
| **Port** | `7000` | Configured in `echo.c` (TCP) |
| **Host NIC** | `192.168.1.x / 24` | Set your PC's Ethernet adapter to the same subnet |
| **Protocol** | `TCP` (recommended) or `UDP` | Common DATS framing |

When connecting to the physical board:
1. Ensure the RFSoC Ethernet cable is connected and the link LED is up.
2. Confirm you can ping `192.168.1.10`.
3. In the GUI top bar, enter `192.168.1.10` : `7000` and click **Connect**.
4. The status indicator will turn green once the TCP connection is established.

---

## Operating Workflow

1. **Carrier Setup**:
   - Enable/disable required carriers (1 to 12).
   - Set modulation type, bit rate, subcarrier frequency, and frame length.
   - Adjust frequency offsets (in Hz relative to 2.25 GHz) and output power (-150 to +20 dBm).
   - Use **"Copy to all"** if you want to quickly duplicate parameters across all 12 carriers.
2. **Apply Configuration**:
   - Click **"Apply"** to transmit configuration frames to the hardware.
   - The app sends `SET_MODE` followed by `CARRIER_CONFIG` for each configured carrier, verifying the ACK for each packet.
3. **RF Control**:
   - Click **Start RF** to enable DAC transmission.
   - Click **Stop RF** to shut down output.
   - *In Radiation mode, safety prompt confirmation is required before RF can be enabled.*
4. **Waveform Analysis (Simulation Mode)**:
   - Drag and drop Vivado ILA CSV files (`bpsk.csv`, `fsk.csv`, etc.) or raw I/Q data.
   - Interactive plots display time-domain signals (up to 10,000 samples for high-resolution transitions), power spectral density, and I/Q constellation.
   - Click **"Send to Carrier N"** to stream arbitrary baseband samples directly to a carrier.

---

## Protocol Specification

### Common Frame Structure (29 + N bytes)

```
[ SOP (4B) ] [ Routing & Header (20B) ] [ Payload (N B) ] [ XOR Checksum (1B) ] [ EOP (4B) ]
```

| Field | Offset | Length | Description |
| :--- | :---: | :---: | :--- |
| **SOP** | 0 | 4 | Magic sync: `0xB1 0xB1 0xB1 0xB1` |
| **Destination ID** | 4 | 1 | Target subsystem ID (`0x02` for simulator) |
| **Source ID** | 5 | 1 | Originator ID (`0x01` for console) |
| **Subsystems** | 6..9 | 4 | Destination/Source subsystem & sub-subsystem |
| **Sequence Counter**| 10 | 1 | Increments per transmitted frame (0–255) |
| **Command ID** | 11 | 1 | Identifies command type |
| **Reserved** | 12 | 1 | `0x00` |
| **Packet Kind** | 13 | 1 | `0xAA` = Data/Command, `0xBB` = ACK |
| **Timestamp** | 14 | 8 | 64-bit Unix epoch seconds (Big-Endian) |
| **Data Length (N)** | 22 | 2 | Payload byte count (Big-Endian) |
| **Payload** | 24 | N | Command-specific parameters |
| **Checksum** | 24+N | 1 | XOR of all preceding bytes (byte 0 to byte 23+N) |
| **EOP** | 25+N | 4 | Magic trailer: `0xE1 0xE1 0xE1 0xE1` |

### Command IDs

| ID | Name | Payload Size | Description |
| :---: | :--- | :---: | :--- |
| `0x01` | `RF_CONTROL` | 1 byte | `0x01` = Start RF, `0x00` = Stop RF |
| `0x02` | `SET_MODE` | 1 byte | `0x00` = Simulation, `0x01` = Radiation |
| `0x10` | `CARRIER_CONFIG`| 17 bytes | Carrier #, enable, waveform, rate, offset, power |
| `0x20` | `IQ_DATA` | 7 + 4n bytes | Stream chunk: sequence, count, interleaved I/Q |
| `0x21` | `IQ_BEGIN` | 9 bytes | Carrier #, sample rate (Hz), total sample count |
| `0x22` | `IQ_END` | 5 bytes | Carrier #, total transmitted chunk count |

### ACK Response (30 bytes)
Upon receiving a valid frame, the board replies with an ACK frame:
- Dest/Source IDs swapped.
- Same sequence counter and command ID.
- `Kind` set to `0xBB`.
- Payload = 1 byte (`0x00` = OK).

---

## Firmware Project (`rfsoc_eth_app`)

The embedded firmware running on the RFSoC Zynq UltraScale+ Cortex-A53 is located in `rfsoc_eth_app/`:
- **`echo.c`**: TCP server using lwIP raw API. Listens on port 7000, validates SOP/EOP/Checksum, and sends ACKs.
- **`process.c`**: Decodes command payloads and writes parameters to Vivado PL registers using `writeToVivadoD()`.
- **`struct_def.h`**: Memory layouts and constants for the DATS message protocol.

### Building Firmware in Xilinx Vitis
1. Open Xilinx Vitis 2020.2+ and select `rfsoc_eth_app` as workspace.
2. Build the application project.
3. Program the FPGA bitstream and run the ELF on target hardware via JTAG or SD card boot.

---

## Repository Structure

```
├── backend/                  # Python FastAPI service & hardware interface
│   ├── must_sim/             # Core logic: frame codec, commands, waveform parser
│   ├── tests/                # Pytest test suite (frame, waveform, spec validation)
│   ├── mock_device.py        # Hardware emulator for offline testing
│   └── run.py                # Server entry point
├── frontend/                 # React + TypeScript operator interface
│   ├── src/                  # Components, state store, spectrum/constellation plots
│   └── dist/                 # Pre-compiled static assets served by FastAPI
├── config/
│   └── commands.json         # Command ID table and network endianness config
├── rfsoc_eth_app/            # Xilinx Vitis bare-metal Ethernet app (PS TCP server)
├── rfsoc_rfdc_app/           # Xilinx Vitis RFDC & clock configuration app
└── samples/                  # Vivado ILA waveform captures (.csv)
```

---

## Development & Testing

```bash
# Run backend test suite
cd backend
python -m pytest -v

# Frontend development server (optional; only needed when modifying UI)
cd frontend
npm install
npm run dev

# Rebuild frontend production bundle
npm run build
```
