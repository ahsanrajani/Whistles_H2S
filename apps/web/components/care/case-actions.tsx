"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {useState} from "react";
import {apiFetch} from "@/lib/api";
import {useTenantHref} from "@/components/tenant-link";
import {useCareAgents, useMe} from "@/hooks/use-api";
import type {CareCustomer} from "@/lib/types";
import {cn} from "@/lib/utils";
import {isAgentScoped} from "@/lib/permissions";
import {Button} from "@/components/ui/button";
import {Input} from "@/components/ui/input";
import {Select} from "@/components/ui/select";

const CLOSURE = ["resolved", "no_response", "duplicate", "not_actionable", "escalated", "spam"];
const BLOCK_CATEGORIES = ["harassment", "spam", "abuse", "impersonation", "other"];
const STATES = ["in_progress", "internal_hold", "closed", "open"];

type Panel = null | "assign" | "reassign" | "transition" | "note" | "block";

export function CaseActions({caseId, customer}: {caseId: number; customer: CareCustomer}) {
  const query = useQueryClient();
  const href = useTenantHref();
  const me = useMe();
  // Hamza: "the agent accounts should be able to access only the
  // conversations assigned to them, nothing else" -- /care/agents and
  // /care/cases/{id}/export both 403 for an agent-scoped user now, so hide
  // the controls that would only fail on click rather than show them dead.
  const agentScoped = isAgentScoped(me.data?.user.roles);
  const agents = useCareAgents({enabled: !agentScoped});
  const [panel, setPanel] = useState<Panel>(null);

  const [assignee, setAssignee] = useState("");
  const [reason, setReason] = useState("");
  const [toState, setToState] = useState("in_progress");
  const [closure, setClosure] = useState("");
  const [note, setNote] = useState("");
  const [blockReason, setBlockReason] = useState("");
  const [blockCategory, setBlockCategory] = useState("");

  const refresh = () => {
    query.invalidateQueries({queryKey: ["care", "case", caseId]});
    query.invalidateQueries({queryKey: ["care", "cases"]});
    setPanel(null);
  };

  const post = (path: string, body: Record<string, unknown>) =>
    apiFetch(`/care/cases/${caseId}${path}`, {method: "POST", body: JSON.stringify(body)});

  const assign = useMutation({mutationFn: () => post("/assign", assignee ? {user_id: Number(assignee)} : {}), onSuccess: refresh});
  const reassign = useMutation({mutationFn: () => post("/reassign", {user_id: Number(assignee), reason}), onSuccess: refresh});
  const transition = useMutation({mutationFn: () => post("/transition", {state: toState, closure_category: toState === "closed" ? closure : undefined}), onSuccess: refresh});
  const addNote = useMutation({mutationFn: () => post("/note", {body: note}), onSuccess: () => {setNote(""); refresh();}});
  const block = useMutation({
    mutationFn: () => post("/block", {
      target_ref: `u:${customer.handle ?? customer.id}`,
      platform: customer.platform ?? "meta",
      reason: blockReason, category: blockCategory,
    }),
    onSuccess: refresh,
  });

  const busy = [assign, reassign, transition, addNote, block].some((m) => m.isPending);
  const err = [assign, reassign, transition, addNote, block].map((m) => m.error).find(Boolean) as Error | undefined;

  const agentOptions = (agents.data?.agents ?? []).map((a) => (
    <option key={a.user_id} value={a.user_id}>{a.username} ({a.live}/{a.capacity})</option>
  ));

  // An agent-scoped user can only act on their own case -- assigning it away
  // (assign to someone else / reassign) and export both need care:export or
  // a full agents list, neither of which they have. transition/note/block
  // stay: all three operate on the one case already confirmed as theirs.
  const panels = agentScoped
    ? (["transition", "note", "block"] as const)
    : (["assign", "reassign", "transition", "note", "block"] as const);

  return (
    <div className="grid gap-2 border-t pt-2">
      <div className="flex flex-wrap gap-1.5">
        {panels.map((p) => (
          <button key={p} type="button" aria-pressed={panel === p} onClick={() => setPanel(panel === p ? null : p)}
            className={cn(
              "rounded-[0.5rem] border px-2.5 py-1 text-xs font-semibold capitalize",
              panel === p ? "border-primary/40 bg-primary/10 text-primary dark:text-highlight" : "bg-card hover:bg-muted",
            )}>
            {p}
          </button>
        ))}
        {!agentScoped && (
          <>
            <a href={href(`/api/v1/care/cases/${caseId}/export?format=pdf`)} download
              className="rounded-[0.5rem] border bg-card px-2.5 py-1 text-xs font-semibold hover:bg-muted">PDF</a>
            <a href={href(`/api/v1/care/cases/${caseId}/export?format=xlsx`)} download
              className="rounded-[0.5rem] border bg-card px-2.5 py-1 text-xs font-semibold hover:bg-muted">XLSX</a>
          </>
        )}
      </div>

      {panel === "assign" && (
        <Field>
          <Select aria-label="Assignee" value={assignee} onChange={(e) => setAssignee(e.target.value)} className="h-8 text-xs">
            <option value="">Auto-assign</option>{agentOptions}
          </Select>
          <Button type="button" className="h-8 text-xs" disabled={busy} onClick={() => assign.mutate()}>Assign</Button>
        </Field>
      )}

      {panel === "reassign" && (
        <Field>
          <Select aria-label="Reassign to" value={assignee} onChange={(e) => setAssignee(e.target.value)} className="h-8 text-xs">
            <option value="">Choose agent…</option>{agentOptions}
          </Select>
          <Input aria-label="Reassign reason" placeholder="Reason (required)" value={reason}
            onChange={(e) => setReason(e.target.value)} className="h-8 text-xs"/>
          <Button type="button" className="h-8 text-xs" disabled={busy || !assignee || !reason.trim()}
            onClick={() => reassign.mutate()}>Reassign</Button>
        </Field>
      )}

      {panel === "transition" && (
        <Field>
          <Select aria-label="New state" value={toState} onChange={(e) => setToState(e.target.value)} className="h-8 text-xs">
            {STATES.map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}
          </Select>
          {toState === "closed" && (
            <Select aria-label="Closure category" value={closure} onChange={(e) => setClosure(e.target.value)} className="h-8 text-xs">
              <option value="">Closure category…</option>
              {CLOSURE.map((c) => <option key={c} value={c}>{c.replaceAll("_", " ")}</option>)}
            </Select>
          )}
          <Button type="button" className="h-8 text-xs"
            disabled={busy || (toState === "closed" && !closure)}
            onClick={() => transition.mutate()}>Apply</Button>
        </Field>
      )}

      {panel === "note" && (
        <div className="grid gap-1.5">
          <textarea aria-label="Internal note" value={note} onChange={(e) => setNote(e.target.value)} rows={2}
            placeholder="Internal note — not visible to the customer. Use @name to tag."
            className="w-full resize-y rounded-[0.625rem] border bg-card p-2 text-xs outline-none focus-visible:ring-2 focus-visible:ring-highlight/40"/>
          <Button type="button" className="h-8 w-max text-xs" disabled={busy || !note.trim()}
            onClick={() => addNote.mutate()}>Add note</Button>
        </div>
      )}

      {panel === "block" && (
        <div className="grid gap-1.5">
          <Field>
            <Select aria-label="Block category" value={blockCategory} onChange={(e) => setBlockCategory(e.target.value)} className="h-8 text-xs">
              <option value="">Category…</option>
              {BLOCK_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </Select>
            <Input aria-label="Block reason" placeholder="Reason (required)" value={blockReason}
              onChange={(e) => setBlockReason(e.target.value)} className="h-8 text-xs"/>
          </Field>
          <Button type="button" variant="danger" className="h-8 w-max text-xs"
            disabled={busy || !blockReason.trim() || !blockCategory}
            onClick={() => block.mutate()}>Block customer</Button>
        </div>
      )}

      {err && <p role="alert" className="m-0 text-xs text-danger">{err.message}</p>}
    </div>
  );
}

function Field({children}: {children: React.ReactNode}) {
  return <div className="flex flex-wrap items-center gap-1.5">{children}</div>;
}
