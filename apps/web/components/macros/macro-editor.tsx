"use client";

import {useMutation} from "@tanstack/react-query";
import {ArrowDown, ArrowUp, Trash2} from "lucide-react";
import {useRef, useState} from "react";
import {useCareAgents} from "@/hooks/use-api";
import {apiFetch} from "@/lib/api";
import {
  ACTION_LABEL, CLOSURE_CATEGORIES, MACRO_CATEGORIES, MAX_ACTIONS, PLACEHOLDERS, PRIORITIES, STATUSES,
  humanize, newAction, sampleRender,
} from "@/lib/macro-utils";
import type {Macro, MacroAction} from "@/lib/types";
import {Button} from "@/components/ui/button";
import {Card} from "@/components/ui/card";
import {Input} from "@/components/ui/input";
import {Select} from "@/components/ui/select";

// Stable row ids so per-row local state (the tags text) follows a row when others move or go.
let seq = 0;
const row = (a: MacroAction) => ({id: ++seq, a});

const field = "h-9 text-sm";
const area = "w-full resize-y rounded-[0.625rem] border bg-card p-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-highlight/40";

export function MacroEditor({initial, quickCount, onSaved, onCancel}: {
  initial?: Macro; quickCount: number; onSaved: () => void; onCancel: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [category, setCategory] = useState(initial?.category ?? "general");
  const [shortcut, setShortcut] = useState(initial?.shortcut ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [body, setBody] = useState(initial?.body ?? "");
  const [rows, setRows] = useState(() => (initial?.actions ?? []).map(row));
  const actions = rows.map((r) => r.a);
  const [isQuick, setIsQuick] = useState(initial?.is_quick ?? false);
  const [active, setActive] = useState(initial?.active ?? true);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const agents = useCareAgents();

  const save = useMutation({
    mutationFn: () => {
      const payload = {name, category, shortcut: shortcut.trim().replace(/^\//, "") || null,
        description: description.trim() || null, body, actions, is_quick: isQuick, active};
      return initial
        ? apiFetch(`/macros/${initial.id}`, {method: "PUT", body: JSON.stringify(payload)})
        : apiFetch("/macros", {method: "POST", body: JSON.stringify(payload)});
    },
    onSuccess: onSaved,
  });

  function insertPlaceholder(key: string) {
    const el = bodyRef.current;
    const token = `{{${key}}}`;
    const [from, to] = el ? [el.selectionStart, el.selectionEnd] : [body.length, body.length];
    setBody(body.slice(0, from) + token + body.slice(to));
    requestAnimationFrame(() => {el?.focus(); el?.setSelectionRange(from + token.length, from + token.length);});
  }
  const patch = (i: number, next: MacroAction) => setRows(rows.map((r, j) => (j === i ? {...r, a: next} : r)));
  const move = (i: number, by: -1 | 1) => {
    const next = [...rows];
    [next[i], next[i + by]] = [next[i + by], next[i]];
    setRows(next);
  };
  const empty = !body.trim() && actions.length === 0;
  const quickFull = !initial?.is_quick && quickCount >= 8;

  return (
    <Card className="gp-rise grid gap-3">
      <div className="flex flex-wrap gap-2">
        <Input aria-label="Macro name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Name, e.g. Refund acknowledged" className={`${field} min-w-48 flex-1`}/>
        <Select aria-label="Macro category" value={category} onChange={(e) => setCategory(e.target.value)} className={`${field} max-w-40`}>
          {MACRO_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </Select>
        <div className="relative w-40">
          <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">/</span>
          <Input aria-label="Macro shortcut" value={shortcut.replace(/^\//, "")} onChange={(e) => setShortcut(e.target.value.toLowerCase())}
            placeholder="shortcut" className={`${field} w-full pl-5`}/>
        </div>
      </div>
      <Input aria-label="Macro description" value={description} onChange={(e) => setDescription(e.target.value)}
        placeholder="When to use it (optional — shown in the picker)" className={field}/>

      <div className="grid gap-1.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-semibold text-muted-foreground">Reply text</span>
          {PLACEHOLDERS.map((p) => (
            <button key={p.key} type="button" onClick={() => insertPlaceholder(p.key)} title={`{{${p.key}}}`}
              className="rounded-full border bg-card px-2 py-0.5 text-[0.6875rem] font-medium hover:bg-muted">+ {p.label}</button>
          ))}
        </div>
        <textarea ref={bodyRef} aria-label="Macro body" value={body} onChange={(e) => setBody(e.target.value)} rows={4}
          placeholder="Hi {{customer.first_name|there}}, thanks for reaching out…" className={area}/>
        <p className="m-0 text-[0.6875rem] text-muted-foreground">
          Add a fallback with <code>{"{{customer.first_name|there}}"}</code> for when a detail is unknown.
          {body.trim() && <> Sample: <span className="text-foreground">{sampleRender(body)}</span></>}
        </p>
      </div>

      <div className="grid gap-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-muted-foreground">Then, on the case</span>
          <span className="text-[0.6875rem] text-muted-foreground">(optional — runs when the agent sends)</span>
        </div>
        {rows.map(({id, a}, i) => (
          <div key={id} className="gp-rise flex flex-wrap items-center gap-1.5 rounded-[0.625rem] border bg-muted/30 p-1.5">
            <Select aria-label={`Action ${i + 1} type`} value={a.type} className="h-8 text-xs"
              onChange={(e) => setRows(rows.map((r, j) => (j === i ? row(newAction(e.target.value as MacroAction["type"])) : r)))}>
              {(Object.keys(ACTION_LABEL) as MacroAction["type"][]).map((t) => <option key={t} value={t}>{ACTION_LABEL[t]}</option>)}
            </Select>
            <ActionParams action={a} onChange={(next) => patch(i, next)} agents={agents.data?.agents ?? []} index={i}/>
            <span className="ml-auto flex items-center gap-0.5">
              <button type="button" aria-label="Move up" disabled={i === 0} onClick={() => move(i, -1)} className="rounded p-1 text-muted-foreground hover:text-foreground disabled:opacity-30"><ArrowUp size={13}/></button>
              <button type="button" aria-label="Move down" disabled={i === actions.length - 1} onClick={() => move(i, 1)} className="rounded p-1 text-muted-foreground hover:text-foreground disabled:opacity-30"><ArrowDown size={13}/></button>
              <button type="button" aria-label="Remove action" onClick={() => setRows(rows.filter((_, j) => j !== i))} className="rounded p-1 text-muted-foreground hover:text-danger"><Trash2 size={13}/></button>
            </span>
          </div>
        ))}
        {actions.length < MAX_ACTIONS && (
          <Select aria-label="Add an action" value="" className="h-8 w-max text-xs"
            onChange={(e) => e.target.value && setRows([...rows, row(newAction(e.target.value as MacroAction["type"]))])}>
            <option value="">+ Add an action…</option>
            {(Object.keys(ACTION_LABEL) as MacroAction["type"][]).map((t) => <option key={t} value={t}>{ACTION_LABEL[t]}</option>)}
          </Select>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 text-xs">
        <label className={`flex items-center gap-1.5 ${quickFull ? "opacity-50" : ""}`}
          title={quickFull ? "8 macros are already pinned — unpin one first" : "Shows in every agent's Send dropdown for one-click use"}>
          <input type="checkbox" checked={isQuick} disabled={quickFull} onChange={(e) => setIsQuick(e.target.checked)}/>
          Pin as quick macro <span className="text-muted-foreground">({quickCount}/8 pinned)</span>
        </label>
        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)}/>Active
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" disabled={!name.trim() || empty || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? "Saving…" : "Save macro"}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
        {empty && name.trim() && <span className="text-xs text-muted-foreground">Add reply text or at least one action.</span>}
        {save.isError && <span role="alert" className="text-xs text-danger">{(save.error as Error).message}</span>}
      </div>
    </Card>
  );
}

function ActionParams({action, onChange, agents, index}: {
  action: MacroAction; onChange: (a: MacroAction) => void;
  agents: {user_id: number; username: string}[]; index: number;
}) {
  const [tagText, setTagText] = useState(action.type === "add_tags" ? action.tags.join(", ") : "");
  const cls = "h-8 text-xs";
  switch (action.type) {
    case "set_status":
      return (
        <>
          <Select aria-label={`Action ${index + 1} status`} value={action.status} className={cls}
            onChange={(e) => onChange({type: "set_status", status: e.target.value as typeof action.status,
              closure_category: e.target.value === "closed" ? "resolved" : undefined})}>
            {STATUSES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </Select>
          {action.status === "closed" && (
            <Select aria-label={`Action ${index + 1} closure reason`} value={action.closure_category ?? "resolved"} className={cls}
              onChange={(e) => onChange({...action, closure_category: e.target.value})}>
              {CLOSURE_CATEGORIES.map((c) => <option key={c} value={c}>{humanize(c)}</option>)}
            </Select>
          )}
        </>
      );
    case "assign":
      return (
        <>
          <Select aria-label={`Action ${index + 1} assignee`} className={cls}
            value={action.mode === "agent" ? `agent:${action.user_id ?? ""}` : action.mode}
            onChange={(e) => {
              const v = e.target.value;
              onChange(v.startsWith("agent:") ? {type: "assign", mode: "agent", user_id: Number(v.slice(6)) || undefined}
                : {type: "assign", mode: v as "self" | "auto"});
            }}>
            <option value="self">Me (the agent who sends)</option>
            <option value="auto">Next available agent</option>
            <option value="agent:">A specific agent…</option>
            {agents.map((a) => <option key={a.user_id} value={`agent:${a.user_id}`}>{a.username}</option>)}
          </Select>
        </>
      );
    case "add_note":
      return (
        <input aria-label={`Action ${index + 1} note`} value={action.body} onChange={(e) => onChange({...action, body: e.target.value})}
          placeholder="Internal note (supports {{placeholders}})" className="h-8 min-w-48 flex-1 rounded-[0.625rem] border bg-card px-2.5 text-xs"/>
      );
    case "set_priority":
      return (
        <Select aria-label={`Action ${index + 1} priority`} value={action.priority} className={cls}
          onChange={(e) => onChange({type: "set_priority", priority: e.target.value as typeof action.priority})}>
          {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
        </Select>
      );
    default:
      return (
        <input aria-label={`Action ${index + 1} tags`} value={tagText} placeholder="refund, vip"
          onChange={(e) => {
            setTagText(e.target.value);
            onChange({type: "add_tags", tags: e.target.value.split(",").map((t) => t.trim()).filter(Boolean)});
          }}
          className="h-8 min-w-40 flex-1 rounded-[0.625rem] border bg-card px-2.5 text-xs"/>
      );
  }
}

