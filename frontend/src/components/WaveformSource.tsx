import { useEffect, useState } from "react";
import { useStore } from "../store";
import { useCarrierState } from "../lib/hooks";
import { fmtDuration, fmtNum, fmtRate } from "../lib/format";

const UNITS = [
  { label: "Hz", mul: 1 },
  { label: "kHz", mul: 1e3 },
  { label: "MHz", mul: 1e6 },
];

export function WaveformSource() {
  const analysis = useStore((s) => s.analysis);
  const status = useStore((s) => s.status)!;
  const busy = useStore((s) => s.busy);
  const progress = useStore((s) => s.progress);
  const setRate = useStore((s) => s.setSampleRate);
  const send = useStore((s) => s.sendWaveform);
  const spec = useStore((s) => s.spec)!;
  const carriers = useStore((s) => s.carriers);
  const cs = useCarrierState();

  const [rateText, setRateText] = useState("");
  const [unit, setUnit] = useState(1e6);
  const [target, setTarget] = useState(1);
  const [warnings, setWarnings] = useState<string[]>([]);

  // Show the sample rate in a sensible unit whenever a new analysis arrives.
  useEffect(() => {
    const hz = analysis?.sample_rate;
    if (!hz) return setRateText("");
    const u = hz >= 1e6 ? 1e6 : hz >= 1e3 ? 1e3 : 1;
    setUnit(u);
    setRateText(String(Number((hz / u).toPrecision(8))));
  }, [analysis?.sample_rate, analysis?.name]);

  // Manage warnings: show when new file/analysis arrives, auto-dismiss after 6 seconds
  useEffect(() => {
    if (analysis?.warnings && analysis.warnings.length > 0) {
      setWarnings(analysis.warnings);
      const timer = setTimeout(() => {
        setWarnings([]);
      }, 6000);
      return () => clearTimeout(timer);
    } else {
      setWarnings([]);
    }
  }, [analysis?.name, analysis?.warnings]);

  const dismissWarning = (idx: number) => {
    setWarnings((prev) => prev.filter((_, i) => i !== idx));
  };

  const commitRate = () => {
    const hz = Number(rateText) * unit;
    if (hz > 0 && hz !== analysis?.sample_rate) void setRate(hz);
  };

  const sending = busy === "Sending waveform";
  const canSend =
    status.connected &&
    !!analysis?.sample_rate &&
    !busy &&
    status.mode === "simulation" &&
    !cs.isDirty &&
    !cs.neverApplied;
  const cur = carriers.find((c) => c.number === target);
  const curLabel = cur ? spec.waveforms.find((w) => w.id === cur.waveform)?.label : "";

  if (!analysis) return null;

  return (
    <section className="panel panel-simulation">
      <div className="panel-head">
        <h2>Waveform file</h2>
      </div>

      <label className="field">
            <span>
              Sample rate
              {analysis.sample_rate_source === "file"
                ? " (from file)"
                : analysis.sample_rate_source === "user"
                ? ""
                : " (not in file)"}
            </span>
            <div className="inline">
              <input
                className="mono"
                value={rateText}
                placeholder="e.g. 10"
                onChange={(e) => setRateText(e.target.value)}
                onBlur={commitRate}
                onKeyDown={(e) => e.key === "Enter" && commitRate()}
                inputMode="decimal"
                aria-label="Sample rate"
              />
              <select
                value={unit}
                onChange={(e) => {
                  setUnit(Number(e.target.value));
                }}
                onBlur={commitRate}
                aria-label="Sample rate unit"
              >
                {UNITS.map((u) => (
                  <option key={u.label} value={u.mul}>
                    {u.label}
                  </option>
                ))}
              </select>
            </div>
          </label>
          <dl className="facts">
            <div>
              <dt>Duration</dt>
              <dd className="mono">{fmtDuration(analysis.duration_s)}</dd>
            </div>
            <div>
              <dt>Peak</dt>
              <dd className="mono">{fmtNum(analysis.stats.peak)}</dd>
            </div>
            {analysis.frequency && (
              <div>
                <dt>{analysis.frequency.is_fsk ? "Center Freq" : "Frequency"}</dt>
                <dd className="mono">
                  {analysis.sample_rate
                    ? fmtRate(analysis.frequency.center)
                    : `${fmtNum(analysis.frequency.center, 4)} cyc/smp`}
                </dd>
              </div>
            )}
          </dl>

          {warnings.length > 0 && (
            <div className="warnings-list">
              {warnings.map((w, i) => (
                <div key={i} className="note warn">
                  <span>{w}</span>
                  <button
                    type="button"
                    className="note-close"
                    onClick={() => dismissWarning(i)}
                    title="Dismiss"
                    aria-label="Dismiss notice"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}

          <label className="field">
            <span>Play on carrier</span>
            <select value={target} onChange={(e) => setTarget(Number(e.target.value))}>
              {carriers.map((c) => (
                <option key={c.number} value={c.number}>
                  Carrier {c.number}
                </option>
              ))}
            </select>
          </label>
          <p className="hint">
            Carrier {target} is set to IQ data when you send{cur && cur.waveform !== "iq_data" ? ` (now ${curLabel})` : ""}.
          </p>
          <button className="btn btn-primary wide" onClick={() => void send(target)} disabled={!canSend}>
            {sending ? "Sending…" : `Send to carrier ${target}`}
          </button>
          {!status.connected && (
            <p className="hint">Connect to the simulator to send. The plots work without a connection.</p>
          )}
          {status.connected && (cs.isDirty || cs.neverApplied) && (
            <p className="hint warnc">Press Send to apply carrier configuration first.</p>
          )}
          {progress && (
            <div
              className="progress"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={progress.total}
              aria-valuenow={progress.done}
            >
              <i style={{ width: `${(progress.done / progress.total) * 100}%` }} />
              <span className="mono">
                {progress.done} / {progress.total} chunks
              </span>
            </div>
          )}
    </section>
  );
}
