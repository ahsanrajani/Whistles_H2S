"use client";
import {AlertTriangle, ArrowDownRight, ArrowUpRight, Download, ExternalLink, X} from "lucide-react";
import {Link, useTenantHref, useTenantRouter as useRouter} from "@/components/tenant-link";
import {useSearchParams} from "next/navigation";

import {useMemo, useSyncExternalStore} from "react";
import {useOverview} from "@/hooks/use-api";
import type {Action, Gauge, Mix, Priority, Sov, TopicVolume} from "@/lib/types";
import {cn} from "@/lib/utils";
import {RecentPostsCard} from "./owned-posts";
import {Badge} from "./ui/badge";
import {Card} from "./ui/card";
import {Select} from "./ui/select";
import {InfoHint} from "./viewer-components";
import {EmptyState, ErrorState, LoadingState} from "./states";
import {TrendChart} from "@/components/charts/chart-kit";

const DISMISS_KEY = "guru:overview:dismissed-cards";
function subscribeDismiss(cb: () => void) {
  window.addEventListener("guru:dismiss-change", cb);
  window.addEventListener("storage", cb);
  return () => {window.removeEventListener("guru:dismiss-change", cb); window.removeEventListener("storage", cb);};
}
function dismissSnapshot() {try {return localStorage.getItem(DISMISS_KEY) ?? "[]";} catch {return "[]";}}
function dismissServerSnapshot() {return "[]";}
function dismissCard(title: string) {
  let next: string[];
  try {next = JSON.parse(localStorage.getItem(DISMISS_KEY) ?? "[]");} catch {next = [];}
  if (!next.includes(title)) next.push(title);
  try {localStorage.setItem(DISMISS_KEY, JSON.stringify(next));} catch {/* no-op */}
  window.dispatchEvent(new Event("guru:dismiss-change"));
}

function MixBar({mix}: {mix: Mix}) {return <div>{mix.total ? <><div className="flex h-3 overflow-hidden rounded-full bg-muted">{mix.cats.map(cat => <Link key={cat.key} href={`/mentions?type=${cat.key}`} title={`${cat.label}: ${cat.n}`} style={{width: `${cat.pct}%`, background: cat.colour}} className="min-w-1 hover:brightness-125"/>)}</div><div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-xs text-muted-foreground">{mix.cats.map(cat => <Link key={cat.key} href={`/mentions?type=${cat.key}`} className="hover:text-foreground"><span className="mr-1.5 inline-block size-2 rounded-full" style={{background: cat.colour}}/>{cat.label} <b className="numeric text-foreground">{cat.n}</b></Link>)}</div></> : <p className="text-sm text-muted-foreground">Collect and classify mentions to see the conversation mix.</p>}</div>;}

function GaugeArc({gauge}: {gauge: Gauge}) {if (!gauge) return <p className="py-12 text-center text-sm text-muted-foreground">Score sentiment to estimate positive share.</p>; return <div className="text-center"><svg viewBox={`0 0 120 ${gauge.vb_h}`} className="mx-auto w-full max-w-64" role="img" aria-label={`${gauge.pos_pct}% positive sentiment`}><path d={gauge.track} fill="none" stroke="var(--muted)" strokeWidth="9" strokeLinecap="round"/>{gauge.segs.map(seg => <path key={seg.cls} d={seg.d} fill="none" stroke={seg.cls === "pos" ? "var(--success)" : seg.cls === "neg" ? "var(--danger)" : "var(--muted-foreground)"} strokeWidth="9"/>)}</svg><div className="-mt-6"><strong className="numeric text-4xl">{gauge.pos_pct}%</strong><p className="m-1 text-sm text-muted-foreground">positive · 95% {gauge.lo}–{gauge.hi}% · {gauge.scored} scored</p></div></div>;}

function TopicChart({chart, focusId, period}: {chart: TopicVolume; focusId?: number; period: string}) {
  const router = useRouter();
  if (!chart.peak) return <p className="py-20 text-center text-sm text-muted-foreground">No dated news mentions in this slice yet.</p>;
  // Mentions per day as a rolling mean, one labelled line per brand; the focus brand leads and is drawn heaviest.
  const data = chart.axis.map((date, i) => ({date, ...Object.fromEntries(chart.series.map((s) => [s.name, (s.smooth ?? s.counts)[i] ?? null]))}));
  return <TrendChart data={data} ariaLabel={`${chart.window ?? 7}-day rolling mentions by brand`}
    series={chart.series.map((s) => ({key: s.name, label: s.name, focus: s.focus}))}
    format={(v) => (Number.isInteger(Number(v)) ? String(v) : Number(v).toFixed(1))}
    onChartClick={() => router.push(`/mentions?brand_id=${focusId ?? ""}&since=${period === "all" ? "all" : period}`)}/>;
}

function Interval({brand}: {brand: Sov}) {return <div className="relative h-2 min-w-32 rounded-full bg-muted"><span className="absolute top-0 h-2 rounded-full bg-primary/25" style={{left: `${brand.lo*100}%`, width: `${Math.max((brand.hi-brand.lo)*100, 1)}%`}}/><span className="absolute top-1 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary ring-2 ring-card" style={{left: `${brand.p*100}%`}}/></div>;}
function PriorityStrip({priorities, onDismiss}: {priorities: Priority[]; onDismiss: (key: string) => void}) {
  if (!priorities.length) return null;
  return <section aria-label="Priorities">
    <div className="mb-2 flex items-center gap-2"><AlertTriangle size={15} className="text-danger"/><h2 className="m-0 flex items-center text-base font-semibold">Priorities — act on these<InfoHint text="The highest-severity signals firing right now across every analysis surface (alerts, complaint triage, switch intent, branch performance). Each card opens the surface it came from."/></h2><span className="numeric text-xs text-muted-foreground">{priorities.length}</span></div>
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {priorities.map(priority => <Link key={priority.key} href={priority.href} className={cn(
        "group relative rounded-[0.75rem] border border-l-4 bg-card p-4 transition hover:-translate-y-0.5",
        priority.severity === "critical" ? "border-l-danger" : "border-l-warning")}>
        <button type="button" onClick={e => {e.preventDefault(); e.stopPropagation(); onDismiss(priority.key);}}
          aria-label={`Dismiss "${priority.title}"`}
          className="absolute right-2 top-2 rounded-full p-1 text-muted-foreground/60 hover:bg-muted hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40">
          <X size={14}/>
        </button>
        <div className="flex items-center gap-2 pr-6">
          <Badge className={priority.severity === "critical" ? "border-danger/40 bg-danger/10 text-danger" : "border-warning/40 bg-warning/10 text-warning"}>{priority.severity}</Badge>
          {priority.when && <span className="text-[0.6875rem] text-muted-foreground">{priority.when}</span>}
          <span className="ml-auto text-xs font-semibold text-primary opacity-0 transition group-hover:opacity-100 dark:text-highlight">Open →</span>
        </div>
        <h3 className="mb-1 mt-2.5 pr-6 text-sm font-semibold leading-5">{priority.title}</h3>
        <p className="m-0 line-clamp-2 text-xs text-muted-foreground">{priority.detail}</p>
      </Link>)}
    </div>
  </section>;
}

function ActionCard({card, onDismiss}: {card: Action; onDismiss?: () => void}) {const tones = {risk: "border-danger/40", watch: "border-warning/40", opportunity: "border-primary/40", ok: "border-success/40"}; const actionHref = (card.action?.href ?? "").replace("/evidence", "/mentions"); return <Card className={cn("relative border-l-4", tones[card.tone])}>{onDismiss && <button type="button" onClick={onDismiss} aria-label={`Dismiss "${card.title}"`} className="absolute right-2 top-2 rounded-full p-1 text-muted-foreground/60 hover:bg-muted hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"><X size={14}/></button>}<div className="flex items-center justify-between gap-3 pr-6"><Badge>{card.tag}</Badge>{card.stat && <span className="numeric text-sm font-semibold">{card.stat}</span>}</div><h3 className="mt-4 font-semibold">{card.title}</h3><p className="text-sm leading-6 text-muted-foreground">{card.body}</p>{card.action && <Link className="text-sm font-semibold text-primary dark:text-highlight" href={actionHref}>{card.action.label} →</Link>}</Card>;}

export function OverviewView() {const params = useSearchParams(); const router = useRouter(); const href = useTenantHref(); const query = params.toString(); const result = useOverview(query);
  const dismissedRaw = useSyncExternalStore(subscribeDismiss, dismissSnapshot, dismissServerSnapshot);
  const dismissed = useMemo<string[]>(() => {try {return JSON.parse(dismissedRaw);} catch {return [];}}, [dismissedRaw]);
  if (result.isLoading) return <LoadingState/>; if (result.error) return <ErrorState message={result.error.message}/>; const data = result.data; if (!data) return <EmptyState title="No overview yet" body="Connect a source and run a collection to populate this workspace."/>; const changed = data.kpis.filter(k => k.delta !== null); function set(name: string, value: string) {const next = new URLSearchParams(params.toString()); if (value === "all" && name === "channel") next.delete(name); else next.set(name, value); router.replace(`/overview?${next}`);}
  const period = data.period === "all" ? "all" : data.period;
  const visibleCards = data.cards.filter(card => !dismissed.includes(card.title));
  const visiblePriorities = data.priorities.filter(priority => !dismissed.includes(priority.key));
  return <div className="mx-auto grid max-w-[100rem] gap-5">
    <div className="flex flex-wrap items-end justify-between gap-3"><div><p className="mb-0.5 text-sm font-semibold text-primary dark:text-highlight">Daily intelligence</p><h1 className="m-0 text-2xl font-semibold tracking-tight md:text-3xl">Overview</h1></div><div className="flex flex-wrap gap-2">{data.report_ready && <a href="/api/v1/report" download className="inline-flex items-center gap-2 rounded-[0.625rem] border bg-card px-3 py-2 text-sm font-medium hover:bg-muted"><Download size={15}/>Download report</a>}<Select aria-label="Period" value={data.period} onChange={e => set("period", e.target.value)}>{["7d","30d","90d","12mo","all"].map(value => <option value={value} key={value}>{value === "all" ? "All time" : value}</option>)}</Select><Select aria-label="Channel" value={data.channel} onChange={e => set("channel", e.target.value)}><option value="all">All channels</option>{data.channels.map(value => <option key={value}>{value}</option>)}</Select></div></div>

    <PriorityStrip priorities={visiblePriorities} onDismiss={dismissCard}/>

    <Card className="border-primary/25 bg-gradient-to-r from-primary/10 to-highlight/5 p-5"><div className="flex flex-wrap items-center gap-x-6 gap-y-1"><p className="m-0 flex items-center text-[0.6875rem] font-bold uppercase tracking-[.16em] text-primary dark:text-highlight">Since prior {data.period_label.replace("last ", "")}<InfoHint text="Change vs the previous period of the same length, shown only when the movement is statistically durable (wouldn't flip on a handful of items)."/></p>{changed.length ? changed.map(stat => <Link key={stat.key} href={`/mentions?since=${period}`} className="flex items-center gap-1.5 text-sm font-medium">{(stat.delta ?? 0) >= 0 ? <ArrowUpRight className="text-success" size={16}/> : <ArrowDownRight className="text-danger" size={16}/>} {stat.label} <b className="numeric">{Math.abs(stat.delta ?? 0).toFixed(stat.key === "rating" ? 1 : 0)}{stat.key === "rating" ? "" : stat.key === "mentions" ? "%" : "pt"}</b></Link>) : <span className="text-sm text-muted-foreground">No statistically durable movement yet; keep collecting.</span>}</div></Card>

    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{data.kpis.map((stat, index) => <Link href={stat.href.replace("/sentiment", "/mentions?sentiment=pos").replace("/competitors", "/mentions").replace("/reviews", "/mentions?surface=app_reviews")} key={stat.key}><Card className={`h-full p-4 hover:-translate-y-0.5${index === 0 ? " gp-hero" : ""}`}><div className="flex items-start justify-between"><p className="m-0 text-xs text-muted-foreground">{stat.label}</p>{stat.delta !== null && <Badge className={stat.delta >= 0 ? "text-success" : "text-danger"}>{stat.delta >= 0 ? "↑" : "↓"}{Math.abs(stat.delta).toFixed(stat.key === "rating" ? 1 : 0)}</Badge>}</div><p className="numeric my-2 text-3xl font-semibold tracking-tight">{stat.value}</p><p className="m-0 text-[0.6875rem] text-muted-foreground">{stat.sub}</p></Card></Link>)}</div>

    {/* at-a-glance band: sentiment · conversation mix · trending topics */}
    <div className="grid gap-4 lg:grid-cols-3">
      <Card className="p-5"><h2 className="mt-0 flex items-center text-sm font-semibold text-muted-foreground">Positive share<InfoHint text="Share of scored English mentions that read as positive, with a 95% confidence interval. Neutral and not-scored mentions are excluded from the percentage."/></h2><GaugeArc gauge={data.gauge}/></Card>
      <Card className="p-5"><div className="flex items-baseline justify-between"><h2 className="mt-0 flex items-center text-sm font-semibold text-muted-foreground">Conversation mix<InfoHint text="Every mention classified into one type (complaint, praise, question, comparison, news, fraud, feature request, other). Click a segment to filter Mentions to it."/></h2><span className="numeric text-xs text-muted-foreground">{data.mix.total}</span></div><div className="mt-3"><MixBar mix={data.mix}/></div></Card>
      <Card className="p-5"><div className="flex items-baseline justify-between"><h2 className="mt-0 flex items-center text-sm font-semibold text-muted-foreground">Trending topics<InfoHint text="Recurring terms in recent mention text, sized by frequency and tinted by the sentiment leaning of the mentions they appear in. Click a term to search Mentions."/></h2><Link href="/themes" className="text-xs font-semibold text-primary dark:text-highlight">All →</Link></div><div className="mt-3 flex max-h-40 flex-wrap gap-1.5 overflow-auto">{data.themes.length ? data.themes.slice(0,24).map(theme => <Link href={`/mentions?q=${encodeURIComponent(theme.term)}`} key={theme.term}><Badge className={theme.lean === "negative" ? "border-danger/30 text-danger" : theme.lean === "positive" ? "border-success/30 text-success" : ""} style={{fontSize: `${Math.min(15, 11 + theme.n/4)}px`}}>{theme.term} <span className="numeric ml-1 opacity-70">{theme.n}</span></Badge></Link>) : <p className="text-sm text-muted-foreground">More mention text needed for durable themes.</p>}</div></Card>
    </div>

    {/* topic volume + share of voice side by side */}
    <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
      <Card className="p-5"><div className="mb-3"><h2 className="m-0 flex items-center text-base font-semibold">Topic volume<InfoHint text="Rolling count of dated mentions per brand over the selected period. The focus brand is the bold line — click a point to open those mentions."/></h2><p className="text-xs text-muted-foreground">Dated mentions by brand · select a point to investigate</p></div><TopicChart chart={data.topic_volume} focusId={data.focus?.id} period={data.period}/></Card>
      <Card className="p-5"><h2 className="mt-0 flex items-center text-base font-semibold">Competitive share of voice<InfoHint text="Each brand's share of total brand mentions in this workspace, with a 95% interval. Overlapping intervals mean the ranking between those brands isn't statistically distinguishable." align="right"/></h2><div className="mt-3 grid gap-3">{data.sov.map((brand,index) => <Link key={brand.id} href={`/mentions?brand_id=${brand.id}`} className="grid grid-cols-[20px_minmax(80px,1fr)_2fr_48px] items-center gap-2 text-sm hover:opacity-80"><span className="numeric text-muted-foreground">{index+1}</span><span className={brand.focus ? "font-bold text-primary dark:text-highlight" : "font-medium"}>{brand.name}</span><Interval brand={brand}/><span className="numeric text-right font-semibold">{(brand.p*100).toFixed(1)}%</span></Link>)}</div>{data.pairs.length > 0 && <p className="mt-4 text-xs text-muted-foreground">{data.pairs.length} pair{data.pairs.length === 1 ? " is" : "s are"} statistically tied (overlapping 95% intervals).</p>}</Card>
    </div>

    {visibleCards.length > 0 && <section><h2 className="mb-2 flex items-center text-base font-semibold">What to act on<InfoHint text="Data-coverage and measurement nudges from the current corpus — how the listening itself can be improved. Dismiss any that aren't relevant; they stay hidden on this browser."/></h2><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{visibleCards.map((card,index) => <ActionCard key={`${card.title}-${index}`} card={card} onDismiss={() => dismissCard(card.title)}/>)}</div></section>}

    <div className="grid gap-4 xl:grid-cols-3">
      <Card className="p-5"><h2 className="mt-0 flex items-center text-base font-semibold">App rating<InfoHint text="Mean star rating across connected app stores, with the 95% interval on the share of reviews rating 4★ or higher. Click a bar to see reviews at that rating."/></h2>{data.reviews ? <><p className="numeric mb-1 text-4xl font-semibold">{data.reviews.overall_avg.toFixed(1)}<span className="text-xl text-warning">★</span></p><p className="text-xs text-muted-foreground">{data.reviews.overall_n} reviews · 95% {(data.reviews.good_lo*100).toFixed(0)}–{(data.reviews.good_hi*100).toFixed(0)}% rate 4★+</p><div className="mt-4 grid gap-1.5">{[5,4,3,2,1].map(star => <Link key={star} href={`/mentions?surface=app_reviews&rating=${star}`} className="grid grid-cols-[28px_1fr_32px] items-center gap-2 rounded-[0.375rem] text-xs hover:bg-muted"><span>{star}★</span><span className="h-2 rounded-full bg-muted"><span className="block h-2 rounded-full bg-warning" style={{width: `${100*data.reviews!.dist[star-1]/data.reviews!.overall_n}%`}}/></span><span className="numeric text-right">{data.reviews!.dist[star-1]}</span></Link>)}</div></> : <p className="py-8 text-center text-sm text-muted-foreground">Connect app-store reviews to see rating quality.</p>}</Card>
      <Card className="p-5"><div className="flex items-center justify-between"><h2 className="mt-0 text-base font-semibold">Recent stories</h2><Link href="/mentions" className="text-xs font-semibold text-primary dark:text-highlight">All mentions →</Link></div><div className="mt-1 divide-y">{data.feed.slice(0,8).map(item => <a key={item.id} href={item.url ?? href(`/mentions?q=${encodeURIComponent(item.text.slice(0,24))}`)} target={item.url ? "_blank" : undefined} rel="noreferrer" className="block py-2.5"><div className="flex items-center gap-2 text-[0.6875rem] text-muted-foreground"><span>{item.brand}</span><span>·</span><span>{item.outlet ?? item.surface}</span>{item.url && <ExternalLink size={10}/>}</div><p className="mb-0 mt-0.5 line-clamp-2 text-sm font-medium">{item.text}</p></a>)}</div></Card>
      <RecentPostsCard/>
    </div>

    {data.admin && <section className="grid gap-4"><div><p className="mb-0.5 text-[0.6875rem] font-bold uppercase tracking-[.16em] text-primary dark:text-highlight">Admin evidence</p><h2 className="m-0 text-lg font-semibold">Measurement quality</h2></div><div className="grid gap-4 xl:grid-cols-3"><AdminTable title="Listening coverage" rows={data.admin.ledger}/><AdminTable title="Entity precision" rows={data.admin.rules}/><AdminTable title="Boundary rejections" rows={data.admin.exclusions.map(([reason,n]) => ({reason: reason || "Unspecified", n}))}/></div></section>}
  </div>;
}

function AdminTable({title, rows}: {title: string; rows: Record<string, unknown>[]}) {return <Card><h3 className="mt-0">{title}</h3>{rows.length ? <div className="max-h-72 overflow-auto"><table className="w-full text-left text-xs"><tbody>{rows.map((row,index) => <tr className="border-t" key={index}>{Object.entries(row).slice(0,3).map(([key,value]) => <td className="py-2 pr-2" key={key}>{String(value ?? "—")}</td>)}</tr>)}</tbody></table></div> : <p className="text-sm text-muted-foreground">No measured rows yet.</p>}</Card>;}

export {MixBar};
