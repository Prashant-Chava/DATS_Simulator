"""Frame codec for the DATS/MuST Simulator IDD "Common Message Structure".

Layout (offsets in bytes):

     0  SOP                     4   B1 B1 B1 B1
     4  Source ID               1   Host endpoint ID (default 1)
     5  Destination ID          1   FPGA endpoint ID (default 2)
     6  Source subsystem        1   default 0
     7  Destination subsystem   1   default 0
     8  Source sub-subsys       1   default 0
     9  Destination sub-subsys  1   default 0
    10  Command ID              1   0x31 = DDC pulse data, etc.
    11  Message counter         1   Increment each pulse, modulo 256
    12  Data / Ack              1   0x00 = Data, 0x01 = Ack
    13  Reserved                1   0x00
    14  Timestamp               8   UTC Unix nanoseconds (uint64 LE)
    22  Data length             4   uint32 LE (14 + n * 8 for DDC pulse data)
    26  Data packet             N   Pulse ID ... Samples Per Block + I/Q
  26+N  EOP                     4   E1 E1 E1 E1

Total frame size = 30 + N bytes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

SOP = bytes([0xB1] * 4)
EOP = bytes([0xE1] * 4)
KIND_DATA = 0x00
KIND_ACK = 0x01
HEADER_LEN = 26
TRAILER_LEN = 4  # EOP only (no checksum)
MAX_PAYLOAD = 0xFFFFFFFF


def xor_checksum(data: bytes) -> int:
    """XOR of all bytes (kept for backward compatibility)."""
    value = 0
    for b in data:
        value ^= b
    return value


@dataclass
class Frame:
    command_id: int
    payload: bytes = b""
    counter: int = 0
    kind: int = KIND_DATA
    src_id: int = 0x01
    dest_id: int = 0x02
    src_sub: int = 0
    dest_sub: int = 0
    src_subsub: int = 0
    dest_subsub: int = 0
    reserved: int = 0
    timestamp: int = 0

    @property
    def is_ack(self) -> bool:
        return self.kind == KIND_ACK


def encode(frame: Frame, byte_order: str = "little") -> bytes:
    if len(frame.payload) > MAX_PAYLOAD:
        raise ValueError(f"Data packet is {len(frame.payload)} bytes; the length field allows at most {MAX_PAYLOAD}.")
    ts = frame.timestamp if (frame.timestamp is not None and frame.timestamp != 0) else time.time_ns()
    head = SOP + bytes(
        [
            frame.src_id,
            frame.dest_id,
            frame.src_sub,
            frame.dest_sub,
            frame.src_subsub,
            frame.dest_subsub,
            frame.command_id,
            frame.counter & 0xFF,
            frame.kind,
            frame.reserved,
        ]
    )
    head += ts.to_bytes(8, byte_order) + len(frame.payload).to_bytes(4, byte_order)
    return head + frame.payload + EOP


@dataclass
class FrameError:
    message: str
    raw: bytes


class FrameParser:
    """Turns a byte stream (TCP) or single datagrams (UDP) into frames.

    TCP does not keep message boundaries, so one read can hold half a frame or
    two frames. Feed every chunk in; complete, verified frames come out.
    """

    def __init__(self, byte_order: str = "little") -> None:
        self.byte_order = byte_order
        self.buf = bytearray()

    def feed(self, data: bytes) -> list[Frame | FrameError]:
        self.buf += data
        out: list[Frame | FrameError] = []
        while True:
            i = self.buf.find(SOP)
            if i < 0:
                if len(self.buf) > 3:  # keep a possible partial SOP
                    junk = bytes(self.buf[:-3])
                    out.append(FrameError(f"Ignored {len(junk)} bytes that are not part of a frame", junk))
                    del self.buf[:-3]
                break
            if i > 0:
                junk = bytes(self.buf[:i])
                out.append(FrameError(f"Ignored {i} bytes before the start-of-packet marker", junk))
                del self.buf[:i]
            if len(self.buf) < HEADER_LEN:
                break
            n = int.from_bytes(self.buf[22:26], self.byte_order)
            total = HEADER_LEN + n + TRAILER_LEN
            if len(self.buf) < total:
                break
            raw = bytes(self.buf[:total])
            if raw[-4:] != EOP:
                out.append(FrameError("End-of-packet marker missing where the length field points", raw[:HEADER_LEN]))
                del self.buf[:1]  # resync on the next SOP
                continue
            del self.buf[:total]
            out.append(
                Frame(
                    src_id=raw[4],
                    dest_id=raw[5],
                    src_sub=raw[6],
                    dest_sub=raw[7],
                    src_subsub=raw[8],
                    dest_subsub=raw[9],
                    command_id=raw[10],
                    counter=raw[11],
                    kind=raw[12],
                    reserved=raw[13],
                    timestamp=int.from_bytes(raw[14:22], self.byte_order),
                    payload=raw[HEADER_LEN : HEADER_LEN + n],
                )
            )
        return out
