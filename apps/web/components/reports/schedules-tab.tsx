"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {useReportSchedules} from "@/hooks/use-api";
import {apiFetch} from "@/lib/api";
import {EmptyState, ErrorState, LoadingState} from "@/components/states";
import {Button} from "@/components/ui/button";
import {Card} from "@/components/ui/card";

/** F5.7 — saved report schedules: create / edit / delete / run-now / delivery
 * history with last status. Creation happens from each report tab's
 * "Schedule…" button (report-shell); this tab is the management surface. */
export function SchedulesTab() {
  const query = useQueryClient();
  const list = useReportSchedules();
  const refresh = () => query.invalidateQueries({queryKey: ["reports", "schedules"]});

  const run = useMutation({mutationFn: (id: number) => apiFetch(`/reports/schedules/${id}/run`, {method: "POST"}), onSuccess: refresh});
  const toggle = useMutation({
    mutationFn: ({id, active, name, kind, cron, format, recipients}: {id: number; active: boolean; name: string; kind: string; cron: string; format: string; recipients: string[]}) =>
      apiFetch(`/reports/schedules/${id}`, {method: "PUT", body: JSON.stringify({name, kind, cron, format, recipients, active})}),
    onSuccess: refresh,
  });
  const remove = useMutation({mutationFn: (id: number) => apiFetch(`/reports/schedules/${id}`, {method: "DELETE"}), onSuccess: refresh});

  if (list.isLoading) return <LoadingState label="Loading schedules…"/>;
  if (list.error) return <ErrorState message={list.error.message}/>;
  const rows = list.data?.schedules ?? [];
  if (rows.length === 0) {
    return <EmptyState title="No scheduled reports" body="Use “Schedule…” on any report tab to create one."/>;
  }

  return (
    <Card className="overflow-x-auto">
      <table className="w-full min-w-[51.25rem] border-collapse text-left text-sm">
        <thead>
          <tr className="border-b text-xs text-muted-foreground">
            <th className="py-2">Name</th><th className="py-2">Kind</th><th className="py-2">Cron</th>
            <th className="py-2">Recipients</th><th className="py-2">Last run</th><th className="py-2">Status</th>
            <th className="py-2 text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.id} className="border-b last:border-0">
              <td className="py-2 font-medium">{s.name}</td>
              <td className="py-2">{s.kind}</td>
              <td className="numeric py-2 text-xs">{s.cron}</td>
              <td className="max-w-40 truncate py-2 text-xs">{s.recipients.join(", ")}</td>
              <td className="py-2 text-xs text-muted-foreground">{s.last_run_at ? new Date(s.last_run_at).toLocaleString() : "never"}</td>
              <td className="py-2 text-xs">{s.last_status ?? "—"} {!s.active && <span className="text-muted-foreground">(paused)</span>}</td>
              <td className="py-2 text-right">
                <div className="flex justify-end gap-1.5">
                  <Button type="button" variant="outline" className="h-7 text-xs" disabled={run.isPending} onClick={() => run.mutate(s.id)}>Run now</Button>
                  <Button type="button" variant="outline" className="h-7 text-xs" disabled={toggle.isPending}
                    onClick={() => toggle.mutate({id: s.id, active: !s.active, name: s.name, kind: s.kind, cron: s.cron, format: s.format, recipients: s.recipients})}>
                    {s.active ? "Pause" : "Resume"}
                  </Button>
                  <Button type="button" variant="danger" className="h-7 text-xs" disabled={remove.isPending} onClick={() => remove.mutate(s.id)}>Delete</Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
