"use client";

import { useLang } from "@/context/LangContext";

export type BarDatum = {
  key: string;
  label: string;
  value: number;
  secondary?: number;
};

type Props = {
  title: string;
  subtitle?: string;
  unit: string;
  data: BarDatum[];
  emptyText: string;
  insufficientText?: string;
  minBarsForTrend?: number;
  valueFormat?: (n: number) => string;
  secondaryUnit?: string;
};

/**
 * Lightweight SVG bar chart — no extra package.
 * Calm retail labels, RTL-aware text anchor, mobile-friendly.
 */
export function BarSeriesChart({
  title,
  subtitle,
  unit,
  data,
  emptyText,
  insufficientText,
  minBarsForTrend = 1,
  valueFormat = (n) => n.toFixed(0),
  secondaryUnit,
}: Props) {
  const { lang } = useLang();
  const rtl = lang === "ar";

  if (!data.length) {
    return (
      <section className="chart-panel" aria-label={title}>
        <h3 className="chart-title">{title}</h3>
        {subtitle && <p className="chart-sub muted">{subtitle}</p>}
        <p className="muted chart-empty">{emptyText}</p>
      </section>
    );
  }

  if (data.length < minBarsForTrend) {
    return (
      <section className="chart-panel" aria-label={title}>
        <h3 className="chart-title">{title}</h3>
        {subtitle && <p className="chart-sub muted">{subtitle}</p>}
        <p className="muted chart-empty">
          {insufficientText || emptyText}
        </p>
      </section>
    );
  }

  const max = Math.max(...data.map((d) => d.value), 1);
  const w = 640;
  const h = 220;
  const padL = 48;
  const padR = 16;
  const padT = 20;
  const padB = 56;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;
  const gap = 8;
  const barW = Math.max(8, (innerW - gap * (data.length - 1)) / data.length);

  return (
    <section className="chart-panel" aria-label={title}>
      <div className="chart-head">
        <h3 className="chart-title">{title}</h3>
        <span className="chart-unit muted">{unit}</span>
      </div>
      {subtitle && <p className="chart-sub muted">{subtitle}</p>}
      <div className="chart-svg-wrap">
        <svg
          viewBox={`0 0 ${w} ${h}`}
          role="img"
          aria-label={`${title}: ${data.map((d) => `${d.label} ${valueFormat(d.value)} ${unit}`).join("; ")}`}
        >
          {/* Y grid */}
          {[0, 0.5, 1].map((t) => {
            const y = padT + innerH * (1 - t);
            return (
              <g key={t}>
                <line
                  x1={padL}
                  x2={w - padR}
                  y1={y}
                  y2={y}
                  className="chart-grid"
                />
                <text
                  x={rtl ? w - padR + 4 : padL - 6}
                  y={y + 4}
                  textAnchor={rtl ? "start" : "end"}
                  className="chart-axis"
                >
                  {valueFormat(max * t)}
                </text>
              </g>
            );
          })}
          {data.map((d, i) => {
            const bh = (d.value / max) * innerH;
            const x = padL + i * (barW + gap);
            const y = padT + innerH - bh;
            return (
              <g key={d.key}>
                <title>
                  {d.label}: {valueFormat(d.value)} {unit}
                  {d.secondary != null && secondaryUnit
                    ? ` · ${d.secondary} ${secondaryUnit}`
                    : ""}
                </title>
                <rect
                  x={x}
                  y={y}
                  width={barW}
                  height={Math.max(2, bh)}
                  rx={2}
                  className="chart-bar"
                />
                <text
                  x={x + barW / 2}
                  y={h - 28}
                  textAnchor="middle"
                  className="chart-tick"
                >
                  {d.label.length > 8 ? `${d.label.slice(0, 7)}…` : d.label}
                </text>
                <text
                  x={x + barW / 2}
                  y={y - 6}
                  textAnchor="middle"
                  className="chart-value"
                >
                  {valueFormat(d.value)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <ul className="chart-legend muted">
        {data.map((d) => (
          <li key={d.key}>
            <strong>{d.label}</strong>: {valueFormat(d.value)} {unit}
            {d.secondary != null && secondaryUnit
              ? ` · ${d.secondary} ${secondaryUnit}`
              : ""}
          </li>
        ))}
      </ul>
    </section>
  );
}
