"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {useSourceHealth} from "@/hooks/use-api";
import {apiFetch} from "@/lib/api";
import {cn} from "@/lib/utils";
import {EmptyState, ErrorState, LoadingState} from "@/components/states";
import {Button} from "@/components/ui/button";
import {Card} from "@/components/ui/card";

const HEALTH_CLS: Record<string, string> = {
  ok: "text-success", stale: "text-warning", failing: "text-danger",
  down: "text-danger", unknown: "text-muted-foreground",
};

/** F6.1 — per-source collection health: band, last success, consecutive
 * failures, circuit state, items last run. Manual retry + circuit reset. */
export function SourceHealthTab() {
  const query = useQueryClient();
  const health = useSourceHealth();
  const refresh = () => query.invalidateQueries({queryKey: ["admin", "source-health"]});
  const retry = useMutation({mutationFn: (id: string) => apiFetch(`/admin/sources/${id}/retry`, {method: "POST"}), onSuccess: refresh});
  const reset = useMutation({mutationFn: (id: string) => apiFetch(`/admin/sources/${id}/reset-circuit`, {method: "POST"}), onSuccess: refresh});

  if (health.isLoading) return <LoadingState label="Loading source health…"/>;
  if (health.error) return <ErrorState message={health.error.message}/>;
  const data = health.data!;
  if (data.sources.length === 0) return <EmptyState title="No collectors" body="No cadenced sources are configured."/>;

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
        {Object.entries(data.counts).map(([k, v]) => <span key={k}><b className="text-foreground">{v}</b> {k}</span>)}
      </div>
      <Card className="overflow-x-auto">
        <table className="w-full min-w-[53.75rem] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b text-xs text-muted-foreground">
              <th className="py-2">Source</th><th className="py-2">Health</th><th className="py-2">Circuit</th>
              <th className="py-2 text-right">Failures</th><th className="py-2 text-right">Items last run</th>
              <th className="py-2">Last success</th><th className="py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {data.sources.map((s) => (
              <tr key={s.source} className="border-b last:border-0">
                <td className="py-2">{s.label}<span className="ml-1.5 text-[0.625rem] text-muted-foreground">{s.source_class}</span></td>
                <td className={cn("py-2 font-semibold capitalize", HEALTH_CLS[s.health])}>{s.health}</td>
                <td className="py-2 text-xs">{s.circuit_state}</td>
                <td className="numeric py-2 text-right">{s.consecutive_failures}</td>
                <td className="numeric py-2 text-right">{s.items_last_run}</td>
                <td className="py-2 text-xs text-muted-foreground">{s.last_success_at ? new Date(s.last_success_at).toLocaleString() : "never"}</td>
                <td className="py-2 text-right">
                  <div className="flex justify-end gap-1.5">
                    <Button type="button" variant="outline" className="h-7 text-xs" disabled={retry.isPending} onClick={() => retry.mutate(s.source)}>Retry</Button>
                    {s.circuit_state !== "closed" && (
                      <Button type="button" variant="outline" className="h-7 text-xs" disabled={reset.isPending} onClick={() => reset.mutate(s.source)}>Reset circuit</Button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
