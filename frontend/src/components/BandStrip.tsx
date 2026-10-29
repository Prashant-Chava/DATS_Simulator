import { useEffect, useMemo, useRef, useState } from "react";
import { useStore } from "../store";
import { occupiedKhz } from "../lib/rules";

const H = 168;
const PAD = { l: 52, r: 16, t: 22, b: 30 };

export interface Lobe {
  n: number;
  center: number; // MHz absolute
  lo: number;
  hi: number;
  p: number;
  label: string;
  bw: number;
}

interface BandStripProps {
  bare?: boolean;
  onHover?: (l: Lobe | null) => void;
}

export function BandStrip({ bare = false, onHover }: BandStripProps = {}) {
  const spec = useStore((s) => s.spec)!;
  const carriers = useStore((s) => s.carriers);
  const analysis = useStore((s) => s.analysis);
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(900);
  const [hover, setHover] = useState<number | null>(null);

  const handleHover = (n: number | null) => {
    setHover(n);
    if (!onHover) return;
    const item = n !== null ? lobes.find((l) => l.n === n) ?? null : null;
    onHover(item);
  };

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(Math.max(320, el.clientWidth)));
    ro.observe(el);
    setW(Math.max(320, el.clientWidth));
    return () => ro.disconnect();
  }, []);

  const centerMHz = spec.rf_frequency_hz / 1e6;
  const halfMHz = spec.bandwidth_hz / 2e6;
  const [pLo, pHi] = spec.power_dbm;

  const lobes: Lobe[] = useMemo(
    () =>
      carriers
        .filter((c) => c.enabled)
        .map((c) => {
          const bw = Math.max(occupiedKhz(c, spec, analysis?.sample_rate) / 1000, 0.5);
          const center = centerMHz + (c.freq_offset_hz || 0) / 1e6;
          const wf = spec.waveforms.find((x) => x.id === c.waveform)?.label ?? c.waveform;
          return { n: c.number, center, lo: center - bw / 2, hi: center + bw / 2, p: c.power_dbm, label: wf, bw };
        }),
    [carriers, spec, analysis?.sample_rate, centerMHz],
  );

  const overlaps = useMemo(() => {
    const set = new Set<number>();
    const pairs: [number, number][] = [];
    const sorted = [...lobes].sort((a, b) => a.lo - b.lo);
    for (let i = 0; i < sorted.length; i++)
      for (let j = i + 1; j < sorted.length && sorted[j].lo < sorted[i].hi; j++) {
        set.add(sorted[i].n);
        set.add(sorted[j].n);
        pairs.push([sorted[i].n, sorted[j].n]);
      }
    return { set, pairs };
  }, [lobes]);

  const x0 = centerMHz - halfMHz;
  const iw = w - PAD.l - PAD.r;
  const ih = H - PAD.t - PAD.b;
  const X = (mhz: number) => PAD.l + ((mhz - x0) / (2 * halfMHz)) * iw;
  const Y = (dbm: number) => PAD.t + ih - ((dbm - pLo) / (pHi - pLo)) * ih;
  const xticks = Array.from({ length: 11 }, (_, i) => x0 + i * 10);
  const yticks = [-150, -100, -50, 0, 20];
  const hv = lobes.find((l) => l.n === hover);

  const content = (
    <>
      <div ref={ref} className="band">
        <svg width={w} height={H} role="img" aria-label={`${lobes.length} carriers across the 100 MHz band centred on 2.25 GHz`}>
          {yticks.map((t) => (
            <g key={t}>
              <line x1={PAD.l} x2={w - PAD.r} y1={Y(t)} y2={Y(t)} className="grid" />
              <text x={PAD.l - 8} y={Y(t) + 4} textAnchor="end" className="tick">{t}</text>
            </g>
          ))}
          <text x={6} y={12} className="axis-title">dBm</text>
          {xticks.map((t, i) => (
            <g key={t}>
              <line x1={X(t)} x2={X(t)} y1={PAD.t} y2={H - PAD.b} className="grid v" />
              {(i % 2 === 0) && <text x={X(t)} y={H - 10} textAnchor="middle" className="tick">{(t / 1000).toFixed(2)}</text>}
            </g>
          ))}
          <text x={PAD.l - 8} y={H - 10} textAnchor="end" className="axis-title">GHz</text>
          <line x1={PAD.l} x2={w - PAD.r} y1={H - PAD.b} y2={H - PAD.b} className="axis" />
          <line x1={X(centerMHz)} x2={X(centerMHz)} y1={PAD.t} y2={H - PAD.b} className="center" />

          {lobes.map((l) => {
            const top = Y(l.p);
            const a = X(l.lo), b = X(l.hi), k = (b - a) * 0.2;
            const clash = overlaps.set.has(l.n);
            return (
              <g key={l.n} className={`lobe ${clash ? "clash" : ""} ${hover === l.n ? "hov" : ""}`} onMouseEnter={() => handleHover(l.n)} onMouseLeave={() => handleHover(null)} tabIndex={0} onFocus={() => handleHover(l.n)} onBlur={() => handleHover(null)}>
                <path d={`M${a},${H - PAD.b} L${a + k},${top} L${b - k},${top} L${b},${H - PAD.b} Z`} />
                <text x={(a + b) / 2} y={top - 5} textAnchor="middle">{l.n}</text>
                <rect x={a - 3} y={Math.min(top, H - PAD.b - 4) - 16} width={b - a + 6} height={H - PAD.b - top + 16} fill="transparent" />
              </g>
            );
          })}
        </svg>
        {lobes.length === 0 && <p className="band-empty">No carriers are switched on.</p>}
      </div>
      {overlaps.pairs.length > 0 && (
        <p className="note warn">
          Overlapping carriers: {overlaps.pairs.slice(0, 6).map(([a, b]) => `${a} and ${b}`).join(", ")}
          {overlaps.pairs.length > 6 ? "…" : ""}. Move their frequency offsets apart if they should not interfere.
        </p>
      )}
    </>
  );

  if (bare) return content;

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Carriers in the band</h2>
        <span className="meta">
          {hv ? (
            <span className="mono">
              Carrier {hv.n} · {hv.label} · {hv.center.toFixed(4)} MHz · {hv.p > 0 ? "+" : ""}{hv.p} dBm · about {hv.bw.toFixed(2)} MHz wide
            </span>
          ) : (
            "Layout preview from the settings below, not a measurement"
          )}
        </span>
      </div>
      {content}
    </section>
  );
}
