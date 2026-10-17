"use client";

import {useMutation} from "@tanstack/react-query";
import {BellRing, CheckCircle2, Send} from "lucide-react";
import {Link} from "@/components/tenant-link";
import {apiFetch} from "@/lib/api";
import type {AlertDispatchResult, AlertRule, AlertSeverity} from "@/lib/types";
import {useAlerts, useMe} from "@/hooks/use-api";
import {Badge} from "./ui/badge";
import {Button} from "./ui/button";
import {Card} from "./ui/card";
import {PageHeader} from "./viewer-components";
import {ErrorState, LoadingState} from "./states";

const SEVERITY_CLASS: Record<AlertSeverity, string> = {
  critical: "border-danger/40 bg-danger/10 text-danger",
  warning: "border-warning/40 bg-warning/10 text-warning",
};

function Kpi({label, value, sub}: {label: string; value: string | number; sub?: string}) {
  return <Card className="p-5"><p className="m-0 text-xs text-muted-foreground">{label}</p><p className="numeric my-1.5 text-3xl font-semibold tracking-tight">{value}</p><p className="m-0 text-[0.6875rem] text-muted-foreground">{sub ?? " "}</p></Card>;
}

function AlertCard({alert}: {alert: AlertRule}) {
  return <Card className={`rounded-[0.75rem] border-l-4 p-4 ${alert.severity === "critical" ? "border-l-danger" : "border-l-warning"}`}>
    <div className="flex flex-wrap items-center gap-2">
      <Badge className={SEVERITY_CLASS[alert.severity]}>{alert.severity}</Badge>
      <span className="font-semibold">{alert.title}</span>
      <span className="ml-auto numeric text-xs text-muted-foreground">value {alert.value} · threshold {alert.threshold}</span>
    </div>
    <p className="mb-2 mt-2 text-sm text-muted-foreground">{alert.detail}</p>
    <Link href={alert.href} className="text-xs font-semibold text-primary dark:text-highlight">View {alert.href} →</Link>
  </Card>;
}

function DispatchPanel() {
  const dispatch = useMutation({mutationFn: () => apiFetch<AlertDispatchResult>("/alerts/dispatch", {method: "POST"})});
  return <Card className="grid gap-3 p-5">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div><h2 className="m-0 text-sm font-semibold">Dispatch</h2><p className="m-0 text-xs text-muted-foreground">Push the firing alerts to the configured Slack / generic webhook now. Wire <code>ALERT_SLACK_WEBHOOK</code> / <code>ALERT_WEBHOOK_URL</code> in <Link href="/admin" className="font-semibold text-primary dark:text-highlight">Admin → API keys</Link>; run this from cron for scheduled alerting.</p></div>
      <Button onClick={() => dispatch.mutate()} disabled={dispatch.isPending}><Send size={15}/>{dispatch.isPending ? "Sending…" : "Send now"}</Button>
    </div>
    {dispatch.data && <div className="rounded-[0.625rem] bg-muted p-3 text-xs">
      <p className="m-0">Sent to: <b>{dispatch.data.sent.join(", ") || "no channel configured"}</b> · {dispatch.data.firing} firing</p>
      {dispatch.data.errors.map(error => <p key={error.channel} className="m-0 text-danger">{error.channel}: {error.error}</p>)}
      <pre className="mt-2 whitespace-pre-wrap font-mono text-[0.6875rem] text-muted-foreground">{dispatch.data.text}</pre>
    </div>}
    {dispatch.error && <p className="text-xs text-danger">{(dispatch.error as Error).message}</p>}
  </Card>;
}

export function AlertsView() {
  const result = useAlerts();
  const me = useMe();
  if (result.isLoading) return <LoadingState label="Evaluating alerts…"/>;
  if (result.error) return <ErrorState message={result.error.message}/>;
  const data = result.data;
  if (!data) return <ErrorState message="The alerts response was empty."/>;
  const isAdmin = me.data?.user?.role === "admin";

  return <div className="mx-auto grid max-w-[75rem] gap-5">
    <PageHeader title="Alert center" subtitle="Deterministic threshold rules over the analysis surfaces — what needs attention right now." stat={<span className="text-xs text-muted-foreground">{data.counts.rules} rules</span>}/>

    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Kpi label="Firing" value={data.counts.firing} sub={`${data.counts.rules} rules evaluated`}/>
      <Kpi label="Critical" value={data.counts.critical}/>
      <Kpi label="Warning" value={data.counts.warning}/>
      <Kpi label="All clear" value={data.counts.firing === 0 ? "yes" : "no"}/>
    </div>

    {data.firing.length
      ? <div className="grid gap-3">{data.firing.map(alert => <AlertCard key={alert.key} alert={alert}/>)}</div>
      : <Card className="flex items-center gap-3 p-5 text-sm text-muted-foreground"><CheckCircle2 className="text-success" size={18}/>No alert rule is firing. All monitored surfaces are within threshold.</Card>}

    {isAdmin && <DispatchPanel/>}

    <Card className="p-5">
      <div className="flex items-center gap-2"><BellRing size={16} className="text-muted-foreground"/><h2 className="m-0 text-base font-semibold">All rules</h2></div>
      <div className="mt-3 overflow-x-auto"><table className="w-full min-w-[35rem] border-collapse text-left text-sm">
        <thead><tr className="border-b text-xs text-muted-foreground"><th className="py-2 pr-3">Rule</th><th className="py-2 pr-3 text-right">Value</th><th className="py-2 pr-3 text-right">Threshold</th><th className="py-2">Status</th></tr></thead>
        <tbody>{data.alerts.map(alert => <tr key={alert.key} className="border-b last:border-0">
          <td className="py-2.5 pr-3"><Link href={alert.href} className="hover:text-primary">{alert.title}</Link></td>
          <td className="numeric py-2.5 pr-3 text-right">{alert.value}</td>
          <td className="numeric py-2.5 pr-3 text-right text-muted-foreground">{alert.threshold}</td>
          <td className="py-2.5">{alert.fired ? <Badge className={SEVERITY_CLASS[alert.severity]}>{alert.severity}</Badge> : <span className="text-xs text-success">ok</span>}</td>
        </tr>)}</tbody>
      </table></div>
      <details className="mt-4 text-xs text-muted-foreground"><summary className="cursor-pointer font-medium">Thresholds ({Object.keys(data.config).length})</summary>
        <dl className="mt-2 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 rounded-[0.625rem] bg-muted p-3">{Object.entries(data.config).map(([key, value]) => <div key={key} className="contents"><dt>{key}</dt><dd className="numeric text-right">{String(value)}</dd></div>)}</dl>
        <p className="mt-2">Override with the <code>ALERT_CONFIG</code> key (JSON).</p>
      </details>
    </Card>
  </div>;
}
