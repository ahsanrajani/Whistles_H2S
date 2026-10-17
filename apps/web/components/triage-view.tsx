"use client";

import {ExternalLink, ListChecks} from "lucide-react";
import {Link} from "@/components/tenant-link";
import {useSearchParams} from "next/navigation";
import {useTriage} from "@/hooks/use-api";
import type {TriageBandKey, TriageCase, TriagePage} from "@/lib/types";
import {Badge} from "./ui/badge";
import {Card} from "./ui/card";
import {PageHeader, PeriodControl} from "./viewer-components";
import {EmptyState, ErrorState, LoadingState} from "./states";

const BAND_CLASS: Record<TriageBandKey, string> = {
  critical: "border-danger/50 bg-danger/15 text-danger",
  high: "border-danger/40 bg-danger/10 text-danger",
  elevated: "border-warning/40 bg-warning/10 text-warning",
  watch: "border-primary/30 bg-primary/10 text-primary dark:text-highlight",
  routine: "text-muted-foreground",
};
const BAND_ORDER: TriageBandKey[] = ["critical", "high", "elevated", "watch", "routine"];

function labelFor(key: string, data: TriagePage) {
  return data.policy.signals.find(rule => rule.key === key)?.label ?? key.replace(/_/g, " ");
}

function Kpi({label, value, sub}: {label: string; value: string | number; sub?: string}) {
  return <Card className="p-5"><p className="m-0 text-xs text-muted-foreground">{label}</p><p className="numeric my-1.5 text-3xl font-semibold tracking-tight">{value}</p><p className="m-0 text-[0.6875rem] text-muted-foreground">{sub ?? " "}</p></Card>;
}

function BandBar({data}: {data: TriagePage}) {
  const counts: Record<TriageBandKey, number> = {critical: data.summary.critical, high: data.summary.high, elevated: data.summary.elevated, watch: data.summary.watch, routine: Math.max(data.summary.scanned - data.summary.critical - data.summary.high - data.summary.elevated - data.summary.watch, 0)};
  const total = data.summary.scanned || 1;
  const fill: Record<TriageBandKey, string> = {critical: "bg-danger", high: "bg-danger/70", elevated: "bg-warning", watch: "bg-primary/60", routine: "bg-muted-foreground/30"};
  return <div><div className="flex h-3 overflow-hidden rounded-full bg-muted">{BAND_ORDER.map(band => counts[band] ? <span key={band} className={fill[band]} title={`${band}: ${counts[band]}`} style={{width: `${100 * counts[band] / total}%`}}/> : null)}</div>
    <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">{BAND_ORDER.map(band => <span key={band}><i className={`mr-1.5 inline-block size-2 rounded-full ${fill[band]}`}/>{band} <b className="numeric text-foreground">{counts[band]}</b></span>)}</div></div>;
}

function SignalBars({data, kind}: {data: TriagePage; kind: "text" | "context"}) {
  const rows = data.signals.filter(rule => rule.kind === kind);
  const peak = Math.max(...rows.map(rule => rule.n), 1);
  return <div className="grid gap-2.5">{rows.map(rule => <div key={rule.key} className="grid grid-cols-[minmax(140px,1.3fr)_3fr_auto] items-center gap-3 text-sm">
    <span className="font-medium">{rule.label} <span className="text-xs text-muted-foreground">+{rule.weight}</span></span>
    <span className="h-2.5 rounded-full bg-muted"><span className="block h-2.5 rounded-full bg-warning/70" style={{width: `${100 * rule.n / peak}%`}}/></span>
    <span className="numeric text-right tabular-nums">{rule.n}</span>
  </div>)}</div>;
}

function Stars({rating}: {rating: number}) {
  return <span title={`${rating} of 5`} className="text-xs text-warning">{"★".repeat(rating)}<span className="opacity-25">{"★".repeat(5 - rating)}</span></span>;
}

function CaseCard({item, data}: {item: TriageCase; data: TriagePage}) {
  return <Card className="rounded-[0.75rem] p-5">
    <div className="flex flex-wrap items-center gap-2">
      <Badge className={BAND_CLASS[item.band]}>{item.band} · {item.score}</Badge>
      {item.brand && <span className={item.focus ? "text-xs font-bold text-primary dark:text-highlight" : "text-xs font-semibold text-muted-foreground"}>{item.brand}</span>}
      <span className="text-xs text-muted-foreground">{item.outlet ?? item.surface}</span>
      <span className="text-xs text-muted-foreground">· {item.published_at?.slice(0, 10) ?? "undated"}</span>
      {item.rating != null && <Stars rating={item.rating}/>}
      <span className="ml-auto numeric text-[0.6875rem] text-muted-foreground">GE-{item.id}</span>
    </div>
    <div className="mt-3 flex flex-wrap gap-1.5">{item.signals.map(key => <Badge key={key} className="border-warning/20 bg-warning/5 text-warning">{labelFor(key, data)}</Badge>)}</div>
    <p className="mb-3 mt-4 whitespace-pre-line text-sm font-medium leading-6">{item.text}</p>
    <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
      {item.url && <a href={item.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-semibold text-primary dark:text-highlight">Open source <ExternalLink size={12}/></a>}
      <span>{item.source}</span>
      <Link href={`/mentions?q=${encodeURIComponent(item.text.slice(0, 28))}`} className="ml-auto font-semibold hover:text-foreground">In Mentions →</Link>
    </div>
  </Card>;
}

export function TriageView() {
  const params = useSearchParams();
  const result = useTriage(params.toString());
  if (result.isLoading) return <LoadingState label="Scoring complaints…"/>;
  if (result.error) return <ErrorState message={result.error.message}/>;
  const data = result.data;
  if (!data) return <ErrorState message="The triage response was empty."/>;

  const header = <PageHeader title="Complaint triage" subtitle="Deterministic escalation-risk scoring over complaint-shaped mentions — every rank traces to a rule." stat={<PeriodControl value={data.period}/>}/>;
  if (!data.coverage.scanned) {
    return <div className="grid gap-6">{header}<EmptyState title="No complaint-shaped mentions yet" body="Collect and score mentions. Anything classified complaint or fraud, negative in sentiment, or rated 1–2★ is picked up here and ranked by escalation risk."/></div>;
  }

  return <div className="mx-auto grid max-w-[93.75rem] gap-5">
    {header}
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Kpi label="Complaints scanned" value={data.summary.scanned.toLocaleString()} sub={`${data.coverage.focus_brand ?? "focus brand"} + competitors`}/>
      <Kpi label="Flagged" value={data.summary.flagged.toLocaleString()} sub={`${data.summary.focus_flagged} on ${data.coverage.focus_brand ?? "focus brand"}`}/>
      <Kpi label="Critical + high" value={(data.summary.critical + data.summary.high).toLocaleString()} sub={`${data.summary.elevated} elevated · ${data.summary.watch} watch`}/>
      <Kpi label="Max score" value={data.policy.max_score} sub="score ≥ 8 is Critical"/>
    </div>

    <Card className="p-5"><div className="mb-4 flex items-baseline justify-between"><h2 className="m-0 text-base font-semibold">Severity distribution</h2><span className="numeric text-xs text-muted-foreground">{data.summary.scanned} scored</span></div><BandBar data={data}/></Card>

    <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
      <Card className="p-5"><h2 className="mt-0 text-base font-semibold">Escalation signals</h2>
        <p className="mb-3 mt-1 text-xs text-muted-foreground">Text rules</p><SignalBars data={data} kind="text"/>
        <p className="mb-3 mt-5 text-xs text-muted-foreground">Context rules</p><SignalBars data={data} kind="context"/>
      </Card>
      <Card className="p-5"><h2 className="mt-0 text-sm font-semibold text-muted-foreground">How the score works</h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">Each rule below adds a fixed weight when it applies. The total is the escalation score — no model. Bands:</p>
        <div className="mt-3 flex flex-wrap gap-2">{data.policy.bands.filter(band => band.key !== "routine").map(band => <Badge key={band.key} className={BAND_CLASS[band.key]}>{band.label} · ≥ {band.min_score}</Badge>)}</div>
        <ul className="mt-4 grid gap-1.5 text-xs text-muted-foreground">{data.policy.signals.map(rule => <li key={rule.key} className="flex justify-between gap-4"><span>{rule.label} <span className="opacity-60">({rule.kind})</span></span><span className="numeric">+{rule.weight}</span></li>)}</ul>
        <p className="mt-4 text-[0.6875rem] text-muted-foreground">{data.coverage.note}</p>
      </Card>
    </div>

    <section className="grid gap-3">
      <div className="flex items-center justify-between"><h2 className="m-0 text-base font-semibold">Triage queue</h2><span className="numeric text-xs text-muted-foreground">{data.queue.length} shown{data.queue_total > data.queue.length ? ` of ${data.queue_total}` : ""}</span></div>
      {data.queue.length ? <div className="grid gap-3">{data.queue.map(item => <CaseCard key={item.id} item={item} data={data}/>)}</div>
        : <Card className="flex items-center gap-3 p-5 text-sm text-muted-foreground"><ListChecks className="text-success" size={18}/>No complaint crossed the scoring threshold in this period.</Card>}
    </section>

    {data.by_brand.length > 1 && <Card className="p-5"><h2 className="mt-0 text-base font-semibold">By brand</h2><div className="overflow-x-auto"><table className="w-full min-w-[32.5rem] border-collapse text-left text-sm"><thead><tr className="border-b text-xs text-muted-foreground"><th className="py-3">Brand</th><th className="py-3 text-right">Complaints</th><th className="py-3 text-right">Flagged</th><th className="py-3 text-right">Critical + high</th></tr></thead><tbody>{data.by_brand.map(row => <tr key={row.brand} className="border-b last:border-0"><th className="py-3 font-medium">{row.focus ? <span className="text-primary dark:text-highlight">{row.brand}</span> : row.brand}</th><td className="numeric py-3 text-right">{row.scanned}</td><td className="numeric py-3 text-right">{row.flagged}</td><td className="numeric py-3 text-right">{row.high}</td></tr>)}</tbody></table></div></Card>}
  </div>;
}
