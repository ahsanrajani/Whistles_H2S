"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {useState} from "react";
import {useRoutingPolicy} from "@/hooks/use-api";
import {apiFetch} from "@/lib/api";
import {ErrorState, LoadingState} from "@/components/states";
import {Button} from "@/components/ui/button";
import {Card} from "@/components/ui/card";
import {Input} from "@/components/ui/input";

const FIELDS = [
  {key: "first_response_sla", label: "First-response SLA (seconds)"},
  {key: "resolution_sla", label: "Resolution SLA (seconds)"},
  {key: "escalation_after", label: "Escalate after (seconds)"},
  {key: "default_capacity", label: "Default agent capacity"},
] as const;

/** F6.5 — routing policy: SLA thresholds + default capacity, and the closure
 * category taxonomy currently in use (read-only — categories come from what
 * agents have actually recorded, not a separate list to maintain). */
export function RoutingPolicyTab() {
  const query = useQueryClient();
  const policy = useRoutingPolicy();
  const [form, setForm] = useState<Record<string, number> | null>(null);
  // Render-phase prop-sync (not an effect — Next 16 lint forbids setState in
  // an effect body): seed the editable form from the fetched policy exactly
  // once, the same guarded-direct-call pattern command-palette.tsx uses.
  if (policy.data && !form) setForm({...policy.data.policy});

  const save = useMutation({
    mutationFn: () => apiFetch("/admin/routing-policy", {method: "PUT", body: JSON.stringify(form)}),
    onSuccess: () => query.invalidateQueries({queryKey: ["admin", "routing-policy"]}),
  });

  if (policy.isLoading || !form) return <LoadingState label="Loading routing policy…"/>;
  if (policy.error) return <ErrorState message={policy.error.message}/>;

  return (
    <div className="grid gap-3">
      <Card className="grid max-w-sm gap-2.5">
        {FIELDS.map((f) => (
          <label key={f.key} className="grid gap-1 text-xs text-muted-foreground">
            {f.label}
            <Input type="number" min={0} value={form[f.key]}
              onChange={(e) => setForm({...form, [f.key]: Number(e.target.value) || 0})}
              className="h-9 text-sm text-foreground"/>
          </label>
        ))}
        <Button type="button" className="w-max" disabled={save.isPending} onClick={() => save.mutate()}>Save policy</Button>
        {save.isSuccess && <span className="text-xs text-success">Saved.</span>}
      </Card>

      <Card>
        <h3 className="m-0 mb-2 text-sm font-semibold text-muted-foreground">Closure categories in use</h3>
        {policy.data!.closure_categories_in_use.length === 0
          ? <p className="m-0 text-xs text-muted-foreground">No case has been closed with a category yet.</p>
          : <div className="flex flex-wrap gap-1.5">
              {policy.data!.closure_categories_in_use.map((c) => (
                <span key={c} className="rounded-full border bg-muted px-2 py-0.5 text-xs">{c}</span>
              ))}
            </div>}
      </Card>
    </div>
  );
}
