"""FastAPI app: REST for commands, a WebSocket for live events, and the built UI."""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from . import commands as cmd
from . import spec, waveform
from .link import Link, LinkError


def _dist_dir() -> Path | None:
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(getattr(sys, "_MEIPASS", ".")) / "web")
    candidates.append(Path(__file__).resolve().parents[2] / "frontend" / "dist")
    for c in candidates:
        if (c / "index.html").is_file():
            return c
    return None


class ConnectReq(BaseModel):
    protocol: Literal["tcp", "udp"] = "tcp"
    host: str
    port: int
    ack_timeout_s: float | None = Field(default=None, ge=0, le=60)
    byte_order: Literal["big", "little"] | None = None
    ids: dict[str, int] | None = None


class ModeReq(BaseModel):
    mode: Literal["simulation", "radiation"]


class RfReq(BaseModel):
    on: bool


class CarriersReq(BaseModel):
    carriers: list[dict] | None = None
    channels: list[dict] | None = None

    def get_carriers(self) -> list[dict]:
        return self.carriers if self.carriers is not None else (self.channels or [])


ChannelsReq = CarriersReq


class SendConfigReq(BaseModel):
    mode: Literal["simulation", "radiation"]
    carriers: list[dict] | None = None
    channels: list[dict] | None = None

    def get_carriers(self) -> list[dict]:
        return self.carriers if self.carriers is not None else (self.channels or [])


class SampleRateReq(BaseModel):
    sample_rate: float | None = Field(default=None, gt=0)


class SendWaveformReq(BaseModel):
    carrier: int | None = Field(default=None, ge=1, le=spec.NUM_CARRIERS)
    channel: int | None = Field(default=None, ge=1, le=spec.NUM_CARRIERS)

    def get_carrier(self) -> int:
        if self.carrier is not None:
            return self.carrier
        if self.channel is not None:
            return self.channel
        return 1


async def send_configuration(
    lk: Link,
    mode: str,
    carriers_raw: list[dict],
) -> dict:
    """Send entire configuration: SET_MODE, then CARRIER_CONFIG 1..12."""
    if not lk.connected:
        raise LinkError("Connect to the simulator first.")

    carriers, errors = spec.validate_set(carriers_raw)
    if errors:
        raise HTTPException(status_code=422, detail={"message": "Some carrier settings are not allowed.", "errors": errors})

    carriers.sort(key=lambda c: c.number)

    async with lk.tx_lock:
        if lk.state["rf_on"] is not False and mode != lk.state["mode"]:
            raise HTTPException(status_code=409, detail={"message": "Stop RF before changing the mode.", "errors": []})

        plan: list[tuple[str, str, bytes, tuple[str, Any]]] = [
            ("SET_MODE", f"Mode {mode}", cmd.set_mode(mode), ("mode", mode)),
        ]
        for c in carriers:
            plan.append((
                "CARRIER_CONFIG",
                f"Carrier {c.number}",
                cmd.carrier_config(c, lk.byte_order),
                ("carrier", c),
            ))

        total_steps = len(plan)
        sent: list[str] = []
        applied_carriers: list[dict] = []
        failed: str | None = None
        not_sent: list[str] = []

        for idx, (cmd_name, label, payload, (tag, val)) in enumerate(plan):
            lk.emit("progress", job="send", done=idx, total=total_steps, current=label)
            ack = await lk.send(cmd_name, payload)
            if ack == "timeout":
                failed = label
                not_sent = [item[1] for item in plan[idx + 1 :]]
                break

            sent.append(label)
            if tag == "mode":
                lk.set_state(mode=val)
            elif tag == "carrier":
                applied_carriers.append(val.as_dict())

        lk.emit("progress", job="send", done=len(sent), total=total_steps, finished=True)

        if failed:
            sent_str = ", ".join(sent) if sent else "none"
            not_sent_str = ", ".join(not_sent) if not_sent else "none"
            msg = f"Stopped at {failed}: no ACK from the simulator. Sent: {sent_str}. Not sent: {not_sent_str}."
            return {
                "ok": False,
                "message": msg,
                "sent": sent,
                "failed": failed,
                "not_sent": not_sent,
                "applied_carriers": applied_carriers,
            }

        return {
            "ok": True,
            "message": "Configuration successfully sent and acknowledged by simulator.",
            "sent": sent,
            "failed": None,
            "not_sent": [],
            "applied_carriers": [c.as_dict() for c in carriers],
        }


def create_app() -> FastAPI:
    link_holder: dict = {}
    wf_holder: dict = {"parsed": None, "analysis": None, "rate": None}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        link_holder["link"] = Link(cmd.load_config())
        yield
        await link_holder["link"].disconnect()

    app = FastAPI(title="DATS Simulator", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def link() -> Link:
        return link_holder["link"]

    @app.exception_handler(LinkError)
    async def _link_error(_, exc: LinkError):
        return JSONResponse(status_code=409, content={"detail": {"message": str(exc), "errors": []}})

    @app.exception_handler(waveform.WaveformError)
    async def _wf_error(_, exc: waveform.WaveformError):
        return JSONResponse(status_code=422, content={"detail": {"message": str(exc), "errors": []}})

    @app.exception_handler(RequestValidationError)
    async def _validation(_, exc: RequestValidationError):
        errs = [f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}" for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": {"message": "The request has invalid values.", "errors": errs}})

    def bad(message: str, errors: list[str] | None = None, code: int = 422):
        raise HTTPException(status_code=code, detail={"message": message, "errors": errors or []})

    # ------------------------------------------------------------ info
    @app.get("/api/spec")
    async def get_spec():
        return spec.spec_dict()

    @app.get("/api/status")
    async def get_status():
        return {"version": __version__, **link().status()}

    @app.post("/api/config/reload")
    async def reload_config():
        lk = link()
        if lk.connected:
            bad("Disconnect first, then reload the command table.", code=409)
        cfg = cmd.load_config()
        lk.config, lk.byte_order, lk.ack_timeout, lk.ids = cfg, cfg.byte_order, cfg.ack_timeout_s, dict(cfg.ids)
        lk.log("SYS", f"Command table reloaded from {cfg.source_path}")
        lk.publish_status()
        return lk.status()

    # ------------------------------------------------------------ connection
    @app.post("/api/connect")
    async def connect(req: ConnectReq):
        await link().connect(req.protocol, req.host, req.port, ack_timeout_s=req.ack_timeout_s, byte_order=req.byte_order, ids=req.ids)
        return link().status()

    @app.post("/api/disconnect")
    async def disconnect():
        await link().disconnect()
        return link().status()

    # ------------------------------------------------------------ Send & single commands
    @app.post("/api/send")
    async def send_endpoint(req: SendConfigReq):
        return await send_configuration(link(), req.mode, req.get_carriers())

    @app.post("/api/mode")
    async def set_mode(req: ModeReq):
        lk = link()
        async with lk.tx_lock:
            if lk.state["rf_on"] is not False and req.mode != lk.state["mode"]:
                bad("Stop RF before changing the mode.", code=409)
            ack = await lk.send("SET_MODE", cmd.set_mode(req.mode))
            if ack != "timeout":
                lk.set_state(mode=req.mode)
        return {"ack": ack, **lk.status()}

    @app.post("/api/rf")
    async def set_rf(req: RfReq):
        lk = link()
        async with lk.tx_lock:
            ack = await lk.send("RF_CONTROL", cmd.rf_control(req.on))
            if ack != "timeout":
                lk.set_state(rf_on=req.on)
        return {"ack": ack, **lk.status()}

    @app.post("/api/carriers/apply")
    @app.post("/api/channels/apply")
    async def apply_carriers(req: CarriersReq):
        lk = link()
        carriers, errors = spec.validate_set(req.get_carriers())
        if errors:
            bad("Some carrier settings are not allowed.", errors)
        results = []
        async with lk.tx_lock:
            for c in carriers:
                ack = await lk.send("CARRIER_CONFIG", cmd.carrier_config(c, lk.byte_order))
                results.append({"carrier": c.number, "channel": c.number, "ack": ack})
                if ack == "timeout":
                    break
        failed = [r["carrier"] for r in results if r["ack"] == "timeout"]
        return {"ok": not failed, "results": results, "applied": [c.as_dict() for c in carriers], "failed": failed}

    # ------------------------------------------------------------ waveform (simulation mode)
    @app.get("/api/waveform")
    async def get_waveform():
        return wf_holder["analysis"]

    @app.post("/api/waveform")
    async def upload_waveform(file: UploadFile = File(...), sample_rate: float | None = Form(default=None)):
        raw = await file.read()
        parsed = await asyncio.to_thread(waveform.parse_csv, raw, file.filename or "waveform.csv")
        analysis = await asyncio.to_thread(waveform.analyze, parsed, sample_rate)
        wf_holder.update(parsed=parsed, analysis=analysis, rate=sample_rate)
        return analysis

    @app.patch("/api/waveform")
    async def update_waveform(req: SampleRateReq):
        if wf_holder["parsed"] is None:
            bad("Upload a CSV file first.", code=409)
        analysis = await asyncio.to_thread(waveform.analyze, wf_holder["parsed"], req.sample_rate)
        wf_holder.update(analysis=analysis, rate=req.sample_rate)
        return analysis

    @app.delete("/api/waveform")
    async def clear_waveform():
        wf_holder.update(parsed=None, analysis=None, rate=None)
        return {"ok": True}

    @app.post("/api/waveform/send")
    async def send_waveform(req: SendWaveformReq):
        lk = link()
        target_carrier = req.get_carrier()
        parsed = wf_holder["parsed"]
        analysis = wf_holder["analysis"]
        if parsed is None:
            bad("Upload a CSV file first.", code=409)
        if lk.state["mode"] != "simulation":
            bad("Waveform files can only be sent in Simulation mode.", code=409)
        if not analysis["sample_rate"]:
            bad("Enter the sample rate before sending.", code=409)
        ii, qq, full = waveform.to_int16(parsed)
        n = len(ii)
        chunk = cmd.IQ_CHUNK_SAMPLES
        total_chunks = (n + chunk - 1) // chunk
        order = lk.byte_order
        async with lk.tx_lock:
            ack = await lk.send("IQ_BEGIN", cmd.iq_begin(target_carrier, int(round(analysis["sample_rate"])), n, order))
            if ack == "timeout":
                bad("The simulator did not acknowledge the start of the waveform.", code=409)
            lk.emit("progress", job="waveform", done=0, total=total_chunks)
            for k in range(total_chunks):
                a, b = k * chunk, min(n, (k + 1) * chunk)
                ack = await lk.send("IQ_DATA", cmd.iq_data(target_carrier, k, ii[a:b].tolist(), qq[a:b].tolist(), order), quiet=True)
                if ack == "timeout":
                    bad(f"Stopped at chunk {k + 1} of {total_chunks}: no ACK from the simulator.", code=409)
                if k % 8 == 0 or k == total_chunks - 1:
                    lk.emit("progress", job="waveform", done=k + 1, total=total_chunks)
            ack = await lk.send("IQ_END", cmd.iq_end(target_carrier, total_chunks, order))
        lk.log("SYS", f"Waveform '{parsed.name}' sent to carrier {target_carrier}: {n} samples in {total_chunks} chunks (scaled so peak {full:g} = 32767)")
        return {"ok": ack != "timeout", "samples": n, "chunks": total_chunks, "full_scale": full}

    # ------------------------------------------------------------ live events
    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        await sock.accept()
        lk = link()
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        lk.subscribers.add(q)
        try:
            await sock.send_json({"type": "hello", "status": lk.status(), "history": list(lk.history)})
            while True:
                await sock.send_json(await q.get())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            lk.subscribers.discard(q)

    dist = _dist_dir()
    if dist:
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
    else:

        @app.get("/")
        async def no_ui():
            return JSONResponse({"message": "UI not built. Run 'npm run build' in frontend/ (or use the Vite dev server)."})

    return app


app = create_app()
