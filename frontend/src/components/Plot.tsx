import { useEffect, useRef } from "react";
import uPlot from "uplot";
import { AXIS, GRID, INK_MUTED } from "../lib/theme";

interface Props {
  data: uPlot.AlignedData;
  series: uPlot.Series[];
  xLabel: string;
  yLabel: string;
  height?: number;
  yRange?: [number, number];
  ariaLabel: string;
}

const FONT = "11px 'IBM Plex Mono', monospace";
const LABEL_FONT = "12px 'Archivo Variable', sans-serif";

export function Plot({ data, series, xLabel, yLabel, height = 240, yRange, ariaLabel }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<uPlot | null>(null);

  // Rebuild the chart when its structure changes; just swap data otherwise.
  const structure = JSON.stringify([series.map((s) => [s.label, s.stroke]), xLabel, yLabel, height, yRange]);
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const axis = (label: string): uPlot.Axis => ({
      stroke: INK_MUTED,
      grid: { stroke: GRID, width: 1 },
      ticks: { stroke: AXIS, width: 1, size: 4 },
      border: { stroke: AXIS, width: 1 },
      font: FONT,
      labelFont: LABEL_FONT,
      label,
      labelSize: 18,
      gap: 4,
    });
    const opts: uPlot.Options = {
      width: el.clientWidth || 600,
      height,
      padding: [8, 12, 0, 0],
      cursor: { drag: { x: true, y: false, setScale: true }, points: { size: 8, width: 2 } },
      scales: { x: { time: false }, y: yRange ? { range: () => yRange } : { range: (_u, lo, hi) => { const pad = (hi - lo || 1) * 0.08; return [lo - pad, hi + pad]; } } },
      axes: [{ ...axis(xLabel), size: 40 }, { ...axis(yLabel), size: 58 }],
      series: [{}, ...series],
      legend: { live: true },
    };
    chart.current = new uPlot(opts, data, el);
    const ro = new ResizeObserver(() => chart.current?.setSize({ width: el.clientWidth, height }));
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.current?.destroy();
      chart.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [structure]);

  useEffect(() => {
    chart.current?.setData(data);
  }, [data]);

  return <div ref={host} className="plot" role="img" aria-label={ariaLabel} />;
}
