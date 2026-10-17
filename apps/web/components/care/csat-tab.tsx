"use client";

import {useCsatReport, useComplaintReport} from "@/hooks/use-api";
import {dur} from "@/components/care/supervisor-view";
import {EmptyState, ErrorState, LoadingState} from "@/components/states";
import {Card} from "@/components/ui/card";
import {ExportBar, Measure, RangePicker, useReportRange} from "@/components/reports/report-shell";

/** F5.5 — CSAT / NPS / CES + complaint analytics. Response rate and CSAT are
 * Wilson-scored proportions. */
export function CsatTab() {
  const {start, end, setRange} = useReportRange();
  const csat = useCsatReport(start, end);
  const complaints = useComplaintReport(start, end);

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <RangePicker start={start} end={end} onChange={setRange}/>
        <div className="ml-auto flex gap-2">
          <ExportBar kind="csat" params={{start, end}}/>
          <ExportBar kind="complaints" params={{start, end}}/>
        </div>
      </div>

      {csat.isLoading && <LoadingState label="Loading CSAT…"/>}
      {csat.error && <ErrorState message={csat.error.message}/>}
      {csat.data && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Stat label="Response rate" value={<Measure m={{kind: "proportion", value: csat.data.response_rate.rate, wilson: csat.data.response_rate.wilson as [number, number]}}/>} sub={`${csat.data.responses} / ${csat.data.issued} issued`}/>
          <Stat label="CSAT" value={<Measure m={{kind: "proportion", value: csat.data.csat.rate, wilson: csat.data.csat.wilson as [number, number]}}/>} sub={`${csat.data.csat.k} / ${csat.data.csat.n} satisfied`}/>
          <Stat label="Avg score" value={csat.data.avg_score?.toFixed(1) ?? "no data"}/>
          <Stat label="NPS" value={csat.data.nps == null ? "n/a" : String(csat.data.nps)}/>
        </div>
      )}

      {csat.data && Object.keys(csat.data.distribution).length > 0 && (
        <Card>
          <h2 className="m-0 mb-2 text-sm font-semibold text-muted-foreground">Score distribution</h2>
          <div className="flex items-end gap-2">
            {Object.entries(csat.data.distribution).map(([score, n]) => {
              const max = Math.max(...Object.values(csat.data!.distribution));
              return (
                <div key={score} className="grid justify-items-center gap-1">
                  <span className="numeric text-xs text-muted-foreground">{n}</span>
                  <div className="w-8 rounded-t-[0.375rem] bg-primary/60" style={{height: `${Math.max(6, (n / max) * 80)}px`}}/>
                  <span className="text-xs font-semibold">{score}</span>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {csat.data && csat.data.comments.length > 0 && (
        <Card className="grid gap-2">
          <h2 className="m-0 text-sm font-semibold text-muted-foreground">Comments</h2>
          {csat.data.comments.slice(0, 8).map((c, i) => (
            <p key={i} className="m-0 text-sm">
              <span className="numeric mr-2 font-semibold text-muted-foreground">{c.score ?? "—"}</span>
              {c.comment}
            </p>
          ))}
        </Card>
      )}

      <h2 className="m-0 text-sm font-semibold text-muted-foreground">Complaint analytics</h2>
      {complaints.isLoading && <LoadingState label="Loading complaints…"/>}
      {complaints.error && <ErrorState message={complaints.error.message}/>}
      {complaints.data && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Stat label="Total" value={String(complaints.data.total)} sub={`${complaints.data.closed} closed · ${complaints.data.open} open`}/>
            <Stat label="Reopen rate" value={<Measure m={{kind: "proportion", value: complaints.data.reopen_rate.rate, wilson: complaints.data.reopen_rate.wilson as [number, number]}}/>}/>
            <Stat label="Avg resolution" value={dur(complaints.data.avg_resolution_seconds)}/>
            <Stat label="Avg CSAT" value={complaints.data.avg_csat?.toFixed(1) ?? "no data"}/>
          </div>
          {complaints.data.total === 0
            ? <EmptyState title="No complaints" body="No cases opened in this window."/>
            : (
              <div className="grid gap-4 sm:grid-cols-2">
                <BreakdownCard title="By category" data={complaints.data.by_category}/>
                <BreakdownCard title="By channel" data={complaints.data.by_channel}/>
              </div>
            )}
        </>
      )}
    </div>
  );
}

function Stat({label, value, sub}: {label: string; value: React.ReactNode; sub?: string}) {
  return (
    <Card className="grid gap-1">
      <p className="m-0 text-xs text-muted-foreground">{label}</p>
      <p className="numeric m-0 text-xl font-semibold">{value}</p>
      {sub && <p className="m-0 text-[0.6875rem] text-muted-foreground">{sub}</p>}
    </Card>
  );
}

function BreakdownCard({title, data}: {title: string; data: Record<string, number>}) {
  const entries = Object.entries(data);
  return (
    <Card className="grid gap-1.5">
      <h3 className="m-0 text-xs font-semibold text-muted-foreground">{title}</h3>
      {entries.length === 0 && <p className="m-0 text-xs text-muted-foreground">None.</p>}
      {entries.map(([k, v]) => (
        <div key={k} className="flex items-center justify-between text-sm">
          <span>{k}</span><span className="numeric font-semibold">{v}</span>
        </div>
      ))}
    </Card>
  );
}
