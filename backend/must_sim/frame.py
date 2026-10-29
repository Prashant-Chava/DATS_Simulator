"""Frame codec for the DATS/MuST Simulator IDD "Common Message Structure".

Layout (offsets in bytes):

     0  SOP                     4   B1 B1 B1 B1
     4  Destination ID          1
     5  Source ID               1
     6  Destination subsystem   1
     7  Source subsystem        1
     8  Destination sub-subsys  1
     9  Source sub-subsys       1
    10  Message counter         1
    11  Command ID              1
    12  Reserved                1
    13  Data / Ack              1   0xAA = data, 0xBB = ack
    14  Timestamp               8   Unix seconds
    22  Data length             2   N
    24  Data packet             N
  24+N  Checksum                1   XOR of every byte from SOP to the last data byte
  25+N  EOP                     4   E1 E1 E1 E1

Total frame size = 29 + N bytes.

Open points in the IDD (see README): byte order of the 2-byte length and the
8-byte timestamp is not stated, so it is a parameter (default big-endian).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

SOP = bytes([0xB1] * 4)
EOP = bytes([0xE1] * 4)
KIND_DATA = 0xAA
KIND_ACK = 0xBB
HEADER_LEN = 24
TRAILER_LEN = 5  # checksum + EOP
MAX_PAYLOAD = 0xFFFF


def xor_checksum(data: bytes) -> int:
    """XOR of all bytes. SOP and EOP are four equal bytes each, so they XOR to 0
    and including or excluding them does not change the result."""
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
    dest_id: int = 0x02
    src_id: int = 0x01
    dest_sub: int = 0
    src_sub: int = 0
    dest_subsub: int = 0
    src_subsub: int = 0
    reserved: int = 0
    timestamp: int = 0

    @property
    def is_ack(self) -> bool:
        return self.kind == KIND_ACK


def encode(frame: Frame, byte_order: str = "big") -> bytes:
    if len(frame.payload) > MAX_PAYLOAD:
        raise ValueError(f"Data packet is {len(frame.payload)} bytes; the length field allows at most {MAX_PAYLOAD}.")
    ts = frame.timestamp or int(time.time())
    head = SOP + bytes(
        [
            frame.dest_id,
            frame.src_id,
            frame.dest_sub,
            frame.src_sub,
            frame.dest_subsub,
            frame.src_subsub,
            frame.counter & 0xFF,
            frame.command_id,
            frame.reserved,
            frame.kind,
        ]
    )
    head += ts.to_bytes(8, byte_order) + len(frame.payload).to_bytes(2, byte_order)
    body = head + frame.payload
    return body + bytes([xor_checksum(body)]) + EOP


@dataclass
class FrameError:
    message: str
    raw: bytes


class FrameParser:
    """Turns a byte stream (TCP) or single datagrams (UDP) into frames.

    TCP does not keep message boundaries, so one read can hold half a frame or
    two frames. Feed every chunk in; complete, verified frames come out.
    """

    def __init__(self, byte_order: str = "big") -> None:
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
            n = int.from_bytes(self.buf[22:24], self.byte_order)
            total = HEADER_LEN + n + TRAILER_LEN
            if len(self.buf) < total:
                break
            raw = bytes(self.buf[:total])
            if raw[-4:] != EOP:
                out.append(FrameError("End-of-packet marker missing where the length field points", raw[:HEADER_LEN]))
                del self.buf[:1]  # resync on the next SOP
                continue
            expected = xor_checksum(raw[: HEADER_LEN + n])
            got = raw[HEADER_LEN + n]
            del self.buf[:total]
            if expected != got:
                out.append(FrameError(f"Checksum mismatch: frame has 0x{got:02X}, calculated 0x{expected:02X}", raw))
                continue
            out.append(
                Frame(
                    dest_id=raw[4],
                    src_id=raw[5],
                    dest_sub=raw[6],
                    src_sub=raw[7],
                    dest_subsub=raw[8],
                    src_subsub=raw[9],
                    counter=raw[10],
                    command_id=raw[11],
                    reserved=raw[12],
                    kind=raw[13],
                    timestamp=int.from_bytes(raw[14:22], self.byte_order),
                    payload=raw[HEADER_LEN : HEADER_LEN + n],
                )
            )
        return out
