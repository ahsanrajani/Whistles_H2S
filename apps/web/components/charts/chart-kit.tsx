"use client";

import {useId, useMemo, useState, type ReactNode} from "react";
import {Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis} from "recharts";
import {cn} from "@/lib/utils";

/* One visual language for every chart: the same palette tokens, axes, grid, tooltip and legend, so a line in
   Competitors reads like a line in Sentiment or the Supervisor console. Colours come from --chart-1..6
   (primary violet first, then the coral accent, then neutrals), never from per-chart hex values. */

export const PALETTE = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)", "var(--chart-6)"];
export const TICK = {fontSize: 11, fill: "var(--muted-foreground)"};
export const TOOLTIP_STYLE = {background: "var(--glass-pop)", border: "1px solid var(--glass-border)", borderRadius: 16, fontSize: 12,
  boxShadow: "var(--glass-pop-shadow)", backdropFilter: "blur(20px)", color: "var(--foreground)"} as const;
export const GRID = {stroke: "var(--border)", strokeDasharray: "3 6", vertical: false} as const;

const DAY = new Intl.DateTimeFormat("en-US", {month: "short", day: "numeric", timeZone: "UTC"});
export function fmtDay(value: unknown): string {
  const s = String(value ?? "");
  const d = /^\d{4}-\d{2}-\d{2}/.test(s) ? new Date(`${s.slice(0, 10)}T00:00:00Z`) : null;
  return d && !Number.isNaN(d.getTime()) ? DAY.format(d) : s;
}
export const fmtNum = (v: unknown): string => {
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v ?? "");
  return Number.isInteger(n) ? n.toLocaleString() : n.toFixed(1);
};

type TipRow = {name?: string | number; value?: unknown; color?: string; dataKey?: string | number};
/** Glass tooltip: date heading, then every series sorted high to low. */
export function ChartTooltip({active, payload, label, format = fmtNum, heading = fmtDay}: {
  active?: boolean; payload?: readonly TipRow[]; label?: unknown; format?: (v: unknown) => string; heading?: (v: unknown) => string;
}) {
  if (!active || !payload?.length) return null;
  const rows = [...payload].filter((p) => p.value !== null && p.value !== undefined).sort((a, b) => Number(b.value) - Number(a.value));
  return (
    <div className="gp-tooltip">
      <p className="m-0 mb-1 font-semibold">{heading(label)}</p>
      {rows.map((r) => (
        <p key={String(r.dataKey)} className="m-0 flex items-center gap-2">
          <i className="inline-block size-2 shrink-0 rounded-full" style={{background: r.color}}/>
          <span className="text-muted-foreground">{r.name}</span>
          <b className="numeric ml-auto pl-3">{format(r.value)}</b>
        </p>
      ))}
    </div>
  );
}

export type TrendSeries = {key: string; label: string; color?: string; focus?: boolean};

/** Clickable legend chips: show the latest value, click to hide or bring back a series. */
export function LegendChips({items, hidden, onToggle, format = fmtNum}: {
  items: {key: string; label: string; color: string; last?: unknown}[]; hidden: Set<string>; onToggle: (key: string) => void; format?: (v: unknown) => string;
}) {
  return (
    <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Chart series">
      {items.map((it) => {
        const off = hidden.has(it.key);
        return (
          <button key={it.key} type="button" aria-pressed={!off} onClick={() => onToggle(it.key)}
            title={off ? "Show this series" : "Hide this series"}
            className={cn("inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium hover:bg-muted", off && "opacity-45")}>
            <i className="size-2 rounded-full" style={{background: it.color}}/>
            <span>{it.label}</span>
            {it.last !== undefined && it.last !== null && <b className="numeric text-foreground">{format(it.last)}</b>}
          </button>
        );
      })}
    </div>
  );
}

/**
 * The line chart used across the app.
 *  - labelled axes (dates as "Oct 5", four y ticks), a light dashed grid, no clutter
 *  - the focus series (or the first) is thick with a soft gradient; the others are thinner so they read as context
 *  - one tooltip for all series, sorted; legend chips with latest values that hide/show series
 * `semantic` keeps the colours the caller passes (positive green, negative red); otherwise the palette is used.
 */
export function TrendChart({data, series, xKey = "date", yDomain, height = "15rem", semantic = false, format = fmtNum, onChartClick, ariaLabel, legend = true, xFormat = fmtDay, allowDecimals}: {
  data: Record<string, string | number | null>[]; series: TrendSeries[]; xKey?: string; yDomain?: [number | "auto", number | "auto"];
  height?: string; semantic?: boolean; format?: (v: unknown) => string; onChartClick?: (label: string) => void; ariaLabel?: string;
  legend?: boolean; xFormat?: (v: unknown) => string; allowDecimals?: boolean;
}) {
  const gid = useId().replace(/:/g, "");
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const ordered = useMemo(() => [...series].sort((a, b) => Number(!!b.focus) - Number(!!a.focus)), [series]);
  const colorOf = (s: TrendSeries, i: number) => (semantic && s.color ? s.color : PALETTE[i % PALETTE.length]);
  const toggle = (key: string) => setHidden((prev) => {
    const next = new Set(prev);
    if (next.has(key)) next.delete(key); else if (next.size < ordered.length - 1) next.add(key);
    return next;
  });
  const lastOf = (key: string) => {for (let i = data.length - 1; i >= 0; i--) if (data[i][key] !== null && data[i][key] !== undefined) return data[i][key]; return undefined;};
  const visible = ordered.filter((s) => !hidden.has(s.key));
  const single = ordered.length === 1;

  return (
    <figure className="m-0" aria-label={ariaLabel}>
      <div style={{height}} className="w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{top: 8, right: 10, left: -6, bottom: 0}} style={{cursor: onChartClick ? "pointer" : undefined}}
            onClick={(e) => {const label = (e as {activeLabel?: string} | null)?.activeLabel; if (label && onChartClick) onChartClick(label);}}>
            <defs>
              {ordered.map((s, i) => (
                <linearGradient key={s.key} id={`${gid}-${i}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={colorOf(s, i)} stopOpacity={0.28}/>
                  <stop offset="100%" stopColor={colorOf(s, i)} stopOpacity={0}/>
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid {...GRID}/>
            <XAxis dataKey={xKey} tick={TICK} tickFormatter={xFormat} tickLine={false} axisLine={false} minTickGap={34} tickMargin={8}/>
            <YAxis tick={TICK} tickLine={false} axisLine={false} width={40} tickCount={4} domain={yDomain ?? [0, "auto"]} allowDecimals={allowDecimals ?? false} tickFormatter={format}/>
            <Tooltip content={<ChartTooltip format={format}/>} cursor={{stroke: "var(--muted-foreground)", strokeDasharray: "3 4", strokeOpacity: 0.5}}/>
            {ordered.map((s, i) => {
              if (hidden.has(s.key)) return null;
              const color = colorOf(s, i);
              const strong = i === 0 || single;
              const common = {dataKey: s.key, name: s.label, stroke: color, type: "monotone" as const, connectNulls: true,
                strokeWidth: strong ? 2.75 : 1.75, strokeOpacity: strong ? 1 : 0.9, isAnimationActive: true, animationDuration: 600, animationEasing: "ease-out" as const,
                activeDot: {r: 4.5, strokeWidth: 2, stroke: "var(--background)", fill: color}, dot: false as const};
              return strong && visible[0]?.key === s.key
                ? <Area key={s.key} {...common} fill={`url(#${gid}-${i})`}/>
                : <Line key={s.key} {...common}/>;
            })}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {legend && ordered.length > 1 && (
        <LegendChips hidden={hidden} onToggle={toggle} format={format}
          items={ordered.map((s, i) => ({key: s.key, label: s.label, color: colorOf(s, i), last: lastOf(s.key)}))}/>
      )}
    </figure>
  );
}

/** A titled chart block, so every chart card has the same header rhythm. */
export function ChartHeader({title, subtitle, right}: {title: string; subtitle?: string; right?: ReactNode}) {
  return (
    <div className="mb-3 flex items-start justify-between gap-3">
      <div>
        <h2 className="m-0 text-base font-semibold">{title}</h2>
        {subtitle && <p className="m-0 mt-0.5 text-xs text-muted-foreground">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}
