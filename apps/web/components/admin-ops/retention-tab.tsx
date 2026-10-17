"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {useState} from "react";
import {useRetention} from "@/hooks/use-api";
import {apiFetch} from "@/lib/api";
import {EmptyState, ErrorState, LoadingState} from "@/components/states";
import {Button} from "@/components/ui/button";
import {Card} from "@/components/ui/card";
import {Select} from "@/components/ui/select";

/** F6.2 — per-tenant, per-source-class retention: full (keep author identity)
 * vs hashed (irreversible HMAC). Tightening to hashed rehashes every stored
 * author in the background, so it warns and asks for confirmation first. */
export function RetentionTab() {
  const query = useQueryClient();
  const retention = useRetention();
  const [confirm, setConfirm] = useState<{cls: string; mode: string} | null>(null);

  const save = useMutation({
    mutationFn: ({cls, mode}: {cls: string; mode: string}) =>
      apiFetch("/admin/retention", {method: "PUT", body: JSON.stringify({source_class: cls, retention_mode: mode})}),
    onSuccess: () => {setConfirm(null); query.invalidateQueries({queryKey: ["admin", "retention"]});},
  });

  if (retention.isLoading) return <LoadingState label="Loading retention policy…"/>;
  if (retention.error) return <ErrorState message={retention.error.message}/>;
  const data = retention.data!;
  if (data.classes.length === 0) return <EmptyState title="No source classes" body="Nothing to configure."/>;

  return (
    <div className="grid gap-3">
      <Card className="grid gap-3">
        {data.classes.map((cls) => (
          <div key={cls} className="flex items-center gap-3">
            <span className="w-32 text-sm font-medium capitalize">{cls.replaceAll("_", " ")}</span>
            <Select aria-label={`Retention mode for ${cls}`} value={data.policy[cls]} className="h-9 max-w-40 text-sm"
              onChange={(e) => {
                const mode = e.target.value;
                if (mode === "hashed" && data.policy[cls] !== "hashed") setConfirm({cls, mode});
                else save.mutate({cls, mode});
              }}>
              {data.modes.map((m) => <option key={m} value={m}>{m}</option>)}
            </Select>
          </div>
        ))}
      </Card>

      {confirm && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40" onClick={() => setConfirm(null)}>
          <div className="w-full max-w-sm rounded-card border bg-card p-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="m-0 mb-2 text-sm font-semibold text-danger">Tighten “{confirm.cls}” to hashed?</h3>
            <p className="m-0 mb-3 text-sm text-muted-foreground">
              This queues a background job that irreversibly HMAC-hashes every already-stored
              author identity for this class. There is no undo — the plaintext handles are gone
              once rehashed.
            </p>
            <div className="flex gap-2">
              <Button type="button" variant="danger" disabled={save.isPending} onClick={() => save.mutate(confirm)}>Confirm — hash everything</Button>
              <Button type="button" variant="ghost" onClick={() => setConfirm(null)}>Cancel</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
