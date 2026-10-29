import { useEffect, useMemo, useRef, useState } from "react";
import { useStore } from "../store";
import { SERIES_I, SERIES_Q } from "../lib/theme";
import { fmtNum, fmtRate, scaleFor } from "../lib/format";
import { Plot } from "./Plot";
import { Constellation } from "./Constellation";
import { BandStrip, type Lobe } from "./BandStrip";

type TabId = "waveform" | "spectrum" | "constellation" | "preview";

interface TabDef {
  id: TabId;
  label: string;
}

function DropArea({
  onPick,
  busy,
  label,
}: {
  onPick: (f: File) => void;
  busy: boolean;
  label: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

  return (
    <div
      className={`drop drop-viz ${drag ? "over" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        const f = e.dataTransfer.files?.[0];
        if (f) onPick(f);
      }}
      onClick={(e) => {
        if ((e.target as HTMLElement).tagName !== "BUTTON") {
          inputRef.current?.click();
        }
      }}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          inputRef.current?.click();
        }
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.txt,text/csv"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onPick(f);
          e.target.value = "";
        }}
      />
      <svg width="72" height="28" viewBox="0 0 72 28" aria-hidden="true">
        <path
          d="M2 14 C10 14 10 4 18 4 S26 24 34 24 S42 4 50 4 S58 14 70 14"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
      <p>Drop a CSV file here to see its {label}</p>
      <div className="drop-actions">
        <button
          className="btn small btn-primary"
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            inputRef.current?.click();
          }}
          disabled={busy}
        >
          Choose CSV file
        </button>
      </div>
      <span className="hint">Columns: I and Q, or time, I, Q. A header row is optional.</span>
    </div>
  );
}

export function VisualizationPanel() {
  const a = useStore((s) => s.analysis);
  const formMode = useStore((s) => s.formMode);
  const upload = useStore((s) => s.upload);
  const clear = useStore((s) => s.clearWaveform);
  const busy = useStore((s) => s.busy);

  const replaceRef = useRef<HTMLInputElement>(null);

  // Simulation mode defaults to "waveform"; Radiation mode defaults to null (hidden)
  const [activeTab, setActiveTab] = useState<TabId | null>(formMode === "simulation" ? "waveform" : null);
  const [view, setView] = useState<"start" | "whole">("start");
  const [hoverLobe, setHoverLobe] = useState<Lobe | null>(null);

  // Sync mode changes with appropriate default tab
  useEffect(() => {
    if (formMode === "radiation") {
      setActiveTab(null);
    } else {
      setActiveTab((prev) => (prev === null ? "waveform" : prev));
    }
  }, [formMode]);

  const tabs: TabDef[] = useMemo(() => {
    if (formMode === "radiation") {
      return [{ id: "preview", label: "Preview" }];
    }
    return [
      { id: "waveform", label: "Waveform" },
      { id: "spectrum", label: "Spectrum" },
      { id: "constellation", label: "Constellation" },
      { id: "preview", label: "Preview" },
    ];
  }, [formMode]);

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

  const valFmt = (v: number | null) => (v == null ? "—" : fmtNum(v, 4));
  const iSeries = { label: "I", stroke: SERIES_I, width: 1.4, value: (_u: any, v: number | null) => valFmt(v), points: { show: false } };
  const qSeries = { label: "Q", stroke: SERIES_Q, width: 1.4, value: (_u: any, v: number | null) => valFmt(v), points: { show: false } };

  // Contextual meta text for panel header
  const metaText = useMemo(() => {
    if (activeTab === "waveform") {
      return a
        ? `${a.name} · ${a.n_samples.toLocaleString()} samples${a.sample_rate ? ` at ${fmtRate(a.sample_rate)}` : ""}${a.time.decimated && view === "whole" ? ` · ${a.time.points.toLocaleString()} points` : ""}`
        : "Time-domain signal";
    }
    if (activeTab === "spectrum") {
      return a?.spectrum
        ? `${a.spectrum.complex ? "Complex baseband spectrum" : "One-sided spectrum"}`
        : "Power spectrum";
    }
    if (activeTab === "constellation") {
      return a?.constellation ? "I/Q symbol constellation" : "Constellation diagram";
    }
    if (activeTab === "preview") {
      return hoverLobe
        ? `Carrier ${hoverLobe.n} · ${hoverLobe.label} · ${hoverLobe.center.toFixed(4)} MHz · ${hoverLobe.p > 0 ? "+" : ""}${hoverLobe.p} dBm`
        : "12 carriers across 100 MHz band";
    }
    return formMode === "radiation" ? "Click Preview to view carrier layout" : "Click a tab to view plot";
  }, [activeTab, a, view, hoverLobe, formMode]);

  return (
    <section className="panel viz-panel">
      <div className="panel-head" style={!activeTab ? { marginBottom: 0 } : undefined}>
        <div className="seg viz-seg" role="tablist" aria-label="Visualizations">
          {tabs.map((tab) => {
            const on = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                role="tab"
                aria-selected={on}
                className={on ? "on" : ""}
                onClick={() => setActiveTab(on ? null : tab.id)}
              >
                {tab.label}
              </button>
            );
          })}
        </div>
        <span className="meta mono">{metaText}</span>
        {a && formMode === "simulation" && (
          <div className="head-actions" style={{ marginLeft: "auto" }}>
            <input
              ref={replaceRef}
              type="file"
              accept=".csv,.txt,text/csv"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void upload(f);
                e.target.value = "";
              }}
            />
            <button
              className="btn small"
              onClick={() => replaceRef.current?.click()}
              disabled={!!busy}
            >
              Replace file
            </button>
            <button
              className="btn small ghost"
              onClick={() => void clear()}
              disabled={!!busy}
            >
              Remove
            </button>
          </div>
        )}
      </div>

      {activeTab === "waveform" && (
        <div className="viz-content">
          {!a ? (
            <DropArea
              busy={!!busy}
              onPick={(f) => void upload(f)}
              label="waveform plot"
            />
          ) : (
            <>
              {a.time.decimated && (
                <div className="sub-row" style={{ marginTop: 2 }}>
                  <div className="chips" role="group" aria-label="Time plot range">
                    <button className={`chip ${view === "start" ? "on" : ""}`} onClick={() => setView("start")} aria-pressed={view === "start"}>
                      First {a.time.head.x.length.toLocaleString()} samples
                    </button>
                    <button className={`chip ${view === "whole" ? "on" : ""}`} onClick={() => setView("whole")} aria-pressed={view === "whole"}>
                      Whole file (peaks)
                    </button>
                  </div>
                </div>
              )}
              {time && (
                <Plot
                  key={view}
                  ariaLabel="Time-domain plot of I and Q"
                  data={time.data}
                  series={a.time.q ? [{ ...iSeries, label: "I" }, { ...qSeries, label: "Q" }] : [iSeries]}
                  xLabel={a.x_is_time ? `Time (${time.unit})` : "Sample number"}
                  yLabel="Amplitude"
                  height={220}
                />
              )}
              <dl className="facts inline-facts">
                {a.frequency && (
                  a.frequency.is_fsk ? (
                    <>
                      <div><dt title="Nominal carrier / center frequency">Center (Normal)</dt><dd className="mono">{a.sample_rate ? fmtRate(a.frequency.center) : `${fmtNum(a.frequency.center, 4)} cyc/smp`}</dd></div>
                      <div><dt title="FSK Mark / High tone frequency">FSK Mark</dt><dd className="mono">{a.sample_rate ? fmtRate(a.frequency.f_high) : `${fmtNum(a.frequency.f_high, 4)} cyc/smp`}</dd></div>
                      <div><dt title="FSK Space / Low tone frequency">FSK Space</dt><dd className="mono">{a.sample_rate ? fmtRate(a.frequency.f_low) : `${fmtNum(a.frequency.f_low, 4)} cyc/smp`}</dd></div>
                      <div><dt title="Frequency shift deviation">Deviation</dt><dd className="mono">{a.sample_rate ? `±${fmtRate(a.frequency.deviation)}` : `±${fmtNum(a.frequency.deviation, 4)}`}</dd></div>
                    </>
                  ) : (
                    <div><dt>Frequency</dt><dd className="mono">{a.sample_rate ? fmtRate(a.frequency.center) : `${fmtNum(a.frequency.center, 4)} cyc/smp`}</dd></div>
                  )
                )}
                <div><dt>Peak</dt><dd className="mono">{fmtNum(a.stats.peak)}</dd></div>
                <div><dt>RMS I</dt><dd className="mono">{fmtNum(a.stats.rms_i)}</dd></div>
                {a.stats.rms_q !== null && <div><dt>RMS Q</dt><dd className="mono">{fmtNum(a.stats.rms_q)}</dd></div>}
                <div><dt>DC I</dt><dd className="mono">{fmtNum(a.stats.dc_i)}</dd></div>
                {a.stats.dc_q !== null && <div><dt>DC Q</dt><dd className="mono">{fmtNum(a.stats.dc_q)}</dd></div>}
              </dl>
            </>
          )}
        </div>
      )}

      {activeTab === "spectrum" && (
        <div className="viz-content">
          {!a ? (
            <DropArea
              busy={!!busy}
              onPick={(f) => void upload(f)}
              label="frequency spectrum"
            />
          ) : spec && a.spectrum ? (
            <>
              <Plot
                ariaLabel="Power spectrum"
                data={spec.data}
                series={[{ label: "Power", stroke: "#38c6b4", width: 1.3, fill: "rgba(56,198,180,0.14)", fillTo: () => -100, value: (_u: any, v: number | null) => (v == null ? "—" : `${v.toFixed(1)} dB`), points: { show: false } }]}
                xLabel={a.sample_rate ? `Frequency (${spec.unit})` : "Frequency (cycles per sample)"}
                yLabel="dB relative to peak"
                yRange={[-100, 5]}
                height={220}
              />
              {a.frequency && (
                <dl className="facts inline-facts">
                  {a.frequency.is_fsk ? (
                    <>
                      <div><dt>Center Frequency</dt><dd className="mono">{a.sample_rate ? fmtRate(a.frequency.center) : `${fmtNum(a.frequency.center, 4)} cyc/smp`}</dd></div>
                      <div><dt>Mark Frequency</dt><dd className="mono">{a.sample_rate ? fmtRate(a.frequency.f_high) : `${fmtNum(a.frequency.f_high, 4)} cyc/smp`}</dd></div>
                      <div><dt>Space Frequency</dt><dd className="mono">{a.sample_rate ? fmtRate(a.frequency.f_low) : `${fmtNum(a.frequency.f_low, 4)} cyc/smp`}</dd></div>
                      <div><dt>Deviation</dt><dd className="mono">{a.sample_rate ? `±${fmtRate(a.frequency.deviation)}` : `±${fmtNum(a.frequency.deviation, 4)}`}</dd></div>
                    </>
                  ) : (
                    <div><dt>Peak Frequency</dt><dd className="mono">{a.sample_rate ? fmtRate(a.frequency.center) : `${fmtNum(a.frequency.center, 4)} cyc/smp`}</dd></div>
                  )}
                </dl>
              )}
            </>
          ) : (
            <p className="hint">Not enough samples for a spectrum (needs at least 16).</p>
          )}
        </div>
      )}

      {activeTab === "constellation" && (
        <div className="viz-content">
          {!a ? (
            <DropArea
              busy={!!busy}
              onPick={(f) => void upload(f)}
              label="constellation diagram"
            />
          ) : a.constellation ? (
            <div className="constellation-wrap">
              <Constellation i={a.constellation.i} q={a.constellation.q} height={220} />
            </div>
          ) : (
            <p className="hint">The file has no Q column, so there is no I/Q scatter.</p>
          )}
        </div>
      )}

      {activeTab === "preview" && (
        <div className="viz-content">
          <BandStrip bare onHover={setHoverLobe} />
        </div>
      )}
    </section>
  );
}
