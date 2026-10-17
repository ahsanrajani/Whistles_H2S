"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {Bot, Clock, Trash2} from "lucide-react";
import {useState} from "react";
import {useMacroRules, useMacros} from "@/hooks/use-api";
import {apiFetch} from "@/lib/api";
import {CHANNELS, describeTrigger, humanize} from "@/lib/macro-utils";
import type {Macro, MacroReplyMode, MacroRule, MacroTrigger} from "@/lib/types";
import {cn} from "@/lib/utils";
import {EmptyState, ErrorState, LoadingState} from "@/components/states";
import {Button} from "@/components/ui/button";
import {Card} from "@/components/ui/card";
import {Input} from "@/components/ui/input";
import {Select} from "@/components/ui/select";

type TriggerType = MacroTrigger["type"];
const TRIGGERS: {type: TriggerType; label: string; hint: string}[] = [
  {type: "new_case", label: "A new case opens", hint: "Right after the first message arrives."},
  {type: "no_response", label: "No agent reply for", hint: "Fires if the customer is still waiting after this long."},
  {type: "unassigned_for", label: "Case unassigned for", hint: "Nobody picked it up in this time."},
  {type: "sla_breach", label: "SLA is breached", hint: "When the first-response SLA runs out."},
  {type: "keyword", label: "Message contains", hint: "Any of these words, case-insensitive."},
];
const MODES: {key: MacroReplyMode; label: string; hint: string}[] = [
  {key: "hold", label: "Hold for approval", hint: "Drafts the reply in the approvals queue — a person sends it. Recommended."},
  {key: "send", label: "Send automatically", hint: "Posts the reply to the customer straight away."},
  {key: "none", label: "Don't reply", hint: "Only run the macro's case actions (tag, assign, prioritise…)."},
];

/** Auto macros: rules that run a macro when ANY of their triggers fires. */
export function AutoMacrosTab() {
  const query = useQueryClient();
  const rules = useMacroRules();
  const macroList = useMacros({includeInactive: true});
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const refresh = () => query.invalidateQueries({queryKey: ["care"]});

  const toggle = useMutation({
    mutationFn: (r: MacroRule) => apiFetch(`/macro-rules/${r.id}`, {method: "PUT", body: JSON.stringify({active: !r.active})}),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: number) => apiFetch(`/macro-rules/${id}`, {method: "DELETE"}),
    onSuccess: refresh,
  });
  const macros = (macroList.data?.macros ?? []).filter((m) => m.active);

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-3 rounded-[0.75rem] border bg-card p-3">
        <Bot size={18} className="shrink-0 text-highlight"/>
        <p className="m-0 min-w-56 flex-1 text-xs text-muted-foreground">
          An auto macro runs a macro for you when something happens on a case — for example, no agent has replied in 5 minutes.
          Each rule fires <strong className="text-foreground">at most once per case</strong>, skips closed cases, and only reacts to recent messages.
        </p>
        {editing === null && <Button type="button" variant="outline" className="h-9 text-xs" onClick={() => setEditing("new")}>New auto macro</Button>}
      </div>

      {editing === "new" && (
        <RuleEditor key="new" macros={macros} onSaved={() => {setEditing(null); refresh();}} onCancel={() => setEditing(null)}/>
      )}
      {rules.isLoading && <LoadingState label="Loading auto macros…"/>}
      {rules.error && <ErrorState message={rules.error.message}/>}
      {rules.data && rules.data.rules.length === 0 && editing !== "new" && (
        <EmptyState title="No auto macros" body="Create a rule to nudge customers, route cases or tag them automatically."/>
      )}
      {(rules.data?.rules ?? []).map((r) => editing === r.id ? (
        <RuleEditor key={r.id} initial={r} macros={macros} onSaved={() => {setEditing(null); refresh();}} onCancel={() => setEditing(null)}/>
      ) : (
        <Card key={r.id} className={cn("grid gap-2", !r.active && "opacity-60")}>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{r.name}</span>
            <span className="rounded-full border px-1.5 py-0.5 text-[0.625rem] font-semibold text-muted-foreground">
              {r.reply_mode === "hold" ? "holds reply" : r.reply_mode === "send" ? "auto-sends" : "actions only"}
            </span>
            <span className="ml-auto flex items-center gap-1.5">
              <label className="flex cursor-pointer items-center gap-1.5 text-xs">
                <input type="checkbox" role="switch" checked={r.active} disabled={toggle.isPending} onChange={() => toggle.mutate(r)}/>
                {r.active ? "On" : "Off"}
              </label>
              <Button type="button" variant="outline" className="h-7 text-xs" onClick={() => setEditing(r.id)}>Edit</Button>
              <button type="button" aria-label={`Delete ${r.name}`} disabled={remove.isPending}
                onClick={() => window.confirm(`Delete the auto macro “${r.name}”?`) && remove.mutate(r.id)}
                className="grid size-7 place-items-center rounded-[0.5rem] border text-muted-foreground hover:border-danger/40 hover:text-danger">
                <Trash2 size={13}/>
              </button>
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <span className="font-semibold text-muted-foreground">When any of</span>
            {r.triggers.map((t) => (
              <span key={t.type} className="inline-flex items-center gap-1 rounded-full border bg-muted/40 px-2 py-0.5 text-[0.6875rem] font-medium">
                {(t.type === "no_response" || t.type === "unassigned_for") && <Clock size={10}/>}{describeTrigger(t)}
              </span>
            ))}
            <span className="font-semibold text-muted-foreground">→ run</span>
            <span className="font-semibold">{r.macro_name}</span>
          </div>
          <p className="m-0 flex flex-wrap gap-x-3 text-[0.6875rem] text-muted-foreground">
            {r.filters.channels?.length ? <span>Only on {r.filters.channels.map(humanize).join(", ")}</span> : <span>All channels</span>}
            {r.filters.vip_only && <span>VIP customers only</span>}
            <span className="numeric">Fired on {r.fired_count} case{r.fired_count === 1 ? "" : "s"}{r.last_fired_at ? ` · last ${new Date(r.last_fired_at).toLocaleString()}` : ""}</span>
          </p>
        </Card>
      ))}
      {(toggle.isError || remove.isError) && <p role="alert" className="m-0 text-xs text-danger">{((toggle.error ?? remove.error) as Error).message}</p>}
    </div>
  );
}

function RuleEditor({initial, macros, onSaved, onCancel}: {
  initial?: MacroRule; macros: Macro[]; onSaved: () => void; onCancel: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [macroId, setMacroId] = useState<number | "">(initial?.macro_id ?? "");
  const [trig, setTrig] = useState<Record<string, MacroTrigger>>(
    Object.fromEntries((initial?.triggers ?? []).map((t) => [t.type, t])));
  const [wordText, setWordText] = useState(() => {
    const k = initial?.triggers.find((t) => t.type === "keyword");
    return k && k.type === "keyword" ? k.words.join(", ") : "";
  });
  const [channels, setChannels] = useState<string[]>(initial?.filters.channels ?? []);
  const [vip, setVip] = useState(initial?.filters.vip_only ?? false);
  const [mode, setMode] = useState<MacroReplyMode>(initial?.reply_mode ?? "hold");
  const [active, setActive] = useState(initial?.active ?? true);

  const macro = macros.find((m) => m.id === macroId);
  const noText = !!macro && !macro.body.trim();
  const effectiveMode: MacroReplyMode = noText ? "none" : mode;
  // Assigning "to me" has no meaning when nobody sends -- the server rejects it too.
  const usesSelf = !!macro?.actions.some((a) => a.type === "assign" && a.mode === "self");
  const triggers = Object.values(trig).map((t) => t.type === "keyword"
    ? {...t, words: wordText.split(",").map((w) => w.trim()).filter(Boolean)} : t);

  const flip = (type: TriggerType, on: boolean) => setTrig((cur) => {
    const next = {...cur};
    if (!on) delete next[type];
    else next[type] = type === "no_response" || type === "unassigned_for" ? {type, minutes: 5}
      : type === "keyword" ? {type, words: []} : {type} as MacroTrigger;
    return next;
  });

  const save = useMutation({
    mutationFn: () => {
      const payload = {name, macro_id: macroId, triggers, filters: {channels, vip_only: vip}, reply_mode: effectiveMode, active};
      return initial
        ? apiFetch(`/macro-rules/${initial.id}`, {method: "PUT", body: JSON.stringify(payload)})
        : apiFetch("/macro-rules", {method: "POST", body: JSON.stringify(payload)});
    },
    onSuccess: onSaved,
  });
  const ready = name.trim() && macroId !== "" && triggers.length > 0 && !usesSelf;

  return (
    <Card className="gp-rise grid gap-4">
      <Input aria-label="Auto macro name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Name, e.g. 5-minute nudge" className="h-9 text-sm"/>

      <section className="grid gap-1.5">
        <h3 className="m-0 text-xs font-semibold text-muted-foreground">1 · When <span className="font-normal">(any of these starts the rule)</span></h3>
        {TRIGGERS.map((t) => {
          const cur = trig[t.type];
          return (
            <div key={t.type} className={cn("flex flex-wrap items-center gap-2 rounded-[0.625rem] border px-2.5 py-1.5 text-sm transition-colors",
              cur ? "border-primary/30 bg-primary/5" : "bg-card")}>
              <label className="flex min-w-44 cursor-pointer items-center gap-2">
                <input type="checkbox" checked={!!cur} onChange={(e) => flip(t.type, e.target.checked)}/>
                {t.label}
              </label>
              {cur && (cur.type === "no_response" || cur.type === "unassigned_for") && (
                <span className="gp-rise flex items-center gap-1.5 text-xs">
                  <Input type="number" min={1} max={10080} aria-label={`${t.label} minutes`} value={cur.minutes}
                    onChange={(e) => setTrig({...trig, [t.type]: {type: cur.type, minutes: Number(e.target.value)}})}
                    className="numeric h-8 w-20 text-xs"/>
                  minutes
                </span>
              )}
              {cur?.type === "keyword" && (
                <Input aria-label="Trigger keywords" value={wordText} onChange={(e) => setWordText(e.target.value)}
                  placeholder="refund, scam, chargeback" className="gp-rise h-8 min-w-48 flex-1 text-xs"/>
              )}
              <span className="ml-auto hidden text-[0.6875rem] text-muted-foreground sm:inline">{t.hint}</span>
            </div>
          );
        })}
      </section>

      <section className="grid gap-1.5">
        <h3 className="m-0 text-xs font-semibold text-muted-foreground">2 · Only if <span className="font-normal">(optional filters)</span></h3>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs">
          {CHANNELS.map((c) => (
            <label key={c.key} className="flex cursor-pointer items-center gap-1.5">
              <input type="checkbox" checked={channels.includes(c.key)}
                onChange={(e) => setChannels(e.target.checked ? [...channels, c.key] : channels.filter((x) => x !== c.key))}/>
              {c.label}
            </label>
          ))}
          <span className="text-muted-foreground">{channels.length === 0 ? "(none ticked = all channels)" : ""}</span>
          <label className="flex cursor-pointer items-center gap-1.5"><input type="checkbox" checked={vip} onChange={(e) => setVip(e.target.checked)}/>VIP customers only</label>
        </div>
      </section>

      <section className="grid gap-1.5">
        <h3 className="m-0 text-xs font-semibold text-muted-foreground">3 · Run this macro</h3>
        <Select aria-label="Macro to run" value={macroId} onChange={(e) => setMacroId(e.target.value ? Number(e.target.value) : "")} className="h-9 max-w-md text-sm">
          <option value="">Choose a macro…</option>
          {macros.map((m) => <option key={m.id} value={m.id}>{m.category} · {m.name}{m.body.trim() ? "" : " (actions only)"}</option>)}
        </Select>
        {usesSelf && <p role="alert" className="m-0 text-xs text-danger">This macro assigns cases “to me”, which has no meaning for an automatic run. Change that action to a specific agent or “next available” first.</p>}
        <div className="grid gap-1">
          {MODES.map((m) => {
            const off = noText && m.key !== "none";
            return (
              <label key={m.key} className={cn("flex cursor-pointer items-start gap-2 rounded-[0.625rem] border px-2.5 py-1.5 text-xs transition-colors",
                effectiveMode === m.key ? "border-primary/30 bg-primary/5" : "bg-card", off && "cursor-not-allowed opacity-50")}>
                <input type="radio" name="reply-mode" className="mt-0.5" checked={effectiveMode === m.key} disabled={off} onChange={() => setMode(m.key)}/>
                <span><span className="font-semibold">{m.label}</span><span className="block text-muted-foreground">{m.hint}</span></span>
              </label>
            );
          })}
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" disabled={!ready || save.isPending} onClick={() => save.mutate()}>{save.isPending ? "Saving…" : "Save auto macro"}</Button>
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
        <label className="flex items-center gap-1.5 text-xs"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)}/>Active</label>
        {effectiveMode === "send" && <span className="text-xs text-warning">Replies will go to customers without review.</span>}
        {save.isError && <span role="alert" className="text-xs text-danger">{(save.error as Error).message}</span>}
      </div>
    </Card>
  );
}
