"use client";

import {ExternalLink, ShieldAlert} from "lucide-react";
import {Link} from "@/components/tenant-link";
import {useSearchParams} from "next/navigation";
import {useScam} from "@/hooks/use-api";
import type {ScamFlag, ScamOffender, ScamPage, ScamSeverity} from "@/lib/types";
import {Badge} from "./ui/badge";
import {Card} from "./ui/card";
import {PageHeader, PeriodControl} from "./viewer-components";
import {EmptyState, ErrorState, LoadingState} from "./states";

const SEVERITY_CLASS: Record<ScamSeverity, string> = {
  high: "border-danger/40 bg-danger/10 text-danger",
  elevated: "border-warning/40 bg-warning/10 text-warning",
  low: "border-primary/30 bg-primary/10 text-primary dark:text-highlight",
  clear: "text-muted-foreground",
};

function labelFor(key: string, data: ScamPage) {
  return data.policy.signals.find(signal => signal.key === key)?.label ?? key.replace(/_/g, " ");
}

function Kpi({label, value, sub}: {label: string; value: string | number; sub?: string}) {
  return <Card className="p-5"><p className="m-0 text-xs text-muted-foreground">{label}</p><p className="numeric my-1.5 text-3xl font-semibold tracking-tight">{value}</p><p className="m-0 text-[0.6875rem] text-muted-foreground">{sub ?? " "}</p></Card>;
}

function SignalBars({data}: {data: ScamPage}) {
  const peak = Math.max(...data.signals.map(signal => signal.n), 1);
  return <div className="grid gap-3">{data.signals.map(signal => <div key={signal.key} className="grid grid-cols-[minmax(120px,1.2fr)_3fr_auto] items-center gap-3 text-sm">
    <span className="font-medium">{signal.label} <span className="text-xs text-muted-foreground">+{signal.weight}</span></span>
    <span className="h-2.5 rounded-full bg-muted"><span className="block h-2.5 rounded-full bg-danger/70" style={{width: `${100 * signal.n / peak}%`}}/></span>
    <span className="numeric text-right tabular-nums">{signal.n}</span>
  </div>)}</div>;
}

function PolicyCard({data}: {data: ScamPage}) {
  return <Card className="p-5"><h2 className="mt-0 text-sm font-semibold text-muted-foreground">How the score works</h2>
    <p className="mt-2 text-sm leading-6 text-muted-foreground">Each signal below adds a fixed weight when it appears in a comment. The total is the scam score — no model, no learned threshold. Severity bands:</p>
    <div className="mt-3 flex flex-wrap gap-2">{data.policy.bands.filter(band => band.key !== "clear").map(band => <Badge key={band.key} className={SEVERITY_CLASS[band.key]}>{band.label} · score ≥ {band.min_score}</Badge>)}</div>
    <ul className="mt-4 grid gap-1.5 text-xs text-muted-foreground">{data.policy.signals.map(signal => <li key={signal.key} className="flex justify-between gap-4"><span>{signal.label}</span><span className="numeric">+{signal.weight}</span></li>)}</ul>
    <p className="mt-4 text-[0.6875rem] text-muted-foreground">{data.coverage.note}</p>
  </Card>;
}

function FlagCard({flag, data}: {flag: ScamFlag; data: ScamPage}) {
  return <Card className="rounded-[0.75rem] p-5">
    <div className="flex flex-wrap items-center gap-2">
      <Badge className={SEVERITY_CLASS[flag.severity]}>{flag.severity} · {flag.score}</Badge>
      {flag.brand && <span className="text-xs font-bold text-primary dark:text-highlight">{flag.brand}</span>}
      <span className="text-xs text-muted-foreground">{flag.outlet ?? flag.surface}</span>
      <span className="text-xs text-muted-foreground">· {flag.published_at?.slice(0, 10) ?? "undated"}</span>
      {flag.repeat && <Badge className="border-danger/30 bg-danger/10 text-danger">repeat offender</Badge>}
      <span className="ml-auto numeric text-[0.6875rem] text-muted-foreground">{flag.author_ref ?? "no id"}</span>
    </div>
    <div className="mt-3 flex flex-wrap gap-1.5">{flag.signals.map(key => <Badge key={key} className="border-danger/20 bg-danger/5 text-danger">{labelFor(key, data)}</Badge>)}</div>
    <p className="mb-3 mt-4 whitespace-pre-line text-sm font-medium leading-6">{flag.text}</p>
    <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
      {flag.url && <a href={flag.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-semibold text-primary dark:text-highlight">Open comment <ExternalLink size={12}/></a>}
      <span>{flag.source}</span>
      <Link href={`/mentions?surface=${flag.surface}`} className="ml-auto font-semibold hover:text-foreground">In Mentions →</Link>
    </div>
  </Card>;
}

function OffenderTable({offenders, data}: {offenders: ScamOffender[]; data: ScamPage}) {
  return <div className="overflow-x-auto"><table className="w-full min-w-[40rem] border-collapse text-left text-sm">
    <thead><tr className="border-b text-xs text-muted-foreground"><th className="py-3">Commenter (hashed)</th><th className="py-3 text-right">Flagged</th><th className="py-3 text-right">Score</th><th className="px-6 py-3">Peak severity</th><th className="py-3">Signals</th></tr></thead>
    <tbody>{offenders.map(offender => <tr key={offender.actor_ref} className="border-b last:border-0 align-top">
      <th className="py-4 font-medium"><span className="numeric">{offender.actor_ref}</span>{offender.repeat && <Badge className="ml-2 border-danger/30 bg-danger/10 text-danger">repeat</Badge>}<p className="mt-1 max-w-sm text-xs font-normal text-muted-foreground">{offender.sample}</p></th>
      <td className="numeric py-4 text-right">{offender.flagged}<span className="text-muted-foreground"> / {offender.comments}</span></td>
      <td className="numeric py-4 text-right">{offender.score_sum}</td>
      <td className="px-6 py-4"><Badge className={SEVERITY_CLASS[offender.max_severity]}>{offender.max_severity}</Badge></td>
      <td className="py-4 text-xs text-muted-foreground">{offender.signals.map(key => labelFor(key, data)).join(", ")}</td>
    </tr>)}</tbody>
  </table></div>;
}

export function ScamView() {
  const params = useSearchParams();
  const result = useScam(params.toString());
  if (result.isLoading) return <LoadingState label="Scoring comments…"/>;
  if (result.error) return <ErrorState message={result.error.message}/>;
  const data = result.data;
  if (!data) return <ErrorState message="The scam-signal response was empty."/>;

  const header = <PageHeader title="Scam signals" subtitle="Deterministic scoring of owned-channel comments for phone numbers, off-platform contact, and payout lures." stat={<PeriodControl value={data.period}/>}/>;
  if (!data.coverage.scanned) {
    return <div className="grid gap-6">{header}<EmptyState title="No owned-channel comments to score yet" body="Connect the focus brand's Facebook or Instagram page and collect comments (Bright Data or Meta Graph). Scored flags appear here once comments arrive."/></div>;
  }

  return <div className="mx-auto grid max-w-[93.75rem] gap-5">
    {header}
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Kpi label="Comments scanned" value={data.summary.scanned.toLocaleString()} sub={`${data.coverage.sources.length} source${data.coverage.sources.length === 1 ? "" : "s"}`}/>
      <Kpi label="Flagged" value={data.summary.flagged.toLocaleString()} sub={`${data.summary.flag_rate}% of scanned`}/>
      <Kpi label="High severity" value={data.summary.high.toLocaleString()} sub={`${data.summary.elevated} elevated · ${data.summary.low} low`}/>
      <Kpi label="Repeat offenders" value={data.summary.repeat_offenders.toLocaleString()} sub="2+ flagged comments"/>
    </div>

    <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
      <Card className="p-5"><div className="mb-4 flex items-baseline justify-between"><h2 className="m-0 text-base font-semibold">Signal breakdown</h2><span className="numeric text-xs text-muted-foreground">comments tripping each rule</span></div>{data.signals.some(signal => signal.n) ? <SignalBars data={data}/> : <p className="text-sm text-muted-foreground">No comment tripped a scam rule in this period.</p>}</Card>
      <PolicyCard data={data}/>
    </div>

    <section className="grid gap-3">
      <div className="flex items-center justify-between"><h2 className="m-0 text-base font-semibold">Flagged comments</h2><span className="numeric text-xs text-muted-foreground">{data.flagged.length} shown{data.flagged_total > data.flagged.length ? ` of ${data.flagged_total}` : ""}</span></div>
      {data.flagged.length ? <div className="grid gap-3">{data.flagged.map(flag => <FlagCard key={flag.id} flag={flag} data={data}/>)}</div>
        : <Card className="flex items-center gap-3 p-5 text-sm text-muted-foreground"><ShieldAlert className="text-success" size={18}/>No comments crossed the scoring threshold in this period.</Card>}
    </section>

    {data.offenders.length > 0 && <Card className="p-5"><h2 className="mt-0 text-base font-semibold">Repeat-offender leaderboard</h2><p className="mb-4 text-xs text-muted-foreground">Grouped by the one-way hashed commenter id preserved at collection time.</p><OffenderTable offenders={data.offenders} data={data}/></Card>}
  </div>;
}
