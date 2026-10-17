"use client";
/* eslint-disable react-hooks/incompatible-library -- TanStack Virtual intentionally returns stable mutable helpers. */

import {useQueryClient} from "@tanstack/react-query";
import {useVirtualizer} from "@tanstack/react-virtual";
import {BellRing, CheckCircle2, Clock, Inbox, Timer, X} from "lucide-react";
import {useEffect, useMemo, useRef, useState} from "react";
import {useSearchParams} from "next/navigation";
import {useTenantRouter as useRouter} from "@/components/tenant-link";
import {useRealtime} from "@/hooks/use-realtime";
import {useCareCases, useMe} from "@/hooks/use-api";
import type {CareCaseRow} from "@/lib/types";
import {cn} from "@/lib/utils";
import {CareSearch} from "@/components/care/care-search";
import {CaseWorkspace} from "@/components/care/case-workspace";
import {CaseCard} from "@/components/care/primitives";
import {RealtimeBanner} from "@/components/care/realtime-banner";
import {isAgentScoped} from "@/lib/permissions";
import {EmptyState, ErrorState, LoadingState} from "@/components/states";
import {Select} from "@/components/ui/select";
import {TabBar} from "@/components/ui/tab-bar";

const ALL_TABS = [
  {key: "queue", label: "Queue"},
  {key: "assigned", label: "All Assigned"},
  {key: "mine", label: "Assigned to Me"},
  {key: "hold", label: "Internal Hold"},
  {key: "closed", label: "All Closed"},
] as const;

// An agent-scoped user (plain "agent" role) only ever sees cases assigned to
// them -- the API enforces this for every tab already (queue/assigned come
// back empty, hold/closed come back filtered to their own), so the only tab
// worth showing them is the one that actually explains what they're looking
// at. Hamza: "agent accounts should be able to access only the conversations
// assigned to them, nothing else."
const AGENT_TABS = ALL_TABS.filter((t) => t.key === "mine");

const SORTS = [
  {key: "new", label: "Newest"},
  {key: "wait", label: "Longest waiting"},
  {key: "old", label: "Oldest"},
] as const;

type MetaNotice = {caseId: number; channel: string};

function sortCases(rows: CareCaseRow[], sort: string): CareCaseRow[] {
  const out = [...rows];
  if (sort === "new") out.sort((a, b) => b.opened_at.localeCompare(a.opened_at));
  else if (sort === "old") out.sort((a, b) => a.opened_at.localeCompare(b.opened_at));
  else out.sort((a, b) => b.waiting_seconds - a.waiting_seconds);
  return out;
}

// F7.2 — a 1,000-case queue must stay responsive: only the rows in (and just
// around) the viewport are ever mounted. Same @tanstack/react-virtual
// absolute-position pattern as mentions-view.tsx's VirtualMentions.
function VirtualCaseList({rows, selected, onSelect}: {
  rows: CareCaseRow[]; selected: number | null; onSelect: (id: number) => void;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  const virtual = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scroller.current,
    estimateSize: () => 96,
    overscan: 8,
    measureElement: (element) => element.getBoundingClientRect().height,
  });

  return (
    <div ref={scroller} className="max-h-[calc(100vh-14rem)] overflow-y-auto pr-1">
      <div className="relative" style={{height: virtual.getTotalSize()}}>
        {virtual.getVirtualItems().map((item) => {
          const c = rows[item.index];
          return (
            <div key={c.id} ref={virtual.measureElement} data-index={item.index}
              className="absolute left-0 top-0 w-full pb-2" style={{transform: `translateY(${item.start}px)`}}>
              <CaseCard
                caseId={c.id}
                customer={c.display_name ?? c.handle ?? "Unknown"}
                channel={c.channel ?? c.platform ?? "channel"}
                sla={{state: c.sla_state ?? "none"}}
                priority={c.priority}
                waitingSeconds={c.waiting_seconds}
                assignee={c.assignee_id ? `#${c.assignee_id}` : null}
                active={c.id === selected}
                onSelect={() => onSelect(c.id)}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Workspace-wide snapshot, top of the console -- what Hamza asked for:
// "Average response time, number of cases closed, currently open cases,
// first response time on the care dashboard top". Per-agent comparison
// (fastest agent, most cases solved) lives on the Supervisor Performance tab,
// which already has the per-agent table this would just duplicate.
//
// Demo data (Hamza: "prettify this, and plug in dummy data as well") --
// real /care/performance was showing "-1486h -11m" for avg first response,
// the exact impossible-negative-duration failure the UI/UX audit flagged
// (a case whose first_response_at somehow predates opened_at throws the
// average deeply negative; nothing here validates that server-side yet).
// Swap back to useCarePerformance() once that's fixed at the source rather
// than papered over client-side.
const PERF_DEMO = [
  {label: "Open now", value: "36", icon: Inbox},
  {label: "Closed (all time)", value: "94", icon: CheckCircle2},
  {label: "Avg first response", value: "3m 42s", icon: Timer},
  {label: "Avg response time", value: "6m 15s", icon: Clock},
] as const;

function PerformanceBar() {
  return (
    <div className="grid grid-cols-2 gap-3 rounded-[0.75rem] border bg-card p-4 sm:grid-cols-4">
      {PERF_DEMO.map(({label, value, icon: Icon}) => (
        <div key={label} className="flex items-center gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-[0.625rem] bg-primary/10 text-primary dark:text-highlight">
            <Icon size={19}/>
          </span>
          <div className="min-w-0">
            <p className="numeric m-0 text-lg font-semibold leading-tight">{value}</p>
            <p className="m-0 truncate text-[0.6875rem] text-muted-foreground">{label}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

export function CareConsoleView() {
  const params = useSearchParams();
  const router = useRouter();
  const query = useQueryClient();
  const me = useMe();
  const wsId = me.data?.user.workspace?.id;
  const agentScoped = isAgentScoped(me.data?.user.roles);
  const tabs = agentScoped ? AGENT_TABS : ALL_TABS;
  const [metaNotice, setMetaNotice] = useState<MetaNotice | null>(null);
  const noticeTimer = useRef<number | undefined>(undefined);

  const tab = tabs.some((t) => t.key === params.get("tab")) ? params.get("tab")! : tabs[0].key;
  const selected = params.get("case") ? Number(params.get("case")) : null;
  const sort = SORTS.some((s) => s.key === params.get("sort")) ? params.get("sort")! : "new";
  const channel = params.get("channel") ?? "";

  const list = useCareCases(tab);

  // F1.2: a change anywhere in this workspace's queue refreshes every tab.
  useRealtime(wsId != null ? `queue:${wsId}` : null, (frame) => {
    query.invalidateQueries({queryKey: ["care", "cases"]});
    const event = frame.data as {kind?: unknown; case_id?: unknown; channel?: unknown};
    if (!agentScoped && event?.kind === "meta_message"
        && typeof event.case_id === "number" && typeof event.channel === "string") {
      window.clearTimeout(noticeTimer.current);
      setMetaNotice({caseId: event.case_id, channel: event.channel});
      noticeTimer.current = window.setTimeout(() => setMetaNotice(null), 10_000);
    }
  });
  useEffect(() => () => window.clearTimeout(noticeTimer.current), []);

  const channels = useMemo(
    () => [...new Set((list.data?.cases ?? []).map((c) => c.channel ?? c.platform).filter(Boolean))] as string[],
    [list.data],
  );
  const visible = useMemo(() => {
    const rows = (list.data?.cases ?? []).filter(
      (c) => !channel || (c.channel ?? c.platform) === channel,
    );
    return sortCases(rows, sort);
  }, [list.data, channel, sort]);

  function go(next: {tab?: string; case?: number | null; sort?: string; channel?: string}) {
    const sp = new URLSearchParams(params.toString());
    if (next.tab !== undefined) {
      sp.set("tab", next.tab);
      sp.delete("case");
    }
    if (next.sort !== undefined) {
      if (next.sort) sp.set("sort", next.sort); else sp.delete("sort");
    }
    if (next.channel !== undefined) {
      if (next.channel) sp.set("channel", next.channel); else sp.delete("channel");
    }
    if (next.case !== undefined) {
      if (next.case == null) sp.delete("case");
      else sp.set("case", String(next.case));
    }
    router.replace(`/care${sp.size ? `?${sp}` : ""}`);
  }

  return (
    <div className="mx-auto grid max-w-[100rem] gap-5">
      {metaNotice && (
        <div role="status" aria-live="assertive"
          className="fixed bottom-5 right-5 z-[1000] w-[min(24rem,calc(100vw-2rem))] rounded-[0.75rem] border border-primary/30 bg-card p-4 shadow-xl">
          <div className="flex items-start gap-3">
            <BellRing className="mt-0.5 shrink-0 text-primary" size={19}/>
            <div className="min-w-0 flex-1">
              <p className="m-0 text-sm font-semibold">New Meta message</p>
              <p className="m-0 mt-1 text-xs text-muted-foreground">
                {metaNotice.channel === "messenger" ? "Facebook Messenger" : "Instagram DM"} activity arrived in C-{metaNotice.caseId}.
              </p>
              <button type="button" className="mt-2 text-xs font-semibold text-primary hover:underline"
                onClick={() => {go({tab: "assigned", case: metaNotice.caseId}); setMetaNotice(null);}}>
                Open conversation
              </button>
            </div>
            <button type="button" aria-label="Dismiss notification"
              className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              onClick={() => setMetaNotice(null)}><X size={16}/></button>
          </div>
        </div>
      )}
      <RealtimeBanner/>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="mb-0.5 text-sm font-semibold text-primary dark:text-highlight">Social care</p>
          <h1 className="m-0 text-2xl font-semibold tracking-tight">Agent console</h1>
        </div>
        {!agentScoped && <CareSearch onOpenCase={(id) => go({case: id})}/>}
      </div>
      {!agentScoped && <PerformanceBar/>}
      <div className="flex">
        <TabBar label="Case tabs" value={tab} onChange={(key) => go({tab: key})}
          items={tabs.map((t) => ({key: t.key, label: t.label, badge: t.key === tab && list.data ? visible.length : undefined}))}/>
      </div>

      <div className="grid min-w-0 items-start gap-4 lg:grid-cols-[minmax(220px,260px)_minmax(0,1fr)]">
        <section aria-label="Case list" className={cn("min-w-0 grid-cols-1 content-start gap-2", selected == null ? "grid" : "hidden lg:grid")}>
          <div className="flex gap-2">
            <Select aria-label="Sort cases" className="min-w-0 flex-1" value={sort}
              onChange={(e) => go({sort: e.target.value})}>
              {SORTS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </Select>
            <Select aria-label="Filter channel" className="min-w-0 flex-1" value={channel}
              onChange={(e) => go({channel: e.target.value})}>
              <option value="">All channels</option>
              {channels.map((c) => <option key={c} value={c}>{c}</option>)}
            </Select>
          </div>
          {list.isLoading && <LoadingState label="Loading cases…"/>}
          {list.error && <ErrorState message={list.error.message}/>}
          {list.data && visible.length === 0 && (
            <EmptyState title="Nothing here" body={`No cases in "${tabs.find((t) => t.key === tab)?.label}".`}/>
          )}
          {visible.length > 0 && (
            <VirtualCaseList rows={visible} selected={selected} onSelect={(id) => go({case: id})}/>
          )}
        </section>

        <div className={cn("min-w-0", selected == null && "hidden lg:block")}>
          {selected != null && <button type="button" onClick={() => go({case: null})}
            className="mb-3 text-sm font-semibold text-primary lg:hidden">Back to cases</button>}
          <CaseWorkspace key={selected ?? "empty"} caseId={selected} onOpenCase={(id) => go({case: id})}/>
        </div>
      </div>
    </div>
  );
}
