/** Pick a unit scale for a value range and return the divisor and label. */
export function scaleFor(maxAbs: number, base: "s" | "Hz"): { div: number; unit: string } {
  const steps =
    base === "s"
      ? [
          { div: 1, unit: "s" },
          { div: 1e-3, unit: "ms" },
          { div: 1e-6, unit: "µs" },
          { div: 1e-9, unit: "ns" },
        ]
      : [
          { div: 1e9, unit: "GHz" },
          { div: 1e6, unit: "MHz" },
          { div: 1e3, unit: "kHz" },
          { div: 1, unit: "Hz" },
        ];
  for (const s of steps) if (maxAbs >= s.div) return s;
  return steps[steps.length - 1];
}

export function fmtNum(v: number, digits = 3): string {
  if (!isFinite(v)) return "—";
  if (v === 0) return "0";
  const a = Math.abs(v);
  if (a >= 1e4 || a < 1e-2) return v.toExponential(2);
  return Number(v.toPrecision(digits)).toString();
}

export function fmtRate(hz: number | null): string {
  if (!hz) return "—";
  const s = scaleFor(hz, "Hz");
  return `${Number((hz / s.div).toPrecision(6))} ${s.unit}`;
}

export function fmtDuration(s: number | null): string {
  if (s == null) return "—";
  const sc = scaleFor(s, "s");
  return `${Number((s / sc.div).toPrecision(4))} ${sc.unit}`;
}

export function fmtMHz(khz: number, digits = 3): string {
  return (khz / 1000).toFixed(digits);
}

export function fmtClock(totalSeconds: number): string {
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = Math.floor(totalSeconds % 60);
  return [h, m, s].map((n) => String(n).padStart(2, "0")).join(":");
}
