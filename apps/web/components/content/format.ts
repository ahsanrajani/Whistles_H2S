import type {ComplianceSeverity, RateInterval} from "@/lib/types";

const pct = (v: number) => `${Math.round(v * 100)}%`;

/** "60% (95% CI 31–83%, 6 of 10)" -- no proportion is shown without its interval. */
export function fmtRate(r: RateInterval | null | undefined): string {
  if (!r || r.n === 0 || r.rate === null || r.ci_low === null || r.ci_high === null) return "no comments yet";
  return `${pct(r.rate)} (95% CI ${pct(r.ci_low)}–${pct(r.ci_high)}, ${r.k} of ${r.n})`;
}

export const SEVERITY_STYLE: Record<ComplianceSeverity, {label: string; className: string}> = {
  high: {label: "Fix before approval", className: "bg-danger/15 text-danger"},
  review: {label: "Compliance review", className: "bg-warning/15 text-warning"},
  note: {label: "Minor note", className: "bg-muted text-muted-foreground"},
  clear: {label: "Clear", className: "bg-success/15 text-success"},
};
