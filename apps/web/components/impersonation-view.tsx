"use client";

import {ShieldQuestion} from "lucide-react";
import {Link} from "@/components/tenant-link";
import {useImpersonation} from "@/hooks/use-api";
import type {ImpersonationBandKey, ImpersonationCandidate, ImpersonationDns, ImpersonationPage} from "@/lib/types";
import {Badge} from "./ui/badge";
import {Card} from "./ui/card";
import {PageHeader} from "./viewer-components";
import {EmptyState, ErrorState, LoadingState} from "./states";

const BAND_CLASS: Record<ImpersonationBandKey, string> = {
  high: "border-danger/40 bg-danger/10 text-danger",
  elevated: "border-warning/40 bg-warning/10 text-warning",
  watch: "border-primary/30 bg-primary/10 text-primary dark:text-highlight",
  none: "text-muted-foreground",
};
const DNS_CLASS: Record<ImpersonationDns, string> = {
  resolves: "border-danger/30 bg-danger/10 text-danger",
  nxdomain: "text-muted-foreground",
  unknown: "border-warning/30 bg-warning/10 text-warning",
};

function techniqueLabel(key: string, data: ImpersonationPage) {
  return data.policy.techniques.find(t => t.key === key)?.label ?? key.replace(/_/g, " ");
}

function Kpi({label, value, sub}: {label: string; value: string | number; sub?: string}) {
  return <Card className="p-5"><p className="m-0 text-xs text-muted-foreground">{label}</p><p className="numeric my-1.5 text-3xl font-semibold tracking-tight">{value}</p><p className="m-0 text-[0.6875rem] text-muted-foreground">{sub ?? " "}</p></Card>;
}

function Row({candidate, data}: {candidate: ImpersonationCandidate; data: ImpersonationPage}) {
  return <tr className="border-b last:border-0">
    <td className="py-3 pr-3 font-medium">{candidate.domain}</td>
    <td className="py-3 pr-3 text-xs text-muted-foreground">{techniqueLabel(candidate.technique, data)}</td>
    <td className="py-3 pr-3"><Badge className={DNS_CLASS[candidate.dns]}>{candidate.dns}</Badge></td>
    <td className="py-3 pr-3">{candidate.ct_observed ? <Badge className="border-danger/30 bg-danger/10 text-danger">cert seen</Badge> : <span className="text-xs text-muted-foreground">—</span>}</td>
    <td className="py-3 text-right"><Badge className={BAND_CLASS[candidate.band]}>{candidate.band} · {candidate.score}</Badge></td>
  </tr>;
}

export function ImpersonationView() {
  const result = useImpersonation();
  if (result.isLoading) return <LoadingState label="Probing lookalike domains…"/>;
  if (result.error) return <ErrorState message={result.error.message}/>;
  const data = result.data;
  if (!data) return <ErrorState message="The impersonation response was empty."/>;

  const header = <PageHeader title="Brand abuse" subtitle="Lookalike-domain permutations of the official brand domains, checked for a live DNS record and a Certificate Transparency match." stat={<span className="text-xs text-muted-foreground">{data.official.join(" · ") || "no domains configured"}</span>}/>;
  if (!data.official.length) {
    return <div className="grid gap-6">{header}<EmptyState title="No brand domains configured" body="Set BRAND_DOMAINS (comma or space separated) in Admin → API keys, then reload. Permutations and checks run against those."/></div>;
  }

  return <div className="mx-auto grid max-w-[75rem] gap-5">
    {header}
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Kpi label="Candidates" value={data.summary.candidates.toLocaleString()} sub={`${data.summary.dns_checked} DNS-checked this run`}/>
      <Kpi label="Resolving" value={data.summary.resolving.toLocaleString()} sub="have a live A record"/>
      <Kpi label="Seen in CT" value={data.summary.ct_observed.toLocaleString()} sub={data.ct_status === "unavailable" ? "crt.sh unreachable" : "certificate issued"}/>
      <Kpi label="High + elevated" value={(data.summary.high + data.summary.elevated).toLocaleString()} sub={`${data.summary.watch} watch`}/>
    </div>

    {data.ct_status === "unavailable" && <Card className="flex items-center gap-3 border-warning/40 p-5 text-sm text-warning"><ShieldQuestion size={18}/>Certificate Transparency lookup (crt.sh) was unreachable from the server — results below are DNS-only. Re-run when outbound HTTPS is available.</Card>}

    <Card className="p-5">
      <h2 className="mt-0 text-base font-semibold">Candidates by risk</h2>
      <p className="mb-3 text-xs text-muted-foreground">Risk = technique weight + {data.policy.resolves_bonus} if it resolves + {data.policy.ct_bonus} if a certificate exists.</p>
      <div className="overflow-x-auto"><table className="w-full min-w-[40rem] border-collapse text-left text-sm">
        <thead><tr className="border-b text-xs text-muted-foreground"><th className="py-2 pr-3">Domain</th><th className="py-2 pr-3">Technique</th><th className="py-2 pr-3">DNS</th><th className="py-2 pr-3">CT</th><th className="py-2 text-right">Risk</th></tr></thead>
        <tbody>{data.candidates.map(candidate => <Row key={candidate.domain} candidate={candidate} data={data}/>)}</tbody>
      </table></div>
    </Card>

    <Card className="p-5">
      <h2 className="mt-0 text-sm font-semibold text-muted-foreground">Technique weights</h2>
      <ul className="mt-3 grid gap-1.5 text-xs text-muted-foreground sm:grid-cols-2">{data.policy.techniques.map(technique => <li key={technique.key} className="flex justify-between gap-4"><span>{technique.label}</span><span className="numeric">+{technique.weight}</span></li>)}</ul>
      <p className="mt-4 text-[0.6875rem] text-muted-foreground">Defensive monitoring only. A resolving or cert-bearing lookalike is a lead to investigate, not proof of abuse. <Link href="/admin" className="font-semibold text-primary dark:text-highlight">Admin → API keys</Link> holds BRAND_DOMAINS.</p>
    </Card>
  </div>;
}
