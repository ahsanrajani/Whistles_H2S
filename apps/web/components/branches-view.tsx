"use client";

import {Building2, ExternalLink, MapPin, Star} from "lucide-react";
import dynamic from "next/dynamic";
import {Link, useTenantRouter as useRouter} from "@/components/tenant-link";
import {useSearchParams} from "next/navigation";

import {useEffect} from "react";
import {useBranchMap, useBranches} from "@/hooks/use-api";
import type {BranchBandKey, BranchRow, BranchesPage} from "@/lib/types";
import {cn} from "@/lib/utils";
import {Badge} from "./ui/badge";
import {Card} from "./ui/card";
import {PageHeader, PeriodControl} from "./viewer-components";
import {BranchItems} from "./branch-items";
import {EmptyState, ErrorState, LoadingState} from "./states";

const BranchMap = dynamic(() => import("./branch-map").then(m => m.BranchMap), {
  ssr: false,
  loading: () => <div className="h-[28.75rem] animate-pulse rounded-card bg-muted"/>,
});

const BAND_CLASS: Record<BranchBandKey, string> = {
  high: "border-danger/50 bg-danger/15 text-danger",
  elevated: "border-warning/40 bg-warning/10 text-warning",
  watch: "border-primary/30 bg-primary/10 text-primary dark:text-highlight",
  none: "text-muted-foreground",
};

function issueLabel(key: string, data: BranchesPage) {
  return data.policy.issues.find(i => i.key === key)?.label ?? key.replace(/_/g, " ");
}

function Kpi({label, value, sub}: {label: string; value: string | number; sub?: string}) {
  return <Card className="p-5"><p className="m-0 text-xs text-muted-foreground">{label}</p><p className="numeric my-1.5 text-3xl font-semibold tracking-tight">{value}</p><p className="m-0 text-[0.6875rem] text-muted-foreground">{sub ?? " "}</p></Card>;
}

function Rating({value}: {value: number | null}) {
  if (value == null) return <span className="text-xs text-muted-foreground">no reviews</span>;
  const full = Math.round(value);
  return <span className="inline-flex items-center gap-1 text-xs">
    <span className="text-warning">{"★".repeat(full)}<span className="opacity-25">{"★".repeat(5 - full)}</span></span>
    <span className="numeric font-semibold">{value.toFixed(1)}</span>
  </span>;
}

function Delta({value}: {value: number | null}) {
  if (value == null) return <span className="text-xs text-muted-foreground">—</span>;
  const up = value > 0;
  return <span className={cn("numeric text-xs font-semibold", value <= -0.3 ? "text-danger" : up ? "text-success" : "text-muted-foreground")}>
    {up ? "+" : ""}{value.toFixed(1)} 30d
  </span>;
}

function BranchCard({branch, data, highlighted, hrefFor, activeIssue}: {
  branch: BranchRow; data: BranchesPage; highlighted?: boolean;
  hrefFor: (branch: BranchRow, issue?: string) => string; activeIssue?: string;
}) {
  const total = branch.reviews + branch.social;
  return <Card id={`branch-${branch.key}`}
              className={cn("rounded-[0.75rem] border-l-4 p-5 scroll-mt-24",
                branch.band === "high" ? "border-l-danger" : branch.band === "elevated" ? "border-l-warning" : "border-l-border",
                highlighted && "ring-2 ring-primary ring-offset-2 ring-offset-background")}>
    <div className="flex flex-wrap items-center gap-2">
      <Badge className={BAND_CLASS[branch.band]}>{branch.band} · {branch.score}</Badge>
      <span className="font-semibold">{branch.name}</span>
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground"><MapPin size={11}/>{branch.city} · {branch.code}</span>
      <span className="ml-auto flex items-center gap-3"><Rating value={branch.mean_rating}/><Delta value={branch.rating_delta}/></span>
    </div>
    <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
      <span>{branch.reviews} reviews</span>
      <span>{branch.social} social mentions</span>
      <span className={branch.complaints ? "text-warning" : ""}>{branch.complaints} complaints</span>
      <span className={branch.critical ? "font-semibold text-danger" : ""}>{branch.critical} critical</span>
      {branch.neg_share != null && <span>{Math.round(branch.neg_share * 100)}% negative</span>}
    </div>
    {branch.issues.length > 0 && <div className="mt-3 flex flex-wrap gap-1.5">
      {branch.issues.map(issue => {
        const active = highlighted && activeIssue === issue.key;
        return <Link key={issue.key} scroll={false}
                     href={hrefFor(branch, active ? undefined : issue.key)}
                     aria-pressed={active}
                     title={active ? "Show all items" : `Show every item tagged ${issueLabel(issue.key, data)}`}>
          <Badge className={cn("cursor-pointer transition-colors hover:bg-warning/15",
            active ? "border-warning bg-warning/20 text-warning" : "border-warning/20 bg-warning/5 text-warning")}>
            {issueLabel(issue.key, data)} · {issue.n}
          </Badge>
        </Link>;
      })}
    </div>}
    {highlighted ? <BranchItems branchKey={branch.key} period={data.period}/> : <>
    {branch.samples.length > 0 && <ul className="mt-3 divide-y">
      {branch.samples.map(sample => <li key={sample.id} className="py-2">
        <div className="flex items-center gap-2 text-[0.6875rem] text-muted-foreground">
          {sample.rating != null && <span className="text-warning">{"★".repeat(sample.rating)}</span>}
          <span>{sample.outlet ?? sample.surface}</span>
          <span>· {(sample.published_at ?? "").slice(0, 10)}</span>
          {sample.issue && <Badge className="border-border text-muted-foreground">{issueLabel(sample.issue, data)}</Badge>}
          {sample.url && <a href={sample.url} target="_blank" rel="noreferrer" className="ml-auto"><ExternalLink size={11}/></a>}
        </div>
        <p className="m-0 mt-1 line-clamp-3 text-sm">{sample.text}</p>
      </li>)}
    </ul>}
    {total > branch.samples.length && <Link href={hrefFor(branch)} scroll={false}
      className="mt-2 inline-block text-xs font-semibold text-primary underline-offset-4 hover:underline dark:text-highlight">
      See all {total} reviews & mentions →
    </Link>}
    </>}
  </Card>;
}

export function BranchesView() {
  const params = useSearchParams();
  const router = useRouter();
  const result = useBranches(params.toString());
  const mapResult = useBranchMap();
  const city = params.get("city") ?? "";
  const highlightKey = params.get("branch");

  function setCity(next: string) {
    const q = new URLSearchParams(params.toString());
    if (next) q.set("city", next); else q.delete("city");
    q.delete("branch"); q.delete("issue"); q.delete("page");
    router.replace(`/branches${q.size ? `?${q}` : ""}`);
  }

  function branchHref(branch: BranchRow, issue?: string) {
    const q = new URLSearchParams(params.toString());
    q.set("branch", branch.key);
    q.delete("page");
    if (issue) q.set("issue", issue); else q.delete("issue");
    return `/branches?${q}`;
  }

  useEffect(() => {
    if (!highlightKey) return;
    document.getElementById(`branch-${highlightKey}`)?.scrollIntoView({behavior: "smooth", block: "start"});
  }, [highlightKey, result.data]);

  if (result.isLoading) return <LoadingState label="Rolling up branch signals…"/>;
  if (result.error) return <ErrorState message={result.error.message}/>;
  const data = result.data;
  if (!data) return <ErrorState message="The branches response was empty."/>;

  const header = <PageHeader title="Branch & ATM" subtitle="Google Maps reviews and branch-resolved social listening, rolled up per branch and ranked by attention score." stat={<PeriodControl value={data.period}/>}/>;
  const noSignalYet = !data.coverage.reviews && !data.coverage.social_matched;

  const cities = Array.from(new Set(data.branches.map(b => b.city))).sort();
  const shown = city ? data.branches.filter(b => b.city === city) : data.branches;
  const flagged = shown.filter(b => b.band === "high" || b.band === "elevated");
  const selected = highlightKey ? shown.find(b => b.key === highlightKey) : undefined;
  const detailBranches = selected ? [selected] : flagged;

  return <div className="mx-auto grid max-w-[93.75rem] gap-5">
    {header}
    {noSignalYet && (
      <EmptyState title="No branch-attributed signal yet" body="The network map below is real (data/branches.csv). Collect Google Maps reviews for the branches, or wait for social mentions that name a branch, to score them into the per-branch rollup."/>
    )}
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Kpi label="Branches flagged" value={data.summary.branches_flagged} sub={`${data.summary.high} high · ${data.summary.elevated} elevated`}/>
      <Kpi label="Reviews scored" value={data.coverage.reviews.toLocaleString()} sub={`mean ${data.summary.mean_rating?.toFixed(1) ?? "—"}★ across branches`}/>
      <Kpi label="Social matched" value={data.coverage.social_matched.toLocaleString()} sub={`${data.coverage.unresolved_social} named a branch we couldn't place`}/>
      <Kpi label="Branches tracked" value={data.coverage.branches} sub="PoC catalogue subset"/>
    </div>

    {mapResult.data && <BranchMap data={mapResult.data}/>}

    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="text-muted-foreground">City</span>
      <button type="button" onClick={() => setCity("")} className={cn("rounded-full border px-2.5 py-1", !city ? "border-primary bg-primary/10 text-primary dark:text-highlight" : "text-muted-foreground hover:text-foreground")}>All</button>
      {cities.map(c => <button key={c} type="button" onClick={() => setCity(c)} className={cn("rounded-full border px-2.5 py-1", city === c ? "border-primary bg-primary/10 text-primary dark:text-highlight" : "text-muted-foreground hover:text-foreground")}>{c}</button>)}
    </div>

    {detailBranches.length > 0 && <section className="grid gap-3">
      <h2 className="m-0 text-base font-semibold">{selected ? "Branch complaints" : "Needs attention"}</h2>
      <div className="grid gap-3">{detailBranches.map(branch => <BranchCard key={branch.key} branch={branch} data={data} highlighted={branch.key === highlightKey}
                                                                   hrefFor={branchHref} activeIssue={params.get("issue") ?? undefined}/>)}</div>
    </section>}

    <Card className="p-5">
      <div className="flex items-center gap-2"><Building2 size={16} className="text-muted-foreground"/><h2 className="m-0 text-base font-semibold">All branches</h2></div>
      <div className="mt-3 overflow-x-auto"><table className="w-full min-w-[47.5rem] border-collapse text-left text-sm">
        <thead><tr className="border-b text-xs text-muted-foreground">
          <th className="py-2 pr-3">Branch</th><th className="py-2 pr-3">City</th>
          <th className="py-2 pr-3 text-right">Rating</th><th className="py-2 pr-3 text-right">Δ30d</th>
          <th className="py-2 pr-3 text-right">Reviews</th><th className="py-2 pr-3 text-right">Complaints</th>
          <th className="py-2 pr-3">Top issue</th><th className="py-2 text-right">Score</th>
        </tr></thead>
        <tbody>{shown.map(branch => <tr key={branch.key} className="border-b last:border-0">
          <td className="py-2.5 pr-3 font-medium">
            <Link href={branchHref(branch)}
                  className="underline-offset-4 hover:text-primary hover:underline focus-visible:text-primary"
                  aria-label={`View complaints for ${branch.name}`}>
              {branch.name}
            </Link>
          </td>
          <td className="py-2.5 pr-3 text-muted-foreground">{branch.city}</td>
          <td className="numeric py-2.5 pr-3 text-right">{branch.mean_rating?.toFixed(1) ?? "—"}</td>
          <td className="numeric py-2.5 pr-3 text-right"><span className={branch.rating_delta != null && branch.rating_delta <= -0.3 ? "text-danger" : "text-muted-foreground"}>{branch.rating_delta == null ? "—" : `${branch.rating_delta > 0 ? "+" : ""}${branch.rating_delta.toFixed(1)}`}</span></td>
          <td className="numeric py-2.5 pr-3 text-right">{branch.reviews}</td>
          <td className="numeric py-2.5 pr-3 text-right">{branch.complaints}{branch.critical ? <span className="text-danger"> ·{branch.critical}</span> : ""}</td>
          <td className="py-2.5 pr-3 text-xs text-muted-foreground">{branch.top_issue ? issueLabel(branch.top_issue, data) : "—"}</td>
          <td className="py-2.5 text-right"><Badge className={BAND_CLASS[branch.band]}>{branch.score}</Badge></td>
        </tr>)}</tbody>
      </table></div>
    </Card>

    <Card className="flex items-start gap-3 p-5 text-xs text-muted-foreground">
      <Star size={16} className="mt-0.5 shrink-0"/>
      <p className="m-0">Attention score is fixed rules over the numbers: low mean rating (+3/+2), a 30-day rating drop ≤ −0.7 (+2), any Critical-scored complaint at the branch (+3, via the triage scorer), ≥ 3 complaints (+2), ≥ 50% negative social with n ≥ 5 (+2), and +1 per recurring issue theme (cap +3). Bands high ≥ 7 / elevated ≥ 4 / watch ≥ 2. Reviews carry their branch id; social mentions are matched by <Link href="/mentions" className="font-semibold text-primary dark:text-highlight">branch name / area / code</Link>.</p>
    </Card>
  </div>;
}
