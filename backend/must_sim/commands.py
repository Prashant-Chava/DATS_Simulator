"""Command table (placeholder IDs) and the data-packet encoders / decoders.

The IDD defines the frame but its 'Command ID table IV' was not available, so
command numbers live in config/commands.json and the data-packet layouts below
are PROPOSALS. Change them here when the real table is known. Nothing else in
the app needs to change.

Data packet layouts (multi-byte numbers use the configured byte order):

RF_CONTROL      1 B   0 = stop, 1 = start
SET_MODE        1 B   0 = simulation, 1 = radiation
SET_CLOCK       1 B   0 = internal 100 MHz, 1 = external 100 MHz
CARRIER_CONFIG 17 B   carrier u8 | enabled u8 | waveform u8 | bit rate kbps u16 |
                      subcarrier kHz u16 | PCM code u8 (0 NRZ-L, 1 NRZ-S) |
                      convolutional u8 | frame length u16 |
                      frequency offset Hz i32 (from 2.25 GHz) | power dBm i16
IQ_BEGIN        9 B   carrier u8 | sample rate Hz u32 | total samples u32
IQ_DATA     7+4n B    carrier u8 | sequence u32 | n u16 | n x (I i16, Q i16)
IQ_END          5 B   carrier u8 | total chunks u32
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .spec import PCM_CODE_VALUE, WAVEFORMS, Carrier, Channel

DEFAULT_CONFIG_PATH = Path(__file__).with_name("default_commands.json")
IQ_CHUNK_SAMPLES = 1024

MODE_VALUE = {"simulation": 0, "radiation": 1}


@dataclass
class Config:
    byte_order: str = "big"
    ack_timeout_s: float = 2.0
    ids: dict = field(default_factory=dict)
    commands: dict = field(default_factory=dict)
    source_path: str = ""

    def command_name(self, command_id: int) -> str | None:
        for name, value in self.commands.items():
            if value == command_id:
                return name
        return None


def _candidate_paths() -> list[Path]:
    paths: list[Path] = []
    env = os.environ.get("MUST_SIM_CONFIG")
    if env:
        paths.append(Path(env))
    if getattr(sys, "frozen", False):  # PyInstaller build: look next to the .exe
        paths.append(Path(sys.executable).parent / "config" / "commands.json")
    paths.append(Path.cwd() / "config" / "commands.json")
    paths.append(Path(__file__).resolve().parents[2] / "config" / "commands.json")  # project root
    paths.append(DEFAULT_CONFIG_PATH)
    return paths


def load_config() -> Config:
    for p in _candidate_paths():
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            raw_cmds = {k: int(v) for k, v in data.get("commands", {}).items()}
            # Normalize CARRIER_CONFIG if an older file used CHANNEL_CONFIG
            if "CHANNEL_CONFIG" in raw_cmds and "CARRIER_CONFIG" not in raw_cmds:
                raw_cmds["CARRIER_CONFIG"] = raw_cmds["CHANNEL_CONFIG"]
            if "CARRIER_CONFIG" in raw_cmds and "CHANNEL_CONFIG" not in raw_cmds:
                raw_cmds["CHANNEL_CONFIG"] = raw_cmds["CARRIER_CONFIG"]

            cfg = Config(
                byte_order=data.get("byte_order", "big"),
                ack_timeout_s=float(data.get("ack_timeout_s", 2.0)),
                ids=dict(data.get("ids", {})),
                commands=raw_cmds,
                source_path=str(p),
            )
            if cfg.byte_order not in ("big", "little"):
                raise ValueError(f"{p}: byte_order must be 'big' or 'little'")
            for need in ("RF_CONTROL", "SET_MODE", "CARRIER_CONFIG", "IQ_DATA", "IQ_BEGIN", "IQ_END"):
                if need not in cfg.commands:
                    raise ValueError(f"{p}: command '{need}' is missing")
            return cfg
    raise FileNotFoundError("No commands.json found")


# ---------------------------------------------------------------- encoders
def _u(v: int, n: int, order: str) -> bytes:
    return int(v).to_bytes(n, order)


def _s(v: int, n: int, order: str) -> bytes:
    return int(v).to_bytes(n, order, signed=True)


def rf_control(on: bool) -> bytes:
    return bytes([1 if on else 0])


def set_mode(mode: str) -> bytes:
    return bytes([MODE_VALUE[mode]])


def carrier_config(c: Carrier, order: str) -> bytes:
    wf = WAVEFORMS[c.waveform]
    return (
        bytes([c.number, 1 if c.enabled else 0, wf["code"]])
        + _u(c.bit_rate_kbps, 2, order)
        + _u(c.subcarrier_khz, 2, order)
        + bytes([PCM_CODE_VALUE[c.pcm_code], 1 if c.conv_coding else 0])
        + _u(c.frame_length, 2, order)
        + _s(c.freq_offset_hz, 4, order)
        + _s(c.power_dbm, 2, order)
    )


channel_config = carrier_config


def iq_begin(carrier: int, sample_rate_hz: int, total_samples: int, order: str) -> bytes:
    return bytes([carrier]) + _u(sample_rate_hz, 4, order) + _u(total_samples, 4, order)


def iq_data(carrier: int, seq: int, i_vals, q_vals, order: str) -> bytes:
    """i_vals / q_vals: sequences of ints already scaled into int16 range."""
    n = len(i_vals)
    out = bytearray(bytes([carrier]) + _u(seq, 4, order) + _u(n, 2, order))
    for a, b in zip(i_vals, q_vals):
        out += _s(a, 2, order) + _s(b, 2, order)
    return bytes(out)


def iq_end(carrier: int, total_chunks: int, order: str) -> bytes:
    return bytes([carrier]) + _u(total_chunks, 4, order)


# ---------------------------------------------------------------- decoders
def decode_carrier(payload: bytes, order: str) -> dict:
    if len(payload) != 17:
        raise ValueError(f"CARRIER_CONFIG should be 17 bytes, got {len(payload)}")
    wf_by_code = {v["code"]: k for k, v in WAVEFORMS.items()}
    return dict(
        number=payload[0],
        enabled=bool(payload[1]),
        waveform=wf_by_code.get(payload[2], f"code {payload[2]}"),
        bit_rate_kbps=int.from_bytes(payload[3:5], order),
        subcarrier_khz=int.from_bytes(payload[5:7], order),
        pcm_code="NRZ-S" if payload[7] == 1 else "NRZ-L",
        conv_coding=bool(payload[8]),
        frame_length=int.from_bytes(payload[9:11], order),
        freq_offset_hz=int.from_bytes(payload[11:15], order, signed=True),
        power_dbm=int.from_bytes(payload[15:17], order, signed=True),
    )


decode_channel = decode_carrier


def describe(name: str | None, payload: bytes, order: str) -> str:
    """One readable line for the packet log."""
    try:
        if name == "RF_CONTROL":
            return "RF " + ("start" if payload[0] else "stop")
        if name == "SET_MODE":
            return "Mode " + ("radiation" if payload[0] else "simulation")
        if name in ("CARRIER_CONFIG", "CHANNEL_CONFIG"):
            c = decode_carrier(payload, order)
            wf = WAVEFORMS.get(c["waveform"], {}).get("label", c["waveform"])
            state = "on" if c["enabled"] else "off"
            extra = f" {c['bit_rate_kbps']} kbps" if c["bit_rate_kbps"] else ""
            extra += f" sc {c['subcarrier_khz']} kHz" if c["subcarrier_khz"] else ""
            return f"Carrier {c['number']} {state} {wf}{extra} {c['power_dbm']:+d} dBm offset {c['freq_offset_hz']:+d} Hz"
        if name == "IQ_BEGIN":
            return f"IQ begin carrier {payload[0]}, {int.from_bytes(payload[1:5], order)} Hz, {int.from_bytes(payload[5:9], order)} samples"
        if name == "IQ_DATA":
            return f"IQ data carrier {payload[0]} chunk {int.from_bytes(payload[1:5], order)} ({int.from_bytes(payload[5:7], order)} samples)"
        if name == "IQ_END":
            return f"IQ end carrier {payload[0]}, {int.from_bytes(payload[1:5], order)} chunks"
    except Exception:  # a malformed payload must never break logging
        return "Malformed data packet"
    return f"{len(payload)} data bytes"
