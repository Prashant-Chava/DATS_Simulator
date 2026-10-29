import { useEffect, useState } from "react";
import { useStore } from "../store";

const KEY = "dats-sim-connection";

function load() {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    /* storage unavailable */
  }
  return {};
}

export function ConnectionPanel() {
  const status = useStore((s) => s.status)!;
  const busy = useStore((s) => s.busy);
  const connect = useStore((s) => s.connect);
  const disconnect = useStore((s) => s.disconnect);

  const saved = load();
  const [protocol, setProtocol] = useState<"tcp" | "udp">(saved.protocol ?? "tcp");
  const [host, setHost] = useState<string>(saved.host ?? "192.168.1.10");
  const [port, setPort] = useState<string>(saved.port ?? "7000");
  const [ack, setAck] = useState<string>(saved.ack ?? String(status.ack_timeout_s ?? 2));
  const [order, setOrder] = useState<"big" | "little">(saved.order ?? status.byte_order ?? "big");
  const [src, setSrc] = useState<string>(saved.src ?? String(status.ids?.source ?? 1));
  const [dst, setDst] = useState<string>(saved.dst ?? String(status.ids?.destination ?? 2));

  // Show what the backend is really connected to (e.g. after a page reload).
  useEffect(() => {
    if (status.connected && status.host && status.port) {
      setProtocol(status.protocol ?? "tcp");
      setHost(status.host);
      setPort(String(status.port));
    }
  }, [status.connected, status.host, status.port, status.protocol]);

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify({ protocol, host, port, ack, order, src, dst }));
    } catch {
      /* ignore */
    }
  }, [protocol, host, port, ack, order, src, dst]);

  const portNum = Number(port);
  const portOk = Number.isInteger(portNum) && portNum >= 1 && portNum <= 65535;
  const hostOk = host.trim().length > 0;
  const connected = status.connected;
  const locked = connected || !!busy;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (connected) return void disconnect();
    if (!portOk || !hostOk) return;
    void connect({
      protocol,
      host: host.trim(),
      port: portNum,
      ack_timeout_s: Math.max(0, Number(ack) || 0),
      byte_order: order,
      ids: { source: Number(src) || 0, destination: Number(dst) || 0 },
    });
  };

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Connection</h2>
      </div>
      <form className="form" onSubmit={submit}>
        <label className="field">
          <span>Protocol</span>
          <select value={protocol} onChange={(e) => setProtocol(e.target.value as "tcp" | "udp")} disabled={locked}>
            <option value="tcp">TCP (client)</option>
            <option value="udp">UDP</option>
          </select>
        </label>
        <label className="field">
          <span>IP address</span>
          <input className="mono" value={host} onChange={(e) => setHost(e.target.value)} disabled={locked} inputMode="decimal" spellCheck={false} aria-invalid={!hostOk} />
        </label>
        <label className="field">
          <span>Port</span>
          <input className="mono" value={port} onChange={(e) => setPort(e.target.value.replace(/\D/g, ""))} disabled={locked} inputMode="numeric" aria-invalid={!portOk} />
        </label>

        <details className="more">
          <summary>Frame settings</summary>
          <div className="form-grid">
            <label className="field">
              <span>ACK wait (s)</span>
              <input className="mono" value={ack} onChange={(e) => setAck(e.target.value)} disabled={locked} inputMode="decimal" />
            </label>
            <label className="field">
              <span>Byte order</span>
              <select value={order} onChange={(e) => setOrder(e.target.value as "big" | "little")} disabled={locked}>
                <option value="big">Big-endian</option>
                <option value="little">Little-endian</option>
              </select>
            </label>
            <label className="field">
              <span>Source ID</span>
              <input className="mono" value={src} onChange={(e) => setSrc(e.target.value.replace(/\D/g, ""))} disabled={locked} />
            </label>
            <label className="field">
              <span>Destination ID</span>
              <input className="mono" value={dst} onChange={(e) => setDst(e.target.value.replace(/\D/g, ""))} disabled={locked} />
            </label>
          </div>
          <p className="hint">Set ACK wait to 0 if the simulator does not send ACK frames.</p>
        </details>

        <button className={`btn ${connected ? "" : "btn-primary"} wide`} type="submit" disabled={!!busy || (!connected && (!portOk || !hostOk))}>
          {busy === "Connecting" ? "Connecting…" : connected ? "Disconnect" : "Connect"}
        </button>
        {protocol === "udp" && !connected && <p className="hint">UDP has no handshake. Connect only opens the socket.</p>}
      </form>
    </section>
  );
}
