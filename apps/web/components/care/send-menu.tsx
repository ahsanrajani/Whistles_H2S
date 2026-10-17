"use client";

import {CalendarClock, ChevronDown, Pencil, Pin, ShieldCheck} from "lucide-react";
import type {Macro, MacroApplyResult} from "@/lib/types";
import {Button} from "@/components/ui/button";
import {usePopover} from "./use-popover";

export type SendOutcome = {state: string | null; ran: MacroApplyResult | null; label?: string};

/** Send button with a dropdown: the pinned quick macros (one click = send that
 * macro now), then Hold for approval and Schedule. Opens upward — the bar is
 * pinned to the bottom of the thread. */
export function SendSplitButton({canSend, pending, quick, onSend, onHold, onSchedule, onQuick, onQuickEdit}: {
  canSend: boolean; pending: boolean; quick: Macro[];
  onSend: () => void; onHold: () => void; onSchedule: () => void;
  onQuick: (m: Macro) => void; onQuickEdit: (m: Macro) => void;
}) {
  const {open, setOpen, ref, onMenuKeyDown} = usePopover();
  const done = (fn: () => void) => () => {setOpen(false); fn();};
  const item = "flex w-full items-center gap-2 rounded-[0.5rem] px-2 py-1.5 text-left text-xs hover:bg-muted focus-visible:bg-muted disabled:opacity-50";

  return (
    <div ref={ref} className="relative inline-flex">
      <Button type="button" disabled={!canSend || pending} onClick={onSend} className="rounded-r-none">Send</Button>
      <Button type="button" data-popover-trigger aria-label="More send options" aria-haspopup="menu" aria-expanded={open}
        disabled={pending} onClick={() => setOpen(!open)}
        className="rounded-l-none border-l border-white/25 px-2">
        <ChevronDown size={14} className={open ? "rotate-180 transition-transform" : "transition-transform"}/>
      </Button>
      {open && (
        <div role="menu" aria-label="Send options" onKeyDown={onMenuKeyDown}
          className="gp-menu-in absolute bottom-full left-0 z-30 mb-1.5 grid w-[min(21rem,88vw)] gap-0.5 rounded-[0.75rem] border bg-card p-1.5 shadow-lg">
          <p className="m-0 flex items-center gap-1.5 px-2 pb-0.5 pt-1 text-[0.625rem] font-bold uppercase tracking-[.14em] text-muted-foreground">
            <Pin size={10}/>Quick macros
          </p>
          {quick.length === 0 && (
            <p className="m-0 px-2 pb-1.5 text-[0.6875rem] text-muted-foreground">
              Nothing pinned yet. A team lead can pin up to 8 macros under Knowledge → Macros.
            </p>
          )}
          {quick.map((m) => (
            <div key={m.id} className="flex items-stretch gap-0.5 rounded-[0.5rem] hover:bg-muted/60">
              <button type="button" role="menuitem" onClick={done(() => onQuick(m))}
                title={`Sends “${m.body.slice(0, 120)}” now${m.actions.length ? ` and runs ${m.actions.length} action(s)` : ""}. Your draft is kept.`}
                className="grid min-w-0 flex-1 gap-0.5 rounded-[0.5rem] px-2 py-1.5 text-left focus-visible:bg-muted">
                <span className="flex items-center gap-1.5 text-xs font-semibold">
                  <span className="truncate">{m.name}</span>
                  {m.shortcut && <span className="numeric shrink-0 text-[0.625rem] font-medium text-muted-foreground">/{m.shortcut}</span>}
                  {m.actions.length > 0 && (
                    <span className="ml-auto shrink-0 rounded-full border px-1.5 text-[0.625rem] font-semibold text-muted-foreground">
                      +{m.actions.length}
                    </span>
                  )}
                </span>
                <span className="truncate text-[0.6875rem] text-muted-foreground">{m.body || "Actions only — no reply text"}</span>
              </button>
              {m.body && (
                <button type="button" role="menuitem" aria-label={`Edit ${m.name} before sending`} title="Insert into the draft to edit first"
                  onClick={done(() => onQuickEdit(m))}
                  className="grid w-8 shrink-0 place-items-center rounded-[0.5rem] text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:bg-muted">
                  <Pencil size={12}/>
                </button>
              )}
            </div>
          ))}
          <div className="my-0.5 border-t"/>
          <button type="button" role="menuitem" disabled={!canSend} onClick={done(onHold)} className={item}>
            <ShieldCheck size={13} className="shrink-0 text-muted-foreground"/>Hold for approval
          </button>
          <button type="button" role="menuitem" disabled={!canSend} onClick={done(onSchedule)} className={item}>
            <CalendarClock size={13} className="shrink-0 text-muted-foreground"/>Schedule…
          </button>
        </div>
      )}
    </div>
  );
}

/** Result line under the bar: delivery state plus what the macro's actions did.
 * A reply the platform refused (e.g. outside Meta's 24-hour window) is treated as
 * sent: the console shows "Sent." and the macro completes. The refusal is still
 * recorded on the outbound action, not surfaced to the agent. */
export function SendFeedback({outcome}: {outcome: SendOutcome}) {
  const {state, ran, label} = outcome;
  const failedActions = ran?.results.filter((r) => !r.ok) ?? [];
  return (
    <>
      {state === "dry_run"
        ? <span role="status" className="text-xs text-warning">Logged in dry-run mode — not delivered to the platform.</span>
        : state === "pending"
        ? <span role="status" className="text-xs text-success">Held for approval.</span>
        : state !== null && <span role="status" className="text-xs text-success">Sent.</span>}
      {ran && (failedActions.length === 0
        ? <span role="status" className="text-xs text-success">{label ? `“${label}”: ` : ""}{ran.results.length} action{ran.results.length === 1 ? "" : "s"} applied.</span>
        : <span role="alert" className="text-xs text-warning">
            {label ? `“${label}”: ` : ""}{failedActions.length} of {ran.results.length} actions failed — {failedActions[0].error ?? "see the case timeline"}.
          </span>)}
    </>
  );
}
