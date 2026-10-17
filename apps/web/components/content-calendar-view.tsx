"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {useMemo, useState} from "react";
import {useSearchParams} from "next/navigation";
import {useTenantRouter as useRouter} from "@/components/tenant-link";
import {useContentCalendar, useContentRisk, useMe} from "@/hooks/use-api";
import {apiFetch, ApiError} from "@/lib/api";
import {addMonths, addWeeks, isoDay, monthGrid, weekGrid, WEEKDAY_LABELS} from "@/lib/calendar-dates";
import {can} from "@/lib/permissions";
import type {ComplianceSeverity, ContentListItem} from "@/lib/types";
import {cn} from "@/lib/utils";
import {ChannelBadge} from "@/components/care/primitives";
import {ErrorState, LoadingState} from "@/components/states";
import {Button} from "@/components/ui/button";
import {Card} from "@/components/ui/card";
import {Select} from "@/components/ui/select";

import {SEVERITY_STYLE} from "./content/format";
import {InsightsPanel} from "./content/insights-panel";
import {ItemPanel} from "./content/item-panel";
import {SignalsPanel} from "./content/signals-panel";
import {STATE_COLOR, STATES, CHANNELS} from "./content/shared";
import {TabBar} from "@/components/ui/tab-bar";

export function ContentCalendarView() {
  const params = useSearchParams();
  const router = useRouter();
  const query = useQueryClient();
  const me = useMe();
  const canEdit = can(me.data?.user.perms, "templates:edit");

  const view = params.get("view") === "week" ? "week" : "month";
  const anchor = params.get("d") ? new Date(`${params.get("d")}T00:00:00Z`) : new Date();
  const channel = params.get("channel") ?? "";
  const stateFilter = params.get("state") ?? "";
  const itemParam = params.get("item");
  const selected = itemParam === "new" ? "new" : itemParam ? Number(itemParam) : null;

  const grid = view === "month" ? monthGrid(anchor) : weekGrid(anchor);
  const start = isoDay(grid[0]);
  const end = isoDay(grid[grid.length - 1]);
  const cal = useContentCalendar(start, end, stateFilter || undefined);
  const riskById = useContentRisk(start, end).data?.risk ?? {};

  function setParam(patch: Record<string, string | null>) {
    const sp = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v === null) sp.delete(k); else sp.set(k, v);
    }
    router.replace(`/content?${sp}`);
  }

  const items = useMemo(
    () => (cal.data?.items ?? []).filter((i) => !channel || i.channel === channel),
    [cal.data, channel],
  );
  const unscheduled = items.filter((i) => !i.scheduled_for);
  const byDay = useMemo(() => {
    const map = new Map<string, ContentListItem[]>();
    for (const i of items) {
      if (!i.scheduled_for) continue;
      const key = i.scheduled_for.slice(0, 10);
      const list = map.get(key) ?? [];
      list.push(i);
      map.set(key, list);
    }
    return map;
  }, [items]);

  const move = useMutation({
    mutationFn: ({id, day}: {id: number; day: string}) =>
      apiFetch(`/content/${id}`, {method: "PATCH", body: JSON.stringify({scheduled_for: `${day}T09:00:00Z`})}),
    onMutate: async ({id, day}) => {
      await query.cancelQueries({queryKey: ["content", "calendar"]});
      const prev = query.getQueriesData<{window: {start: string; end: string}; items: ContentListItem[]}>({queryKey: ["content", "calendar"]});
      query.setQueriesData<{window: {start: string; end: string}; items: ContentListItem[]} | undefined>(
        {queryKey: ["content", "calendar"]},
        (data) => data && {...data, items: data.items.map((i) => (i.id === id ? {...i, scheduled_for: `${day}T09:00:00Z`} : i))},
      );
      return {prev};
    },
    onError: (err, _vars, ctx) => {
      ctx?.prev.forEach(([key, data]) => query.setQueryData(key, data));
      setDragError(err instanceof ApiError ? err.message : "Could not move that item.");
    },
    onSettled: () => query.invalidateQueries({queryKey: ["content", "calendar"]}),
  });
  const [dragError, setDragError] = useState<string | null>(null);

  return (
    <div className="mx-auto grid max-w-[93.75rem] gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="mb-0.5 text-sm font-semibold text-primary dark:text-highlight">Content</p>
          <h1 className="m-0 text-2xl font-semibold tracking-tight">Content calendar</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <TabBar mode="tab" label="Calendar view" items={[{key: "month", label: "Month"}, {key: "week", label: "Week"}]} value={view} onChange={(key) => setParam({view: key})}/>
          <Button type="button" variant="outline" className="h-8 px-2 text-xs"
            onClick={() => setParam({d: isoDay(view === "month" ? addMonths(anchor, -1) : addWeeks(anchor, -1))})}>←</Button>
          <Button type="button" variant="outline" className="h-8 px-2 text-xs" onClick={() => setParam({d: null})}>Today</Button>
          <Button type="button" variant="outline" className="h-8 px-2 text-xs"
            onClick={() => setParam({d: isoDay(view === "month" ? addMonths(anchor, 1) : addWeeks(anchor, 1))})}>→</Button>
          <Select aria-label="Filter channel" className="h-8 max-w-32 text-xs" value={channel} onChange={(e) => setParam({channel: e.target.value || null})}>
            <option value="">All channels</option>
            {CHANNELS.map((c) => <option key={c} value={c}>{c}</option>)}
          </Select>
          <Select aria-label="Filter state" className="h-8 max-w-32 text-xs" value={stateFilter} onChange={(e) => setParam({state: e.target.value || null})}>
            <option value="">All states</option>
            {STATES.map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}
          </Select>
          {canEdit && <Button type="button" className="h-8 text-xs" onClick={() => setParam({item: "new"})}>New post</Button>}
        </div>
      </div>

      {dragError && (
        <p role="alert" className="m-0 rounded-[0.625rem] border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
          {dragError} <button type="button" className="ml-2 underline" onClick={() => setDragError(null)}>dismiss</button>
        </p>
      )}

      <SignalsPanel canCreate={can(me.data?.user.perms, "templates:create")} onCreated={(id) => setParam({item: String(id)})}/>

      <div className="grid gap-4 lg:grid-cols-[1fr_260px]">
        {cal.isLoading && <LoadingState label="Loading calendar…"/>}
        {cal.error && <ErrorState message={cal.error.message}/>}
        {!cal.isLoading && !cal.error && (
          <CalendarGrid
            grid={grid} view={view} byDay={byDay} anchor={anchor} riskById={riskById}
            onOpen={(id) => setParam({item: String(id)})}
            onDrop={(id, day) => move.mutate({id, day})}
          />
        )}

        <Card className="grid content-start gap-2">
          <h2 className="m-0 text-xs font-semibold text-muted-foreground">Unscheduled ({unscheduled.length})</h2>
          {unscheduled.length === 0 && <p className="m-0 text-xs text-muted-foreground">Nothing in flight without a date.</p>}
          {unscheduled.map((i) => <ItemChip key={i.id} item={i} risk={riskById[i.id]?.severity} onClick={() => setParam({item: String(i.id)})}/>)}
        </Card>
      </div>

      <InsightsPanel/>

      {selected !== null && (
        <ItemPanel id={selected === "new" ? null : selected} onClose={() => setParam({item: null})}/>
      )}
    </div>
  );
}

const RISK_DOT: Record<ComplianceSeverity, string> = {high: "bg-danger", review: "bg-warning", note: "bg-muted-foreground", clear: ""};

function ItemChip({item, onClick, draggable, risk}: {item: ContentListItem; onClick: () => void; draggable?: boolean; risk?: ComplianceSeverity}) {
  return (
    <button
      type="button"
      draggable={draggable}
      onDragStart={(e) => e.dataTransfer.setData("text/plain", String(item.id))}
      onClick={onClick}
      className={cn("flex w-full items-center gap-1.5 truncate rounded-[0.4375rem] px-1.5 py-1 text-left text-[0.6875rem] font-medium", STATE_COLOR[item.state])}>
      {risk && risk !== "clear" && <span role="img" aria-label={`Compliance: ${SEVERITY_STYLE[risk].label}`} title={SEVERITY_STYLE[risk].label} className={cn("size-2 shrink-0 rounded-full", RISK_DOT[risk])}/>}
      <span className="truncate flex-1">{item.title}</span>
      {item.channel && <ChannelBadge channel={item.channel} className="shrink-0 border-0 bg-transparent px-0"/>}
    </button>
  );
}

function CalendarGrid({grid, view, byDay, anchor, riskById, onOpen, onDrop}: {
  grid: Date[]; view: "month" | "week"; byDay: Map<string, ContentListItem[]>; anchor: Date;
  riskById: Record<string, {severity: ComplianceSeverity}>;
  onOpen: (id: number) => void; onDrop: (id: number, day: string) => void;
}) {
  const month = anchor.getUTCMonth();
  return (
    <Card className="grid gap-px overflow-hidden bg-border p-0" style={{gridTemplateColumns: "repeat(7, 1fr)"}}>
      {WEEKDAY_LABELS.map((w) => (
        <div key={w} className="bg-card px-2 py-1.5 text-center text-[0.6875rem] font-semibold text-muted-foreground">{w}</div>
      ))}
      {grid.map((d) => {
        const key = isoDay(d);
        const dayItems = byDay.get(key) ?? [];
        const dim = view === "month" && d.getUTCMonth() !== month;
        return (
          <div key={key}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const id = Number(e.dataTransfer.getData("text/plain"));
              if (id) onDrop(id, key);
            }}
            className={cn("min-h-24 bg-card p-1.5", dim && "opacity-40", view === "week" && "min-h-40")}>
            <p className={cn("numeric m-0 mb-1 text-[0.6875rem]", isoDay(new Date()) === key ? "font-bold text-primary dark:text-highlight" : "text-muted-foreground")}>
              {d.getUTCDate()}
            </p>
            <div className="grid gap-1">
              {dayItems.slice(0, view === "month" ? 3 : 8).map((i) => (
                <ItemChip key={i.id} item={i} draggable risk={riskById[i.id]?.severity} onClick={() => onOpen(i.id)}/>
              ))}
              {dayItems.length > (view === "month" ? 3 : 8) && (
                <span className="text-[0.625rem] text-muted-foreground">+{dayItems.length - (view === "month" ? 3 : 8)} more</span>
              )}
            </div>
          </div>
        );
      })}
    </Card>
  );
}
