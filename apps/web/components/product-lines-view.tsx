"use client";

import {ExternalLink, Layers} from "lucide-react";
import {Link} from "@/components/tenant-link";
import {useSearchParams} from "next/navigation";
import {useProductLines} from "@/hooks/use-api";
import type {ProductLine, ProductLinesPage} from "@/lib/types";
import {Badge} from "./ui/badge";
import {Card} from "./ui/card";
import {PageHeader, PeriodControl} from "./viewer-components";
import {EmptyState, ErrorState, LoadingState} from "./states";

function Kpi({label, value, sub}: {label: string; value: string | number; sub?: string}) {
  return <Card className="p-5"><p className="m-0 text-xs text-muted-foreground">{label}</p><p className="numeric my-1.5 text-3xl font-semibold tracking-tight">{value}</p><p className="m-0 text-[0.6875rem] text-muted-foreground">{sub ?? " "}</p></Card>;
}

function SentimentSplit({line}: {line: ProductLine}) {
  if (!line.scored) return <span className="text-xs text-muted-foreground">not scored</span>;
  const seg = (n: number, cls: string, title: string) => n ? <span className={cls} style={{width: `${100 * n / line.scored}%`}} title={title}/> : null;
  return <span className="flex h-2 w-28 overflow-hidden rounded-full bg-muted">
    {seg(line.neg, "bg-danger", `${line.neg} negative`)}
    {seg(line.neu, "bg-muted-foreground", `${line.neu} neutral`)}
    {seg(line.pos, "bg-success", `${line.pos} positive`)}
  </span>;
}

function NegShare({line}: {line: ProductLine}) {
  if (line.neg_share == null) return <span className="text-xs text-muted-foreground">Not estimable</span>;
  const half = (((line.neg_hi ?? 0) - (line.neg_lo ?? 0)) * 50).toFixed(1);
  return <span className="numeric text-xs">{(line.neg_share * 100).toFixed(0)}% neg · ±{half}</span>;
}

function ShareBars({data}: {data: ProductLinesPage}) {
  const rows = data.lines.filter(line => line.n);
  const peak = Math.max(...rows.map(line => line.share), data.other.share, 1);
  return <div className="grid gap-2.5">
    {rows.map(line => <div key={line.key} className="grid grid-cols-[minmax(120px,1fr)_3fr_auto] items-center gap-3 text-sm">
      <Link href={`/mentions?q=${encodeURIComponent(line.keywords[0].replace("*", ""))}`} className="font-medium hover:text-primary">{line.label}</Link>
      <span className="flex h-3 overflow-hidden rounded-full bg-muted" style={{width: `${Math.max(100 * line.share / peak, 2)}%`}}>
        {line.scored ? <>
          <span className="bg-danger" style={{width: `${100 * line.neg / Math.max(line.scored, 1)}%`}}/>
          <span className="bg-muted-foreground" style={{width: `${100 * line.neu / Math.max(line.scored, 1)}%`}}/>
          <span className="bg-success" style={{width: `${100 * line.pos / Math.max(line.scored, 1)}%`}}/>
        </> : <span className="w-full bg-primary/40"/>}
      </span>
      <span className="numeric text-right tabular-nums">{line.share}% <span className="text-muted-foreground">({line.n})</span></span>
    </div>)}
    {data.other.n > 0 && <div className="grid grid-cols-[minmax(120px,1fr)_3fr_auto] items-center gap-3 text-sm text-muted-foreground">
      <span>Other / unclassified</span>
      <span className="flex h-3 rounded-full bg-muted" style={{width: `${Math.max(100 * data.other.share / peak, 2)}%`}}><span className="w-full rounded-full bg-muted-foreground/30"/></span>
      <span className="numeric text-right">{data.other.share}% <span>({data.other.n})</span></span>
    </div>}
  </div>;
}

function LineCard({line}: {line: ProductLine}) {
  return <Card className="p-5">
    <div className="flex flex-wrap items-center gap-2">
      <span className="font-semibold">{line.label}</span>
      <span className="numeric text-xs text-muted-foreground">{line.n} mentions · {line.share}% share</span>
      <span className="ml-auto flex items-center gap-2"><SentimentSplit line={line}/><NegShare line={line}/></span>
    </div>
    <div className="mt-2 flex flex-wrap gap-1">{line.keywords.slice(0, 6).map(keyword => <Badge key={keyword} className="text-muted-foreground">{keyword}</Badge>)}{line.keywords.length > 6 && <Badge className="text-muted-foreground">+{line.keywords.length - 6}</Badge>}</div>
    {line.sample.length > 0 && <ul className="mt-3 divide-y">{line.sample.map(sample => <li key={sample.id} className="py-2">
      <p className="m-0 line-clamp-2 text-sm">{sample.text}</p>
      <span className="mt-1 flex items-center gap-1 text-[0.6875rem] text-muted-foreground">{sample.sentiment ?? "unscored"} · {sample.outlet ?? "—"} · {(sample.published_at ?? "").slice(0, 10)} {sample.url && <a href={sample.url} target="_blank" rel="noreferrer"><ExternalLink size={11}/></a>}</span>
    </li>)}</ul>}
  </Card>;
}

export function ProductLinesView() {
  const params = useSearchParams();
  const result = useProductLines(params.toString());
  if (result.isLoading) return <LoadingState label="Tagging product lines…"/>;
  if (result.error) return <ErrorState message={result.error.message}/>;
  const data = result.data;
  if (!data) return <ErrorState message="The product-lines response was empty."/>;

  const header = <PageHeader title="Product lines" subtitle={`Which parts of ${data.coverage.focus_brand ?? "the focus brand"} the conversation is about, by keyword.`} stat={<PeriodControl value={data.period}/>}/>;
  if (!data.coverage.total) {
    return <div className="grid gap-6">{header}<EmptyState title="No focus-brand mentions yet" body="Collect mentions of the focus brand; each is tagged into a product line by keyword and the share of voice builds up here."/></div>;
  }
  const top = data.lines[0];

  return <div className="mx-auto grid max-w-[93.75rem] gap-5">
    {header}
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Kpi label="Focus-brand mentions" value={data.coverage.total.toLocaleString()} sub={`${data.coverage.classified} tagged`}/>
      <Kpi label="Classified" value={`${data.coverage.total ? Math.round(100 * data.coverage.classified / data.coverage.total) : 0}%`} sub={`${data.other.n} other / unclassified`}/>
      <Kpi label="Leading line" value={top?.n ? top.label : "—"} sub={top?.n ? `${top.share}% of tags` : "no tags yet"}/>
      <Kpi label="Multi-line mentions" value={data.coverage.multi_line.toLocaleString()} sub="tagged into 2+ lines"/>
    </div>

    <Card className="p-5"><div className="mb-4 flex items-baseline justify-between"><h2 className="m-0 text-base font-semibold">Share of voice</h2><span className="text-xs text-muted-foreground">bar length = share · tint = sentiment</span></div><ShareBars data={data}/></Card>

    <div className="grid gap-4 lg:grid-cols-2">{data.lines.filter(line => line.n).map(line => <LineCard key={line.key} line={line}/>)}</div>

    <Card className="flex items-start gap-3 p-5 text-xs text-muted-foreground"><Layers size={16} className="mt-0.5 shrink-0"/><p className="m-0">Tags are deterministic keyword matches on client-safe mention text for {data.coverage.focus_brand}. A mention can carry more than one tag, so shares are of the tag total, not the mention count. Keyword lists are shown on each card and come straight from the API.</p></Card>
  </div>;
}
