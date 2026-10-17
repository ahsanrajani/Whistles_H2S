"use client";

import {useState, type KeyboardEvent} from "react";
import {Pin, Search, X, Zap} from "lucide-react";
import type {Macro, MacroPreview} from "@/lib/types";
import {cn} from "@/lib/utils";
import {Input} from "@/components/ui/input";
import {usePopover} from "./use-popover";

/** A macro that has been dropped into the draft, with its actions still to run
 * on send. `off` holds the indexes the agent un-ticked. */
export type AppliedMacro = {macro: Macro; actions: MacroPreview["actions"]; off: number[]};

const norm = (s: string | null | undefined) => (s ?? "").toLowerCase();

export function MacroPicker({macros, loading, busy, onPick}: {
  macros: Macro[]; loading: boolean; busy: boolean; onPick: (m: Macro) => void;
}) {
  const {open, setOpen, ref, onMenuKeyDown} = usePopover();
  const [q, setQ] = useState("");
  const needle = q.trim().toLowerCase();
  const shown = needle
    ? macros.filter((m) => [m.name, m.shortcut, m.category, m.body].some((f) => norm(f).includes(needle)))
    : macros;

  return (
    <div ref={ref} className="relative">
      <button type="button" data-popover-trigger aria-haspopup="menu" aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="inline-flex h-8 items-center gap-1.5 rounded-[0.5625rem] border bg-card px-2.5 text-xs font-semibold hover:bg-muted">
        <Zap size={12} className="text-highlight"/>Macros
      </button>
      {open && (
        <div role="menu" aria-label="Macros" onKeyDown={onMenuKeyDown}
          className="gp-menu-in absolute left-0 top-full z-30 mt-1.5 grid w-[min(22rem,88vw)] gap-1 rounded-[0.75rem] border bg-card p-1.5 shadow-lg">
          <div className="relative">
            <Search size={12} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"/>
            <Input autoFocus aria-label="Search macros" placeholder="Search macros…" value={q}
              onChange={(e) => setQ(e.target.value)} className="h-8 pl-7 text-xs"/>
          </div>
          <div className="grid max-h-64 gap-0.5 overflow-y-auto">
            {loading && <p className="m-0 p-2 text-xs text-muted-foreground">Loading macros…</p>}
            {!loading && shown.length === 0 && (
              <p className="m-0 p-2 text-xs text-muted-foreground">
                {macros.length === 0
                  ? "No macros yet. A team lead or admin can create them under Knowledge → Macros."
                  : "No macro matches your search."}
              </p>
            )}
            {shown.map((m) => (
              <button key={m.id} type="button" role="menuitem" disabled={busy}
                onClick={() => {onPick(m); setOpen(false); setQ("");}}
                className="grid gap-0.5 rounded-[0.5rem] px-2 py-1.5 text-left hover:bg-muted focus-visible:bg-muted disabled:opacity-50">
                <span className="flex items-center gap-1.5 text-xs font-semibold">
                  {m.is_quick && <Pin size={10} className="shrink-0 text-highlight" aria-label="Quick macro"/>}
                  <span className="truncate">{m.name}</span>
                  {m.shortcut && <span className="numeric shrink-0 text-[0.625rem] font-medium text-muted-foreground">/{m.shortcut}</span>}
                  {m.actions.length > 0 && (
                    <span className="ml-auto shrink-0 rounded-full border px-1.5 text-[0.625rem] font-semibold text-muted-foreground">
                      {m.actions.length} action{m.actions.length === 1 ? "" : "s"}
                    </span>
                  )}
                </span>
                <span className="line-clamp-2 text-[0.6875rem] text-muted-foreground">{m.description || m.body || "Actions only — no reply text"}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---- "/shortcut" typed at the start of an empty draft ------------------------
export function slashQuery(text: string): string | null {
  const m = /^\/([a-z0-9_-]*)$/i.exec(text.trim());
  return m ? m[1].toLowerCase() : null;
}

export function useSlashMenu(text: string, macros: Macro[], onPick: (m: Macro) => void) {
  const q = slashQuery(text);
  // Selection is keyed to the query so it resets as you type, without an effect.
  const [sel, setSel] = useState({q: "", i: 0});
  const matches = q === null ? [] : macros.filter((m) =>
    q === "" ? !!m.shortcut || m.is_quick : norm(m.shortcut).startsWith(q) || norm(m.name).includes(q)).slice(0, 5);
  const index = sel.q === q ? Math.min(sel.i, Math.max(matches.length - 1, 0)) : 0;

  function onKeyDown(e: KeyboardEvent): boolean {
    if (!matches.length) return false;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      const step = e.key === "ArrowDown" ? 1 : -1;
      setSel({q: q ?? "", i: (index + step + matches.length) % matches.length});
    } else if (e.key === "Enter" || e.key === "Tab") {
      onPick(matches[index]);
    } else return false;
    e.preventDefault();
    return true;
  }
  return {matches, index, onKeyDown, onPick};
}

export function SlashList({matches, index, onPick}: {
  matches: Macro[]; index: number; onPick: (m: Macro) => void;
}) {
  if (!matches.length) return null;
  return (
    <ul role="listbox" aria-label="Macro shortcuts"
      className="gp-menu-in m-0 grid list-none gap-0.5 rounded-[0.625rem] border bg-card p-1 shadow-md">
      {matches.map((m, i) => (
        <li key={m.id} role="option" aria-selected={i === index}
          // mousedown (not click) so the textarea keeps focus
          onMouseDown={(e) => {e.preventDefault(); onPick(m);}}
          className={cn("flex cursor-pointer items-center gap-2 rounded-[0.4375rem] px-2 py-1 text-xs",
            i === index ? "bg-primary/10 text-primary dark:text-highlight" : "hover:bg-muted")}>
          <Zap size={11} className="shrink-0"/>
          <span className="font-semibold">{m.name}</span>
          {m.shortcut && <span className="numeric text-[0.625rem] text-muted-foreground">/{m.shortcut}</span>}
          <span className="ml-auto truncate text-[0.6875rem] text-muted-foreground">{m.body.slice(0, 48)}</span>
        </li>
      ))}
    </ul>
  );
}

// ---- action chips under the draft ------------------------------------------------
export function MacroChips({applied, onToggle, onClear}: {
  applied: AppliedMacro; onToggle: (index: number) => void; onClear: () => void;
}) {
  return (
    <div className="gp-rise flex flex-wrap items-center gap-1.5 rounded-[0.625rem] border border-primary/20 bg-primary/5 px-2.5 py-1.5 text-xs">
      <span className="inline-flex items-center gap-1 font-semibold text-primary dark:text-highlight">
        <Zap size={11}/>{applied.macro.name}
      </span>
      {applied.actions.length > 0 && <span className="text-muted-foreground">runs on send:</span>}
      {applied.actions.map((a, i) => {
        const on = !applied.off.includes(i);
        return (
          <label key={i} className={cn("inline-flex cursor-pointer items-center gap-1 rounded-full border bg-card px-2 py-0.5 text-[0.6875rem]",
            on ? "font-medium" : "text-muted-foreground line-through")}>
            <input type="checkbox" checked={on} onChange={() => onToggle(i)} className="size-3"/>{a.summary}
          </label>
        );
      })}
      <button type="button" aria-label="Detach macro" onClick={onClear}
        className="ml-auto text-muted-foreground hover:text-foreground"><X size={12}/></button>
    </div>
  );
}
