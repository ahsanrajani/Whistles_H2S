"use client";

import {ExternalLink, Landmark, Scale} from "lucide-react";
import {Link, useTenantRouter as useRouter} from "@/components/tenant-link";
import {useSearchParams} from "next/navigation";

import {useRegulatory} from "@/hooks/use-api";
import type {RegulatoryNotice, RegulatoryPage} from "@/lib/types";
import {cn} from "@/lib/utils";
import {Badge} from "./ui/badge";
import {Card} from "./ui/card";
import {PageHeader} from "./viewer-components";
import {EmptyState, ErrorState, LoadingState} from "./states";

function topicLabel(key: string, data: RegulatoryPage) {
  return data.policy.topics.find(topic => topic.key === key)?.label ?? key.replace(/_/g, " ");
}

function Kpi({label, value, sub}: {label: string; value: string | number; sub?: string}) {
  return <Card className="p-5"><p className="m-0 text-xs text-muted-foreground">{label}</p><p className="numeric my-1.5 text-3xl font-semibold tracking-tight">{value}</p><p className="m-0 text-[0.6875rem] text-muted-foreground">{sub ?? " "}</p></Card>;
}

function FilterRow({label, active, options, onPick}: {label: string; active: string; options: {key: string; label: string; n: number}[]; onPick: (key: string) => void}) {
  return <div className="flex flex-wrap items-center gap-2 text-xs">
    <span className="text-muted-foreground">{label}</span>
    <button type="button" onClick={() => onPick("")} className={cn("rounded-full border px-2.5 py-1", !active ? "border-primary bg-primary/10 text-primary dark:text-highlight" : "text-muted-foreground hover:text-foreground")}>All</button>
    {options.map(option => <button key={option.key} type="button" onClick={() => onPick(option.key)} className={cn("rounded-full border px-2.5 py-1", active === option.key ? "border-primary bg-primary/10 text-primary dark:text-highlight" : "text-muted-foreground hover:text-foreground")}>{option.label} <span className="numeric opacity-70">{option.n}</span></button>)}
  </div>;
}

function NoticeCard({notice, data}: {notice: RegulatoryNotice; data: RegulatoryPage}) {
  return <Card className="rounded-[0.75rem] p-5">
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <Badge className="border-primary/20 bg-primary/10 text-primary dark:text-highlight">{notice.regulator}</Badge>
      <span className="text-muted-foreground">{notice.published_at?.slice(0, 10) ?? "undated"}</span>
      {notice.names_focus && <Badge className="border-warning/30 bg-warning/10 text-warning">names {data.focus_brand}</Badge>}
      {notice.brands.filter(brand => brand !== data.focus_brand).map(brand => <Badge key={brand}>{brand}</Badge>)}
    </div>
    <p className="mb-1 mt-2 text-sm font-semibold leading-6">{notice.title}</p>
    {notice.summary && <p className="m-0 line-clamp-3 text-sm text-muted-foreground">{notice.summary}</p>}
    <div className="mt-3 flex flex-wrap items-center gap-1.5">
      {notice.topics.map(topic => <Badge key={topic} className="border-border text-muted-foreground">{topicLabel(topic, data)}</Badge>)}
      {notice.url && <a href={notice.url} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 text-xs font-semibold text-primary dark:text-highlight">Open notice <ExternalLink size={12}/></a>}
    </div>
  </Card>;
}

export function RegulatoryView() {
  const params = useSearchParams();
  const router = useRouter();
  const result = useRegulatory();
  const regulator = params.get("regulator") ?? "";
  const topic = params.get("topic") ?? "";

  function setParam(name: string, value: string) {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(name, value); else next.delete(name);
    router.replace(`/regulatory${next.size ? `?${next}` : ""}`);
  }

  if (result.isLoading) return <LoadingState label="Loading regulatory notices…"/>;
  if (result.error) return <ErrorState message={result.error.message}/>;
  const data = result.data;
  if (!data) return <ErrorState message="The regulatory response was empty."/>;

  const header = <PageHeader title="Regulatory watch" subtitle="SBP, Banking Mohtasib and PSX notices, tagged by topic and by any brand they name." stat={<Link href="/mentions?surface=regulatory" className="text-xs font-semibold text-primary dark:text-highlight">In Mentions →</Link>}/>;
  if (!data.total) {
    return <div className="grid gap-6">{header}<EmptyState title="No regulatory notices collected yet" body="The regulatory-watch source pulls public SBP / Mohtasib / PSX feeds on the next collection run. Once items arrive they are listed here."/></div>;
  }

  const enforcement = data.topics.find(t => t.key === "enforcement")?.n ?? 0;
  const filtered = data.notices.filter(notice =>
    (!regulator || notice.regulator === regulator) &&
    (!topic || notice.topics.includes(topic)));

  return <div className="mx-auto grid max-w-[75rem] gap-5">
    {header}
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Kpi label="Notices" value={data.total.toLocaleString()} sub={`${data.regulators.length} regulators`}/>
      <Kpi label={`Name ${data.focus_brand ?? "the focus brand"}`} value={data.brand_hits.find(b => b.brand === data.focus_brand)?.n ?? 0} sub={`${data.brand_hits.length} brands named in total`}/>
      <Kpi label="Enforcement & penalties" value={enforcement} sub="notices matching that topic"/>
      <Kpi label="Topics tracked" value={data.policy.topics.length} sub="deterministic keyword rules"/>
    </div>

    <Card className="grid gap-3 p-5">
      <FilterRow label="Regulator" active={regulator} options={data.regulators.map(r => ({key: r.name, label: r.name, n: r.n}))} onPick={key => setParam("regulator", key)}/>
      <FilterRow label="Topic" active={topic} options={data.topics.filter(t => t.n).map(t => ({key: t.key, label: t.label, n: t.n}))} onPick={key => setParam("topic", key)}/>
    </Card>

    <div className="grid gap-3">
      <p className="text-xs text-muted-foreground"><span className="numeric font-semibold text-foreground">{filtered.length}</span> notice{filtered.length === 1 ? "" : "s"}{regulator || topic ? " match the filters" : ""}</p>
      {filtered.length ? filtered.map(notice => <NoticeCard key={notice.id} notice={notice} data={data}/>)
        : <Card className="flex items-center gap-3 p-5 text-sm text-muted-foreground"><Scale size={18}/>No notice matches these filters.</Card>}
    </div>

    <Card className="flex items-start gap-3 p-5 text-xs text-muted-foreground"><Landmark size={16} className="mt-0.5 shrink-0"/><p className="m-0">Topics are deterministic keyword matches on the notice text: {data.policy.topics.map(t => t.label).join(" · ")}. A notice can carry more than one. Feeds are configured on the <span className="font-medium">regulatory_watch</span> source (extend with <code>REGULATORY_FEEDS</code>).</p></Card>
  </div>;
}
