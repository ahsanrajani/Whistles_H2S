"use client";
import {useMutation, useQueryClient} from "@tanstack/react-query";
import {Eye, EyeOff, Play, RefreshCw} from "lucide-react";
import {useState} from "react";
import {apiFetch} from "@/lib/api";
import {useAdminCost, useAdminFeatures, useAdminKeys, useAdminRuns, useAdminSources} from "@/hooks/use-api";
import {cn} from "@/lib/utils";
import {Badge} from "./ui/badge";
import {Button} from "./ui/button";
import {Card} from "./ui/card";
import {Input} from "./ui/input";
import {InfoTooltip} from "./ui/info-tooltip";
import {ErrorState, LoadingState} from "./states";
import {JobConsole} from "./job-console";

function money(value: number) {
  return value === 0 ? "$0.00" : value < 0.01 ? `$${value.toFixed(4)}` : `$${value.toFixed(2)}`;
}

// ---------------------------------------------------------------------- keys
function KeyRow({envVar, label, value, workspaceId, badge}: {envVar: string; label: string; value: string | null; workspaceId: number; badge: React.ReactNode}) {
  const client = useQueryClient();
  const [next, setNext] = useState(value ?? "");
  const [reveal, setReveal] = useState(false);
  const [seenValue, setSeenValue] = useState(value);
  if (value !== seenValue) {setSeenValue(value); setNext(value ?? "");}
  const save = useMutation({
    mutationFn: () => apiFetch("/admin/keys", {method: "POST", body: JSON.stringify({env_var: envVar, value: next, workspace_id: workspaceId})}),
    onSuccess: () => client.invalidateQueries({queryKey: ["admin", "keys"]}),
  });
  return (
    <tr className="border-b last:border-0 align-top">
      <td className="p-3"><code className="text-xs">{envVar}</code><p className="mt-1 text-xs text-muted-foreground">{label}</p></td>
      <td className="p-3">
        <div className="flex items-center gap-1.5">
          <Input type={reveal ? "text" : "password"} autoComplete="off" placeholder={workspaceId === 0 ? "not set" : "inherits shared"} className="min-w-40 flex-1" value={next} onChange={(event) => setNext(event.target.value)}/>
          <Button type="button" variant="ghost" className="h-9 px-2" aria-label="Reveal" onClick={() => setReveal((current) => !current)}>{reveal ? <EyeOff className="size-4"/> : <Eye className="size-4"/>}</Button>
          <Button type="button" className="h-9 px-3 text-xs" disabled={save.isPending} onClick={() => save.mutate()}>{save.isSuccess ? "Saved" : "Save"}</Button>
        </div>
      </td>
      <td className="p-3 text-right">{badge}</td>
    </tr>
  );
}

export function Keys() {
  const query = useAdminKeys();
  if (query.isLoading) return <LoadingState label="Loading credentials…"/>;
  if (query.error) return <ErrorState message={query.error.message}/>;
  const data = query.data!;
  return (
    <section id="keys" className="scroll-mt-32">
      <h2 className="text-xl font-semibold">API keys</h2>
      <p className="mb-4 text-sm text-muted-foreground">Effective order: environment variable → this workspace → shared.</p>
      <h3 className="mb-2 text-sm font-semibold">This workspace — {data.ws_name}</h3>
      <Card className="p-0">
        <table className="w-full text-left text-sm">
          <thead><tr className="border-b text-xs text-muted-foreground"><th className="p-3">Variable</th><th className="p-3">Value</th><th className="p-3 text-right">State</th></tr></thead>
          <tbody>
            {data.workspace.map((key) => (
              <KeyRow key={key.env_var} envVar={key.env_var} label={key.label} value={key.value} workspaceId={data.ws_id}
                badge={key.value ? <Badge className="border-success/40 text-success">set</Badge> : <Badge className="text-muted-foreground">inherits</Badge>}/>
            ))}
          </tbody>
        </table>
      </Card>
      <h3 className="mb-2 mt-6 text-sm font-semibold">Shared / environment</h3>
      <Card className="p-0">
        <table className="w-full text-left text-sm">
          <thead><tr className="border-b text-xs text-muted-foreground"><th className="p-3">Variable</th><th className="p-3">Value</th><th className="p-3 text-right">State</th></tr></thead>
          <tbody>
            {data.shared.map((key) => (
              <KeyRow key={key.env_var} envVar={key.env_var} label={key.label} value={key.value} workspaceId={0}
                badge={key.from_env ? <Badge className="border-success/40 text-success">local .env</Badge> : key.value ? <Badge className="border-success/40 text-success">set</Badge> : <Badge className="text-muted-foreground">missing</Badge>}/>
            ))}
          </tbody>
        </table>
      </Card>
    </section>
  );
}

// ----------------------------------------------------------------- ops
type DmSyncResult = {messenger?: {ingested: number; error?: string}; instagram?: {ingested: number; error?: string}};

export function Operations() {
  const [careResult, setCareResult] = useState<{scanned: number; created: number} | null>(null);
  const [backfillResult, setBackfillResult] = useState<{queued: boolean; job_id?: string} | null>(null);
  const [dmResult, setDmResult] = useState<DmSyncResult | null>(null);
  const careBridge = useMutation({
    mutationFn: () => apiFetch<{scanned: number; created: number}>("/admin/care/bridge/run", {method: "POST"}),
    onSuccess: setCareResult,
  });
  const webBackfill = useMutation({
    mutationFn: () => apiFetch<{queued: boolean; job_id?: string}>("/admin/backfill/web/run", {method: "POST"}),
    onSuccess: setBackfillResult,
  });
  const dmSync = useMutation({
    mutationFn: () => apiFetch<DmSyncResult>("/admin/dm/sync/run", {method: "POST"}),
    onSuccess: setDmResult,
  });
  const [mediaResult, setMediaResult] = useState<{checked: number; updated: number} | null>(null);
  const mediaBackfill = useMutation({
    mutationFn: () => apiFetch<{checked: number; updated: number}>("/admin/owned-posts/media-backfill/run", {method: "POST"}),
    onSuccess: setMediaResult,
  });
  const [commentResult, setCommentResult] = useState<{checked: number; updated: number} | null>(null);
  const commentBackfill = useMutation({
    mutationFn: () => apiFetch<{checked: number; updated: number}>("/admin/owned-posts/comment-backfill/run", {method: "POST"}),
    onSuccess: setCommentResult,
  });
  return (
    <section id="ops" className="scroll-mt-32">
      <h2 className="text-xl font-semibold">Operations</h2>
      <p className="mb-4 text-sm text-muted-foreground">One-off actions outside the normal schedule. Collection already auto-bridges new comments/reviews and syncs DMs into Care after every run — use these to force it right now instead of waiting for the next tick.</p>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Card>
          <h3 className="mt-0 flex items-center gap-1.5 text-sm font-semibold">
            Care bridge
            <InfoTooltip>Turn already-collected complaint/question-shaped comments and reviews into Care cases right now.</InfoTooltip>
          </h3>
          <Button type="button" disabled={careBridge.isPending} onClick={() => careBridge.mutate()}>
            {careBridge.isPending ? "Running…" : "Run care bridge now"}
          </Button>
          {careResult && <p className="mt-2 text-xs text-success">Scanned {careResult.scanned}, created {careResult.created} case(s).</p>}
          {careBridge.isError && <p className="mt-2 text-xs text-danger">{(careBridge.error as Error).message}</p>}
        </Card>
        <Card>
          <h3 className="mt-0 flex items-center gap-1.5 text-sm font-semibold">
            Historical web backfill
            <InfoTooltip>Year-qualified brand-SERP queries reaching back 3 years — never auto-scheduled, uses the DataForSEO credentials already on file.</InfoTooltip>
          </h3>
          <Button type="button" disabled={webBackfill.isPending} onClick={() => webBackfill.mutate()}>
            {webBackfill.isPending ? "Queuing…" : "Run web backfill"}
          </Button>
          {backfillResult && <p className="mt-2 text-xs text-success">{backfillResult.queued ? `Queued (job ${backfillResult.job_id}).` : "Not queued."}</p>}
          {webBackfill.isError && <p className="mt-2 text-xs text-danger">{(webBackfill.error as Error).message}</p>}
        </Card>
        <Card>
          <h3 className="mt-0 flex items-center gap-1.5 text-sm font-semibold">
            Messenger / Instagram DMs
            <InfoTooltip>Poll Facebook Messenger and Instagram DM conversations and route any new message straight into Care — the &quot;Message Requests&quot; inbox, separate from public comments.</InfoTooltip>
          </h3>
          <Button type="button" disabled={dmSync.isPending} onClick={() => dmSync.mutate()}>
            {dmSync.isPending ? "Syncing…" : "Sync DMs now"}
          </Button>
          {dmResult && (
            <p className="mt-2 text-xs text-success">
              Messenger: {dmResult.messenger?.error ? `failed (${dmResult.messenger.error})` : `${dmResult.messenger?.ingested ?? 0} new`}
              {" · "}
              Instagram: {dmResult.instagram?.error ? `failed (${dmResult.instagram.error})` : `${dmResult.instagram?.ingested ?? 0} new`}
            </p>
          )}
          {dmSync.isError && <p className="mt-2 text-xs text-danger">{(dmSync.error as Error).message}</p>}
        </Card>
        <Card>
          <h3 className="mt-0 flex items-center gap-1.5 text-sm font-semibold">
            Posts media backfill
            <InfoTooltip>Fill in pictures/video on Facebook and Instagram posts collected before media capture shipped — those rows can&apos;t pick it up from a normal re-collection.</InfoTooltip>
          </h3>
          <Button type="button" disabled={mediaBackfill.isPending} onClick={() => mediaBackfill.mutate()}>
            {mediaBackfill.isPending ? "Backfilling…" : "Backfill posts media"}
          </Button>
          {mediaResult && <p className="mt-2 text-xs text-success">Checked {mediaResult.checked}, updated {mediaResult.updated}.</p>}
          {mediaBackfill.isError && <p className="mt-2 text-xs text-danger">{(mediaBackfill.error as Error).message}</p>}
        </Card>
        <Card>
          <h3 className="mt-0 flex items-center gap-1.5 text-sm font-semibold">
            Posts comment-link backfill
            <InfoTooltip>Fix comments/replies collected before nested-reply tracking existed — those rows are on file but weren&apos;t linked to their post, so they never show up under it.</InfoTooltip>
          </h3>
          <Button type="button" disabled={commentBackfill.isPending} onClick={() => commentBackfill.mutate()}>
            {commentBackfill.isPending ? "Backfilling…" : "Backfill comment links"}
          </Button>
          {commentResult && <p className="mt-2 text-xs text-success">Checked {commentResult.checked}, updated {commentResult.updated}.</p>}
          {commentBackfill.isError && <p className="mt-2 text-xs text-danger">{(commentBackfill.error as Error).message}</p>}
        </Card>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------- sources
export function Sources() {
  const query = useAdminSources();
  const q = useQueryClient();
  const toggle = useMutation({
    mutationFn: ({id, enabled}: {id: string; enabled: boolean}) =>
      apiFetch(`/admin/sources/${id}/enabled`, {
        method: "PUT", body: JSON.stringify({enabled}),
      }),
    onSuccess: () => q.invalidateQueries({queryKey: ["admin", "sources"]}),
  });
  if (query.isLoading) return <LoadingState label="Loading sources…"/>;
  if (query.error) return <ErrorState message={query.error.message}/>;
  return (
    <section id="sources" className="scroll-mt-32">
      <h2 className="text-xl font-semibold">Sources</h2>
      <p className="mb-4 text-sm text-muted-foreground">Coverage, cost and client-safety for each source. Turning a source off stops collection for this workspace only — shared credentials are untouched.</p>
      <Card className="overflow-x-auto p-0">
        <table className="w-full min-w-[51.25rem] text-left text-sm">
          <thead><tr className="border-b text-xs text-muted-foreground"><th className="p-3">Source</th><th className="p-3">Surface</th><th className="p-3 text-right">Unit cost</th><th className="p-3">Notes</th><th className="p-3 text-right">Client-safe</th><th className="p-3 text-right">Collection</th></tr></thead>
          <tbody>
            {query.data!.sources.map((source) => (
              <tr key={source.id} className="border-b last:border-0 align-top">
                <th className="p-3 font-semibold">{source.label}</th>
                <td className="p-3 text-muted-foreground">{source.surface}</td>
                <td className="numeric p-3 text-right">{money(source.unit_cost)}<br/><span className="text-[0.6875rem] text-muted-foreground">per {source.unit}</span></td>
                <td className="p-3 text-xs text-muted-foreground">{source.cost_note}{source.warn && <><br/><span className="text-warning">{source.warn}</span></>}</td>
                <td className="p-3 text-right"><Badge className={source.client_safe ? "border-success/40 text-success" : "border-warning/40 text-warning"}>{source.client_safe ? "yes" : "no"}</Badge></td>
                <td className="p-3 text-right">
                  <Button type="button" variant="outline" className="h-7 text-xs"
                    aria-pressed={source.enabled}
                    disabled={toggle.isPending}
                    onClick={() => toggle.mutate({id: source.id, enabled: !source.enabled})}>
                    {source.enabled ? "On" : "Off"}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </section>
  );
}

// ------------------------------------------------------------------ features
const FEATURE_GROUPS: {kind: "module" | "surface" | "cap"; title: string; blurb: string}[] = [
  {kind: "module", title: "Modules", blurb: "Turning a module off hides its whole nav group and blocks its routes for this workspace."},
  {kind: "surface", title: "Analysis surfaces", blurb: "Individual listening surfaces. Off = hidden from the sidebar and the direct URL shows a notice."},
  {kind: "cap", title: "Capabilities", blurb: "Cross-cutting features. Off = the API declines the action for this workspace."},
];

export function Features() {
  const query = useAdminFeatures();
  const q = useQueryClient();
  const toggle = useMutation({
    mutationFn: ({key, enabled}: {key: string; enabled: boolean}) =>
      apiFetch(`/admin/features/${key}`, {method: "PUT", body: JSON.stringify({enabled})}),
    onSuccess: () => q.invalidateQueries({queryKey: ["admin", "features"]}),
  });
  if (query.isLoading) return <LoadingState label="Loading features…"/>;
  if (query.error) return <ErrorState message={query.error.message}/>;
  const byKind = (kind: string) => query.data!.features.filter((f) => f.kind === kind);
  return (
    <section id="features" className="scroll-mt-32">
      <h2 className="text-xl font-semibold">Features</h2>
      <p className="mb-4 text-sm text-muted-foreground">Everything is on by default. Toggles apply to this workspace only.</p>
      <div className="grid gap-4">
        {FEATURE_GROUPS.map((group) => (
          <Card key={group.kind} className="p-0">
            <div className="border-b p-3">
              <h3 className="text-sm font-semibold">{group.title}</h3>
              <p className="mt-0.5 text-xs text-muted-foreground">{group.blurb}</p>
            </div>
            <ul className="divide-y">
              {byKind(group.kind).map((f) => (
                <li key={f.key} className="flex items-center gap-3 p-3">
                  <span className="flex-1 text-sm font-medium">{f.label}</span>
                  <code className="text-[0.6875rem] text-muted-foreground">{f.key}</code>
                  <Button type="button" variant="outline" className="h-7 w-14 text-xs"
                    aria-pressed={f.enabled}
                    disabled={toggle.isPending}
                    onClick={() => toggle.mutate({key: f.key, enabled: !f.enabled})}>
                    {f.enabled ? "On" : "Off"}
                  </Button>
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------- cost
export function Cost() {
  const query = useAdminCost();
  if (query.isLoading) return <LoadingState label="Loading cost…"/>;
  if (query.error) return <ErrorState message={query.error.message}/>;
  const data = query.data!;
  const measuredTotal = data.measured.reduce((sum, row) => sum + row.spend, 0);
  return (
    <section id="cost" className="scroll-mt-32">
      <h2 className="text-xl font-semibold">Cost</h2>
      <p className="mb-4 text-sm text-muted-foreground">Measured spend from the call log, and the modelled monthly cost per brand at the <code>{data.scenario}</code> scenario.</p>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-0">
          <table className="w-full text-left text-sm">
            <thead><tr className="border-b text-xs text-muted-foreground"><th className="p-3">Source</th><th className="p-3 text-right">Calls</th><th className="p-3 text-right">Spend</th><th className="p-3 text-right">Failed</th></tr></thead>
            <tbody>
              {data.measured.length ? data.measured.map((row) => (
                <tr key={row.source} className="border-b last:border-0">
                  <th className="p-3 font-semibold">{row.label}</th>
                  <td className="numeric p-3 text-right">{row.calls}</td>
                  <td className="numeric p-3 text-right">{money(row.spend)}</td>
                  <td className={cn("numeric p-3 text-right", !row.fails && "text-muted-foreground")}>{row.fails}</td>
                </tr>
              )) : <tr><td className="p-4 text-muted-foreground" colSpan={4}>No calls logged yet.</td></tr>}
            </tbody>
            {data.measured.length > 0 && <tfoot><tr className="border-t"><th className="p-3">Measured to date</th><td/><td className="numeric p-3 text-right font-semibold">${measuredTotal.toFixed(4)}</td><td/></tr></tfoot>}
          </table>
        </Card>
        <Card className="p-0">
          <table className="w-full text-left text-sm">
            <thead><tr className="border-b text-xs text-muted-foreground"><th className="p-3">Modelled line</th><th className="p-3 text-right">$/brand/mo</th></tr></thead>
            <tbody>
              {Object.entries(data.model.detail).map(([line, value]) => (
                <tr key={line} className="border-b last:border-0"><td className="p-3">{line}</td><td className="numeric p-3 text-right">${value.toFixed(2)}</td></tr>
              ))}
            </tbody>
            <tfoot><tr className="border-t"><th className="p-3">Total</th><td className="numeric p-3 text-right font-semibold">${data.model.total.toFixed(2)}</td></tr></tfoot>
          </table>
        </Card>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ jobs/runs
export function Jobs() {
  const runs = useAdminRuns();
  const [job, setJob] = useState<string | null>(null);
  const start = useMutation({
    mutationFn: (body: {kind: "refresh" | "score"; reset?: boolean}) =>
      apiFetch<{job_id: string}>(`/jobs/${body.kind}`, {
        method: "POST",
        body: body.kind === "score" ? JSON.stringify({reset: !!body.reset}) : undefined,
      }),
    onSuccess: (result) => setJob(result.job_id),
  });
  return (
    <section id="jobs" className="scroll-mt-32">
      <h2 className="text-xl font-semibold">Jobs & runs</h2>
      <p className="mb-4 text-sm text-muted-foreground">Start a collection, or score mentions. <strong>Score pending</strong> only touches unscored rows; <strong>Re-score everything</strong> clears the workspace and rebuilds — use it after changing how scoring works.</p>
      <div className="flex flex-wrap gap-3">
        <Button disabled={start.isPending} onClick={() => start.mutate({kind: "refresh"})}><Play className="size-4"/>Run collection</Button>
        <Button variant="outline" disabled={start.isPending} onClick={() => start.mutate({kind: "score"})}><Play className="size-4"/>Score pending</Button>
        <Button variant="outline" disabled={start.isPending} onClick={() => start.mutate({kind: "score", reset: true})}><RefreshCw className="size-4"/>Re-score everything</Button>
      </div>
      {start.error && <p className="mt-2 text-sm text-danger">{start.error.message}</p>}
      {job && <div className="mt-4"><JobConsole key={job} jobId={job} onSettled={() => runs.refetch()}/></div>}
      <h3 className="mb-2 mt-6 text-sm font-semibold">Run history</h3>
      <Card className="overflow-x-auto p-0">
        <table className="w-full min-w-[40rem] text-left text-sm">
          <thead><tr className="border-b text-xs text-muted-foreground"><th className="p-3">Run</th><th className="p-3">Started</th><th className="p-3">Finished</th><th className="p-3 text-right">New items</th><th className="p-3 text-right">State</th></tr></thead>
          <tbody>
            {runs.data?.runs.length ? runs.data.runs.map((run) => (
              <tr key={run.id} className="border-b last:border-0">
                <td className="p-3"><code className="text-xs">{run.id}</code></td>
                <td className="p-3 text-muted-foreground">{run.started_at?.slice(0, 19).replace("T", " ")}</td>
                <td className="p-3 text-muted-foreground">{run.finished_at ? run.finished_at.slice(0, 19).replace("T", " ") : "—"}</td>
                <td className="numeric p-3 text-right">{run.new_items ?? "—"}</td>
                <td className="p-3 text-right"><Badge className={run.state === "done" ? "border-success/40 text-success" : run.state === "running" ? "border-highlight/40 text-highlight" : "text-muted-foreground"}>{run.state}</Badge></td>
              </tr>
            )) : <tr><td className="p-4 text-muted-foreground" colSpan={5}>No runs yet.</td></tr>}
          </tbody>
        </table>
      </Card>
    </section>
  );
}
