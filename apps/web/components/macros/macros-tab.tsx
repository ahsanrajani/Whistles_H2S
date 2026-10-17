"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {Pin, PinOff, Search} from "lucide-react";
import {useState} from "react";
import {useCareAgents, useMacros, useMe} from "@/hooks/use-api";
import {apiFetch} from "@/lib/api";
import {MACRO_CATEGORIES, MAX_QUICK, describeAction} from "@/lib/macro-utils";
import {can} from "@/lib/permissions";
import type {Macro} from "@/lib/types";
import {cn} from "@/lib/utils";
import {EmptyState, ErrorState, LoadingState} from "@/components/states";
import {Button} from "@/components/ui/button";
import {Card} from "@/components/ui/card";
import {Input} from "@/components/ui/input";
import {Select} from "@/components/ui/select";
import {MacroEditor} from "./macro-editor";

/** The macro library: everyone with templates:view reads it; templates:create /
 * edit / delete authors it (admin, team lead, supervisor). */
export function MacrosTab() {
  const me = useMe();
  const query = useQueryClient();
  const perms = me.data?.user.perms;
  const canCreate = can(perms, "templates:create");
  const canEdit = can(perms, "templates:edit");
  const canDelete = can(perms, "templates:delete");

  const [category, setCategory] = useState("");
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [confirming, setConfirming] = useState<number | null>(null);
  const list = useMacros({includeInactive: canEdit});
  const agents = useCareAgents({enabled: canEdit});
  const agentName = (id: number) => agents.data?.agents.find((a) => a.user_id === id)?.username ?? `agent #${id}`;
  const refresh = () => query.invalidateQueries({queryKey: ["care"]});

  const all = list.data?.macros ?? [];
  const quickCount = all.filter((m) => m.is_quick).length;
  const needle = q.trim().toLowerCase();
  const shown = all.filter((m) => (!category || m.category === category)
    && (!needle || [m.name, m.shortcut, m.body, m.description].some((f) => (f ?? "").toLowerCase().includes(needle))));

  const toggle = useMutation({
    mutationFn: ({m, patch}: {m: Macro; patch: Partial<Macro>}) => apiFetch(`/macros/${m.id}`, {method: "PUT", body: JSON.stringify(patch)}),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: number) => apiFetch(`/macros/${id}`, {method: "DELETE"}),
    onSuccess: () => {setConfirming(null); refresh();},
  });

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"/>
          <Input aria-label="Search macros" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search macros…" className="h-9 w-56 pl-8 text-xs"/>
        </div>
        <Select aria-label="Filter category" value={category} onChange={(e) => setCategory(e.target.value)} className="h-9 max-w-40 text-xs">
          <option value="">All categories</option>
          {MACRO_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </Select>
        <span className="numeric inline-flex items-center gap-1 text-xs text-muted-foreground" title="Quick macros appear in every agent's Send dropdown">
          <Pin size={11}/>{quickCount}/{MAX_QUICK} quick
        </span>
        {canCreate && editing === null && (
          <Button type="button" variant="outline" className="ml-auto h-9 text-xs" onClick={() => setEditing("new")}>New macro</Button>
        )}
      </div>

      {editing === "new" && (
        <MacroEditor key="new" quickCount={quickCount} onSaved={() => {setEditing(null); refresh();}} onCancel={() => setEditing(null)}/>
      )}

      {list.isLoading && <LoadingState label="Loading macros…"/>}
      {list.error && <ErrorState message={list.error.message}/>}
      {list.data && shown.length === 0 && (
        <EmptyState title="No macros" body={all.length ? "Nothing matches your filters." : canCreate ? "Create your first macro — reply text plus optional case actions." : "None have been set up yet."}/>
      )}
      <div className="grid gap-2">
        {shown.map((m) => editing === m.id ? (
          <MacroEditor key={m.id} initial={m} quickCount={quickCount} onSaved={() => {setEditing(null); refresh();}} onCancel={() => setEditing(null)}/>
        ) : (
          <Card key={m.id} className={cn("grid gap-1.5", !m.active && "opacity-60")}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border bg-muted px-1.5 py-0.5 text-[0.625rem] font-semibold text-muted-foreground">{m.category}</span>
              <span className="font-medium">{m.name}</span>
              {m.shortcut && <span className="numeric text-xs text-muted-foreground">/{m.shortcut}</span>}
              {!m.active && <span className="rounded-full border px-1.5 py-0.5 text-[0.625rem] font-semibold text-muted-foreground">inactive</span>}
              {(m.rule_count ?? 0) > 0 && (
                <span className="rounded-full border border-primary/30 px-1.5 py-0.5 text-[0.625rem] font-semibold text-primary dark:text-highlight">
                  auto · {m.rule_count} rule{m.rule_count === 1 ? "" : "s"}
                </span>
              )}
              <span className="ml-auto flex items-center gap-1.5">
                {canEdit && (
                  <button type="button" aria-pressed={m.is_quick} aria-label={m.is_quick ? `Unpin ${m.name} from quick macros` : `Pin ${m.name} as a quick macro`}
                    title={m.is_quick ? "Pinned to the Send dropdown — click to unpin" : "Pin to every agent's Send dropdown"}
                    disabled={toggle.isPending || (!m.is_quick && quickCount >= MAX_QUICK)}
                    onClick={() => toggle.mutate({m, patch: {is_quick: !m.is_quick}})}
                    className={cn("grid size-7 place-items-center rounded-[0.5rem] border transition-colors disabled:opacity-40",
                      m.is_quick ? "border-highlight/50 bg-highlight/10 text-highlight" : "text-muted-foreground hover:bg-muted")}>
                    {m.is_quick ? <Pin size={13}/> : <PinOff size={13}/>}
                  </button>
                )}
                {canEdit && <Button type="button" variant="outline" className="h-7 text-xs" onClick={() => setEditing(m.id)}>Edit</Button>}
                {canDelete && <Button type="button" variant="danger" className="h-7 text-xs" onClick={() => setConfirming(confirming === m.id ? null : m.id)}>Delete</Button>}
              </span>
            </div>
            {m.description && <p className="m-0 text-xs text-muted-foreground">{m.description}</p>}
            {m.body && <p className="m-0 whitespace-pre-wrap text-sm text-muted-foreground">{m.body}</p>}
            {m.actions.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {m.actions.map((a, i) => (
                  <span key={i} className="rounded-full border bg-muted/40 px-2 py-0.5 text-[0.6875rem] font-medium">{describeAction(a, agentName)}</span>
                ))}
              </div>
            )}
            {confirming === m.id && (
              <div className="gp-rise flex flex-wrap items-center gap-2 rounded-[0.625rem] border border-danger/30 bg-danger/5 p-2 text-xs">
                <span>
                  Delete “{m.name}”?{(m.rule_count ?? 0) > 0 && <> This also removes its {m.rule_count} auto macro rule{m.rule_count === 1 ? "" : "s"}.</>}
                  {" "}Consider unpinning or marking it inactive instead.
                </span>
                <Button type="button" variant="danger" className="ml-auto h-7 text-xs" disabled={remove.isPending} onClick={() => remove.mutate(m.id)}>Yes, delete</Button>
                <Button type="button" variant="ghost" className="h-7 text-xs" onClick={() => setConfirming(null)}>Keep</Button>
              </div>
            )}
          </Card>
        ))}
      </div>
      {(toggle.isError || remove.isError) && (
        <p role="alert" className="m-0 text-xs text-danger">{((toggle.error ?? remove.error) as Error).message}</p>
      )}
    </div>
  );
}
