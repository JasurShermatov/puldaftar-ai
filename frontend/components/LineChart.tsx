"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { money, num, short } from "@/lib/format";

type Point = { label: string; full: string; value: number };

type Props = {
  points: Point[];
  height?: number;
  emptyText?: string;
  unit?: "money" | "count";
};

const PAD = { top: 22, right: 12, bottom: 24, left: 44 };

/** Yengil SVG line chart: gradient area, crosshair + tooltip (touch/mouse), eng yuqori nuqta belgisi. */
export default function LineChart({ points, height = 170, emptyText = "Hali ma'lumot yo'q", unit = "money" }: Props) {
  const fmtTip = unit === "money" ? money : (v: number) => `${num(v)} ta`;
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(320);
  const [active, setActive] = useState<number | null>(null);
  const gid = useId().replace(/:/g, "");

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver((e) => setWidth(Math.max(200, Math.floor(e[0].contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const geo = useMemo(() => {
    const n = points.length;
    const max = Math.max(0, ...points.map((p) => p.value));
    const niceMax = niceCeil(max || 1);
    const iw = width - PAD.left - PAD.right;
    const ih = height - PAD.top - PAD.bottom;
    const x = (i: number) => PAD.left + (n <= 1 ? iw / 2 : (iw * i) / (n - 1));
    const y = (v: number) => PAD.top + ih - (ih * v) / niceMax;
    const xy = points.map((p, i) => [x(i), y(p.value)] as const);
    const line = smoothPath(xy);
    const area = xy.length ? `${line} L${xy[xy.length - 1][0]},${PAD.top + ih} L${xy[0][0]},${PAD.top + ih} Z` : "";
    const ticks = [0, niceMax / 2, niceMax];
    const maxIdx = points.reduce((b, p, i) => (p.value > points[b].value ? i : b), 0);
    const step = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(iw / 58))));
    return { xy, line, area, ticks, y, ih, iw, maxIdx, step, max };
  }, [points, width, height]);

  const hasData = geo.max > 0;

  function onMove(clientX: number) {
    const el = wrap.current;
    if (!el || !points.length) return;
    const r = el.getBoundingClientRect();
    const rel = clientX - r.left - PAD.left;
    const i = Math.round((rel / geo.iw) * (points.length - 1));
    setActive(Math.min(points.length - 1, Math.max(0, i)));
  }

  const a = active != null ? points[active] : null;
  const axy = active != null ? geo.xy[active] : null;

  return (
    <div
      ref={wrap}
      className="chart"
      style={{ height }}
      onMouseMove={(e) => onMove(e.clientX)}
      onMouseLeave={() => setActive(null)}
      onTouchStart={(e) => onMove(e.touches[0].clientX)}
      onTouchMove={(e) => onMove(e.touches[0].clientX)}
      onTouchEnd={() => setTimeout(() => setActive(null), 1600)}
      role="img"
      aria-label={`Grafik: ${points.map((p) => `${p.full} ${money(p.value)}`).join(", ")}`}
    >
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <defs>
          <linearGradient id={`g${gid}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.28" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {geo.ticks.map((t, i) => (
          <g key={i}>
            <line x1={PAD.left} x2={width - PAD.right} y1={geo.y(t)} y2={geo.y(t)} className="grid" />
            <text x={PAD.left - 6} y={geo.y(t) + 4} className="axis" textAnchor="end">
              {short(t)}
            </text>
          </g>
        ))}
        {points.map((p, i) =>
          (i % geo.step === 0 && points.length - 1 - i >= geo.step * 0.7) || i === points.length - 1 ? (
            <text key={i} x={geo.xy[i][0]} y={height - 6} className="axis" textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"}>
              {p.label}
            </text>
          ) : null,
        )}
        {hasData && <path d={geo.area} fill={`url(#g${gid})`} />}
        <path d={geo.line} className="line" />
        {hasData && geo.xy[geo.maxIdx] && active == null && (
          <g>
            <circle cx={geo.xy[geo.maxIdx][0]} cy={geo.xy[geo.maxIdx][1]} r={4} className="dot" />
            <text
              x={clampX(geo.xy[geo.maxIdx][0], width)}
              y={geo.xy[geo.maxIdx][1] - 9}
              className="peak"
              textAnchor="middle"
            >
              {short(points[geo.maxIdx].value)}
            </text>
          </g>
        )}
        {geo.xy.length > 0 && active == null && (
          <circle cx={geo.xy[geo.xy.length - 1][0]} cy={geo.xy[geo.xy.length - 1][1]} r={4} className="dot last" />
        )}
        {axy && (
          <g>
            <line x1={axy[0]} x2={axy[0]} y1={PAD.top - 6} y2={PAD.top + geo.ih} className="cross" />
            <circle cx={axy[0]} cy={axy[1]} r={5} className="dot active" />
          </g>
        )}
      </svg>
      {!hasData && <div className="chart-empty">{emptyText}</div>}
      {a && axy && (
        <div className="tip" style={{ left: Math.min(Math.max(axy[0], 70), width - 70) }}>
          <div className="tip-l">{a.full}</div>
          <div className="tip-v">{fmtTip(a.value)}</div>
        </div>
      )}
    </div>
  );
}

function clampX(x: number, w: number) {
  return Math.min(Math.max(x, PAD.left + 18), w - PAD.right - 18);
}

function niceCeil(v: number): number {
  const exp = Math.pow(10, Math.floor(Math.log10(v)));
  const f = v / exp;
  const nf = f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10;
  return nf * exp;
}

/** Monoton kubik egri chiziq (qiymat 0 dan pastga "tushib ketmaydi") */
function smoothPath(pts: ReadonlyArray<readonly [number, number]>): string {
  if (!pts.length) return "";
  if (pts.length < 3) return pts.map((p, i) => `${i ? "L" : "M"}${p[0]},${p[1]}`).join(" ");
  const n = pts.length;
  const dx: number[] = [], m: number[] = [], t: number[] = [];
  for (let i = 0; i < n - 1; i++) {
    dx.push(pts[i + 1][0] - pts[i][0]);
    m.push((pts[i + 1][1] - pts[i][1]) / dx[i]);
  }
  t.push(m[0]);
  for (let i = 1; i < n - 1; i++) t.push(m[i - 1] * m[i] <= 0 ? 0 : (m[i - 1] + m[i]) / 2);
  t.push(m[n - 2]);
  for (let i = 0; i < n - 1; i++) {
    if (m[i] === 0) {
      t[i] = 0;
      t[i + 1] = 0;
      continue;
    }
    const a = t[i] / m[i], b = t[i + 1] / m[i], s = a * a + b * b;
    if (s > 9) {
      const k = 3 / Math.sqrt(s);
      t[i] = k * a * m[i];
      t[i + 1] = k * b * m[i];
    }
  }
  let d = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 0; i < n - 1; i++) {
    const h = dx[i] / 3;
    d += ` C${pts[i][0] + h},${pts[i][1] + h * t[i]} ${pts[i + 1][0] - h},${pts[i + 1][1] - h * t[i + 1]} ${pts[i + 1][0]},${pts[i + 1][1]}`;
  }
  return d;
}
