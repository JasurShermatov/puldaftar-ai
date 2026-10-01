"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { money, num, short } from "@/lib/format";

export type Series = { key: string; label: string; color: string; values: number[] };
type Label = { label: string; full: string };

type Props = {
  labels: Label[];
  series: Series[];            // 1 yoki 2 ta chiziq (xarajat / daromad) — kesishsa ham alohida ko'rinadi
  height?: number;
  emptyText?: string;
  unit?: "money" | "count";
};

const PAD = { top: 22, right: 12, bottom: 24, left: 46 };

/** Yengil SVG line chart: bir nechta chiziq, gradient area (bitta chiziqda), crosshair + tooltip (touch/mouse). */
export default function LineChart({ labels, series, height = 180, emptyText = "Hali ma'lumot yo'q", unit = "money" }: Props) {
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
    const n = labels.length;
    const max = Math.max(0, ...series.flatMap((s) => s.values));
    const niceMax = niceCeil(max || 1);
    const iw = width - PAD.left - PAD.right;
    const ih = height - PAD.top - PAD.bottom;
    const x = (i: number) => PAD.left + (n <= 1 ? iw / 2 : (iw * i) / (n - 1));
    const y = (v: number) => PAD.top + ih - (ih * v) / niceMax;
    const lines = series.map((s) => {
      const xy = labels.map((_, i) => [x(i), y(s.values[i] || 0)] as const);
      const line = smoothPath(xy);
      const area = xy.length ? `${line} L${xy[xy.length - 1][0]},${PAD.top + ih} L${xy[0][0]},${PAD.top + ih} Z` : "";
      const maxIdx = s.values.reduce((b, v, i) => (v > (s.values[b] || 0) ? i : b), 0);
      return { xy, line, area, maxIdx, max: Math.max(0, ...s.values) };
    });
    const ticks = [0, niceMax / 2, niceMax];
    const step = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(iw / 58))));
    return { lines, ticks, y, x, ih, iw, step, max };
  }, [labels, series, width, height]);

  const hasData = geo.max > 0;

  function onMove(clientX: number) {
    const el = wrap.current;
    if (!el || !labels.length) return;
    const r = el.getBoundingClientRect();
    const rel = clientX - r.left - PAD.left;
    const i = Math.round((rel / geo.iw) * (labels.length - 1));
    setActive(Math.min(labels.length - 1, Math.max(0, i)));
  }

  const a = active != null ? labels[active] : null;
  const ax = active != null ? geo.x(active) : null;
  const single = series.length === 1;

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
      aria-label={`Grafik: ${series.map((s) => `${s.label} ${money(s.values.reduce((p, c) => p + c, 0))}`).join(", ")}`}
    >
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <defs>
          {series.map((s) => (
            <linearGradient key={s.key} id={`g${gid}${s.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={s.color} stopOpacity={single ? 0.26 : 0.12} />
              <stop offset="100%" stopColor={s.color} stopOpacity="0" />
            </linearGradient>
          ))}
        </defs>
        {geo.ticks.map((t, i) => (
          <g key={i}>
            <line x1={PAD.left} x2={width - PAD.right} y1={geo.y(t)} y2={geo.y(t)} className="grid" />
            <text x={PAD.left - 6} y={geo.y(t) + 4} className="axis" textAnchor="end">
              {short(t)}
            </text>
          </g>
        ))}
        {labels.map((p, i) =>
          (i % geo.step === 0 && labels.length - 1 - i >= geo.step * 0.7) || i === labels.length - 1 ? (
            <text key={i} x={geo.x(i)} y={height - 6} className="axis" textAnchor={i === 0 ? "start" : i === labels.length - 1 ? "end" : "middle"}>
              {p.label}
            </text>
          ) : null,
        )}
        {hasData &&
          geo.lines.map((l, si) => (
            <g key={series[si].key}>
              <path d={l.area} fill={`url(#g${gid}${series[si].key})`} />
              <path d={l.line} className="line" style={{ stroke: series[si].color }} />
            </g>
          ))}
        {!hasData && geo.lines[0] && <path d={geo.lines[0].line} className="line" style={{ stroke: series[0]?.color, opacity: 0.35 }} />}
        {hasData && single && active == null && geo.lines[0] && geo.lines[0].max > 0 && (
          <g>
            <circle cx={geo.lines[0].xy[geo.lines[0].maxIdx][0]} cy={geo.lines[0].xy[geo.lines[0].maxIdx][1]} r={4} className="dot" style={{ fill: series[0].color }} />
            <text x={clampX(geo.lines[0].xy[geo.lines[0].maxIdx][0], width)} y={geo.lines[0].xy[geo.lines[0].maxIdx][1] - 9} className="peak" textAnchor="middle">
              {short(series[0].values[geo.lines[0].maxIdx])}
            </text>
          </g>
        )}
        {hasData && active == null &&
          geo.lines.map((l, si) =>
            l.xy.length ? <circle key={series[si].key} cx={l.xy[l.xy.length - 1][0]} cy={l.xy[l.xy.length - 1][1]} r={4} className="dot last" style={{ fill: series[si].color }} /> : null,
          )}
        {ax != null && (
          <g>
            <line x1={ax} x2={ax} y1={PAD.top - 6} y2={PAD.top + geo.ih} className="cross" />
            {geo.lines.map((l, si) => (
              <circle key={series[si].key} cx={l.xy[active!][0]} cy={l.xy[active!][1]} r={5} className="dot active" style={{ fill: series[si].color }} />
            ))}
          </g>
        )}
      </svg>
      {!hasData && <div className="chart-empty">{emptyText}</div>}
      {a && ax != null && (
        <div className="tip" style={{ left: Math.min(Math.max(ax, 80), width - 80) }}>
          <div className="tip-l">{a.full}</div>
          {series.map((s) => (
            <div key={s.key} className="tip-v">
              {!single && <span className="tip-dot" style={{ background: s.color }} />}
              {!single && <span className="tip-k">{s.label}</span>}
              {fmtTip(s.values[active!] || 0)}
            </div>
          ))}
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
