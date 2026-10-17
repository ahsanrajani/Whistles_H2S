"use client";

import {useSearchParams} from "next/navigation";
import {useMemo} from "react";
import {useTenantRouter as useRouter} from "@/components/tenant-link";
import {useMetricCatalog, useMetricReport} from "@/hooks/use-api";
import {EmptyState, ErrorState, LoadingState} from "@/components/states";
import {AnalyticsLineChart} from "@/components/viewer-components";
import {Card} from "@/components/ui/card";
import {Select} from "@/components/ui/select";
import {ExportBar, Measure, RangePicker, useReportRange} from "@/components/reports/report-shell";

/** F5.2 — a generic explorer over every (source, metric) in the P4.1
 * warehouse. Every proportion renders its Wilson interval; a delta is only
 * flagged significant when the backend says so. */
export function MetricsTab() {
  const params = useSearchParams();
  const router = useRouter();
  const {start, end, setRange} = useReportRange();
  const catalog = useMetricCatalog();

  const source = params.get("source") ?? "";
  const metric = params.get("metric") ?? "";
  const groupBy = params.get("group_by") ?? "";
  const compare = params.get("compare") !== "0";

  function setParam(k: string, v: string) {
    const sp = new URLSearchParams(params.toString());
    if (v) sp.set(k, v); else sp.delete(k);
    router.replace(`?${sp}`);
  }

  const entries = catalog.data?.metrics ?? [];
  const current = entries.find((e) => e.source === source && e.metric === metric) ?? entries[0];
  const activeSource = source || current?.source || "";
  const activeMetric = metric || current?.metric || "";

  const qs = new URLSearchParams({
    source: activeSource, metric: activeMetric, start, end, compare: String(compare),
    ...(groupBy ? {group_by: groupBy} : {}),
  }).toString();
  const report = useMetricReport(qs, !!activeSource && !!activeMetric);
  // F7.2 — recomputed only when the series actually changes, not on every
  // render (URL-param changes elsewhere in this tab shouldn't re-map it).
  const chartData = useMemo(
    () => (report.data?.series ?? []).map((p) => ({date: p.day, value: p.value ?? null})),
    [report.data],
  );

  if (catalog.isLoading) return <LoadingState label="Loading catalog…"/>;
  if (catalog.error) return <ErrorState message={catalog.error.message}/>;
  if (entries.length === 0) return <EmptyState title="No metrics yet" body="Owned-analytics ingestion hasn't run. Trigger it from Admin → Owned analytics."/>;

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Select aria-label="Source" value={activeSource}
          onChange={(e) => {setParam("source", e.target.value); setParam("metric", "");}}
          className="h-9 max-w-32 text-xs">
          {[...new Set(entries.map((e) => e.source))].map((s) => <option key={s} value={s}>{s}</option>)}
        </Select>
        <Select aria-label="Metric" value={activeMetric} onChange={(e) => setParam("metric", e.target.value)} className="h-9 max-w-44 text-xs">
          {entries.filter((e) => e.source === activeSource).map((e) => (
            <option key={e.metric} value={e.metric}>{e.metric}{e.is_proportion ? " (rate)" : ""}</option>
          ))}
        </Select>
        {catalog.data && catalog.data.groupable.length > 0 && (
          <Select aria-label="Group by" value={groupBy} onChange={(e) => setParam("group_by", e.target.value)} className="h-9 max-w-36 text-xs">
            <option value="">No grouping</option>
            {catalog.data.groupable.map((g) => <option key={g} value={g}>{g}</option>)}
          </Select>
        )}
        <label className="flex items-center gap-1 text-xs text-muted-foreground">
          <input type="checkbox" checked={compare} onChange={(e) => setParam("compare", e.target.checked ? "1" : "0")}/>
          compare to prior period
        </label>
        <RangePicker start={start} end={end} onChange={setRange}/>
        <div className="ml-auto"><ExportBar kind="metrics" params={{source: activeSource, metric: activeMetric, start, end}}/></div>
      </div>

      {report.isLoading && <LoadingState label="Loading metric…"/>}
      {report.error && <ErrorState message={report.error.message}/>}
      {report.data && (
        <>
          <Card className="flex flex-wrap items-center gap-6">
            <div>
              <p className="m-0 text-xs text-muted-foreground">{activeSource} · {activeMetric}</p>
              <p className="numeric m-0 text-3xl font-semibold"><Measure m={report.data.measure} digits={2}/></p>
            </div>
            {report.data.comparison && (
              <div className="text-sm">
                <p className="m-0 text-xs text-muted-foreground">vs prior period</p>
                <p className={`numeric m-0 font-semibold ${report.data.comparison.significant === false ? "text-muted-foreground" : (report.data.comparison.absolute ?? 0) >= 0 ? "text-success" : "text-danger"}`}>
                  {report.data.comparison.absolute == null ? "no data"
                    : `${report.data.comparison.absolute >= 0 ? "+" : ""}${report.data.comparison.absolute.toFixed(2)}`}
                  {report.data.comparison.significant === false && <span className="ml-1 text-[0.6875rem] text-muted-foreground">(not significant)</span>}
                </p>
              </div>
            )}
          </Card>

          {chartData.length > 1 && (
            <Card>
              <AnalyticsLineChart data={chartData} lines={[{key: "value", label: activeMetric}]}/>
            </Card>
          )}

          {report.data.groups && (
            <Card className="overflow-x-auto">
              <table className="w-full min-w-[26.25rem] border-collapse text-left text-sm">
                <thead><tr className="border-b text-xs text-muted-foreground"><th className="py-2">{groupBy}</th><th className="py-2 text-right">Value</th></tr></thead>
                <tbody>
                  {report.data.groups.map((g) => (
                    <tr key={g.key} className="border-b last:border-0">
                      <td className="py-2">{g.key}</td>
                      <td className="py-2 text-right"><Measure m={g} digits={2}/></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
