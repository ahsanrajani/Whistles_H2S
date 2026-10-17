"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {apiFetch} from "@/lib/api";
import type {components} from "@/lib/api-types";
import {Button} from "./ui/button";
import {Card} from "./ui/card";

type StoreStats = components["schemas"]["ReviewStoreStats"];
type StoreStatsEntry = components["schemas"]["ReviewStoreStatsEntry"];

const STAR_ORDER = ["5", "4", "3", "2", "1"] as const;

function StoreStatsRow({label, entry, icon}: {label: string; entry: StoreStatsEntry | null | undefined; icon?: string | null}) {
  const title = <strong className="inline-flex min-w-0 items-center gap-2">
    {/* eslint-disable-next-line @next/next/no-img-element -- store CDN icon, arbitrary host */}
    {icon && <img src={icon} alt="" width={20} height={20} loading="lazy" referrerPolicy="no-referrer" className="size-5 rounded-[0.3125rem]"/>}
    <span className="truncate">{label}</span>
  </strong>;
  if (!entry || (entry.rating == null && entry.count == null)) {
    return <div className="flex flex-wrap items-center justify-between gap-2 py-4">
      {title}
      <span className="text-sm text-muted-foreground">Unknown — not refreshed yet</span>
    </div>;
  }
  const total = entry.histogram
    ? STAR_ORDER.reduce((sum, star) => sum + (entry.histogram?.[star] ?? 0), 0)
    : 0;
  return <div className="py-4">
    <div className="flex flex-wrap items-center justify-between gap-2">
      {title}
      <span className="numeric text-sm">
        {entry.rating != null ? `${entry.rating.toFixed(1)}★` : "unknown"}
        {" · "}
        {entry.count != null ? `${entry.count.toLocaleString()} ratings` : "unknown count"}
      </span>
    </div>
    {entry.histogram && total > 0 && <div className="mt-2 grid gap-1">
      {STAR_ORDER.map((star) => (
        <div key={star} className="grid grid-cols-[28px_1fr_64px] items-center gap-2 text-xs">
          <span className="font-medium">{star}★</span>
          <span className="h-2 overflow-hidden rounded-full bg-muted">
            <span className="block h-full rounded-full bg-warning" style={{width: `${(100 * (entry.histogram?.[star] ?? 0)) / total}%`}}/>
          </span>
          <span className="numeric text-right text-muted-foreground">{(entry.histogram?.[star] ?? 0).toLocaleString()}</span>
        </div>
      ))}
    </div>}
    {entry.captured_at && <p className="mb-0 mt-2 text-xs text-muted-foreground">As of {entry.captured_at.slice(0, 10)}</p>}
  </div>;
}

export function StoreStatsCard({stats, canEdit}: {stats: StoreStats | null; canEdit: boolean}) {
  const query = useQueryClient();
  const run = useMutation({
    mutationFn: () => apiFetch<{ok: boolean}>("/reviews/store-stats/run", {method: "POST"}),
    onSuccess: () => query.invalidateQueries({queryKey: ["reviews"]}),
  });

  return <Card>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="m-0 text-xl font-semibold">Store ratings</h2>
      {canEdit && <Button type="button" disabled={run.isPending} onClick={() => run.mutate()}>
        {run.isPending ? "Fetching…" : "Refresh"}
      </Button>}
    </div>
    {run.isError && <p role="alert" className="mt-2 rounded-[0.5rem] border border-danger/30 bg-danger/10 p-2 text-xs text-danger">Refresh failed — {(run.error as Error).message}</p>}
    <div className="divide-y">
      {stats?.apps?.length
        ? stats.apps.map((app) => (
          <StoreStatsRow key={`${app.store}:${app.app_id}`} icon={app.icon}
            label={`${app.store === "app_store" ? "App Store" : "Play Store"} · ${app.name ?? app.app_id}`} entry={app}/>
        ))
        : <>
          <StoreStatsRow label="App Store" entry={stats?.app_store}/>
          <StoreStatsRow label="Play Store" entry={stats?.play_store}/>
        </>}
    </div>
    {!stats && <p className="mb-0 text-xs text-muted-foreground">
      {canEdit ? "Not refreshed yet — click Refresh to pull real figures." : "Not refreshed yet. Ask an admin to refresh."}
    </p>}
  </Card>;
}
