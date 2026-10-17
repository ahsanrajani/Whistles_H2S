"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {useEffect, useState} from "react";
import {History} from "lucide-react";
import {apiFetch} from "@/lib/api";
import {useCareSessionHistory, useCareSessionState} from "@/hooks/use-api";
import {cn} from "@/lib/utils";
import {PresenceDot, type Presence} from "@/components/care/primitives";

/**
 * F1.9 — agent shift status in the app shell. Available / Busy / Not available,
 * with an optional reason. Writes POST /care/session; also beats
 * /care/heartbeat every 45s so the supervisor roster sees the agent as online.
 *
 * Hamza, 2026-09-11: "make sure the .../busy/break/ toggle ... works, by
 * default available when logging in, not available when logging out, all
 * times/activity is logged and displayed." Three real gaps this closes:
 * the control used to hardcode "Not available" on every mount instead of
 * reading the real, persisted state (now GET /care/session); login/logout
 * didn't set a state at all (see login-form.tsx and app-shell.tsx's
 * logout()); and there was nowhere to actually see past activity (the
 * history list below, from GET /care/session/history).
 */
const OPTIONS = [
  {value: "ready", label: "Available", presence: "online" as Presence},
  {value: "idle", label: "Busy", presence: "idle" as Presence},
  {value: "not_ready", label: "Not available", presence: "offline" as Presence},
] as const;

const EVENT_LABEL: Record<string, string> = {
  ready: "Available", not_ready: "Not available", idle: "Busy", active: "Active",
  login: "Logged in", logout: "Logged out",
};

function fmtWhen(iso: string): string {
  const d = new Date(iso);
  const sameDay = d.toDateString() === new Date().toDateString();
  return sameDay
    ? d.toLocaleTimeString(undefined, {hour: "numeric", minute: "2-digit"})
    : d.toLocaleString(undefined, {month: "short", day: "numeric", hour: "numeric", minute: "2-digit"});
}

export function AgentStatusControl() {
  const query = useQueryClient();
  const [reason, setReason] = useState("");
  const [open, setOpen] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  const current = useCareSessionState();
  const history = useCareSessionHistory(showHistory);

  const set = useMutation({
    mutationFn: (next: {state: string; reason?: string}) =>
      apiFetch("/care/session", {method: "POST", body: JSON.stringify(next)}),
    onSuccess: () => {
      query.invalidateQueries({queryKey: ["care", "session"]});
      setOpen(false);
      setReason("");
    },
  });

  useEffect(() => {
    const beat = () => { void apiFetch("/care/heartbeat", {method: "POST"}).catch(() => {}); };
    beat();
    const id = window.setInterval(beat, 45_000);
    return () => window.clearInterval(id);
  }, []);

  const state = current.data?.state ?? "not_ready";
  const option = OPTIONS.find((o) => o.value === state) ?? OPTIONS[2];

  return (
    <div className="relative hidden md:block">
      <button type="button" onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu" aria-expanded={open}
        className="inline-flex items-center gap-2 rounded-[0.625rem] border bg-card px-3 py-2 text-sm font-medium hover:bg-muted">
        <PresenceDot presence={option.presence}/>
        {option.label}
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-40 mt-1 w-64 rounded-[0.75rem] border bg-card p-1.5 shadow-2xl">
          {OPTIONS.map((o) => (
            <button key={o.value} type="button" role="menuitemradio" aria-checked={o.value === state}
              disabled={set.isPending}
              onClick={() => set.mutate({state: o.value, reason: reason || undefined})}
              className={cn(
                "flex w-full items-center gap-2 rounded-[0.5625rem] px-2.5 py-2 text-left text-sm disabled:opacity-50",
                o.value === state ? "bg-primary/10 text-primary dark:text-highlight" : "hover:bg-muted",
              )}>
              <PresenceDot presence={o.presence}/>{o.label}
            </button>
          ))}
          <input
            aria-label="Status reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Reason (optional)"
            className="mt-1 h-8 w-full rounded-[0.5625rem] border bg-card px-2 text-xs placeholder:text-muted-foreground"
          />
          {set.isError && <p className="mt-1 px-1 text-xs text-danger">{(set.error as Error).message}</p>}

          <button type="button" onClick={() => setShowHistory((v) => !v)}
            className="mt-1.5 flex w-full items-center gap-1.5 rounded-[0.5625rem] px-2.5 py-1.5 text-left text-xs font-semibold text-muted-foreground hover:bg-muted hover:text-foreground">
            <History size={13}/>{showHistory ? "Hide" : "Show"} recent activity
          </button>
          {showHistory && (
            <div className="mt-1 max-h-40 overflow-y-auto border-t pt-1.5">
              {history.isLoading && <p className="px-2.5 py-1 text-xs text-muted-foreground">Loading…</p>}
              {history.data && history.data.events.length === 0 && (
                <p className="px-2.5 py-1 text-xs text-muted-foreground">No activity yet.</p>
              )}
              {(history.data?.events ?? []).map((e, i) => (
                <div key={`${e.kind}-${e.at}-${i}`} className="flex items-center gap-2 px-2.5 py-1 text-xs">
                  <span className="font-medium">{EVENT_LABEL[e.kind] ?? e.kind}</span>
                  {e.reason && <span className="truncate text-muted-foreground">— {e.reason}</span>}
                  <span className="numeric ml-auto shrink-0 text-muted-foreground">{fmtWhen(e.at)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
