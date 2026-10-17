"use client";

import {useCareAgentReport, useSlaReport} from "@/hooks/use-api";
import {dur} from "@/components/care/supervisor-view";
import {EmptyState, ErrorState, LoadingState} from "@/components/states";
import {Card} from "@/components/ui/card";
import {ExportBar, Measure, RangePicker, useReportRange} from "@/components/reports/report-shell";

/** F5.3 — care activity + SLA compliance. Reconciles against case_event
 * (missed count) and the routing_policy thresholds. */
export function CareSlaTab() {
  const {start, end, setRange} = useReportRange();
  const agents = useCareAgentReport(start, end);
  const sla = useSlaReport(start, end);

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <RangePicker start={start} end={end} onChange={setRange}/>
        <div className="ml-auto"><ExportBar kind="sla" params={{start, end}}/></div>
      </div>

      {sla.isLoading && <LoadingState label="Loading SLA report…"/>}
      {sla.error && <ErrorState message={sla.error.message}/>}
      {sla.data && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Stat label="First-response compliance" value={<Measure m={{kind: "proportion", value: sla.data.first_response.compliance.rate, wilson: sla.data.first_response.compliance.wilson as [number, number]}}/>}
            sub={`${sla.data.first_response.compliance.met} / ${sla.data.first_response.compliance.eligible}`}/>
          <Stat label="Resolution compliance" value={<Measure m={{kind: "proportion", value: sla.data.resolution.compliance.rate, wilson: sla.data.resolution.compliance.wilson as [number, number]}}/>}
            sub={`${sla.data.resolution.compliance.met} / ${sla.data.resolution.compliance.eligible}`}/>
          <Stat label="Avg first response" value={dur(sla.data.first_response.seconds.avg)} sub={`p90 ${dur(sla.data.first_response.seconds.p90)}`}/>
          <Stat label="Avg assignment wait" value={dur(sla.data.assignment_wait.seconds.avg)} sub={`n=${sla.data.assignment_wait.seconds.n}`}/>
          <Stat label="Missed SLAs" value={String(sla.data.missed.total)}
            sub={Object.entries(sla.data.missed.by_check).map(([k, v]) => `${k}: ${v}`).join(" · ") || "none"}/>
          <Stat label="Cases in window" value={String(sla.data.cases)} sub={`policy FRT ${dur(sla.data.policy.first_response_sla)}`}/>
        </div>
      )}

      <h2 className="m-0 text-sm font-semibold text-muted-foreground">Agent activity</h2>
      {agents.isLoading && <LoadingState label="Loading agent activity…"/>}
      {agents.error && <ErrorState message={agents.error.message}/>}
      {agents.data && agents.data.agents.length === 0 && <EmptyState title="No activity" body="No agent sessions in this window."/>}
      {agents.data && agents.data.agents.length > 0 && (
        <Card className="overflow-x-auto">
          <table className="w-full min-w-[47.5rem] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b text-xs text-muted-foreground">
                <th className="py-2">Agent</th><th className="py-2 text-right">Session</th>
                <th className="py-2 text-right">Ready</th><th className="py-2 text-right">Not ready</th>
                <th className="py-2 text-right">Idle</th><th className="py-2 text-right">Cases closed</th>
                <th className="py-2 text-right">Avg handle</th>
              </tr>
            </thead>
            <tbody>
              {agents.data.agents.map((a) => (
                <tr key={a.user_id} className="border-b last:border-0">
                  <td className="py-2">{a.username ?? `#${a.user_id}`}</td>
                  <td className="numeric py-2 text-right">{dur(a.session_seconds)}</td>
                  <td className="numeric py-2 text-right">{dur(a.ready_seconds)}</td>
                  <td className="numeric py-2 text-right">{dur(a.not_ready_seconds)}</td>
                  <td className="numeric py-2 text-right">{dur(a.idle_seconds)}</td>
                  <td className="numeric py-2 text-right">{a.cases_closed}</td>
                  <td className="numeric py-2 text-right">{dur(a.avg_handle_seconds)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
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
