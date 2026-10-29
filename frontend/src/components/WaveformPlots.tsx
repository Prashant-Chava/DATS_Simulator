import { useMemo, useState } from "react";
import { useStore } from "../store";
import { SERIES_I, SERIES_Q } from "../lib/theme";
import { fmtNum, fmtRate, scaleFor } from "../lib/format";
import { Plot } from "./Plot";
import { Constellation } from "./Constellation";

export function WaveformPlots() {
  const a = useStore((s) => s.analysis);
  const [view, setView] = useState<"start" | "whole">("start");

  const time = useMemo(() => {
    if (!a) return null;
    const src = a.time.decimated && view === "start" ? a.time.head : a.time;
    const maxX = src.x.length ? Math.max(Math.abs(src.x[0]), Math.abs(src.x[src.x.length - 1])) : 1;
    const sc = a.x_is_time ? scaleFor(maxX, "s") : { div: 1, unit: "samples" };
    const xs = src.x.map((v) => v / sc.div);
    const data: (number[] | null[])[] = [xs, src.i];
    if (src.q) data.push(src.q);
    return { unit: sc.unit, data: data as any };
  }, [a, view]);

  const spec = useMemo(() => {
    if (!a?.spectrum) return null;
    const maxF = Math.max(...a.spectrum.freq.map(Math.abs), 1e-12);
    const sc = a.sample_rate ? scaleFor(maxF, "Hz") : { div: 1, unit: "cycles/sample" };
    return { unit: sc.unit, data: [a.spectrum.freq.map((f) => f / sc.div), a.spectrum.db] as any };
  }, [a]);

  if (!a) {
    return (
      <section className="panel">
        <div className="panel-head"><h2>Waveform</h2></div>
        <div className="empty">
          <svg width="72" height="28" viewBox="0 0 72 28" aria-hidden="true"><path d="M2 14 C10 14 10 4 18 4 S26 24 34 24 S42 4 50 4 S58 14 70 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
          <p>Upload a CSV file to see its waveform, spectrum and constellation.</p>
        </div>
      </section>
    );
  }

  const valFmt = (v: number | null) => (v == null ? "—" : fmtNum(v, 4));
  const iSeries = { label: "I", stroke: SERIES_I, width: 1.4, value: (_u: any, v: number | null) => valFmt(v), points: { show: false } };
  const qSeries = { label: "Q", stroke: SERIES_Q, width: 1.4, value: (_u: any, v: number | null) => valFmt(v), points: { show: false } };

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Waveform: {a.name}</h2>
        <span className="meta mono">
          {a.n_samples.toLocaleString()} samples{a.sample_rate ? ` at ${fmtRate(a.sample_rate)}` : ""}
          {a.time.decimated && view === "whole" ? ` · ${a.time.points.toLocaleString()} points, peaks kept` : ""}
        </span>
      </div>

      <div className="sub-row">
        <h3 className="sub">Time</h3>
        {a.time.decimated && (
          <div className="chips" role="group" aria-label="Time plot range">
            <button className={`chip ${view === "start" ? "on" : ""}`} onClick={() => setView("start")} aria-pressed={view === "start"}>First {a.time.head.x.length.toLocaleString()} samples</button>
            <button className={`chip ${view === "whole" ? "on" : ""}`} onClick={() => setView("whole")} aria-pressed={view === "whole"}>Whole file (peaks)</button>
          </div>
        )}
      </div>
      {time && (
        <Plot
          key={view}
          ariaLabel="Time-domain plot of I and Q"
          data={time.data}
          series={a.time.q ? [{ ...iSeries, label: `I` }, { ...qSeries, label: `Q` }] : [iSeries]}
          xLabel={a.x_is_time ? `Time (${time.unit})` : "Sample number"}
          yLabel="Amplitude"
          height={250}
        />
      )}

      <div className="plots-row">
        <div>
          <h3 className="sub">Spectrum{a.spectrum ? (a.spectrum.complex ? "" : " (one-sided)") : ""}</h3>
          {spec && a.spectrum ? (
            <Plot
              ariaLabel="Power spectrum"
              data={spec.data}
              series={[{ label: "Power", stroke: "#38c6b4", width: 1.3, fill: "rgba(56,198,180,0.14)", fillTo: () => -100, value: (_u: any, v: number | null) => (v == null ? "—" : `${v.toFixed(1)} dB`), points: { show: false } }]}
              xLabel={a.sample_rate ? `Frequency (${spec.unit})` : "Frequency (cycles per sample)"}
              yLabel="dB relative to peak"
              yRange={[-100, 5]}
              height={240}
            />
          ) : (
            <p className="hint">Not enough samples for a spectrum (needs 16).</p>
          )}
        </div>
        <div>
          <h3 className="sub">Constellation</h3>
          {a.constellation ? <Constellation i={a.constellation.i} q={a.constellation.q} height={240} /> : <p className="hint">The file has no Q column, so there is no I/Q scatter.</p>}
        </div>
      </div>

      <dl className="facts inline-facts">
        <div><dt>Peak</dt><dd className="mono">{fmtNum(a.stats.peak)}</dd></div>
        <div><dt>RMS I</dt><dd className="mono">{fmtNum(a.stats.rms_i)}</dd></div>
        {a.stats.rms_q !== null && <div><dt>RMS Q</dt><dd className="mono">{fmtNum(a.stats.rms_q)}</dd></div>}
        <div><dt>DC offset I</dt><dd className="mono">{fmtNum(a.stats.dc_i)}</dd></div>
        {a.stats.dc_q !== null && <div><dt>DC offset Q</dt><dd className="mono">{fmtNum(a.stats.dc_q)}</dd></div>}
      </dl>
    </section>
  );
}
