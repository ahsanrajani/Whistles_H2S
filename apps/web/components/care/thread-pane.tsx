"use client";

import {useQueryClient} from "@tanstack/react-query";
import {useEffect, useMemo, useRef, useState} from "react";
import {useCareCase} from "@/hooks/use-api";
import {useRealtime} from "@/hooks/use-realtime";
import type {CareCaseDetail} from "@/lib/types";
import {EmptyState, ErrorState, LoadingState} from "@/components/states";
import {Card} from "@/components/ui/card";
import {MessageBubble} from "./primitives";
import {CaseActions} from "./case-actions";
import {ReplyComposer} from "./reply-composer";

function elapsed(fromIso: string, toIso?: string | null): string {
  const from = new Date(fromIso).getTime();
  const to = toIso ? new Date(toIso).getTime() : Date.now();
  const s = Math.max(0, Math.round((to - from) / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${s % 60}s`;
  return `${s}s`;
}

const EVENT_LABEL: Record<string, string> = {
  created: "case opened", assigned: "assigned", reassigned: "reassigned",
  message_in: "inbound message", message_out: "reply sent",
  reply_pending: "reply held for approval", reply_scheduled: "reply scheduled",
  state_change: "state changed", closed: "closed", note: "note added",
  sla_breach: "SLA breached", macro_applied: "macro applied",
  priority_change: "priority changed", tags_added: "tags added",
};

// Hamza: "with every message, assignment/reassignment authorship/ownership
// is logged and displayed eg admin assigned this convo to hamza_rep etc."
// -- actor/target ids were already recorded server-side; care.py's
// case_detail now resolves them to real usernames, this turns that into
// the sentence he asked for.
function whoLabel(username: string | null, id: unknown): string {
  if (username) return username;
  if (typeof id === "number" || typeof id === "string") return `#${id}`;
  return "system";
}

function eventLabel(e: CareCaseDetail["timeline"][number]): string {
  const actor = whoLabel(e.actor_username, e.actor);
  const d = e.detail;
  switch (e.kind) {
    case "assigned": {
      const rule = typeof d.rule === "string" ? ` (${d.rule.replace(/_/g, " ")})` : "";   // auto-assignment records its rule
      return `${actor} assigned this conversation to ${whoLabel(d.assignee_username as string | null, d.assignee_id)}${rule}`;
    }
    case "reassigned": {
      const reason = d.reason ? ` — ${d.reason}` : "";
      return `${actor} reassigned this conversation to ${whoLabel(d.to_username as string | null, d.to_user_id)}${reason}`;
    }
    case "closed":
      return `${actor} closed this case${d.closure_category ? ` (${String(d.closure_category).replaceAll("_", " ")})` : ""}`;
    case "state_change":
      return `${actor} changed state to ${String(d.to_state ?? "").replaceAll("_", " ")}`;
    case "macro_applied": {
      const via = String(d.source ?? "").startsWith("auto:") ? `auto macro (${String(d.source).slice(5)})` : actor;
      return `${via} ran macro “${String(d.macro ?? "")}”`;
    }
    case "priority_change":
      return `${actor} set priority to ${String(d.priority ?? "")}`;
    case "tags_added":
      return `${actor} added tags: ${((d.tags as string[] | undefined) ?? []).join(", ")}`;
    case "created":
      return "Case opened";
    default:
      return `${EVENT_LABEL[e.kind] ?? e.kind.replaceAll("_", " ")} · ${actor}`;
  }
}

type ThreadItem =
  | {t: string; kind: "msg"; m: CareCaseDetail["messages"][number]}
  | {t: string; kind: "note"; id: number; body: string; author: string | null}
  | {t: string; kind: "event"; label: string};

// A stable, content-derived id — never the bare list position, so a
// realtime-triggered refetch that reshuffles `items` mid-interaction can't
// make React reuse the wrong row.
function threadItemKey(it: ThreadItem): string {
  if (it.kind === "note") return `note-${it.id}`;
  if (it.kind === "msg") return `msg-${it.t}-${it.m.direction}`;
  return `event-${it.t}-${it.label}`;
}

export function ThreadPane({caseId, draft, onDraftChange}: {
  caseId: number | null; draft: string; onDraftChange: (text: string) => void;
}) {
  const detail = useCareCase(caseId);
  const query = useQueryClient();
  const scroller = useRef<HTMLDivElement>(null);
  const followLatest = useRef(true);
  const [, tick] = useState(0);
  const data = detail.data;

  // live case timer + refresh on case events
  useEffect(() => {
    const id = window.setInterval(() => tick((n) => n + 1), 30_000);
    return () => window.clearInterval(id);
  }, []);
  useRealtime(caseId != null ? `case:${caseId}` : null, () => {
    query.invalidateQueries({queryKey: ["care", "case", caseId]});
  });

  // F7.2 note — the case *list* is virtualized (the 1,000-row surface); the
  // thread is not. Virtualizing a bounded flex child that also grows on every
  // realtime refetch proved to drop freshly-appended messages, and a 500-row
  // thread of plain bubbles is well within React's comfortable range anyway.
  const items: ThreadItem[] = useMemo(() => {
    if (!data) return [];
    return [
      ...data.messages.map((m) => ({t: m.sent_at, kind: "msg" as const, m})),
      ...data.notes.map((n) => ({
        t: n.created_at, kind: "note" as const, id: n.id, body: n.body,
        author: n.author_username ?? (n.author_id ? `#${n.author_id}` : null),
      })),
      ...data.timeline
        .filter((e) => !["message_in", "message_out", "note"].includes(e.kind))
        .map((e) => ({
          t: e.at, kind: "event" as const,
          label: eventLabel(e),
        })),
    ].sort((a, b) => a.t.localeCompare(b.t));
  }, [data]);
  useEffect(() => {
    if (followLatest.current) scroller.current?.scrollTo({top: scroller.current.scrollHeight});
  }, [items.length]);

  if (caseId == null) {
    return <Card className="grid place-items-center text-sm text-muted-foreground">Select a case to open the thread.</Card>;
  }
  if (detail.isLoading) return <LoadingState label="Loading thread…"/>;
  if (detail.error) return <ErrorState message={detail.error.message}/>;
  if (!data) return <EmptyState title="Case not found" body="It may have been reassigned or closed."/>;

  return (
    <Card aria-label="Conversation" className="flex h-[max(640px,calc(100dvh-16rem))] min-w-0 flex-col gap-3 overflow-hidden p-4">
      <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b pb-3">
        <span className="numeric text-xs font-semibold text-muted-foreground">C-{data.case.id}</span>
        <span className="text-sm font-semibold">{data.customer.display_name ?? data.customer.handle ?? "Unknown"}</span>
        <span className="rounded-full border bg-muted px-2 py-0.5 text-[0.6875rem] font-semibold text-muted-foreground">
          {data.case.state.replaceAll("_", " ")}
        </span>
        <span className="numeric ml-auto text-[0.6875rem] text-muted-foreground">
          open {elapsed(data.case.opened_at, data.case.closed_at)}
          {" · "}
          {data.case.first_response_at
            ? `first reply ${elapsed(data.case.opened_at, data.case.first_response_at)}`
            : "awaiting first reply"}
        </span>
      </div>

      <div ref={scroller} role="region" aria-label="Message thread" tabIndex={0}
        aria-live="polite" aria-relevant="additions"
        onScroll={() => {
          const el = scroller.current;
          if (el) followLatest.current = el.scrollHeight - el.scrollTop - el.clientHeight < 64;
        }}
        className="grid min-h-48 flex-1 content-start gap-2 overflow-y-auto overscroll-contain pr-1 [overflow-wrap:anywhere]">
        {items.length === 0 && <p className="text-sm text-muted-foreground">No activity yet.</p>}
        {items.map((it) => {
          if (it.kind === "msg") {
            return (
              <MessageBubble
                key={threadItemKey(it)}
                direction={it.m.direction}
                body={it.m.body}
                author={it.m.author}
                at={it.m.sent_at}
                channel={it.m.direction === "inbound" ? (it.m.channel as string) : undefined}
                permalink={it.m.permalink}
              />
            );
          }
          if (it.kind === "note") {
            return <MessageBubble key={threadItemKey(it)} direction="note" body={it.body} author={it.author} at={it.t}/>;
          }
          return (
            <p key={threadItemKey(it)} className="my-0.5 text-center text-[0.6875rem] text-muted-foreground">
              · {it.label} · {new Date(it.t).toLocaleTimeString()}
            </p>
          );
        })}
      </div>

      {/* F7.3 — keyed by case: switching cases must not leak one case's draft
          reply, open action panel or stale send-error into the next case.
          Root-caused 2026-09-11: both keys were the bare case id -- React
          requires unique keys among ALL keyed siblings under one parent, not
          just within one .map(), so CaseActions and ReplyComposer sharing
          key={data.case.id} was a genuine "two children with the same key"
          collision (confirmed live via the browser console), not a cache
          artifact -- prefixed apart so they can never collide, including
          with any future sibling that also keys off the case id. */}
      <div className="max-h-[52%] shrink-0 space-y-3 overflow-y-auto overscroll-contain border-t pr-1 pt-3">
        <CaseActions key={`actions-${data.case.id}`} caseId={data.case.id} customer={data.customer}/>

        {data.case.state !== "closed" && (
          <ReplyComposer
            key={`composer-${data.case.id}`}
            caseId={data.case.id}
            value={draft}
            onValueChange={onDraftChange}
            platform={data.customer.platform ?? data.case.channel ?? "meta"}
            channel={data.case.channel}
            targetRef={data.customer.handle}
          />
        )}
      </div>
    </Card>
  );
}

