"use client";

import { useState } from "react";

type Day = { date: string; rows: number; by_submitter: Record<string, number> };

// validated against the dark card surface (dataviz lightness band, CVD separation)
const BAR = "#1e9486";
const FLAGGED = "#cc7f16";
const DROP = 0.25;

function flagged(series: Day[]) {
  // a day is flagged when any submitter lands 25% or more under its own trailing mean
  return series.map((d, i) => {
    const prior = series.slice(Math.max(0, i - 7), i);
    if (prior.length < 3) return null;
    let worst: { sid: string; pct: number } | null = null;
    for (const [sid, rows] of Object.entries(d.by_submitter)) {
      const hist = prior.map((p) => p.by_submitter[sid]).filter((v) => v != null);
      if (hist.length < 3) continue;
      const avg = hist.reduce((a, b) => a + b, 0) / hist.length;
      const pct = rows / avg - 1;
      if (pct <= -DROP && (!worst || pct < worst.pct)) worst = { sid, pct };
    }
    return worst;
  });
}

export function VolumeChart({ series, average }: { series: Day[]; average: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const flags = flagged(series);

  const W = 720;
  const H = 220;
  const pad = { l: 44, r: 12, t: 24, b: 28 };
  const max = Math.max(...series.map((d) => d.rows), average) * 1.1;
  const step = [50, 100, 200, 250, 500, 1000, 2000, 5000, 10000].find((s) => max / s <= 5) ?? 20000;
  const ticks = Array.from({ length: Math.ceil(max / step) + 1 }, (_, i) => i * step);
  const band = (W - pad.l - pad.r) / series.length;
  const barW = Math.min(24, band * 0.6);
  const y = (v: number) => H - pad.b - (v / (ticks[ticks.length - 1] || 1)) * (H - pad.t - pad.b);
  const x = (i: number) => pad.l + band * i + band / 2;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          Rows loaded per business day, latest file per submitter. The line is the 7-day average.
        </p>
        <button onClick={() => setTable((t) => !t)} className="shrink-0 text-xs text-muted-foreground underline-offset-4 hover:underline">
          {table ? "Show chart" : "Show as table"}
        </button>
      </div>
      {table ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs tabular-nums">
            <thead className="text-left text-muted-foreground">
              <tr>
                <th className="py-1 pr-3 font-medium">Date</th>
                <th className="py-1 pr-3 text-right font-medium">Rows</th>
                <th className="py-1 font-medium">Flag</th>
              </tr>
            </thead>
            <tbody>
              {series.map((d, i) => (
                <tr key={d.date} className="border-t">
                  <td className="py-1 pr-3">{d.date}</td>
                  <td className="py-1 pr-3 text-right">{d.rows.toLocaleString()}</td>
                  <td className="py-1">{flags[i] ? `${flags[i]!.sid} ${Math.round(flags[i]!.pct * 100)}%` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="relative overflow-x-auto">
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[520px]" role="img" aria-label="Daily rows loaded">
            {ticks.map((t) => (
              <g key={t}>
                <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke="rgb(255 255 255 / 7%)" strokeWidth={1} />
                <text x={pad.l - 8} y={y(t)} dy="0.32em" textAnchor="end" className="fill-muted-foreground text-[10px] tabular-nums">
                  {t.toLocaleString()}
                </text>
              </g>
            ))}
            {series.map((d, i) => {
              const top = y(d.rows);
              const h = y(0) - top;
              const r = Math.min(4, h);
              const x0 = x(i) - barW / 2;
              return (
                <g key={d.date}>
                  <path
                    d={`M${x0},${y(0)} V${top + r} Q${x0},${top} ${x0 + r},${top} H${x0 + barW - r} Q${x0 + barW},${top} ${x0 + barW},${top + r} V${y(0)} Z`}
                    fill={flags[i] ? FLAGGED : BAR}
                    opacity={hover === null || hover === i ? 1 : 0.55}
                  />
                  {flags[i] && (
                    <text x={x(i)} y={top - 6} textAnchor="middle" className="fill-foreground text-[10px] font-medium">
                      {flags[i]!.sid} {Math.round(flags[i]!.pct * 100)}%
                    </text>
                  )}
                  {(i % 2 === series.length % 2 || i === series.length - 1) && (
                    <text x={x(i)} y={H - pad.b + 16} textAnchor="middle" className="fill-muted-foreground text-[10px]">
                      {d.date.slice(5)}
                    </text>
                  )}
                  <rect
                    x={pad.l + band * i}
                    y={pad.t}
                    width={band}
                    height={H - pad.t - pad.b}
                    fill="transparent"
                    onMouseEnter={() => setHover(i)}
                    onMouseLeave={() => setHover(null)}
                    onFocus={() => setHover(i)}
                    tabIndex={0}
                    aria-label={`${d.date}: ${d.rows} rows`}
                  />
                </g>
              );
            })}
            <line x1={pad.l} x2={W - pad.r} y1={y(average)} y2={y(average)} stroke="#9aa0a8" strokeWidth={2} />
            <text x={W - pad.r} y={y(average) - 6} textAnchor="end" className="fill-muted-foreground text-[10px]">
              7-day avg {Math.round(average).toLocaleString()}
            </text>
          </svg>
          {hover !== null && (
            <div
              className="pointer-events-none absolute top-2 rounded-md border bg-popover px-3 py-2 text-xs shadow-lg"
              style={{ left: `min(calc(${(x(hover) / W) * 100}% + 12px), calc(100% - 11rem))` }}
            >
              <p className="font-medium">{series[hover].date}</p>
              <p className="tabular-nums">{series[hover].rows.toLocaleString()} rows</p>
              <ul className="mt-1 text-muted-foreground tabular-nums">
                {Object.entries(series[hover].by_submitter).map(([sid, n]) => (
                  <li key={sid}>
                    {sid} {n.toLocaleString()}
                    {flags[hover]?.sid === sid && <span className="text-foreground"> · {Math.round(flags[hover]!.pct * 100)}% vs its average</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
