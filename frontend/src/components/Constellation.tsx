import { useEffect, useRef } from "react";
import { AXIS, GRID, INK_MUTED, SERIES_I } from "../lib/theme";

interface Props {
  i: number[];
  q: number[];
  height?: number;
}

export function Constellation({ i, q, height = 260 }: Props) {
  const cv = useRef<HTMLCanvasElement>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const draw = () => {
      const c = cv.current, b = box.current;
      if (!c || !b) return;
      const dpr = window.devicePixelRatio || 1;
      const W = b.clientWidth, H = height;
      c.width = W * dpr;
      c.height = H * dpr;
      c.style.width = `${W}px`;
      c.style.height = `${H}px`;
      const g = c.getContext("2d")!;
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, W, H);

      const size = Math.min(W - 56, H - 40); // square plot area, equal scale on I and Q
      const x0 = (W - size) / 2 + 10, y0 = 10;
      let m = 0;
      for (let k = 0; k < i.length; k++) m = Math.max(m, Math.abs(i[k]), Math.abs(q[k]));
      m = (m || 1) * 1.1;
      const px = (v: number) => x0 + ((v + m) / (2 * m)) * size;
      const py = (v: number) => y0 + size - ((v + m) / (2 * m)) * size;

      g.strokeStyle = GRID;
      g.lineWidth = 1;
      for (let k = -2; k <= 2; k++) {
        const v = (k / 2) * (m / 1.1);
        g.beginPath(); g.moveTo(px(v), y0); g.lineTo(px(v), y0 + size); g.stroke();
        g.beginPath(); g.moveTo(x0, py(v)); g.lineTo(x0 + size, py(v)); g.stroke();
      }
      g.strokeStyle = AXIS;
      g.strokeRect(x0, y0, size, size);

      g.fillStyle = SERIES_I;
      g.globalAlpha = 0.55;
      for (let k = 0; k < i.length; k++) {
        g.beginPath();
        g.arc(px(i[k]), py(q[k]), 1.6, 0, Math.PI * 2);
        g.fill();
      }
      g.globalAlpha = 1;

      g.fillStyle = INK_MUTED;
      g.font = "11px 'IBM Plex Mono', monospace";
      g.textAlign = "center";
      g.fillText(`${(-m / 1.1).toPrecision(3)}`, px(-m / 1.1), y0 + size + 14);
      g.fillText("0", px(0), y0 + size + 14);
      g.fillText(`${(m / 1.1).toPrecision(3)}`, px(m / 1.1), y0 + size + 14);
      g.font = "12px 'Archivo Variable', sans-serif";
      g.fillText("I", x0 + size / 2, y0 + size + 30);
      g.save();
      g.translate(x0 - 10, y0 + size / 2);
      g.rotate(-Math.PI / 2);
      g.fillText("Q", 0, 0);
      g.restore();
    };
    draw();
    const ro = new ResizeObserver(draw);
    if (box.current) ro.observe(box.current);
    return () => ro.disconnect();
  }, [i, q, height]);

  return (
    <div ref={box} className="constellation">
      <canvas ref={cv} role="img" aria-label="I versus Q scatter of the samples" />
    </div>
  );
}
