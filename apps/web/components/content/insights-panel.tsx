"use client";

import {BarChart3} from "lucide-react";
import {useState} from "react";
import {useContentImpact, useContentInsights} from "@/hooks/use-api";
import type {ContentInsights} from "@/lib/types";
import {cn} from "@/lib/utils";
import {Card} from "@/components/ui/card";
import {fmtRate} from "./format";
import {ImpactList} from "./impact-list";
import {TimingStrip} from "./timing-strip";
import {TabBar} from "@/components/ui/tab-bar";

const TABS = [["digest", "Digest"], ["posts", "Posts"], ["timing", "Timing"], ["impact", "Did it help?"]] as const;
type Tab = (typeof TABS)[number][0];

const BAND: Record<string, string> = {above: "bg-success/15 text-success", below: "bg-warning/15 text-warning", typical: "bg-muted text-muted-foreground"};
const DIGEST_DOT: Record<ContentInsights["digest"][number]["kind"], string> = {
  risk: "bg-danger", win: "bg-success", topic: "bg-primary", timing: "bg-highlight", empty: "bg-muted-foreground",
};

function Digest({data}: {data: ContentInsights}) {
  return (
    <ul className="m-0 grid list-none gap-2 p-0">
      {data.digest.map((d, i) => (
        <li key={i} className="flex gap-2 text-sm">
          <span aria-hidden className={cn("mt-1.5 size-2 shrink-0 rounded-full", DIGEST_DOT[d.kind])}/>
          <span>{d.text}{d.url && <> <a href={d.url} target="_blank" rel="noreferrer" className="text-xs text-primary underline dark:text-highlight">open</a></>}</span>
        </li>
      ))}
      {data.baseline.note && <li className="text-xs text-muted-foreground">{data.baseline.note}</li>}
    </ul>
  );
}

function Posts({data}: {data: ContentInsights}) {
  if (data.posts.length === 0) return <p className="m-0 text-xs text-muted-foreground">No owned posts collected yet.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[40rem] border-collapse text-left text-xs">
        <thead className="text-muted-foreground">
          <tr><th className="py-1 pr-2">Post</th><th className="pr-2">Engagement</th><th className="pr-2">Scam comments</th><th>Complaints</th></tr>
        </thead>
        <tbody>
          {data.posts.map((p, i) => (
            <tr key={i} className="border-t align-top">
              <td className="py-1.5 pr-2">
                <span className="text-muted-foreground">{p.platform}</span>{" "}
                {p.url ? <a href={p.url} target="_blank" rel="noreferrer" className="text-primary underline dark:text-highlight">{p.text || "(no text)"}</a> : p.text || "(no text)"}
                {p.scammers_working_it && <span className="ml-1.5 rounded-full bg-danger/15 px-1.5 py-0.5 text-[0.625rem] font-semibold text-danger">scammers active</span>}
              </td>
              <td className="pr-2">
                {p.engagement === null ? <span className="text-muted-foreground">not reported</span> : (
                  <>{p.engagement}{p.band && <span className={cn("ml-1.5 rounded-full px-1.5 py-0.5 text-[0.625rem] font-semibold", BAND[p.band])}>{p.vs_baseline}x · {p.band}</span>}</>
                )}
              </td>
              <td className="pr-2">{p.comments ? fmtRate(p.comments.scam_flagged) : <span className="text-muted-foreground">not analysed</span>}</td>
              <td>{p.comments ? fmtRate(p.comments.complaints) : <span className="text-muted-foreground">not analysed</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {data.topics.length > 0 && (
        <p className="m-0 mt-2 text-[0.6875rem] text-muted-foreground">
          Topics by average engagement: {data.topics.map((t) => `${t.label} (${t.avg_engagement ?? "n/a"}, ${t.posts} posts)`).join(" · ")}
        </p>
      )}
    </div>
  );
}

/** What customers do around the brand's own posts -- engagement, scam activity,
 * timing, and whether published posts moved the numbers. */
export function InsightsPanel() {
  const [tab, setTab] = useState<Tab>("digest");
  const insights = useContentInsights();
  const impact = useContentImpact();

  return (
    <Card className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <BarChart3 size={14} className="text-muted-foreground"/>
        <h2 className="m-0 text-xs font-semibold text-muted-foreground">Audience insights</h2>
        <TabBar mode="tab" label="Insight views" className="ml-auto" items={TABS.map(([key, label]) => ({key, label}))} value={tab} onChange={(key) => setTab(key as Tab)}/>
      </div>
      {tab !== "impact" && insights.isLoading && <p className="m-0 text-xs text-muted-foreground">Reading posts and comments…</p>}
      {tab !== "impact" && insights.error && <p className="m-0 text-xs text-danger">{insights.error.message}</p>}
      {tab === "digest" && insights.data && <Digest data={insights.data}/>}
      {tab === "posts" && insights.data && <Posts data={insights.data}/>}
      {tab === "timing" && insights.data && <TimingStrip timing={insights.data.timing}/>}
      {tab === "impact" && impact.isLoading && <p className="m-0 text-xs text-muted-foreground">Comparing before and after…</p>}
      {tab === "impact" && impact.error && <p className="m-0 text-xs text-danger">{impact.error.message}</p>}
      {tab === "impact" && impact.data && <ImpactList impact={impact.data}/>}
    </Card>
  );
}
