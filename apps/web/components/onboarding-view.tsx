"use client";
import {useMutation, useQueryClient} from "@tanstack/react-query";
import {Check, Loader2} from "lucide-react";
import {useTenantRouter as useRouter} from "@/components/tenant-link";
import {useEffect, useMemo, useState} from "react";
import {apiFetch} from "@/lib/api";
import {useOnboarding} from "@/hooks/use-api";
import {cn} from "@/lib/utils";
import {Badge} from "./ui/badge";
import {Button} from "./ui/button";
import {Input} from "./ui/input";
import {Select} from "./ui/select";
import {ErrorState, LoadingState} from "./states";
import {JobConsole} from "./job-console";

type Preview = {name: string; match_count: number; sample_size: number; matched: {id: number; text: string; outlet: string | null; surface: string}[]};

function StepRail({steps, current}: {steps: string[]; current: number}) {
  return (
    <ol className="grid gap-1">
      {steps.map((label, index) => {
        const position = index + 1;
        const state = position < current ? "done" : position === current ? "on" : "todo";
        return (
          <li key={label} className={cn("flex items-center gap-3 rounded-[0.625rem] px-3 py-2 text-sm",
            state === "on" && "bg-primary/10 font-semibold text-primary dark:text-highlight",
            state === "todo" && "text-muted-foreground")}>
            <span className={cn("grid size-6 place-items-center rounded-full border text-xs",
              state === "done" && "border-success bg-success text-white",
              state === "on" && "border-primary")}>
              {state === "done" ? <Check className="size-3.5"/> : position}
            </span>
            {label}
          </li>
        );
      })}
    </ol>
  );
}

function FocusPreview({name}: {name: string}) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [loading, setLoading] = useState(false);
  const trimmed = name.trim();
  useEffect(() => {
    if (!trimmed) return;
    let alive = true;
    const timer = setTimeout(() => {
      setLoading(true);
      apiFetch<Preview>(`/onboarding/preview?name=${encodeURIComponent(trimmed)}`)
        .then((result) => {if (alive) setPreview(result);})
        .catch(() => {if (alive) setPreview(null);})
        .finally(() => {if (alive) setLoading(false);});
    }, 450);
    return () => {alive = false; clearTimeout(timer);};
  }, [trimmed]);
  if (!trimmed) return null;
  return (
    <div className="rounded-[0.625rem] border bg-muted/40 p-4 text-xs">
      <div className="flex items-center gap-2 font-semibold">
        {loading ? <Loader2 className="size-3.5 animate-spin"/> : null}
        {preview ? `${preview.match_count} sample match${preview.match_count === 1 ? "" : "es"} in ${preview.sample_size} collected items` : "Checking the corpus…"}
      </div>
      {preview?.matched.length ? (
        <ul className="mt-2 max-h-40 space-y-1.5 overflow-auto">
          {preview.matched.map((row) => (
            <li key={row.id} className="border-b pb-1.5 last:border-0">
              <span className="text-[0.6875rem] text-muted-foreground">{row.outlet ?? row.surface}</span>
              <p className="line-clamp-1">{row.text}</p>
            </li>
          ))}
        </ul>
      ) : preview && !loading ? <p className="mt-2 text-muted-foreground">No matches yet — that is fine for a new brand.</p> : null}
    </div>
  );
}

export function OnboardingView() {
  const query = useOnboarding();
  const router = useRouter();
  const client = useQueryClient();
  const [step, setStep] = useState(1);
  const [seeded, setSeeded] = useState(false);
  const [form, setForm] = useState({
    name: "", market: "PK", volume_scenario: "mid",
    focus: "", competitors: ["", "", "", ""] as string[],
    context_text: "", exclude_text: "",
    keys: {} as Record<string, string>, run_now: true,
  });
  const [job, setJob] = useState<string | null>(null);

  const data = query.data;
  if (data && !seeded) {
    setSeeded(true);
    setStep(data.step && data.step > 0 ? data.step : 1);
    setForm((current) => ({
      ...current,
      name: data.workspace?.name ?? "",
      market: data.workspace?.market ?? "PK",
      volume_scenario: data.workspace?.volume_scenario ?? "mid",
      focus: data.brands?.focus ?? "",
      competitors: [...(data.brands?.competitors ?? []), "", "", "", ""].slice(0, 4),
      context_text: data.query?.context_text ?? "",
      exclude_text: data.query?.exclude_text ?? "",
    }));
  }

  const save = useMutation({
    mutationFn: (payload: {step: number; body: Record<string, unknown>}) =>
      apiFetch<{step: number; job_id?: string | null}>(`/onboarding/${payload.step}`, {method: "PATCH", body: JSON.stringify(payload.body)}),
    onSuccess: (result, variables) => {
      client.invalidateQueries({queryKey: ["onboarding"]});
      client.invalidateQueries({queryKey: ["workspaces"]});
      if (variables.step === 5) {
        if (result.job_id) setJob(result.job_id);
        else router.push("/overview");
        return;
      }
      setStep(result.step);
    },
  });

  const connectKeys = useMemo(() => {
    const seen = new Set<string>();
    const out: {source: string; surface: string; vars: {var: string; label: string}[]}[] = [];
    for (const source of data?.sources.connect ?? []) {
      const vars = source.needs.filter((name) => !seen.has(name));
      vars.forEach((name) => seen.add(name));
      if (vars.length) out.push({source: source.label, surface: source.surface, vars: vars.map((name) => ({var: name, label: (data?.key_labels ?? []).find((entry) => entry.var === name)?.label ?? name}))});
    }
    return out;
  }, [data]);

  if (query.isLoading) return <LoadingState label="Loading setup…"/>;
  if (query.error) return <ErrorState message={query.error.message}/>;
  const steps = data?.steps ?? ["Workspace", "Brands", "Listening query", "Connect sources", "Review"];

  function submit() {
    if (step === 1) save.mutate({step: 1, body: {name: form.name, market: form.market, volume_scenario: form.volume_scenario}});
    else if (step === 2) save.mutate({step: 2, body: {focus: form.focus, competitors: form.competitors.filter((name) => name.trim())}});
    else if (step === 3) save.mutate({step: 3, body: {context_text: form.context_text, exclude_text: form.exclude_text}});
    else if (step === 4) save.mutate({step: 4, body: form.keys});
    else save.mutate({step: 5, body: {run_now: form.run_now}});
  }

  if (job) {
    return (
      <div className="mx-auto grid max-w-xl gap-4">
        <h1 className="text-2xl font-semibold">First collection running</h1>
        <JobConsole key={job} jobId={job} onSettled={() => undefined}/>
        <Button onClick={() => router.push("/overview")}>Go to Overview →</Button>
      </div>
    );
  }

  return (
    <div className="mx-auto grid max-w-[68.75rem] gap-5 lg:grid-cols-[240px_1fr]">
      <aside className="lg:sticky lg:top-24 lg:self-start">
        <p className="mb-1 text-sm font-semibold text-primary dark:text-highlight">Guided setup</p>
        <h1 className="mb-4 text-2xl font-semibold tracking-tight">New workspace</h1>
        <StepRail steps={steps} current={step}/>
      </aside>
      <div className="grid max-w-2xl gap-5">
        <div>
          <p className="text-xs font-bold uppercase tracking-[.16em] text-muted-foreground">Step {step} of {steps.length}</p>
          <h2 className="mt-1 text-xl font-semibold">{steps[step - 1]}</h2>
        </div>
        {save.error && <p className="rounded-[0.625rem] bg-danger/10 p-3 text-sm text-danger">{save.error.message}</p>}

        {step === 1 && (
          <div className="grid gap-4">
            <label className="grid gap-1.5 text-sm font-medium">Workspace name
              <Input value={form.name} autoFocus placeholder="e.g. Acme Bank" onChange={(event) => setForm({...form, name: event.target.value})}/></label>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="grid gap-1.5 text-sm font-medium">Market
                <Select value={form.market} onChange={(event) => setForm({...form, market: event.target.value})}><option value="PK">Pakistan</option><option value="INT">International</option></Select></label>
              <label className="grid gap-1.5 text-sm font-medium">Expected monthly volume
                <Select value={form.volume_scenario} onChange={(event) => setForm({...form, volume_scenario: event.target.value})}><option value="low">Low · &lt;1k / mo</option><option value="mid">Mid · ~3k / mo</option><option value="high">High · 10k+ / mo</option></Select></label>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="grid gap-4">
            <label className="grid gap-1.5 text-sm font-medium">Focus brand
              <Input value={form.focus} autoFocus placeholder="e.g. Acme Bank" onChange={(event) => setForm({...form, focus: event.target.value})}/></label>
            <FocusPreview name={form.focus}/>
            <p className="text-sm font-medium">Competitors</p>
            <div className="grid gap-2">
              {form.competitors.map((value, index) => (
                <Input key={index} value={value} placeholder={`Competitor ${index + 1}`}
                  onChange={(event) => {const next = [...form.competitors]; next[index] = event.target.value; setForm({...form, competitors: next});}}/>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">Match rules are generated from each name and can be tuned later in Admin.</p>
          </div>
        )}

        {step === 3 && (
          <div className="grid gap-4">
            <label className="grid gap-1.5 text-sm font-medium">Context terms <span className="font-normal text-muted-foreground">one per line — one must appear alongside an ambiguous brand mention</span>
              <textarea className="min-h-40 rounded-[0.625rem] border bg-card p-3 text-sm" value={form.context_text} onChange={(event) => setForm({...form, context_text: event.target.value})}/></label>
            <label className="grid gap-1.5 text-sm font-medium">Exclusions <span className="font-normal text-muted-foreground">term — reason, one per line</span>
              <textarea className="min-h-24 rounded-[0.625rem] border bg-card p-3 text-sm" placeholder="acme mosque — landmark" value={form.exclude_text} onChange={(event) => setForm({...form, exclude_text: event.target.value})}/></label>
          </div>
        )}

        {step === 4 && (
          <div className="grid gap-4">
            <div>
              <p className="text-sm font-medium">On automatically</p>
              <ul className="mt-2 flex flex-wrap gap-2">{(data?.sources.auto ?? []).map((source) => <li key={source.id}><Badge className="text-muted-foreground">{source.label} · {source.surface}</Badge></li>)}</ul>
            </div>
            <p className="text-sm font-medium">Connect (stored for this workspace only)</p>
            {connectKeys.map((group) => (
              <div key={group.source} className="rounded-[0.625rem] border p-3">
                <p className="text-sm font-semibold">{group.source} <span className="text-muted-foreground">· {group.surface}</span></p>
                <div className="mt-2 grid gap-2">
                  {group.vars.map((entry) => (
                    <label key={entry.var} className="grid gap-1 text-xs text-muted-foreground">{entry.label}
                      <Input type="password" autoComplete="off" placeholder={data?.connected?.includes(entry.var) ? "set" : "paste key, or skip"}
                        value={form.keys[entry.var] ?? ""} onChange={(event) => setForm({...form, keys: {...form.keys, [entry.var]: event.target.value}})}/></label>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {step === 5 && (
          <div className="grid gap-4">
            <dl className="grid gap-3 rounded-[0.625rem] border p-4 text-sm">
              <div className="flex justify-between gap-4"><dt className="text-muted-foreground">Brand</dt><dd className="text-right font-medium">{form.focus || "—"}{form.competitors.filter((n) => n.trim()).length ? ` + ${form.competitors.filter((n) => n.trim()).length} competitors` : ""}</dd></div>
              <div className="flex justify-between gap-4"><dt className="text-muted-foreground">Context terms</dt><dd className="numeric text-right font-medium">{form.context_text.split("\n").filter((line) => line.trim()).length}</dd></div>
              <div className="flex justify-between gap-4"><dt className="text-muted-foreground">Keys entered now</dt><dd className="numeric text-right font-medium">{Object.values(form.keys).filter((value) => value.trim()).length}</dd></div>
            </dl>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.run_now} onChange={(event) => setForm({...form, run_now: event.target.checked})}/> Run the first collection now</label>
          </div>
        )}

        <div className="mt-2 flex items-center justify-between">
          <Button variant="ghost" disabled={step === 1 || save.isPending} onClick={() => setStep((current) => Math.max(1, current - 1))}>← Back</Button>
          <Button disabled={save.isPending} onClick={submit}>
            {save.isPending ? "Saving…" : step === 5 ? "Finish setup →" : "Continue →"}
          </Button>
        </div>
      </div>
    </div>
  );
}
