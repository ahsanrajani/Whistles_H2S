"use client";

import {Activity} from "lucide-react";
import {Link} from "@/components/tenant-link";
import {useIncidents} from "@/hooks/use-api";
import type {IncidentBrand, IncidentStatus, IncidentsPage} from "@/lib/types";
import {Badge} from "./ui/badge";
import {Card} from "./ui/card";
import {PageHeader} from "./viewer-components";
import {EmptyState, ErrorState, LoadingState} from "./states";

const STATUS_CLASS: Record<IncidentStatus, string> = {
  incident: "border-danger/40 bg-danger/10 text-danger",
  elevated: "border-warning/40 bg-warning/10 text-warning",
  normal: "text-muted-foreground",
};

function Sparkline({brand, data}: {brand: IncidentBrand; data: IncidentsPage}) {
  const counts = brand.series.map(day => day.count);
  const peak = Math.max(...counts, 1);
  const vw = 320;
  const vh = 54;
  const step = brand.series.length > 1 ? vw / (brand.series.length - 1) : 0;
  const yOf = (value: number) => vh - 4 - (vh - 8) * (value / peak);
  const points = brand.series.map((day, index) => `${index * step},${yOf(day.count)}`).join(" ");
  const baselineY = yOf(brand.baseline.mean);
  const recentStart = brand.series.length - data.params.recent_days;
  return <svg viewBox={`0 0 ${vw} ${vh}`} preserveAspectRatio="none" className="h-14 w-full" role="img" aria-label={`${brand.brand} daily mentions, last ${brand.series.length} days`}>
    <line x1="0" x2={vw} y1={baselineY} y2={baselineY} stroke="var(--border)" strokeDasharray="3 3"/>
    <rect x={recentStart * step} y="0" width={vw - recentStart * step} height={vh} fill="var(--muted)" opacity="0.5"/>
    <polyline points={points} fill="none" stroke={brand.status === "incident" ? "var(--danger)" : brand.status === "elevated" ? "var(--warning)" : "var(--muted-foreground)"} strokeWidth="1.5" vectorEffect="non-scaling-stroke"/>
    {brand.series.map((day, index) => day.z >= data.params.z_threshold && day.count >= data.params.min_count
      ? <circle key={day.date} cx={index * step} cy={yOf(day.count)} r="3" fill="var(--danger)"><title>{day.date}: {day.count} (z {day.z})</title></circle>
      : null)}
  </svg>;
}

function BrandCard({brand, data}: {brand: IncidentBrand; data: IncidentsPage}) {
  return <Card className="p-5">
    <div className="flex flex-wrap items-center gap-2">
      <span className={brand.focus ? "font-bold text-primary dark:text-highlight" : "font-semibold"}>{brand.brand}</span>
      <Badge className={STATUS_CLASS[brand.status]}>{brand.status}</Badge>
      <span className="ml-auto text-xs text-muted-foreground">peak z <b className="numeric text-foreground">{brand.peak_z.toFixed(1)}</b></span>
    </div>
    <p className="mt-1 text-xs text-muted-foreground">baseline {brand.baseline.mean.toFixed(1)} ± {brand.baseline.stdev.toFixed(1)}/day over {brand.baseline.days} days · shaded = last {data.params.recent_days} days</p>
    <div className="mt-2"><Sparkline brand={brand} data={data}/></div>
    {brand.incidents.length > 0 && <div className="mt-3 grid gap-2">{brand.incidents.map(incident => <div key={incident.date} className="rounded-[0.625rem] border border-border/60 bg-muted/40 p-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <b className="numeric">{incident.date}</b>
        <span>{incident.count} mentions · z {incident.z}</span>
        <span className="text-muted-foreground">vs {incident.baseline_mean}/day baseline</span>
        <Badge className={incident.gated_in ? "border-danger/30 bg-danger/10 text-danger" : "text-muted-foreground"}>{Math.round(incident.keyword_share * 100)}% incident keywords{incident.gated_in ? "" : " — below gate"}</Badge>
      </div>
      {incident.keywords.length > 0 && <div className="mt-2 flex flex-wrap gap-1">{incident.keywords.map(keyword => <Badge key={keyword} className="border-warning/20 bg-warning/5 text-warning">{keyword}</Badge>)}</div>}
      <ul className="mt-2 grid gap-1">{incident.sample.map(sample => <li key={sample.id} className="line-clamp-2 text-xs text-muted-foreground">{sample.url ? <a href={sample.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary dark:text-highlight">↗ </a> : null}{sample.text}</li>)}</ul>
    </div>)}</div>}
  </Card>;
}

export function IncidentsView() {
  const result = useIncidents();
  if (result.isLoading) return <LoadingState label="Scanning mention velocity…"/>;
  if (result.error) return <ErrorState message={result.error.message}/>;
  const data = result.data;
  if (!data) return <ErrorState message="The incidents response was empty."/>;

  const header = <PageHeader title="Incident radar" subtitle="Per-brand mention-velocity spikes vs a trailing 28-day baseline, gated on incident-shaped keywords." stat={<span className="text-xs text-muted-foreground">as of {data.as_of}</span>}/>;
  if (!data.brands.length) return <div className="grid gap-6">{header}<EmptyState title="Not enough dated mentions yet" body="Collect mentions over several weeks so a baseline can form; spikes above it show up here."/></div>;

  return <div className="mx-auto grid max-w-[93.75rem] gap-5">
    {header}
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Card className="p-5"><p className="m-0 text-xs text-muted-foreground">Brands in incident</p><p className="numeric my-1.5 text-3xl font-semibold">{data.incident_count}</p><p className="m-0 text-[0.6875rem] text-muted-foreground">{data.elevated_count} elevated</p></Card>
      <Card className="p-5"><p className="m-0 text-xs text-muted-foreground">Baseline window</p><p className="numeric my-1.5 text-3xl font-semibold">{data.params.baseline_days}d</p><p className="m-0 text-[0.6875rem] text-muted-foreground">recent window {data.params.recent_days}d</p></Card>
      <Card className="p-5"><p className="m-0 text-xs text-muted-foreground">z threshold</p><p className="numeric my-1.5 text-3xl font-semibold">{data.params.z_threshold}</p><p className="m-0 text-[0.6875rem] text-muted-foreground">min {data.params.min_count} mentions/day</p></Card>
      <Card className="p-5"><p className="m-0 text-xs text-muted-foreground">Keyword gate</p><p className="numeric my-1.5 text-3xl font-semibold">{Math.round(data.params.keyword_share * 100)}%</p><p className="m-0 text-[0.6875rem] text-muted-foreground">of spike mentions must match</p></Card>
    </div>

    <div className="grid gap-4 lg:grid-cols-2">{data.brands.map(brand => <BrandCard key={brand.brand} brand={brand} data={data}/>)}</div>

    <Card className="p-5"><div className="flex items-center gap-2"><Activity size={16} className="text-muted-foreground"/><h2 className="m-0 text-sm font-semibold text-muted-foreground">Method</h2></div>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">For each brand, daily client-safe mention counts over the last {data.params.lookback_days} days. The mean and standard deviation of the {data.params.baseline_days}-day baseline (excluding the last {data.params.recent_days} days) give a z-score for each recent day: <span className="numeric">z = (count − mean) / max(stdev, {data.params.stdev_floor})</span>. A day is an <b>incident</b> when z ≥ {data.params.z_threshold}, count ≥ {data.params.min_count}, and at least {Math.round(data.params.keyword_share * 100)}% of that day&apos;s mentions match the incident lexicon below.</p>
      <div className="mt-3 flex flex-wrap gap-1.5">{data.lexicon.map(term => <Badge key={term} className="text-muted-foreground">{term}</Badge>)}</div>
      <p className="mt-3 text-[0.6875rem] text-muted-foreground"><Link href="/mentions" className="font-semibold text-primary dark:text-highlight">Mentions</Link> holds the underlying items.</p>
    </Card>
  </div>;
}
