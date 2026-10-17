"use client";

import {DoorOpen, ExternalLink} from "lucide-react";
import {Link} from "@/components/tenant-link";
import {useSearchParams} from "next/navigation";
import {useSwitchIntent} from "@/hooks/use-api";
import type {SwitchBandKey, SwitchCase, SwitchIntentPage} from "@/lib/types";
import {Badge} from "./ui/badge";
import {Card} from "./ui/card";
import {PageHeader, PeriodControl} from "./viewer-components";
import {EmptyState, ErrorState, LoadingState} from "./states";

const BAND_CLASS: Record<SwitchBandKey, string> = {
  high: "border-danger/40 bg-danger/10 text-danger",
  likely: "border-warning/40 bg-warning/10 text-warning",
  watch: "border-primary/30 bg-primary/10 text-primary dark:text-highlight",
  none: "text-muted-foreground",
};
const BAND_ORDER: SwitchBandKey[] = ["high", "likely", "watch", "none"];

function labelFor(key: string, data: SwitchIntentPage) {
  return data.policy.signals.find(rule => rule.key === key)?.label ?? key.replace(/_/g, " ");
}

function Kpi({label, value, sub}: {label: string; value: string | number; sub?: string}) {
  return <Card className="p-5"><p className="m-0 text-xs text-muted-foreground">{label}</p><p className="numeric my-1.5 text-3xl font-semibold tracking-tight">{value}</p><p className="m-0 text-[0.6875rem] text-muted-foreground">{sub ?? " "}</p></Card>;
}

function BandBar({data}: {data: SwitchIntentPage}) {
  const counts: Record<SwitchBandKey, number> = {high: data.summary.high, likely: data.summary.likely, watch: data.summary.watch, none: Math.max(data.summary.scanned - data.summary.high - data.summary.likely - data.summary.watch, 0)};
  const total = data.summary.scanned || 1;
  const fill: Record<SwitchBandKey, string> = {high: "bg-danger", likely: "bg-warning", watch: "bg-primary/60", none: "bg-muted-foreground/30"};
  return <div><div className="flex h-3 overflow-hidden rounded-full bg-muted">{BAND_ORDER.map(band => counts[band] ? <span key={band} className={fill[band]} title={`${band}: ${counts[band]}`} style={{width: `${100 * counts[band] / total}%`}}/> : null)}</div>
    <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">{BAND_ORDER.map(band => <span key={band}><i className={`mr-1.5 inline-block size-2 rounded-full ${fill[band]}`}/>{band} <b className="numeric text-foreground">{counts[band]}</b></span>)}</div></div>;
}

function SignalBars({data, kind}: {data: SwitchIntentPage; kind: "text" | "context"}) {
  const rows = data.signals.filter(rule => rule.kind === kind);
  const peak = Math.max(...rows.map(rule => rule.n), 1);
  return <div className="grid gap-2.5">{rows.map(rule => <div key={rule.key} className="grid grid-cols-[minmax(150px,1.3fr)_3fr_auto] items-center gap-3 text-sm">
    <span className="font-medium">{rule.label} <span className="text-xs text-muted-foreground">+{rule.weight}</span></span>
    <span className="h-2.5 rounded-full bg-muted"><span className="block h-2.5 rounded-full bg-danger/60" style={{width: `${100 * rule.n / peak}%`}}/></span>
    <span className="numeric text-right tabular-nums">{rule.n}</span>
  </div>)}</div>;
}

function CaseCard({item, data}: {item: SwitchCase; data: SwitchIntentPage}) {
  return <Card className="rounded-[0.75rem] p-5">
    <div className="flex flex-wrap items-center gap-2">
      <Badge className={BAND_CLASS[item.band]}>{item.band} · {item.score}</Badge>
      {item.competitor_named && <Badge className="border-danger/30 bg-danger/10 text-danger">names a rival</Badge>}
      <span className="text-xs text-muted-foreground">{item.outlet ?? item.surface}</span>
      <span className="text-xs text-muted-foreground">· {item.published_at?.slice(0, 10) ?? "undated"}</span>
      <span className="ml-auto numeric text-[0.6875rem] text-muted-foreground">GE-{item.id}</span>
    </div>
    <div className="mt-3 flex flex-wrap gap-1.5">{item.signals.map(key => <Badge key={key} className="border-danger/20 bg-danger/5 text-danger">{labelFor(key, data)}</Badge>)}</div>
    <p className="mb-3 mt-4 whitespace-pre-line text-sm font-medium leading-6">{item.text}</p>
    <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
      {item.url && <a href={item.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-semibold text-primary dark:text-highlight">Open source <ExternalLink size={12}/></a>}
      <span>{item.source}</span>
      <Link href={`/mentions?q=${encodeURIComponent(item.text.slice(0, 28))}`} className="ml-auto font-semibold hover:text-foreground">In Mentions →</Link>
    </div>
  </Card>;
}

export function SwitchIntentView() {
  const params = useSearchParams();
  const result = useSwitchIntent(params.toString());
  if (result.isLoading) return <LoadingState label="Scoring switch intent…"/>;
  if (result.error) return <ErrorState message={result.error.message}/>;
  const data = result.data;
  if (!data) return <ErrorState message="The switch-intent response was empty."/>;

  const header = <PageHeader title="Switch intent" subtitle={`Deterministic churn-risk scoring over mentions of ${data.coverage.focus_brand ?? "the focus brand"} — every rank traces to a rule.`} stat={<PeriodControl value={data.period}/>}/>;
  if (!data.coverage.scanned) {
    return <div className="grid gap-6">{header}<EmptyState title="No focus-brand mentions to score yet" body="Collect mentions of the focus brand. Any that talk about closing an account, switching banks, or preferring a rival are picked up here and ranked by churn risk."/></div>;
  }

  return <div className="mx-auto grid max-w-[93.75rem] gap-5">
    {header}
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Kpi label="Mentions scanned" value={data.summary.scanned.toLocaleString()} sub={`of ${data.coverage.focus_brand ?? "focus brand"}`}/>
      <Kpi label="At-risk (flagged)" value={data.summary.flagged.toLocaleString()} sub="score ≥ 2"/>
      <Kpi label="High + likely" value={(data.summary.high + data.summary.likely).toLocaleString()} sub={`${data.summary.watch} watch`}/>
      <Kpi label="Rivals matched" value={data.coverage.competitors.length} sub={data.coverage.competitors.slice(0, 3).join(", ") || "none configured"}/>
    </div>

    <Card className="p-5"><div className="mb-4 flex items-baseline justify-between"><h2 className="m-0 text-base font-semibold">Churn-risk distribution</h2><span className="numeric text-xs text-muted-foreground">{data.summary.scanned} scored</span></div><BandBar data={data}/></Card>

    <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
      <Card className="p-5"><h2 className="mt-0 text-base font-semibold">Switch-intent signals</h2>
        <p className="mb-3 mt-1 text-xs text-muted-foreground">Text rules</p><SignalBars data={data} kind="text"/>
        <p className="mb-3 mt-5 text-xs text-muted-foreground">Context rules</p><SignalBars data={data} kind="context"/>
      </Card>
      <Card className="p-5"><h2 className="mt-0 text-sm font-semibold text-muted-foreground">How the score works</h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">Each rule below adds a fixed weight when it applies; the total is the churn score. Bands:</p>
        <div className="mt-3 flex flex-wrap gap-2">{data.policy.bands.filter(band => band.key !== "none").map(band => <Badge key={band.key} className={BAND_CLASS[band.key]}>{band.label} · ≥ {band.min_score}</Badge>)}</div>
        <ul className="mt-4 grid gap-1.5 text-xs text-muted-foreground">{data.policy.signals.map(rule => <li key={rule.key} className="flex justify-between gap-4"><span>{rule.label} <span className="opacity-60">({rule.kind})</span></span><span className="numeric">+{rule.weight}</span></li>)}</ul>
        <p className="mt-4 text-[0.6875rem] text-muted-foreground">{data.coverage.note}</p>
      </Card>
    </div>

    <section className="grid gap-3">
      <div className="flex items-center justify-between"><h2 className="m-0 text-base font-semibold">At-risk mentions</h2><span className="numeric text-xs text-muted-foreground">{data.queue.length} shown{data.queue_total > data.queue.length ? ` of ${data.queue_total}` : ""}</span></div>
      {data.queue.length ? <div className="grid gap-3">{data.queue.map(item => <CaseCard key={item.id} item={item} data={data}/>)}</div>
        : <Card className="flex items-center gap-3 p-5 text-sm text-muted-foreground"><DoorOpen className="text-success" size={18}/>No mention crossed the churn-risk threshold in this period.</Card>}
    </section>
  </div>;
}
