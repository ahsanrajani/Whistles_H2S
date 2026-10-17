"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {useState} from "react";
import {useOwnedAnalyticsStatus} from "@/hooks/use-api";
import {apiFetch} from "@/lib/api";
import {EmptyState, ErrorState, LoadingState} from "@/components/states";
import {Button} from "@/components/ui/button";
import {Card} from "@/components/ui/card";
import {Input} from "@/components/ui/input";

/** F6.4 — owned-analytics ingestion state per source + a manual backfill
 * trigger. */
export function OwnedAnalyticsTab() {
  const query = useQueryClient();
  const status = useOwnedAnalyticsStatus();
  const [days, setDays] = useState(1);
  const ingest = useMutation({
    mutationFn: () => apiFetch("/admin/owned-analytics/ingest", {method: "POST", body: JSON.stringify({days})}),
    onSuccess: () => query.invalidateQueries({queryKey: ["admin", "owned-analytics"]}),
  });

  if (status.isLoading) return <LoadingState label="Loading owned-analytics status…"/>;
  if (status.error) return <ErrorState message={status.error.message}/>;
  const data = status.data!;

  return (
    <div className="grid gap-3">
      <Card className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">Backfill</span>
        <Input aria-label="Days to backfill" type="number" min={1} max={90} value={days}
          onChange={(e) => setDays(Math.max(1, Math.min(90, Number(e.target.value) || 1)))}
          className="h-9 w-20 text-sm"/>
        <span className="text-xs text-muted-foreground">days ending yesterday</span>
        <Button type="button" className="ml-auto h-9 text-xs" disabled={ingest.isPending} onClick={() => ingest.mutate()}>
          Queue ingest
        </Button>
        {ingest.isSuccess && <span className="text-xs text-success">Queued.</span>}
      </Card>

      {data.sources.length === 0
        ? <EmptyState title="No data yet" body="No owned-analytics facts ingested. Queue a backfill above."/>
        : (
          <Card className="overflow-x-auto">
            <table className="w-full min-w-[40rem] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b text-xs text-muted-foreground">
                  <th className="py-2">Source</th><th className="py-2">Live?</th>
                  <th className="py-2 text-right">Facts</th><th className="py-2 text-right">Metrics</th>
                  <th className="py-2">First day</th><th className="py-2">Last day</th>
                </tr>
              </thead>
              <tbody>
                {data.sources.map((s) => {
                  const live = data.providers.find((p) => p.platform === s.source)?.live;
                  return (
                    <tr key={s.source} className="border-b last:border-0">
                      <td className="py-2 capitalize">{s.source}</td>
                      <td className="py-2 text-xs">{live ? "live" : "mock"}</td>
                      <td className="numeric py-2 text-right">{s.facts}</td>
                      <td className="numeric py-2 text-right">{s.metrics}</td>
                      <td className="py-2 text-xs text-muted-foreground">{s.first_day ?? "—"}</td>
                      <td className="py-2 text-xs text-muted-foreground">{s.last_day ?? "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>
        )}
    </div>
  );
}
