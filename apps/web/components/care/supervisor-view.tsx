"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import dynamic from "next/dynamic";
import {useState} from "react";
import {useSearchParams} from "next/navigation";
import {Link, useTenantRouter as useRouter} from "@/components/tenant-link";
import {useRealtime} from "@/hooks/use-realtime";
import {useCareAgentReport, useCarePending, useCareQueues, useCareRoster, useMe} from "@/hooks/use-api";
import {apiFetch} from "@/lib/api";
import {cn} from "@/lib/utils";
import type {CareAgentReportRow, CarePendingRow} from "@/lib/types";
import {useTenantHref} from "@/components/tenant-link";
import {AgentAvatar, PresenceDot} from "@/components/care/primitives";
import {AssignmentRuleCard} from "@/components/care/assignment-rule-card";
import {RealtimeBanner} from "@/components/care/realtime-banner";
import {SupervisorAnalytics} from "@/components/care/supervisor-analytics";
import {EmptyState, ErrorState, LoadingState} from "@/components/states";
import {Button} from "@/components/ui/button";
import {Card} from "@/components/ui/card";
import {Select} from "@/components/ui/select";
import {TabBar} from "@/components/ui/tab-bar";

// Care & SLA / CSAT & complaints / MIS moved here from Reports (2026-09-14,
// Hamza) — same components (apps/web/components/care/{care-sla,csat,mis}
// -tab.tsx), just hosted here now. Lazy-loaded, same as they were as Reports
// tabs, so they don't ship on first load of the console.
const loading = () => <LoadingState label="Loading…"/>;
const CareSlaTab = dynamic(() => import("@/components/care/care-sla-tab").then((m) => m.CareSlaTab), {loading});
const CsatTab = dynamic(() => import("@/components/care/csat-tab").then((m) => m.CsatTab), {loading});
const MisTab = dynamic(() => import("@/components/care/mis-tab").then((m) => m.MisTab), {loading});

const TABS = [
  {key: "overview", label: "Overview"},
  {key: "roster", label: "Roster"},
  {key: "queues", label: "Queues"},
  {key: "approvals", label: "Approvals"},
  {key: "performance", label: "Performance"},
  {key: "care-sla", label: "Care & SLA"},
  {key: "csat", label: "CSAT & complaints"},
  {key: "mis", label: "MIS"},
] as const;

export function dur(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m`;
  return `${s}s`;
}

const today = () => new Date().toISOString().slice(0, 10);

export function SupervisorView() {
  const params = useSearchParams();
  const router = useRouter();
  const tab = TABS.some((t) => t.key === params.get("tab")) ? params.get("tab")! : "overview";

  function goTab(key: string) {
    const sp = new URLSearchParams(params.toString());
    sp.set("tab", key);
    router.replace(`/care/supervisor?${sp}`);
  }

  return (
    <div className="mx-auto grid max-w-[87.5rem] gap-5">
      <RealtimeBanner/>
      <div>
        <p className="mb-0.5 text-sm font-semibold text-primary dark:text-highlight">Social care</p>
        <h1 className="m-0 text-2xl font-semibold tracking-tight">Supervisor console</h1>
      </div>
      <TabBar label="Supervisor tabs" items={TABS.map((t) => ({key: t.key, label: t.label}))} value={tab} onChange={goTab}/>

      {tab === "overview" && <SupervisorAnalytics/>}
      {tab === "roster" && <RosterTab/>}
      {tab === "queues" && <QueuesTab/>}
      {tab === "approvals" && <ApprovalsTab/>}
      {tab === "performance" && <PerformanceTab/>}
      {tab === "care-sla" && <CareSlaTab/>}
      {tab === "csat" && <CsatTab/>}
      {tab === "mis" && <MisTab/>}
    </div>
  );
}

function pct(n: number | null): string {
  return n == null ? "—" : `${Math.round(n * 100)}%`;
}

// Per-agent comparison Hamza asked for -- "fastest agent, most no of cases
// solved by this agent etc" -- derived from the same window/table below, not
// a second fetch. Needs at least two agents with real data to mean anything.
function Leaderboard({agents}: {agents: CareAgentReportRow[]}) {
  const withResponse = agents.filter((a) => a.avg_first_response_seconds != null);
  const withClosed = agents.filter((a) => a.cases_closed > 0);
  const fastest = withResponse.length >= 2
    ? withResponse.reduce((best, a) => (a.avg_first_response_seconds! < best.avg_first_response_seconds! ? a : best))
    : null;
  const mostClosed = withClosed.length >= 2
    ? withClosed.reduce((best, a) => (a.cases_closed > best.cases_closed ? a : best))
    : null;
  if (!fastest && !mostClosed) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {fastest && (
        <span className="rounded-full border border-success/40 bg-success/10 px-3 py-1 text-xs font-semibold text-success">
          Fastest first response — {fastest.username ?? `#${fastest.user_id}`} ({dur(fastest.avg_first_response_seconds)})
        </span>
      )}
      {mostClosed && (
        <span className="rounded-full border border-highlight/40 bg-highlight/10 px-3 py-1 text-xs font-semibold text-highlight">
          Most cases closed — {mostClosed.username ?? `#${mostClosed.user_id}`} ({mostClosed.cases_closed})
        </span>
      )}
    </div>
  );
}

function PerformanceTab() {
  const href = useTenantHref();
  const [start, setStart] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 6);
    return d.toISOString().slice(0, 10);
  });
  const [end, setEnd] = useState(today());
  const [agent, setAgent] = useState("");

  const report = useCareAgentReport(start, end);
  const agents = (report.data?.agents ?? []).filter((a) => !agent || String(a.user_id) === agent);
  const exportQS = `kind=care_agents&start=${start}&end=${end}`;

  return (
    <Card className="grid gap-3 overflow-x-auto">
      <div className="flex flex-wrap items-center gap-2">
        <input type="date" aria-label="Start date" value={start} onChange={(e) => setStart(e.target.value)}
          className="h-9 rounded-[0.625rem] border bg-card px-2 text-xs"/>
        <span className="text-xs text-muted-foreground">to</span>
        <input type="date" aria-label="End date" value={end} onChange={(e) => setEnd(e.target.value)}
          className="h-9 rounded-[0.625rem] border bg-card px-2 text-xs"/>
        <Select aria-label="Filter agent" value={agent} onChange={(e) => setAgent(e.target.value)}
          className="h-9 max-w-40 text-xs">
          <option value="">All agents</option>
          {(report.data?.agents ?? []).map((a) => (
            <option key={a.user_id} value={a.user_id}>{a.username ?? `#${a.user_id}`}</option>
          ))}
        </Select>
        <span className="ml-auto flex gap-1">
          {(["csv", "xlsx", "pdf"] as const).map((f) => (
            <a key={f} download href={href(`/api/v1/reports/export?${exportQS}&format=${f}`)}
              className="rounded-[0.5rem] border bg-card px-2.5 py-1.5 text-xs font-semibold hover:bg-muted">
              {f.toUpperCase()}
            </a>
          ))}
        </span>
      </div>

      {report.isLoading && <LoadingState label="Loading performance…"/>}
      {report.error && <ErrorState message={report.error.message}/>}
      {report.data && agents.length === 0 && <EmptyState title="No data" body="No agent activity in this window."/>}
      {report.data && agents.length > 0 && <Leaderboard agents={agents}/>}
      {report.data && agents.length > 0 && (
        <table className="w-full min-w-[51.25rem] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b text-xs text-muted-foreground">
              <th className="py-2">Agent</th>
              <th className="py-2 text-right">Cases closed</th>
              <th className="py-2 text-right">Avg first response</th>
              <th className="py-2 text-right">Avg handle time</th>
              <th className="py-2 text-right">Occupancy</th>
              <th className="py-2 text-right">Session</th>
              <th className="py-2 text-right">Ready / idle</th>
            </tr>
          </thead>
          <tbody>
            {agents.map((a) => (
              <tr key={a.user_id} className="border-b last:border-0">
                <td className="py-3">{a.username ?? `#${a.user_id}`}</td>
                <td className="numeric py-3 text-right">{a.cases_closed}</td>
                <td className="numeric py-3 text-right">{dur(a.avg_first_response_seconds)}</td>
                <td className="numeric py-3 text-right">{dur(a.avg_handle_seconds)}</td>
                <td className="numeric py-3 text-right">{pct(a.occupancy)}</td>
                <td className="numeric py-3 text-right text-muted-foreground">{dur(a.session_seconds)}</td>
                <td className="numeric py-3 text-right text-muted-foreground">{dur(a.ready_seconds)} / {dur(a.idle_seconds)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

function ApprovalsTab() {
  const query = useQueryClient();
  const pending = useCarePending();
  const refresh = () => {
    query.invalidateQueries({queryKey: ["care", "pending"]});
    query.invalidateQueries({queryKey: ["care", "cases"]});
  };

  if (pending.isLoading) return <LoadingState label="Loading approvals…"/>;
  if (pending.error) return <ErrorState message={pending.error.message}/>;
  const rows = pending.data?.pending ?? [];
  if (rows.length === 0) return <EmptyState title="Nothing to approve" body="No replies are held for approval right now."/>;

  return (
    <div className="grid gap-3">
      {rows.map((p) => (
        <ApprovalCard key={p.id} row={p} onDone={refresh}/>
      ))}
    </div>
  );
}

function ApprovalCard({row, onDone}: {row: CarePendingRow; onDone: () => void}) {
  const [text, setText] = useState(row.request?.text ?? "");
  const [note, setNote] = useState("");
  const dirty = text !== (row.request?.text ?? "");

  const edit = useMutation({
    mutationFn: () => apiFetch(`/care/outbound/${row.id}`, {method: "PUT", body: JSON.stringify({text})}),
  });
  const approve = useMutation({
    mutationFn: async () => {
      if (dirty) await apiFetch(`/care/outbound/${row.id}`, {method: "PUT", body: JSON.stringify({text})});
      return apiFetch(`/care/outbound/${row.id}/approve`, {method: "POST"});
    },
    onSuccess: onDone,
  });
  const reject = useMutation({
    mutationFn: () => apiFetch(`/care/outbound/${row.id}/reject`, {method: "POST", body: JSON.stringify({note})}),
    onSuccess: onDone,
  });
  const busy = edit.isPending || approve.isPending || reject.isPending;

  return (
    <Card className="grid gap-2">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span className="rounded-full border bg-muted px-1.5 py-0.5 font-semibold">{row.platform} · {row.action}</span>
        {row.request?.case_id != null && (
          <Link href={`/care?case=${row.request.case_id}`} className="font-semibold text-primary dark:text-highlight">
            open C-{row.request.case_id}
          </Link>
        )}
        <span className="ml-auto">by {row.actor ?? "—"} · {new Date(row.created_at).toLocaleString()}</span>
      </div>
      <textarea aria-label="Held reply text" value={text} onChange={(e) => setText(e.target.value)} rows={3}
        className="w-full resize-y rounded-[0.625rem] border bg-card p-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-highlight/40"/>
      <input aria-label="Rejection note" value={note} onChange={(e) => setNote(e.target.value)}
        placeholder="Note to the agent (if rejecting)…"
        className="h-9 rounded-[0.625rem] border bg-card px-2.5 text-xs placeholder:text-muted-foreground"/>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" className="h-8 text-xs" disabled={busy} onClick={() => approve.mutate()}>
          {dirty ? "Save & approve" : "Approve"}
        </Button>
        <Button type="button" variant="outline" className="h-8 text-xs" disabled={busy || dirty}
          onClick={() => edit.mutate()}>Save edit</Button>
        <Button type="button" variant="danger" className="h-8 text-xs" disabled={busy}
          onClick={() => reject.mutate()}>Reject</Button>
        {(approve.error || reject.error || edit.error) &&
          <span className="text-xs text-danger">{((approve.error || reject.error || edit.error) as Error).message}</span>}
      </div>
    </Card>
  );
}

function QueuesTab() {
  const query = useQueryClient();
  const me = useMe();
  const wsId = me.data?.user.workspace?.id;
  const queues = useCareQueues();

  useRealtime(wsId != null ? `queue:${wsId}` : null, () => {
    query.invalidateQueries({queryKey: ["care", "queues"]});
  });

  if (queues.isLoading) return <LoadingState label="Loading queues…"/>;
  if (queues.error) return <ErrorState message={queues.error.message}/>;
  const rows = queues.data?.queues ?? [];
  if (rows.length === 0) return <EmptyState title="Queues are clear" body="No open cases in any channel."/>;

  return (
    <Card className="overflow-x-auto">
      <table className="w-full min-w-[40rem] border-collapse text-left text-sm">
        <thead>
          <tr className="border-b text-xs text-muted-foreground">
            <th className="py-2">Channel / page</th>
            <th className="py-2 text-right">Open</th>
            <th className="py-2 text-right">Unassigned</th>
            <th className="py-2 text-right">Oldest waiting</th>
            <th className="py-2 text-right">SLA at risk</th>
            <th className="py-2 text-right">SLA breached</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.channel ?? "—"} className={cn("border-b last:border-0", r.breached > 0 && "bg-danger/5")}>
              <td className="py-3 font-medium">{r.channel ?? "unknown"}</td>
              <td className="numeric py-3 text-right">{r.open}</td>
              <td className={cn("numeric py-3 text-right", r.unassigned > 0 && "font-semibold text-warning")}>{r.unassigned}</td>
              <td className="numeric py-3 text-right text-muted-foreground">{dur(r.oldest_waiting_s)}</td>
              <td className={cn("numeric py-3 text-right", r.at_risk > 0 && "font-semibold text-warning")}>{r.at_risk}</td>
              <td className={cn("numeric py-3 text-right", r.breached > 0 && "font-semibold text-danger")}>{r.breached}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function statusLabel(a: {available: number; presence: string}): {label: string; presence: "online" | "idle" | "offline" | "unknown"} {
  if (a.presence === "offline" || a.presence === "unknown") return {label: "Offline", presence: "offline"};
  if (a.presence === "idle") return {label: "Busy", presence: "idle"};
  return a.available ? {label: "Available", presence: "online"} : {label: "Not available", presence: "offline"};
}

function RosterTab() {
  const query = useQueryClient();
  const me = useMe();
  const wsId = me.data?.user.workspace?.id;
  const roster = useCareRoster();
  const report = useCareAgentReport(today(), today());
  const sessionByUser = new Map((report.data?.agents ?? []).map((a) => [a.user_id, a.session_seconds]));

  useRealtime(wsId != null ? `presence:${wsId}` : null, () => {
    query.invalidateQueries({queryKey: ["care", "roster"]});
  });

  const override = useMutation({
    mutationFn: ({userId, available}: {userId: number; available: boolean}) =>
      apiFetch(`/care/agents/${userId}/status`, {method: "POST", body: JSON.stringify({available})}),
    onSuccess: () => query.invalidateQueries({queryKey: ["care", "roster"]}),
  });

  if (roster.isLoading) return <LoadingState label="Loading roster…"/>;
  if (roster.error) return <ErrorState message={roster.error.message}/>;
  const agents = roster.data?.agents ?? [];
  if (agents.length === 0) return <EmptyState title="No agents" body="No care agents are configured for this workspace."/>;

  return (
    <div className="space-y-4">
      <AssignmentRuleCard/>
      <Card className="overflow-x-auto">
        <table className="w-full min-w-[42.5rem] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b text-xs text-muted-foreground">
              <th className="py-2">Agent</th>
              <th className="py-2">Status</th>
              <th className="py-2 text-right">Live / capacity</th>
              <th className="py-2 text-right">Session today</th>
              <th className="py-2 text-right">Override</th>
            </tr>
          </thead>
          <tbody>
            {agents.map((a) => {
              const st = statusLabel(a);
              const over = a.live >= a.capacity;
              return (
                <tr key={a.user_id} className="border-b last:border-0">
                  <td className="py-3"><span className="inline-flex items-center gap-2"><AgentAvatar name={a.username} presence={st.presence} size="sm"/>{a.username}</span></td>
                  <td className="py-3"><span className="inline-flex items-center gap-1.5 text-xs"><PresenceDot presence={st.presence}/>{st.label}</span></td>
                  <td className={cn("numeric py-3 text-right", over && "font-semibold text-danger")}>{a.live} / {a.capacity}</td>
                  <td className="numeric py-3 text-right text-muted-foreground">{dur(sessionByUser.get(a.user_id))}</td>
                  <td className="py-3 text-right">
                    <Select aria-label={`Override ${a.username} status`} className="ml-auto h-8 max-w-32 text-xs"
                      value={a.available ? "available" : "not"}
                      onChange={(e) => override.mutate({userId: a.user_id, available: e.target.value === "available"})}>
                      <option value="available">Available</option>
                      <option value="not">Not available</option>
                    </Select>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
