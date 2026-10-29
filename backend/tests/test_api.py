"""End to end: the real FastAPI app talking to the mock device over real sockets."""
import asyncio
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pytest
from fastapi.testclient import TestClient

import mock_device
from must_sim.app import create_app


class MockServer:
    """Runs the mock device (TCP + UDP) on a free port in a background thread."""

    def __init__(self, no_ack=False):
        mock_device.ARGS.no_ack = no_ack
        mock_device.ARGS.byte_order = "big"
        mock_device.EVENTS.clear()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        async def main():
            srv = await asyncio.start_server(mock_device.handle_tcp, "127.0.0.1", 0)
            self.port = srv.sockets[0].getsockname()[1]
            loop = asyncio.get_running_loop()
            await loop.create_datagram_endpoint(mock_device.UdpServer, local_addr=("127.0.0.1", self.port))
            self.stop = asyncio.Event()
            self.loop = loop
            self.ready.set()
            await self.stop.wait()
            srv.close()

        asyncio.run(main())

    def __enter__(self):
        self.thread.start()
        assert self.ready.wait(5)
        return self

    def __exit__(self, *a):
        self.loop.call_soon_threadsafe(self.stop.set)
        self.thread.join(2)


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


def connect(client, port, protocol="tcp", ack=1.0):
    r = client.post("/api/connect", json={"protocol": protocol, "host": "127.0.0.1", "port": port, "ack_timeout_s": ack})
    assert r.status_code == 200, r.text
    return r.json()


def test_spec_endpoint(client):
    s = client.get("/api/spec").json()
    assert s["max_active"] == 12 and s["num_carriers"] == 12
    assert s["bit_rates_kbps"][-1] == 2048 and s["power_dbm"] == [-150, 20]
    assert s["offset_hz"] == [-50_000_000, 50_000_000]
    assert len(s["default_carriers"]) == 12


def test_commands_need_a_connection(client):
    r = client.post("/api/rf", json={"on": True})
    assert r.status_code == 409 and "Connect" in r.json()["detail"]["message"]

    r = client.post("/api/send", json={"mode": "simulation", "carriers": []})
    assert r.status_code == 409 and "Connect" in r.json()["detail"]["message"]


def test_connect_failure_message(client):
    r = client.post("/api/connect", json={"protocol": "tcp", "host": "127.0.0.1", "port": 1})
    assert r.status_code == 409 and "Could not connect" in r.json()["detail"]["message"]


def test_nothing_is_sent_while_editing(client):
    """Connecting and changing local settings sends no frames until Send is pressed."""
    with MockServer() as m:
        st = connect(client, m.port)
        assert st["connected"]
        time.sleep(0.05)
        # No command frames were sent over the wire on connect!
        assert len(mock_device.EVENTS) == 0
        client.post("/api/disconnect")


def test_send_order_and_all_twelve_carriers(client):
    """Send transmits in exact order: SET_MODE, CARRIER_CONFIG 1..12."""
    with MockServer() as m:
        st = connect(client, m.port)
        assert st["connected"] and st["protocol"] == "tcp"

        spec_data = client.get("/api/spec").json()
        carriers = spec_data["default_carriers"]
        # Enable all 12 carriers to verify all 12 can be active at once
        for c in carriers:
            c["enabled"] = True

        r = client.post("/api/send", json={"mode": "simulation", "carriers": carriers})
        assert r.status_code == 200, r.text
        res = r.json()
        assert res["ok"] is True
        assert len(res["sent"]) == 13  # SET_MODE + 12 CARRIER_CONFIG
        assert res["sent"][0] == "Mode simulation"
        assert res["sent"][1] == "Carrier 1"
        assert res["sent"][-1] == "Carrier 12"

        # Check mock device received events in the exact required order
        evs = mock_device.EVENTS
        assert len(evs) == 13
        assert "Mode simulation" in evs[0]
        assert "Carrier 1" in evs[1]
        assert "Carrier 12" in evs[12]
        assert "12 carriers on" in evs[12]

        # Verify status reflected the changes
        st = client.get("/api/status").json()
        assert st["mode"] == "simulation"

        # Now start RF
        assert client.post("/api/rf", json={"on": True}).json()["rf_on"] is True
        # Mode cannot change while RF is on
        r = client.post("/api/send", json={"mode": "radiation", "carriers": carriers})
        assert r.status_code == 409 and "Stop RF" in r.json()["detail"]["message"]

        # Stop RF
        assert client.post("/api/rf", json={"on": False}).json()["rf_on"] is False

        # Switch to radiation mode
        r = client.post("/api/send", json={"mode": "radiation", "carriers": carriers})
        assert r.status_code == 200
        assert client.get("/api/status").json()["mode"] == "radiation"

        client.post("/api/disconnect")
        assert client.get("/api/status").json()["connected"] is False


def test_stop_on_missing_ack(client):
    """Stops at first missing ACK and reports exactly what was and was not sent."""
    with MockServer(no_ack=True) as m:
        connect(client, m.port, ack=0.2)
        spec_data = client.get("/api/spec").json()
        carriers = spec_data["default_carriers"]

        r = client.post("/api/send", json={"mode": "simulation", "carriers": carriers})
        assert r.status_code == 200
        res = r.json()
        assert res["ok"] is False
        assert res["failed"] == "Mode simulation"
        assert "Stopped at Mode simulation: no ACK" in res["message"]
        assert "Not sent: Carrier 1" in res["message"]
        assert res["sent"] == []

        client.post("/api/disconnect")


def test_invalid_carriers_are_rejected_with_readable_errors(client):
    spec_data = client.get("/api/spec").json()
    carriers = spec_data["default_carriers"]
    carriers[0]["bit_rate_kbps"] = 100
    carriers[1]["freq_offset_hz"] = 50_000_001
    carriers[2]["power_dbm"] = 25

    with MockServer() as m:
        connect(client, m.port)
        r = client.post("/api/send", json={"mode": "simulation", "carriers": carriers})
        assert r.status_code == 422
        errs = r.json()["detail"]["errors"]
        assert any("bit rate 100" in e for e in errs)
        assert any("frequency offset must be between" in e for e in errs)
        assert any("output power must be" in e for e in errs)
        client.post("/api/disconnect")


def test_udp(client):
    with MockServer() as m:
        connect(client, m.port, protocol="udp")
        spec_data = client.get("/api/spec").json()
        r = client.post("/api/send", json={"mode": "simulation", "carriers": spec_data["default_carriers"]})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        client.post("/api/disconnect")


def test_disconnect_while_rf_on_marks_state_unknown(client):
    with MockServer() as m:
        connect(client, m.port)
        client.post("/api/rf", json={"on": True})
        client.post("/api/disconnect")
        st = client.get("/api/status").json()
        assert st["rf_on"] is None


def test_waveform_upload_plot_data_and_send(client):
    n, fs = 5000, 1e6
    t = np.arange(n) / fs
    rows = "time,I,Q\n" + "\n".join(f"{a},{np.cos(2*np.pi*50e3*a)},{np.sin(2*np.pi*50e3*a)}" for a in t)
    r = client.post("/api/waveform", files={"file": ("tone.csv", rows.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["n_samples"] == n and a["sample_rate"] == pytest.approx(fs, rel=1e-6) and a["sample_rate_source"] == "file"
    assert a["has_q"] and len(a["constellation"]["i"]) > 100 and a["spectrum"]["complex"]
    f, db = np.array(a["spectrum"]["freq"]), np.array(a["spectrum"]["db"])
    assert f[np.argmax(db)] == pytest.approx(50e3, abs=1e3)

    # change sample rate
    b = client.patch("/api/waveform", json={"sample_rate": 2e6}).json()
    assert b["sample_rate_source"] == "user" and b["duration_s"] == pytest.approx(n / 2e6)

    with MockServer() as m:
        connect(client, m.port)
        # Send waveform to carrier 4
        r = client.post("/api/waveform/send", json={"carrier": 4})
        assert r.status_code == 200, r.text
        assert r.json()["chunks"] == 5 and r.json()["samples"] == n
        assert any("received 5000 samples in 5 chunks (expected 5000)" in e for e in mock_device.EVENTS)

        # Radiation mode blocks sending waveform CSV
        spec_data = client.get("/api/spec").json()
        client.post("/api/send", json={"mode": "radiation", "carriers": spec_data["default_carriers"]})
        r = client.post("/api/waveform/send", json={"carrier": 4})
        assert r.status_code == 409 and "Simulation" in r.json()["detail"]["message"]
        client.post("/api/disconnect")
