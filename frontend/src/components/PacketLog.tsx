import { useEffect, useMemo, useRef, useState } from "react";
import { useStore } from "../store";

type Filter = "all" | "TX" | "RX" | "ERR";

export function PacketLog() {
  const log = useStore((s) => s.log);
  const clear = useStore((s) => s.clearLog);
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<number | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  const rows = useMemo(() => log.filter((e) => (filter === "all" ? true : filter === "ERR" ? e.dir === "ERR" : e.dir === filter)), [log, filter]);
  const counts = useMemo(() => ({ TX: log.filter((e) => e.dir === "TX").length, RX: log.filter((e) => e.dir === "RX").length, ERR: log.filter((e) => e.dir === "ERR").length }), [log]);

  useEffect(() => {
    const el = box.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [rows]);

  const save = () => {
    const text = log.map((e) => `${e.ts}\t${e.dir}\t${e.summary}\t${e.hex}`).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    a.download = `dats-simulator-log-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Packet log</h2>
        <div className="chips" role="group" aria-label="Filter log">
          {([["all", `All ${log.length}`], ["TX", `Sent ${counts.TX}`], ["RX", `Received ${counts.RX}`], ["ERR", `Errors ${counts.ERR}`]] as [Filter, string][]).map(([k, label]) => (
            <button key={k} className={`chip ${filter === k ? "on" : ""}`} onClick={() => setFilter(k)} aria-pressed={filter === k}>{label}</button>
          ))}
        </div>
        <div className="head-actions">
          <button className="btn small ghost" onClick={save} disabled={log.length === 0}>Save log</button>
          <button className="btn small ghost" onClick={clear} disabled={log.length === 0}>Clear</button>
        </div>
      </div>
      <div className="log" ref={box} onScroll={(e) => { const el = e.currentTarget; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24; }}>
        {rows.length === 0 && <p className="log-empty">{log.length === 0 ? "Nothing yet. Sent and received frames appear here." : "No entries match this filter."}</p>}
        {rows.map((e) => (
          <div key={e.id} className={`row dir-${e.dir}`}>
            <button className="row-main" onClick={() => setOpen(open === e.id ? null : e.id)} aria-expanded={open === e.id} disabled={!e.hex}>
              <span className="ts mono">{e.ts}</span>
              <span className={`dir mono dir-${e.dir}`}>{e.dir === "TX" ? "TX ▸" : e.dir === "RX" ? "◂ RX" : e.dir === "ERR" ? "ERR !" : "SYS"}</span>
              <span className="sum">{e.summary}</span>
            </button>
            {open === e.id && e.hex && (
              <div className="detail">
                <div className="fields mono">{Object.entries(e.fields).map(([k, v]) => <span key={k}>{k} <b>{String(v)}</b></span>)}</div>
                <code className="mono">{e.hex}</code>
                <span className="muted mono">{e.size} bytes</span>
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
