"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {useJobsQueue, useScheduledTasks} from "@/hooks/use-api";
import {apiFetch} from "@/lib/api";
import {EmptyState, ErrorState, LoadingState} from "@/components/states";
import {Button} from "@/components/ui/button";
import {Card} from "@/components/ui/card";

/** F6.6 — job queue depth by state, the dead-letter list with retry, and
 * every scheduled_task with its next run. */
export function JobsTab() {
  const query = useQueryClient();
  const jobs = useJobsQueue();
  const scheduled = useScheduledTasks();
  const retry = useMutation({
    mutationFn: (id: number) => apiFetch(`/admin/jobs/${id}/retry`, {method: "POST"}),
    onSuccess: () => query.invalidateQueries({queryKey: ["admin", "jobs-queue"]}),
  });

  if (jobs.isLoading || scheduled.isLoading) return <LoadingState label="Loading job queue…"/>;
  if (jobs.error) return <ErrorState message={jobs.error.message}/>;
  if (scheduled.error) return <ErrorState message={scheduled.error.message}/>;

  return (
    <div className="grid gap-4">
      <div className="grid gap-3 sm:grid-cols-4">
        {Object.entries(jobs.data!.by_state).map(([state, n]) => (
          <Card key={state} className="grid gap-1">
            <p className="m-0 text-xs capitalize text-muted-foreground">{state}</p>
            <p className={`numeric m-0 text-2xl font-semibold ${state === "dead" && n > 0 ? "text-danger" : ""}`}>{n}</p>
          </Card>
        ))}
      </div>

      <h2 className="m-0 text-sm font-semibold text-muted-foreground">Dead-lettered jobs</h2>
      {jobs.data!.dead.length === 0
        ? <EmptyState title="Nothing dead-lettered" body="Every job has completed or is still retrying."/>
        : (
          <Card className="overflow-x-auto">
            <table className="w-full min-w-[45rem] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b text-xs text-muted-foreground">
                  <th className="py-2">ID</th><th className="py-2">Kind</th><th className="py-2">Attempts</th>
                  <th className="py-2">Error</th><th className="py-2">Updated</th><th className="py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {jobs.data!.dead.map((j) => (
                  <tr key={j.id} className="border-b last:border-0">
                    <td className="numeric py-2">{j.id}</td>
                    <td className="py-2">{j.kind}</td>
                    <td className="numeric py-2">{j.attempts}/{j.max_attempts}</td>
                    <td className="max-w-64 truncate py-2 text-xs text-danger">{j.last_error ?? "—"}</td>
                    <td className="py-2 text-xs text-muted-foreground">{new Date(j.updated_at).toLocaleString()}</td>
                    <td className="py-2 text-right">
                      <Button type="button" variant="outline" className="h-7 text-xs" disabled={retry.isPending} onClick={() => retry.mutate(j.id)}>Retry</Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}

      <h2 className="m-0 text-sm font-semibold text-muted-foreground">Scheduled tasks</h2>
      {scheduled.data!.scheduled.length === 0
        ? <EmptyState title="Nothing scheduled" body="No recurring or one-shot tasks are registered."/>
        : (
          <Card className="overflow-x-auto">
            <table className="w-full min-w-[45rem] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b text-xs text-muted-foreground">
                  <th className="py-2">Name</th><th className="py-2">Kind</th><th className="py-2">Cron</th>
                  <th className="py-2">Enabled</th><th className="py-2">Last run</th><th className="py-2">Next run</th>
                </tr>
              </thead>
              <tbody>
                {scheduled.data!.scheduled.map((t) => (
                  <tr key={t.id} className="border-b last:border-0">
                    <td className="max-w-40 truncate py-2 font-medium">{t.name}</td>
                    <td className="py-2">{t.kind}</td>
                    <td className="numeric py-2 text-xs">{t.cron}</td>
                    <td className="py-2 text-xs">{t.enabled ? "yes" : "paused"}</td>
                    <td className="py-2 text-xs text-muted-foreground">{t.last_run ? new Date(t.last_run).toLocaleString() : "never"}</td>
                    <td className="py-2 text-xs text-muted-foreground">{new Date(t.next_run).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
    </div>
  );
}
