import type {ContentImpact, ImpactVerdict} from "@/lib/types";
import {cn} from "@/lib/utils";
import {fmtRate} from "./format";

const VERDICT: Record<ImpactVerdict, {label: string; className: string}> = {
  improved: {label: "Improved", className: "bg-success/15 text-success"},
  worse: {label: "Got worse", className: "bg-danger/15 text-danger"},
  no_durable_change: {label: "No durable change", className: "bg-muted text-muted-foreground"},
  too_early: {label: "Too early", className: "bg-warning/15 text-warning"},
  not_enough_data: {label: "Not enough data", className: "bg-muted text-muted-foreground"},
};

/** Closed loop: the same risk signal in comments, the week before versus the week after each published post. */
export function ImpactList({impact}: {impact: ContentImpact}) {
  if (impact.items.length === 0) {
    return <p className="m-0 text-xs text-muted-foreground">Nothing published yet. Once a post from the calendar goes out, its effect on scam and complaint comments is measured here.</p>;
  }
  const s = impact.summary;
  return (
    <div className="grid gap-2">
      <p className="m-0 text-xs text-muted-foreground">
        {s.improved} improved · {s.no_durable_change} no durable change · {s.worse} worse · {s.pending} still pending.
        Windows: {impact.window_days} days before vs after, at least {impact.min_comments} comments in each.
      </p>
      {impact.items.map((i) => (
        <div key={i.id} className="grid gap-0.5 rounded-[0.625rem] border bg-card p-2.5 text-xs">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold">{i.title}</span>
            <span className={cn("rounded-full px-2 py-0.5 text-[0.6875rem] font-semibold", VERDICT[i.verdict].className)}>{VERDICT[i.verdict].label}</span>
            <span className="text-muted-foreground">{new Date(i.published_at).toLocaleDateString()}{i.from_signal ? " · from a live signal" : ""}</span>
          </div>
          <p className="m-0 text-muted-foreground">Measures {i.measures}</p>
          <p className="m-0">Before: {fmtRate(i.before)}</p>
          <p className="m-0">After: {fmtRate(i.after)}</p>
          <p className="m-0 text-muted-foreground">{i.reason}</p>
        </div>
      ))}
      <p className="m-0 text-[0.6875rem] text-muted-foreground">{impact.note}</p>
    </div>
  );
}
