"use client";

import {Info} from "lucide-react";
import {Link, useTenantRouter as useRouter} from "@/components/tenant-link";
import {usePathname, useSearchParams} from "next/navigation";

import type {Gauge, Sov, Theme} from "@/lib/types";
import {Badge} from "./ui/badge";
import {Select} from "./ui/select";
import {TrendChart} from "@/components/charts/chart-kit";

export function InfoHint({text, align = "center"}: {text: string; align?: "center" | "left" | "right"}) {
  const pos = align === "left" ? "left-0 translate-x-0" : align === "right" ? "right-0 translate-x-0" : "left-1/2 -translate-x-1/2";
  return <span className="group relative ml-1 inline-flex align-middle">
    <button type="button" aria-label="What is this?" className="inline-flex rounded-full text-muted-foreground/60 hover:text-foreground focus:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40">
      <Info size={13}/>
    </button>
    <span role="tooltip" className={`pointer-events-none absolute top-[calc(100%+6px)] z-40 w-56 whitespace-normal rounded-[0.5rem] border bg-card p-2.5 text-xs font-normal leading-5 text-muted-foreground opacity-0 shadow-md transition duration-150 group-hover:opacity-100 group-focus-within:opacity-100 ${pos}`}>
      {text}
    </span>
  </span>;
}

export function PageHeader({title, subtitle, stat}: {title: string; subtitle: string; stat?: React.ReactNode}) {
  return <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="mb-1 text-sm font-semibold text-primary dark:text-highlight">Client insight</p><h1 className="m-0 text-3xl font-semibold tracking-tight md:text-4xl">{title}</h1><p className="mb-0 text-muted-foreground">{subtitle}</p></div>{stat}</div>;
}

export function PeriodControl({value}: {value: string}) {
  const params = useSearchParams(); const pathname = usePathname(); const router = useRouter();
  return <Select aria-label="Period" value={value} onChange={event => {const next = new URLSearchParams(params.toString()); next.set("period", event.target.value); router.replace(`${pathname}?${next}`);}}>{["7d", "30d", "90d", "12mo", "all"].map(period => <option value={period} key={period}>{period === "all" ? "All time" : period}</option>)}</Select>;
}

export function SentimentGauge({gauge}: {gauge: Gauge}) {
  if (!gauge) return <p className="py-16 text-center text-sm text-muted-foreground">Score English mentions to estimate positive share.</p>;
  return <div className="text-center"><svg viewBox={`0 0 120 ${gauge.vb_h}`} className="mx-auto w-full max-w-72" role="img" aria-label={`${gauge.pos_pct}% positive sentiment`}><path d={gauge.track} fill="none" stroke="var(--muted)" strokeWidth="10" strokeLinecap="round"/>{gauge.segs.map(segment => <path key={segment.cls} d={segment.d} fill="none" stroke={segment.cls === "pos" ? "var(--success)" : segment.cls === "neg" ? "var(--danger)" : "var(--muted-foreground)"} strokeWidth="10"/>)}</svg><p className="numeric -mt-3 mb-1 text-5xl font-semibold">{gauge.pos_pct}%</p><p className="text-sm text-muted-foreground">95% {gauge.lo}–{gauge.hi}% · {gauge.scored} scored (EN)</p><div className="mt-5 flex justify-center gap-5 text-xs"><span className="text-success">Positive {gauge.pos}</span><span className="text-muted-foreground">Neutral {gauge.neu}</span><span className="text-danger">Negative {gauge.neg}</span></div></div>;
}

export function AnalyticsLineChart({data, lines, yDomain, semantic = false, format}: {
  data: Record<string, string | number | null>[]; lines: {key: string; label: string; color?: string; focus?: boolean}[];
  yDomain?: [number, number]; semantic?: boolean; format?: (v: unknown) => string;
}) {
  return <TrendChart data={data} series={lines} yDomain={yDomain} semantic={semantic} format={format}/>;
}

export function IntervalBar({brand}: {brand: Sov}) {
  return <div className="relative h-2 min-w-28 rounded-full bg-muted" title={`95% ${(brand.lo*100).toFixed(1)}–${(brand.hi*100).toFixed(1)}%`}><span className="absolute h-2 rounded-full bg-primary/25" style={{left: `${brand.lo*100}%`, width: `${Math.max((brand.hi-brand.lo)*100, 1)}%`}}/><span className="absolute top-1 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary ring-2 ring-card" style={{left: `${brand.p*100}%`}}/></div>;
}

export function ThemeCloud({themes, extraQuery = ""}: {themes: Theme[]; extraQuery?: string}) {
  if (!themes.length) return <p className="text-sm text-muted-foreground">Not enough recurring text yet.</p>;
  const peak = Math.max(...themes.map(theme => theme.n), 1);
  return <div className="flex flex-wrap gap-2">{themes.map(theme => <Link key={theme.term} href={`/mentions?q=${encodeURIComponent(theme.term)}${extraQuery}`}><Badge className={theme.lean === "negative" ? "border-danger/30 text-danger" : theme.lean === "positive" ? "border-success/30 text-success" : theme.lean === "mixed" ? "border-warning/30 text-warning" : ""} style={{fontSize: `${12 + 8*theme.n/peak}px`, padding: ".55rem .75rem"}}>{theme.term} <span className="numeric ml-1 opacity-70">{theme.n}</span></Badge></Link>)}</div>;
}
