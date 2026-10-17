"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {Radar} from "lucide-react";
import {useContentSignals} from "@/hooks/use-api";
import {apiFetch} from "@/lib/api";
import type {ContentDraftFromSignal, ContentNudge, RateInterval} from "@/lib/types";
import {cn} from "@/lib/utils";
import {Button} from "@/components/ui/button";
import {Card} from "@/components/ui/card";
import {fmtRate, SEVERITY_STYLE} from "./format";

const SEVERITY: Record<ContentNudge["severity"], string> = {
  high: "bg-danger/15 text-danger",
  elevated: "bg-warning/15 text-warning",
  watch: "bg-muted text-muted-foreground",
};
const KIND: Record<ContentNudge["kind"], string> = {scam: "Scam activity", incident: "Customer incident", regulatory: "Regulatory"};

function Evidence({nudge}: {nudge: ContentNudge}) {
  const ev = nudge.evidence;
  if (nudge.kind === "scam") {
    const rate: RateInterval = {k: Number(ev.flagged), n: Number(ev.scanned), rate: Number(ev.rate), ci_low: Number(ev.ci_low), ci_high: Number(ev.ci_high)};
    return <p className="m-0 text-[0.6875rem] text-muted-foreground">Flagged comments: {fmtRate(rate)}</p>;
  }
  if (nudge.kind === "incident") {
    return <p className="m-0 text-[0.6875rem] text-muted-foreground">Peak {Number(ev.peak_z).toFixed(1)}σ over a {String(ev.baseline_mean)}/day baseline</p>;
  }
  return <p className="m-0 text-[0.6875rem] text-muted-foreground">Published {String(ev.age_days)} days ago{ev.names_brand ? " · names the brand" : ""}</p>;
}

/** What customers are exposed to right now, as posts worth publishing. Each card
 * shows why (with its evidence); creating a draft records the signal so the
 * closed loop can later measure whether the post helped. */
export function SignalsPanel({canCreate, onCreated}: {canCreate: boolean; onCreated: (id: number) => void}) {
  const query = useQueryClient();
  const signals = useContentSignals();
  const create = useMutation({
    mutationFn: (key: string) => apiFetch<ContentDraftFromSignal>("/content/ai/signals/draft", {method: "POST", body: JSON.stringify({key})}),
    onSuccess: (out) => {
      query.invalidateQueries({queryKey: ["content"]});
      onCreated(out.id);
    },
  });
  const nudges = signals.data?.nudges ?? [];

  return (
    <Card className="grid gap-2">
      <div className="flex items-center gap-1.5">
        <Radar size={14} className="text-muted-foreground"/>
        <h2 className="m-0 text-xs font-semibold text-muted-foreground">Suggested from live signals ({nudges.length})</h2>
      </div>
      {signals.isLoading && <p className="m-0 text-xs text-muted-foreground">Reading scam, incident and regulatory activity…</p>}
      {signals.error && <p className="m-0 text-xs text-danger">{signals.error.message}</p>}
      {signals.data && nudges.length === 0 && (
        <p className="m-0 text-xs text-muted-foreground">Nothing needs a post right now. Scam waves, customer incidents and new regulator notices will appear here.</p>
      )}
      {create.isError && <p role="alert" className="m-0 text-xs text-danger">{(create.error as Error).message}</p>}
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        {nudges.map((n) => (
          <div key={n.key} className="grid content-start gap-1 rounded-[0.625rem] border bg-card p-2.5">
            <div className="flex items-center gap-1.5">
              <span className={cn("rounded-full px-2 py-0.5 text-[0.625rem] font-semibold uppercase", SEVERITY[n.severity])}>{n.severity}</span>
              <span className="text-[0.6875rem] text-muted-foreground">{KIND[n.kind]}</span>
            </div>
            <p className="m-0 text-sm font-semibold">{n.title}</p>
            <p className="m-0 text-xs">{n.why}</p>
            <Evidence nudge={n}/>
            {n.links.length > 0 && (
              <p className="m-0 truncate text-[0.6875rem]">
                {n.links.map((l, i) => (
                  <a key={l.url} href={l.url} target="_blank" rel="noreferrer" className="text-primary underline dark:text-highlight">
                    {i > 0 && " · "}source {i + 1}
                  </a>
                ))}
              </p>
            )}
            {canCreate && (
              <Button type="button" className="mt-1 h-7 w-max text-[0.6875rem]" disabled={create.isPending}
                onClick={() => create.mutate(n.key)}>
                {create.isPending && create.variables === n.key ? "Creating…" : "Create draft"}
              </Button>
            )}
          </div>
        ))}
      </div>
      {create.data && (
        <p className="m-0 text-[0.6875rem] text-muted-foreground">
          Draft created · compliance <span className={cn("rounded-full px-1.5 py-0.5 font-semibold", SEVERITY_STYLE[create.data.compliance.severity].className)}>
            {SEVERITY_STYLE[create.data.compliance.severity].label}</span>{create.data.mock && " · template text (no AI key set)"}
        </p>
      )}
    </Card>
  );
}
