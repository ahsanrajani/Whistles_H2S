"use client";
import {useMutation, useQueryClient} from "@tanstack/react-query";
import {AlertTriangle, Check, Eye, KeyRound, Loader2, Pencil, Power, RefreshCw, Trash2, X} from "lucide-react";
import {useEffect, useMemo, useState} from "react";
import {apiFetch} from "@/lib/api";
import {useAdminBrands, useAdminRoles, useAdminUsers, useAdminWorkspaces, useMe} from "@/hooks/use-api";
import type {AdminUser, BrandPreview, BrandRule} from "@/lib/types";
import {cn} from "@/lib/utils";
import {Badge} from "./ui/badge";
import {Button} from "./ui/button";
import {Card} from "./ui/card";
import {Input} from "./ui/input";
import {InfoTooltip} from "./ui/info-tooltip";
import {Select} from "./ui/select";
import {ErrorState, LoadingState} from "./states";
import {Keys, Operations, Sources, Features, Cost, Jobs} from "./admin-view-ops";

const SECTIONS = [
  {id: "workspaces", label: "Workspaces"},
  {id: "brands", label: "Brands & rules"},
  {id: "users", label: "Users"},
  {id: "keys", label: "API keys"},
  {id: "sources", label: "Sources"},
  {id: "ops", label: "Operations"},
  {id: "features", label: "Features"},
  {id: "cost", label: "Cost"},
  {id: "jobs", label: "Jobs & runs"},
];

function SectionNav() {
  return (
    <nav className="sticky top-20 z-20 -mx-4 mb-2 flex gap-1 overflow-x-auto border-b bg-background/90 px-4 py-2 backdrop-blur md:mx-0 md:rounded-[0.625rem] md:border md:px-2">
      {SECTIONS.map((section) => (
        <a key={section.id} href={`#${section.id}`}
          className="whitespace-nowrap rounded-[0.5rem] px-3 py-1.5 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground">
          {section.label}
        </a>
      ))}
    </nav>
  );
}

// --------------------------------------------------------------- workspaces
function Workspaces() {
  const query = useAdminWorkspaces();
  const client = useQueryClient();
  const [draft, setDraft] = useState({name: "", market: "PK", volume_scenario: "mid"});
  const create = useMutation({
    mutationFn: () => apiFetch("/admin/workspaces", {method: "POST", body: JSON.stringify(draft)}),
    onSuccess: () => {
      setDraft({name: "", market: "PK", volume_scenario: "mid"});
      client.invalidateQueries({queryKey: ["admin"]});
      client.invalidateQueries({queryKey: ["workspaces"]});
    },
  });
  const open = useMutation({
    mutationFn: (id: number) => apiFetch("/workspace/switch", {method: "POST", body: JSON.stringify({ws_id: id})}),
    onSuccess: () => client.invalidateQueries(),
  });
  if (query.isLoading) return <LoadingState label="Loading workspaces…"/>;
  if (query.error) return <ErrorState message={query.error.message}/>;
  const data = query.data!;
  return (
    <section id="workspaces" className="scroll-mt-32">
      <h2 className="text-xl font-semibold">Workspaces</h2>
      <p className="mb-4 text-sm text-muted-foreground">A workspace is one focus brand and the competitors it is measured against. The volume scenario drives the modelled cost and the X read cap.</p>
      <Card className="p-0">
        <table className="w-full text-left text-sm">
          <thead><tr className="border-b text-xs text-muted-foreground"><th className="p-4">Workspace</th><th className="p-4">Market</th><th className="p-4">Scenario</th><th className="p-4 text-right">State</th></tr></thead>
          <tbody>
            {data.list.map((workspace) => (
              <tr key={workspace.id} className="border-b last:border-0">
                <th className="p-4 font-semibold">{workspace.name}</th>
                <td className="p-4">{workspace.market}</td>
                <td className="p-4"><code className="rounded bg-muted px-1.5 py-0.5 text-xs">{workspace.volume_scenario}</code></td>
                <td className="p-4 text-right">
                  {workspace.id === data.active_id
                    ? <Badge className="border-highlight/40 text-highlight">active</Badge>
                    : <Button variant="outline" className="h-8 px-3 text-xs" disabled={open.isPending} onClick={() => open.mutate(workspace.id)}>Open</Button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Card className="mt-4">
        <h3 className="mt-0 text-sm font-semibold">Add a workspace</h3>
        <form className="mt-3 flex flex-wrap gap-2" onSubmit={(event) => {event.preventDefault(); if (draft.name.trim()) create.mutate();}}>
          <Input required placeholder="Client name" className="min-w-48 flex-1" value={draft.name} onChange={(event) => setDraft({...draft, name: event.target.value})}/>
          <Input placeholder="Market" className="w-24" value={draft.market} onChange={(event) => setDraft({...draft, market: event.target.value})}/>
          <Select value={draft.volume_scenario} onChange={(event) => setDraft({...draft, volume_scenario: event.target.value})}>
            {["low", "mid", "high"].map((scenario) => <option key={scenario} value={scenario}>{scenario}</option>)}
          </Select>
          <Button type="submit" disabled={create.isPending}>Add workspace</Button>
        </form>
        {create.error && <p className="mt-2 text-sm text-danger">{create.error.message}</p>}
      </Card>
    </section>
  );
}

// -------------------------------------------------------------------- brands
type Draft = {name: string; is_focus: boolean; archive: boolean; safe: string; gated: string; context: string; exclude: string};

function toDraft(brand: BrandRule): Draft {
  return {
    name: brand.name,
    is_focus: brand.is_focus,
    archive: !brand.active,
    safe: brand.safe_patterns.join("\n"),
    gated: JSON.stringify(brand.gated_patterns, null, 2),
    context: brand.context_patterns.join("\n"),
    exclude: JSON.stringify(brand.exclude_patterns, null, 2),
  };
}

const BLANK: Draft = {name: "", is_focus: false, archive: false, safe: "", gated: "{}", context: "", exclude: "[]"};

function payloadOf(draft: Draft, brandId?: number) {
  return {
    brand_id: brandId,
    name: draft.name,
    is_focus: draft.is_focus,
    archive: draft.archive,
    safe_patterns: draft.safe,
    gated_patterns: draft.gated,
    context_patterns: draft.context,
    exclude_patterns: draft.exclude,
  };
}

function RulePreview({draft}: {draft: Draft}) {
  const [preview, setPreview] = useState<BrandPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const body = useMemo(() => JSON.stringify(payloadOf(draft)), [draft]);
  useEffect(() => {
    let alive = true;
    const timer = setTimeout(() => {
      setLoading(true);
      apiFetch<BrandPreview>("/admin/brands/preview", {method: "POST", body})
        .then((result) => {if (alive) setPreview(result);})
        .catch(() => {if (alive) setPreview(null);})
        .finally(() => {if (alive) setLoading(false);});
    }, 450);
    return () => {alive = false; clearTimeout(timer);};
  }, [body]);
  return (
    <div className="rounded-[0.625rem] border bg-muted/40 p-4">
      <div className="flex items-center gap-2 text-xs font-semibold">
        {loading ? <Loader2 className="size-3.5 animate-spin"/> : <Eye className="size-3.5"/>}
        Live match preview
        {preview && !preview.errors.length && (
          <span className="numeric ml-auto text-muted-foreground">
            {preview.match_count} match{preview.match_count === 1 ? "" : "es"} in {preview.sample_size} items
            {preview.excluded_count > 0 && ` · ${preview.excluded_count} excluded`}
          </span>
        )}
      </div>
      {preview?.errors.length ? (
        <ul className="mt-3 space-y-1 text-xs text-danger">
          {preview.errors.map((issue, index) => (
            <li key={index}><AlertTriangle className="mr-1 inline size-3"/><code>{issue.group}</code>: {issue.error} — <code>{issue.pattern}</code></li>
          ))}
        </ul>
      ) : preview?.matched.length ? (
        <ul className="mt-3 max-h-56 space-y-2 overflow-auto text-xs">
          {preview.matched.map((row) => (
            <li key={row.id} className="border-b pb-2 last:border-0">
              <div className="flex flex-wrap items-center gap-2 text-[0.6875rem] text-muted-foreground">
                <span>{row.outlet ?? row.surface}</span>
                <Badge className="px-1.5 py-0 text-[0.625rem]">{row.rule}</Badge>
                {row.needs_review && <Badge className="border-warning/40 px-1.5 py-0 text-[0.625rem] text-warning">gated</Badge>}
                {row.excluded && <Badge className="border-danger/40 px-1.5 py-0 text-[0.625rem] text-danger">excluded{row.reason ? `: ${row.reason}` : ""}</Badge>}
              </div>
              <p className="mt-1 line-clamp-2">{row.text}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-xs text-muted-foreground">{loading ? "Checking the corpus…" : "No sample matches for these rules yet."}</p>
      )}
    </div>
  );
}

function Field({label, hint, children}: {label: string; hint?: string; children: React.ReactNode}) {
  return (
    <label className="grid gap-1.5 text-sm font-medium">
      {label}
      {children}
      {hint && <span className="text-xs font-normal text-muted-foreground">{hint}</span>}
    </label>
  );
}

function BrandEditor({brand, onDone}: {brand?: BrandRule; onDone?: () => void}) {
  const client = useQueryClient();
  const [draft, setDraft] = useState<Draft>(brand ? toDraft(brand) : BLANK);
  // Re-seed the form when a different brand row is opened (adjust state on prop
  // change, the React-sanctioned render-phase pattern — no effect).
  const [seenBrand, setSeenBrand] = useState(brand?.id);
  if (brand && brand.id !== seenBrand) {setSeenBrand(brand.id); setDraft(toDraft(brand));}
  const save = useMutation({
    mutationFn: () => apiFetch("/admin/brands", {method: "POST", body: JSON.stringify(payloadOf(draft, brand?.id))}),
    onSuccess: () => {
      client.invalidateQueries({queryKey: ["admin"]});
      if (!brand) setDraft(BLANK);
      onDone?.();
    },
  });
  const set = (patch: Partial<Draft>) => setDraft((current) => ({...current, ...patch}));
  const textarea = "min-h-24 rounded-[0.625rem] border bg-card p-3 font-mono text-xs leading-5";
  return (
    <form className="grid gap-4 lg:grid-cols-[1.1fr_.9fr]" onSubmit={(event) => {event.preventDefault(); if (draft.name.trim()) save.mutate();}}>
      <div className="grid gap-4">
        <Field label="Name"><Input required value={draft.name} onChange={(event) => set({name: event.target.value})}/></Field>
        <Field label="Safe patterns" hint="One regex per line, or a JSON list. Matches on their own."><textarea className={textarea} value={draft.safe} onChange={(event) => set({safe: event.target.value})}/></Field>
        <Field label="Gated patterns" hint="JSON object mapping regex → rule name. Needs a context hit and goes to review."><textarea className={textarea} value={draft.gated} onChange={(event) => set({gated: event.target.value})}/></Field>
        <Field label="Context patterns" hint="One regex per line. One must co-occur for a gated match to count."><textarea className={textarea} value={draft.context} onChange={(event) => set({context: event.target.value})}/></Field>
        <Field label="Exclusions" hint='JSON list of [regex, reason]. Rejects same-group entities.'><textarea className={textarea} value={draft.exclude} onChange={(event) => set({exclude: event.target.value})}/></Field>
        <div className="flex flex-wrap items-center gap-5 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" checked={draft.is_focus} onChange={(event) => set({is_focus: event.target.checked})}/> focus brand</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={draft.archive} onChange={(event) => set({archive: event.target.checked})}/> archived</label>
          <Button type="submit" className="ml-auto" disabled={save.isPending}>{save.isPending ? "Saving…" : brand ? "Save brand" : "Add brand"}</Button>
        </div>
        {save.error && <p className="text-sm text-danger">{save.error.message}</p>}
        {save.isSuccess && brand && <p className="flex items-center gap-1 text-sm text-success"><Check className="size-4"/>Saved.</p>}
      </div>
      <RulePreview draft={draft}/>
    </form>
  );
}

function Brands() {
  const query = useAdminBrands();
  const client = useQueryClient();
  const [open, setOpen] = useState<number | "new" | null>("new");
  const rematch = useMutation({
    mutationFn: () => apiFetch<{mentions: number}>("/admin/rematch", {method: "POST"}),
    onSuccess: () => client.invalidateQueries(),
  });
  if (query.isLoading) return <LoadingState label="Loading brands…"/>;
  if (query.error) return <ErrorState message={query.error.message}/>;
  const data = query.data!;
  return (
    <section id="brands" className="scroll-mt-32">
      <h2 className="text-xl font-semibold">Brands & matching rules</h2>
      <p className="mb-4 text-sm text-muted-foreground">Safe patterns match on their own. Gated patterns match only when a context pattern co-occurs, and go to the review queue. Exclusions reject same-group entities.</p>
      <div className="grid gap-3">
        {data.brands.map((brand) => (
          <Card key={brand.id} className="p-0">
            <button type="button" onClick={() => setOpen(open === brand.id ? null : brand.id)}
              className="flex w-full items-center gap-3 p-4 text-left">
              <span className="font-semibold">{brand.name}</span>
              {brand.is_focus && <Badge className="border-primary/40 text-primary dark:text-highlight">focus</Badge>}
              {!brand.active && <Badge className="text-muted-foreground">archived</Badge>}
              <span className="numeric ml-auto text-xs text-muted-foreground">{brand.safe_patterns.length} safe · {Object.keys(brand.gated_patterns).length} gated</span>
            </button>
            {open === brand.id && <div className="border-t p-4"><BrandEditor brand={brand} onDone={() => undefined}/></div>}
          </Card>
        ))}
        <Card className="p-0">
          <button type="button" onClick={() => setOpen(open === "new" ? null : "new")} className="flex w-full items-center gap-3 p-4 text-left font-semibold">
            + Add a brand
          </button>
          {open === "new" && <div className="border-t p-4"><BrandEditor onDone={() => setOpen(null)}/></div>}
        </Card>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button variant="outline" disabled={rematch.isPending} onClick={() => rematch.mutate()}>
          <RefreshCw className={cn("size-4", rematch.isPending && "animate-spin")}/>
          Re-match existing corpus against saved rules
        </Button>
        <InfoTooltip>Re-runs matching only. No new collection, no API cost.</InfoTooltip>
        {rematch.isSuccess && <span className="text-xs text-success">Rebuilt · {rematch.data.mentions} mentions.</span>}
      </div>
    </section>
  );
}

// --------------------------------------------------------------------- users
type UserPanel = null | "edit" | "password";

function UserRow({user, workspaces, roles, roleLabel, isSelf}: {
  user: AdminUser; workspaces: {id: number; name: string}[]; roles: {key: string; label: string; rank: number}[];
  roleLabel: (key: string) => string; isSelf: boolean;
}) {
  const client = useQueryClient();
  const [panel, setPanel] = useState<UserPanel>(null);
  const [role, setRole] = useState(user.role);
  const [workspaceId, setWorkspaceId] = useState(user.workspace_id ? String(user.workspace_id) : "");
  const [password, setPassword] = useState("");
  const refresh = () => client.invalidateQueries({queryKey: ["admin", "users"]});

  const saveAccess = useMutation({
    mutationFn: () => apiFetch(`/admin/users/${user.id}`, {
      method: "PUT",
      body: JSON.stringify({role, workspace_id: role === "admin" && !workspaceId ? "" : (workspaceId || undefined)}),
    }),
    onSuccess: () => {setPanel(null); refresh();},
  });
  const toggleActive = useMutation({
    mutationFn: () => apiFetch(`/admin/users/${user.id}/active`, {
      method: "POST", body: JSON.stringify({active: !user.active}),
    }),
    onSuccess: refresh,
  });
  const savePassword = useMutation({
    mutationFn: () => apiFetch(`/admin/users/${user.id}/password`, {
      method: "POST", body: JSON.stringify({password}),
    }),
    onSuccess: () => {setPassword(""); setPanel(null);},
  });
  const remove = useMutation({
    mutationFn: () => apiFetch(`/admin/users/${user.id}`, {method: "DELETE"}),
    onSuccess: refresh,
  });

  const needsWorkspace = role !== "admin";
  const err = (saveAccess.error ?? toggleActive.error ?? savePassword.error ?? remove.error) as Error | undefined;

  return (
    <>
      <tr className="border-b last:border-0">
        <th className="p-4 font-semibold">{user.username}{isSelf && <span className="ml-1.5 font-normal text-muted-foreground">(you)</span>}</th>
        <td className="p-4">{roleLabel(user.role)}</td>
        <td className="p-4">{user.workspace ?? (user.role === "admin" ? "all workspaces" : "—")}</td>
        <td className="p-4">
          <Badge className={user.active ? "text-success" : "text-muted-foreground"}>{user.active ? "active" : "disabled"}</Badge>
        </td>
        <td className="p-4">
          <div className="flex items-center justify-end gap-1">
            <button type="button" aria-label="Edit access" onClick={() => setPanel(panel === "edit" ? null : "edit")}
              className="rounded-[0.5rem] p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"><Pencil size={14}/></button>
            <button type="button" aria-label="Set password" onClick={() => setPanel(panel === "password" ? null : "password")}
              className="rounded-[0.5rem] p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"><KeyRound size={14}/></button>
            <button type="button" aria-label={user.active ? "Deactivate" : "Reactivate"} disabled={isSelf || toggleActive.isPending}
              onClick={() => toggleActive.mutate()}
              className="rounded-[0.5rem] p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground disabled:pointer-events-none disabled:opacity-30">
              <Power size={14}/>
            </button>
            <button type="button" aria-label="Delete" disabled={isSelf || remove.isPending}
              onClick={() => {if (confirm(`Delete ${user.username}? This can't be undone.`)) remove.mutate();}}
              className="rounded-[0.5rem] p-1.5 text-muted-foreground hover:bg-danger/10 hover:text-danger disabled:pointer-events-none disabled:opacity-30">
              <Trash2 size={14}/>
            </button>
          </div>
        </td>
      </tr>
      {panel && (
        <tr className="border-b bg-muted/30 last:border-0">
          <td colSpan={5} className="p-4">
            {panel === "edit" && (
              <div className="flex flex-wrap items-center gap-2">
                <Select value={role} onChange={(e) => setRole(e.target.value)} className="h-9 text-xs">
                  {[...roles].sort((a, b) => a.rank - b.rank).map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
                </Select>
                <Select required={needsWorkspace} disabled={!needsWorkspace} value={workspaceId}
                  onChange={(e) => setWorkspaceId(e.target.value)} className="h-9 text-xs">
                  <option value="">{needsWorkspace ? "assign to workspace…" : "all workspaces"}</option>
                  {workspaces.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
                </Select>
                <Button className="h-9 text-xs" disabled={saveAccess.isPending || (needsWorkspace && !workspaceId)}
                  onClick={() => saveAccess.mutate()}>Save</Button>
                <button type="button" aria-label="Cancel" onClick={() => setPanel(null)}
                  className="rounded-[0.5rem] p-1.5 text-muted-foreground hover:bg-muted"><X size={14}/></button>
              </div>
            )}
            {panel === "password" && (
              <div className="flex flex-wrap items-center gap-2">
                <Input type="password" placeholder="new password (min 8 characters)" value={password}
                  onChange={(e) => setPassword(e.target.value)} className="h-9 max-w-64 text-xs"/>
                <Button className="h-9 text-xs" disabled={savePassword.isPending || password.length < 8}
                  onClick={() => savePassword.mutate()}>Set password</Button>
                <button type="button" aria-label="Cancel" onClick={() => setPanel(null)}
                  className="rounded-[0.5rem] p-1.5 text-muted-foreground hover:bg-muted"><X size={14}/></button>
                {savePassword.isSuccess && <span className="text-xs text-success">Password updated.</span>}
              </div>
            )}
            {err && <p className="mt-2 text-xs text-danger">{err.message}</p>}
          </td>
        </tr>
      )}
    </>
  );
}

function Users() {
  const query = useAdminUsers();
  const roles = useAdminRoles();
  const me = useMe();
  const client = useQueryClient();
  const [draft, setDraft] = useState({username: "", password: "", role: "bank_viewer", workspace_id: ""});
  const create = useMutation({
    mutationFn: () => apiFetch("/admin/users", {
      method: "POST",
      body: JSON.stringify({...draft, workspace_id: draft.workspace_id ? Number(draft.workspace_id) : undefined}),
    }),
    onSuccess: () => {setDraft({username: "", password: "", role: "bank_viewer", workspace_id: ""}); client.invalidateQueries({queryKey: ["admin", "users"]});},
  });
  if (query.isLoading || roles.isLoading) return <LoadingState label="Loading users…"/>;
  if (query.error) return <ErrorState message={query.error.message}/>;
  if (roles.error) return <ErrorState message={roles.error.message}/>;
  const data = query.data!;
  const roleLabel = (key: string) => roles.data?.roles.find((r) => r.key === key)?.label ?? key;
  const needsWorkspace = draft.role !== "admin";
  const canSubmit = draft.username && draft.password && (!needsWorkspace || draft.workspace_id);
  return (
    <section id="users" className="scroll-mt-32">
      <h2 className="text-xl font-semibold">Users</h2>
      <p className="mb-4 text-sm text-muted-foreground">Care roles (Agent → Team Lead) work their assigned workspace&apos;s queue; a Client Viewer sees only its workspace&apos;s reports; Administrators see every workspace and can switch between them.</p>
      <Card className="p-0">
        <table className="w-full text-left text-sm">
          <thead><tr className="border-b text-xs text-muted-foreground"><th className="p-4">Username</th><th className="p-4">Role</th><th className="p-4">Workspace</th><th className="p-4">Status</th><th className="p-4 text-right">Actions</th></tr></thead>
          <tbody>
            {data.users.map((user) => (
              <UserRow key={user.id} user={user} workspaces={data.workspaces} roles={roles.data!.roles}
                roleLabel={roleLabel} isSelf={user.id === me.data?.user.id}/>
            ))}
          </tbody>
        </table>
      </Card>
      <Card className="mt-4">
        <h3 className="mt-0 text-sm font-semibold">Add a user</h3>
        <form className="mt-3 flex flex-wrap gap-2" onSubmit={(event) => {event.preventDefault(); if (canSubmit) create.mutate();}}>
          <Input required placeholder="username" value={draft.username} onChange={(event) => setDraft({...draft, username: event.target.value})}/>
          <Input required type="password" placeholder="password" value={draft.password} onChange={(event) => setDraft({...draft, password: event.target.value})}/>
          <Select required value={draft.role} onChange={(event) => setDraft({...draft, role: event.target.value})}>
            {[...(roles.data?.roles ?? [])].sort((a, b) => a.rank - b.rank).map((r) => (
              <option key={r.key} value={r.key}>{r.label}</option>
            ))}
          </Select>
          <Select required={needsWorkspace} disabled={!needsWorkspace} value={draft.workspace_id} onChange={(event) => setDraft({...draft, workspace_id: event.target.value})}>
            <option value="">{needsWorkspace ? "assign to workspace…" : "all workspaces"}</option>
            {data.workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}
          </Select>
          <Button type="submit" disabled={!canSubmit || create.isPending}>Add user</Button>
        </form>
        {create.error && <p className="mt-2 text-sm text-danger">{create.error.message}</p>}
      </Card>
    </section>
  );
}

export function AdminView() {
  return (
    <div className="mx-auto grid max-w-[93.75rem] gap-5">
      <div>
        <p className="mb-1 text-sm font-semibold text-primary dark:text-highlight">Configuration</p>
        <h1 className="m-0 text-3xl font-semibold tracking-tight md:text-4xl">Admin</h1>
        <p className="text-muted-foreground">Workspaces, matching rules, credentials, cost, and collection jobs.</p>
      </div>
      <SectionNav/>
      <Workspaces/>
      <Brands/>
      <Users/>
      <Keys/>
      <Sources/>
      <Operations/>
      <Features/>
      <Cost/>
      <Jobs/>
    </div>
  );
}
