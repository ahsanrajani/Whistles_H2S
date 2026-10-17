"use client";

import {useMemo} from "react";
import {useMisClosedCases, useMisDaily} from "@/hooks/use-api";
import {AnalyticsLineChart} from "@/components/viewer-components";
import {EmptyState, ErrorState, LoadingState} from "@/components/states";
import {Card} from "@/components/ui/card";
import {ExportBar, RangePicker, useReportRange} from "@/components/reports/report-shell";

/** F5.6 — MIS: daily case counts and the flat 13-column closed-case export.
 * Column order matches the BRD exactly — it comes straight from the backend
 * `headers` array, never re-derived here. */
export function MisTab() {
  const {start, end, setRange} = useReportRange();
  const daily = useMisDaily(start, end);
  const closed = useMisClosedCases(start, end);

  // F7.2 — recomputed only when the daily series changes.
  const chartData = useMemo(
    () => (daily.data?.daily ?? []).map((d) => ({date: d.day, opened: d.opened, closed: d.closed, reopened: d.reopened})),
    [daily.data],
  );

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <RangePicker start={start} end={end} onChange={setRange}/>
        <div className="ml-auto flex gap-2">
          <ExportBar kind="mis_daily" params={{start, end}}/>
          <ExportBar kind="mis_closed" params={{start, end}}/>
        </div>
      </div>

      {daily.isLoading && <LoadingState label="Loading daily counts…"/>}
      {daily.error && <ErrorState message={daily.error.message}/>}
      {daily.data && (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <Stat label="Opened" value={daily.data.totals.opened}/>
            <Stat label="Closed" value={daily.data.totals.closed}/>
            <Stat label="Reopened" value={daily.data.totals.reopened}/>
          </div>
          {chartData.length > 1 && (
            <Card>
              <AnalyticsLineChart data={chartData} semantic lines={[
                {key: "opened", label: "Opened", color: "var(--primary)"},
                {key: "closed", label: "Closed", color: "var(--success)"},
                {key: "reopened", label: "Reopened", color: "var(--danger)"},
              ]}/>
            </Card>
          )}
        </>
      )}

      <h2 className="m-0 text-sm font-semibold text-muted-foreground">Closed-case report ({closed.data?.count ?? 0})</h2>
      {closed.isLoading && <LoadingState label="Loading closed cases…"/>}
      {closed.error && <ErrorState message={closed.error.message}/>}
      {closed.data && closed.data.count === 0 && <EmptyState title="No closed cases" body="No cases closed in this window."/>}
      {closed.data && closed.data.count > 0 && (
        <Card className="overflow-x-auto">
          <table className="w-full min-w-[68.75rem] border-collapse text-left text-xs">
            <thead>
              <tr className="border-b text-muted-foreground">
                {closed.data.headers.map((h) => <th key={h} className="whitespace-nowrap py-2 pr-3">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {closed.data.rows.slice(0, 100).map((row, i) => (
                <tr key={i} className="border-b last:border-0">
                  {closed.data!.headers.map((h) => (
                    <td key={h} className="whitespace-nowrap py-2 pr-3">{row[h] ?? "—"}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {closed.data.count > 100 && (
            <p className="mt-2 text-[0.6875rem] text-muted-foreground">Showing the first 100 of {closed.data.count} — export for the full set.</p>
          )}
        </Card>
      )}
    </div>
  );
}

function Stat({label, value}: {label: string; value: number}) {
  return (
    <Card className="grid gap-1">
      <p className="m-0 text-xs text-muted-foreground">{label}</p>
      <p className="numeric m-0 text-2xl font-semibold">{value}</p>
    </Card>
  );
}
