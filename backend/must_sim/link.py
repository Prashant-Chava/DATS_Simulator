"""Connection to the simulator: TCP client or UDP, ACK tracking, event stream."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from datetime import datetime

from . import commands as cmd
from .frame import KIND_ACK, KIND_DATA, Frame, FrameError, FrameParser, encode


class LinkError(Exception):
    """Something the operator can act on. The message is shown in the UI as is."""


class _UdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, link: "Link") -> None:
        self.link = link

    def datagram_received(self, data: bytes, addr) -> None:
        # one datagram = one frame, so every datagram gets a fresh parser
        self.link._handle_items(FrameParser(self.link.byte_order).feed(data), data)

    def error_received(self, exc: Exception) -> None:
        self.link.log("ERR", f"UDP error: {exc}")

    def connection_lost(self, exc) -> None:
        pass


class Link:
    def __init__(self, config: cmd.Config) -> None:
        self.config = config
        self.byte_order = config.byte_order
        self.ack_timeout = config.ack_timeout_s
        self.ids = dict(config.ids)

        self.connected = False
        self.protocol: str | None = None
        self.host: str | None = None
        self.port: int | None = None
        # None = unknown (after a disconnect while RF was on)
        self.state: dict = {"mode": "simulation", "rf_on": False}

        self._writer: asyncio.StreamWriter | None = None
        self._udp: asyncio.DatagramTransport | None = None
        self._task: asyncio.Task | None = None
        self._parser = FrameParser(self.byte_order)
        self._counter = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._log_id = 0

        self.subscribers: set[asyncio.Queue] = set()
        self.history: deque = deque(maxlen=500)
        self.tx_lock = asyncio.Lock()  # one command sequence at a time

    # ------------------------------------------------------------ events
    def emit(self, type_: str, **data) -> None:
        msg = {"type": type_, **data}
        for q in list(self.subscribers):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    def log(self, direction: str, summary: str, raw: bytes | None = None, fields: dict | None = None) -> None:
        self._log_id += 1
        entry = {
            "id": self._log_id,
            "ts": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "dir": direction,  # TX, RX, SYS, ERR
            "summary": summary,
            "fields": fields or {},
            "hex": _hex(raw),
            "size": len(raw) if raw is not None else 0,
        }
        self.history.append(entry)
        self.emit("log", entry=entry)

    def status(self) -> dict:
        return {
            "connected": self.connected,
            "protocol": self.protocol,
            "host": self.host,
            "port": self.port,
            "ack_timeout_s": self.ack_timeout,
            "byte_order": self.byte_order,
            "ids": self.ids,
            "commands": self.config.commands,
            "config_path": self.config.source_path,
            **self.state,
        }

    def publish_status(self) -> None:
        self.emit("status", status=self.status())

    def set_state(self, **kw) -> None:
        self.state.update(kw)
        self.publish_status()

    # ------------------------------------------------------------ connect
    async def connect(self, protocol: str, host: str, port: int, *, ack_timeout_s=None, byte_order=None, ids=None) -> None:
        if protocol not in ("tcp", "udp"):
            raise LinkError("Protocol must be TCP or UDP.")
        host = (host or "").strip()
        if not host:
            raise LinkError("Enter the IP address of the simulator.")
        if not 1 <= int(port) <= 65535:
            raise LinkError("Port must be between 1 and 65535.")
        if self.connected:
            await self.disconnect()

        if byte_order:
            self.byte_order = byte_order
        if ack_timeout_s is not None:
            self.ack_timeout = max(0.0, float(ack_timeout_s))
        if ids:
            self.ids.update({k: int(v) for k, v in ids.items() if v is not None})
        self._parser = FrameParser(self.byte_order)

        loop = asyncio.get_running_loop()
        try:
            if protocol == "tcp":
                reader, writer = await asyncio.wait_for(asyncio.open_connection(host, int(port)), timeout=4)
                self._writer = writer
                self._task = asyncio.create_task(self._tcp_read_loop(reader))
            else:
                transport, _ = await loop.create_datagram_endpoint(lambda: _UdpProtocol(self), remote_addr=(host, int(port)))
                self._udp = transport
        except asyncio.TimeoutError:
            raise LinkError(f"No answer from {host}:{port} after 4 s. Check the IP address, the cable and that the simulator is on.")
        except OSError as e:
            raise LinkError(f"Could not connect to {host}:{port} ({protocol.upper()}): {e.strerror or e}")

        self.connected, self.protocol, self.host, self.port = True, protocol, host, int(port)
        note = " (UDP has no handshake, so this only means the socket is ready)" if protocol == "udp" else ""
        self.log("SYS", f"Connected to {host}:{port} over {protocol.upper()}{note}")
        self.publish_status()

    async def disconnect(self, reason: str = "Disconnected") -> None:
        if self._task:
            self._task.cancel()
            self._task = None
        self._close_transport()
        self._mark_closed(reason)

    def _close_transport(self) -> None:
        if self._writer:
            try:
                self._writer.close()
            except Exception:
                pass
            self._writer = None
        if self._udp:
            self._udp.close()
            self._udp = None

    def _mark_closed(self, reason: str) -> None:
        was = self.connected
        self.connected = False
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()
        if was:
            # If RF was on we cannot know what the device does now, so say so.
            if self.state.get("rf_on"):
                self.state["rf_on"] = None
                self.log("ERR", "RF state is unknown. Reconnect and send Stop RF to be sure.")
            self.state["mode"] = "simulation"  # nothing is known about the device while disconnected
            self.log("SYS", reason)
        self.publish_status()

    async def _tcp_read_loop(self, reader: asyncio.StreamReader) -> None:
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                self._handle_items(self._parser.feed(data), data)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self._close_transport()
            self._mark_closed(f"Connection lost: {e}")
            return
        self._close_transport()
        self._mark_closed("Connection closed by the simulator")

    # ------------------------------------------------------------ receive
    def _handle_items(self, items, chunk: bytes) -> None:
        for item in items:
            if isinstance(item, FrameError):
                self.log("ERR", item.message, item.raw)
            else:
                self._on_frame(item)

    def _on_frame(self, f: Frame) -> None:
        name = self.config.command_name(f.command_id) or f"0x{f.command_id:02X}"
        kind = "ACK" if f.kind == KIND_ACK else "DATA" if f.kind == KIND_DATA else f"kind 0x{f.kind:02X}"
        fields = {"counter": f.counter, "command": name, "kind": kind, "from": f.src_id, "to": f.dest_id, "length": len(f.payload), "timestamp": f.timestamp}
        summary = f"{kind} #{f.counter} {name}"
        if f.payload:
            summary += f" payload {_hex(f.payload, 12)}"
        raw = encode(f, self.byte_order)
        self.log("RX", summary, raw, fields)
        if f.kind == KIND_ACK:
            fut = self._pending.pop(f.counter, None)
            if fut and not fut.done():
                fut.set_result(f)

    # ------------------------------------------------------------ send
    def _next_counter(self) -> int:
        self._counter = (self._counter + 1) % 256
        return self._counter

    async def send(self, name: str, payload: bytes, *, quiet: bool = False, wait: bool = True) -> str:
        """Send one command. Returns 'ack', 'timeout' or 'not_waited'."""
        if not self.connected:
            raise LinkError("Not connected. Connect to the simulator first.")
        command_id = self.config.commands[name]
        counter = self._next_counter()
        i = self.ids
        frame = Frame(
            command_id=command_id,
            payload=payload,
            counter=counter,
            kind=KIND_DATA,
            dest_id=i.get("destination", 2),
            src_id=i.get("source", 1),
            dest_sub=i.get("destination_subsystem", 0),
            src_sub=i.get("source_subsystem", 0),
            dest_subsub=i.get("destination_subsubsystem", 0),
            src_subsub=i.get("source_subsubsystem", 0),
            timestamp=int(time.time()),
        )
        raw = encode(frame, self.byte_order)

        fut = None
        if wait and self.ack_timeout > 0:
            fut = asyncio.get_running_loop().create_future()
            self._pending[counter] = fut
        try:
            if self._writer:
                self._writer.write(raw)
                await self._writer.drain()
            elif self._udp:
                self._udp.sendto(raw)
        except (ConnectionError, OSError) as e:
            self._pending.pop(counter, None)
            self._close_transport()
            self._mark_closed(f"Connection lost while sending: {e}")
            raise LinkError(f"Send failed: {e}")

        if not quiet:
            fields = {"counter": counter, "command": name, "kind": "DATA", "from": frame.src_id, "to": frame.dest_id, "length": len(payload), "timestamp": frame.timestamp}
            self.log("TX", f"#{counter} {name}: {cmd.describe(name, payload, self.byte_order)}", raw, fields)

        if fut is None:
            return "not_waited"
        try:
            await asyncio.wait_for(fut, timeout=self.ack_timeout)
            return "ack"
        except asyncio.TimeoutError:
            self._pending.pop(counter, None)
            self.log("ERR", f"No ACK for #{counter} {name} after {self.ack_timeout:g} s")
            return "timeout"
        except asyncio.CancelledError:
            if not self.connected:
                raise LinkError("Connection closed while waiting for the ACK.")
            raise


def _hex(data: bytes | None, limit: int = 40) -> str:
    if not data:
        return ""
    s = data[:limit].hex(" ").upper()
    return s + (f" … (+{len(data) - limit} B)" if len(data) > limit else "")
