#!/usr/bin/env python3
"""Fake MuST simulator for testing the GUI without hardware.

Listens on TCP and/or UDP, checks every frame, prints what it understood and
answers with an ACK frame (same counter and command ID, IDs swapped).
The ACK data packet is one status byte, 0x00 = OK (a proposal; adjust to the IDD).

    python mock_device.py --port 7000
    python mock_device.py --port 7000 --protocol udp
    python mock_device.py --no-ack            # test the GUI's timeout handling
    python mock_device.py --byte-order little
"""

from __future__ import annotations

import argparse
import asyncio
import time

from must_sim import commands as cmd
from must_sim.frame import KIND_ACK, KIND_DATA, Frame, FrameError, FrameParser, encode

cfg = cmd.load_config()
ARGS = argparse.Namespace(host="127.0.0.1", port=7000, protocol="both", byte_order=cfg.byte_order, no_ack=False, delay=0)
EVENTS: list[str] = []  # what the device understood (used by the tests)


def ack_for(f: Frame) -> bytes:
    return encode(
        Frame(
            command_id=f.command_id,
            payload=b"\x00",
            counter=f.counter,
            kind=KIND_ACK,
            src_id=f.dest_id,
            dest_id=f.src_id,
            src_sub=f.dest_sub,
            dest_sub=f.src_sub,
            src_subsub=f.dest_subsub,
            dest_subsub=f.src_subsub,
            timestamp=time.time_ns(),
        ),
        ARGS.byte_order,
    )


class Device:
    """Tiny state model so the console shows what a real unit would be doing."""

    def __init__(self) -> None:
        self.carriers: dict[int, dict] = {}
        self.iq: dict[int, dict] = {}

    def handle(self, f: Frame) -> str:
        name = cfg.command_name(f.command_id) or f"0x{f.command_id:02X}"
        order = ARGS.byte_order
        if name in ("CARRIER_CONFIG", "CHANNEL_CONFIG"):
            c = cmd.decode_carrier(f.payload, order)
            self.carriers[c["number"]] = c
            active = sum(1 for x in self.carriers.values() if x["enabled"])
            return f"{cmd.describe('CARRIER_CONFIG', f.payload, order)}   [{active} carriers on]"
        if name == "IQ_BEGIN":
            ch = f.payload[0]
            self.iq[ch] = {"samples": 0, "chunks": 0, "expect": int.from_bytes(f.payload[5:9], order)}
        elif name == "IQ_DATA":
            ch = f.payload[0]
            st = self.iq.setdefault(ch, {"samples": 0, "chunks": 0, "expect": 0})
            st["samples"] += int.from_bytes(f.payload[5:7], order)
            st["chunks"] += 1
            return f"IQ chunk {st['chunks']} for carrier {ch} ({st['samples']}/{st['expect']} samples)" if st["chunks"] % 20 == 1 else ""
        elif name == "IQ_END":
            ch = f.payload[0]
            st = self.iq.get(ch, {})
            return f"IQ end carrier {ch}: received {st.get('samples')} samples in {st.get('chunks')} chunks (expected {st.get('expect')})"
        elif name in ("DDC_PULSE_DATA", "DDC_DATA") or f.command_id == 0x31:
            d = cmd.decode_ddc_pulse_data(f.payload, order)
            return f"DDC Pulse #{d['pulse_id']} Ch {d['channel_id']} Freq {d['frequency_id']} ({d['num_samples']} samples)"
        return cmd.describe(name, f.payload, order)


def report(prefix: str, f: Frame, text: str) -> None:
    if text:
        EVENTS.append(text)
        print(f"{time.strftime('%H:%M:%S')} {prefix} #{f.counter:<3} {text}", flush=True)


async def handle_tcp(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    peer = writer.get_extra_info("peername")
    print(f"TCP client connected: {peer}", flush=True)
    parser, dev = FrameParser(ARGS.byte_order), Device()
    try:
        while data := await reader.read(65536):
            for item in parser.feed(data):
                if isinstance(item, FrameError):
                    print(f"  bad frame: {item.message}", flush=True)
                    continue
                if item.kind != KIND_DATA:
                    continue
                report("RX", item, dev.handle(item))
                if not ARGS.no_ack:
                    if ARGS.delay:
                        await asyncio.sleep(ARGS.delay / 1000)
                    writer.write(ack_for(item))
                    await writer.drain()
    except ConnectionError:
        pass
    print(f"TCP client left: {peer}", flush=True)
    writer.close()


class UdpServer(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.dev = Device()

    def connection_made(self, transport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:
        for item in FrameParser(ARGS.byte_order).feed(data):
            if isinstance(item, FrameError):
                print(f"  bad frame: {item.message}", flush=True)
            elif item.kind == KIND_DATA:
                report("RX", item, self.dev.handle(item))
                if not ARGS.no_ack:
                    self.transport.sendto(ack_for(item), addr)


async def main() -> None:
    srv = []
    if ARGS.protocol in ("tcp", "both"):
        srv.append(await asyncio.start_server(handle_tcp, ARGS.host, ARGS.port))
        print(f"Mock MuST simulator listening on TCP {ARGS.host}:{ARGS.port}", flush=True)
    if ARGS.protocol in ("udp", "both"):
        loop = asyncio.get_running_loop()
        await loop.create_datagram_endpoint(UdpServer, local_addr=(ARGS.host, ARGS.port))
        print(f"Mock MuST simulator listening on UDP {ARGS.host}:{ARGS.port}", flush=True)
    print(f"Command table: {cfg.source_path}   byte order: {ARGS.byte_order}   ACKs: {'off' if ARGS.no_ack else 'on'}", flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=7000)
    p.add_argument("--protocol", choices=["tcp", "udp", "both"], default="both")
    p.add_argument("--byte-order", choices=["big", "little"], default=cfg.byte_order)
    p.add_argument("--no-ack", action="store_true", help="never answer (to test timeouts)")
    p.add_argument("--delay", type=int, default=0, help="ACK delay in ms")
    ARGS = p.parse_args()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
