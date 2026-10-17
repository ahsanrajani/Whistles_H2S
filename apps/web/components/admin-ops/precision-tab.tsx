"use client";

import {Link} from "@/components/tenant-link";
import {usePrecision} from "@/hooks/use-api";
import type {PrecisionEntry} from "@/lib/types";
import {cn} from "@/lib/utils";
import {EmptyState, ErrorState, LoadingState} from "@/components/states";
import {Card} from "@/components/ui/card";

/** F6.3 — per brand x safe/gated pattern class, Wilson-scored precision
 * against the labelled review sample, target met/missed. Rows failing their
 * target link into the calibration review queue. */
export function PrecisionTab() {
  const precision = usePrecision();
  if (precision.isLoading) return <LoadingState label="Loading precision…"/>;
  if (precision.error) return <ErrorState message={precision.error.message}/>;
  const data = precision.data!;
  if (data.brands.length === 0) return <EmptyState title="No brands" body="Nothing configured for this workspace."/>;

  return (
    <div className="grid gap-3">
      <Card className="flex flex-wrap items-center gap-4 text-sm">
        <span>Sample: <b className="numeric">{data.sample_size}</b> / {data.sample_target}</span>
        <span>Targets: safe ≥ {(data.targets.safe * 100).toFixed(0)}% · gated ≥ {(data.targets.gated * 100).toFixed(0)}%</span>
        <span className={cn("ml-auto font-semibold", data.all_measured_met ? "text-success" : "text-warning")}>
          {data.all_measured_met ? "All measured targets met" : "Some measured targets missed"}
        </span>
      </Card>
      <Card className="overflow-x-auto">
        <table className="w-full min-w-[45rem] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b text-xs text-muted-foreground">
              <th className="py-2">Brand</th><th className="py-2">Class</th>
              <th className="py-2 text-right">Precision (95% CI)</th>
              <th className="py-2 text-right">Labelled / matched</th>
              <th className="py-2 text-right">Target</th><th className="py-2 text-right">Review</th>
            </tr>
          </thead>
          <tbody>
            {data.brands.flatMap((b) => [b.safe, b.gated].map((c: PrecisionEntry) => (
              <tr key={`${b.brand}-${c.class}`} className="border-b last:border-0">
                <td className="py-2">{b.brand}</td>
                <td className="py-2 capitalize">{c.class}</td>
                <td className="numeric py-2 text-right">
                  {c.precision == null ? "no data" : `${(c.precision * 100).toFixed(1)}% (${(c.ci_low! * 100).toFixed(1)}–${(c.ci_high! * 100).toFixed(1)}%)`}
                </td>
                <td className="numeric py-2 text-right">{c.labelled} / {c.matched}</td>
                <td className={cn("py-2 text-right font-semibold", c.labelled === 0 ? "text-muted-foreground" : c.met ? "text-success" : "text-danger")}>
                  {c.labelled === 0 ? "unmeasured" : c.met ? "met" : "missed"}
                </td>
                <td className="py-2 text-right">
                  {!c.met && c.labelled > 0 && <Link href="/review" className="text-xs font-semibold text-primary dark:text-highlight">Review queue →</Link>}
                </td>
              </tr>
            )))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
