"use client";

import {useState} from "react";
import {useSocialReport} from "@/hooks/use-api";
import type {SocialPost} from "@/lib/types";
import {ChannelBadge} from "@/components/care/primitives";
import {EmptyState, ErrorState, LoadingState} from "@/components/states";
import {Card} from "@/components/ui/card";
import {Select} from "@/components/ui/select";
import {ExportBar, Measure, RangePicker, useReportRange} from "@/components/reports/report-shell";

const SOURCES = ["meta", "instagram", "x", "linkedin"];

/** F5.4 — account/post/video/Reel scorecards + engagement by media type, all
 * Wilson-scored where they're proportions. */
export function SocialTab() {
  const {start, end, setRange} = useReportRange();
  const [source, setSource] = useState(SOURCES[0]);
  const report = useSocialReport(source, start, end);

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Select aria-label="Source" value={source} onChange={(e) => setSource(e.target.value)} className="h-9 max-w-32 text-xs">
          {SOURCES.map((s) => <option key={s} value={s}>{s}</option>)}
        </Select>
        <RangePicker start={start} end={end} onChange={setRange}/>
        <div className="ml-auto"><ExportBar kind="social" params={{source, start, end}}/></div>
      </div>

      {report.isLoading && <LoadingState label="Loading social report…"/>}
      {report.error && <ErrorState message={report.error.message}/>}
      {report.data && Object.keys(report.data.account).length === 0
        && report.data.posts.length === 0 && report.data.video.length === 0 && report.data.reels.length === 0 && (
        <EmptyState title="No social data yet" body={`No account or post-level metrics for "${source}" in this range yet.`}/>
      )}
      {report.data && (Object.keys(report.data.account).length > 0
        || report.data.posts.length > 0 || report.data.video.length > 0 || report.data.reels.length > 0) && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {Object.entries(report.data.account).map(([metric, m]) => (
              <Card key={metric} className="grid gap-1">
                <p className="m-0 text-xs capitalize text-muted-foreground">{metric.replaceAll("_", " ")}</p>
                <p className="numeric m-0 text-xl font-semibold"><Measure m={m.measure} digits={2}/></p>
                {m.comparison?.pct != null && (
                  <p className={`m-0 text-[0.6875rem] ${m.comparison.pct >= 0 ? "text-success" : "text-danger"}`}>
                    {m.comparison.pct >= 0 ? "+" : ""}{(m.comparison.pct * 100).toFixed(0)}% vs prior
                  </p>
                )}
              </Card>
            ))}
          </div>

          <div>
            <h2 className="m-0 mb-2 text-sm font-semibold text-muted-foreground">Engagement by media type</h2>
            <div className="flex flex-wrap gap-3">
              {report.data.engagement_by_media_type.length === 0 && <p className="text-sm text-muted-foreground">No post-level data yet.</p>}
              {report.data.engagement_by_media_type.map((g) => (
                <Card key={g.media_type} className="grid gap-1">
                  <ChannelBadge channel={g.media_type}/>
                  <p className="numeric m-0 text-lg font-semibold"><Measure m={g} digits={1}/></p>
                </Card>
              ))}
            </div>
          </div>

          <PostTable title="Top posts" rows={report.data.posts}/>
          <PostTable title="Video" rows={report.data.video}/>
          <PostTable title="Reels" rows={report.data.reels}/>
        </>
      )}
    </div>
  );
}

function PostTable({title, rows}: {title: string; rows: SocialPost[]}) {
  if (rows.length === 0) {
    return (
      <div>
        <h2 className="m-0 mb-2 text-sm font-semibold text-muted-foreground">{title}</h2>
        <p className="m-0 text-sm text-muted-foreground">No {title.toLowerCase()} data yet.</p>
      </div>
    );
  }
  return (
    <div>
      <h2 className="m-0 mb-2 text-sm font-semibold text-muted-foreground">{title}</h2>
      <Card className="overflow-x-auto">
        <table className="w-full min-w-[35rem] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b text-xs text-muted-foreground">
              <th className="py-2">Post</th><th className="py-2">Media</th>
              <th className="py-2 text-right">Impressions</th><th className="py-2 text-right">Engagements</th>
              <th className="py-2 text-right">Engagement rate</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 10).map((p) => (
              <tr key={p.post} className="border-b last:border-0">
                <td className="max-w-40 truncate py-2">{p.post}</td>
                <td className="py-2"><ChannelBadge channel={p.media_type}/></td>
                <td className="numeric py-2 text-right">{p.impressions?.toLocaleString() ?? "—"}</td>
                <td className="numeric py-2 text-right">{p.engagements?.toLocaleString() ?? "—"}</td>
                <td className="py-2 text-right"><Measure m={p.engagement_rate}/></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
