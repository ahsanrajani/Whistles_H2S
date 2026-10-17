"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {useState} from "react";
import {Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis} from "recharts";
import {apiFetch} from "@/lib/api";
import {useMe, useVantageEvidence, useVantageInsights, useVantagePrompts} from "@/hooks/use-api";
import type {VantageEvidenceRow, VantageRunQueued} from "@/lib/types";
import {can} from "@/lib/permissions";
import {Badge} from "./ui/badge";
import {Button} from "./ui/button";
import {Card} from "./ui/card";
import {Input} from "./ui/input";
import {EmptyState, ErrorState, LoadingState} from "./states";
import {JobConsole} from "./job-console";
import {PageHeader} from "./viewer-components";
import {GRID, TICK, TOOLTIP_STYLE} from "@/components/charts/chart-kit";

const SLICE_COLORS = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)", "var(--chart-6)"];

function pct(value: number | null): string {
  return value == null ? "—" : `${(value * 100).toFixed(1)}%`;
}

/** const 1.96 == the 95% Wilson bound already baked into the backend's
 * wilson()/rate — this just renders the [lo, hi] the API returns. */
function MentionRateBar({rate, wilson}: {rate: number | null; wilson: [number | null, number | null]}) {
  const [lo, hi] = wilson;
  if (rate == null || lo == null || hi == null) return <span className="text-xs text-muted-foreground">no data</span>;
  return (
    <div className="relative h-2 w-full min-w-28 rounded-full bg-muted" title={`95% ${pct(lo)}–${pct(hi)}`}>
      <span className="absolute h-2 rounded-full bg-primary/25" style={{left: `${lo * 100}%`, width: `${Math.max((hi - lo) * 100, 1)}%`}}/>
      <span className="absolute top-1 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary ring-2 ring-card" style={{left: `${rate * 100}%`}}/>
    </div>
  );
}

const FLAG_LABEL: Record<string, string> = {
  possible_wrong_entity: "⚠ possibly confused with JPMorgan Chase",
  uncertain: "model said it has no information",
};

function EvidenceRow({row}: {row: VantageEvidenceRow}) {
  const [open, setOpen] = useState(false);
  const text = row.error ? `Failed — ${row.error}` : row.response_text;
  const short = text.length > 160 && !open ? `${text.slice(0, 160)}…` : text;
  return (
    <li className="py-3">
      <div className="flex items-start justify-between gap-3">
        <p className="m-0 flex-1 text-sm font-medium">{row.prompt_text}</p>
        <span className="whitespace-nowrap text-xs text-muted-foreground">{row.provider}/{row.model} · {row.day}</span>
      </div>
      <p className={`mb-1 mt-1.5 whitespace-pre-wrap text-sm ${row.error ? "text-danger" : "text-muted-foreground"}`}>{short}</p>
      {text.length > 160 && (
        <button type="button" onClick={() => setOpen((v) => !v)} className="text-xs font-medium text-primary hover:underline">
          {open ? "Show less" : "Show full answer"}
        </button>
      )}
      {row.flags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {row.flags.map((f) => <Badge key={f} className="border-warning/40 bg-warning/10 text-warning">{FLAG_LABEL[f] ?? f}</Badge>)}
        </div>
      )}
      {row.mentions.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {row.mentions.map((m) => (
            <Badge key={m.brand_id} className={m.is_focus ? "bg-primary/15 text-primary" : "bg-muted text-muted-foreground"}>{m.name}</Badge>
          ))}
        </div>
      )}
    </li>
  );
}

export function VantageView() {
  const me = useMe();
  const canEdit = can(me.data?.user.perms, "admin:edit");
  const prompts = useVantagePrompts();
  const insights = useVantageInsights();
  const evidence = useVantageEvidence();
  const query = useQueryClient();
  const [newPrompt, setNewPrompt] = useState("");
  const [job, setJob] = useState<string | null>(null);

  const invalidate = () => {
    query.invalidateQueries({queryKey: ["vantage"]});
  };

  const run = useMutation({
    // Queued on the background worker — a run is minutes of sequential LLM calls.
    mutationFn: () => apiFetch<VantageRunQueued>("/vantage/panel/run", {method: "POST"}),
    onSuccess: (data) => setJob(data.job_id),
  });
  const addPrompt = useMutation({
    mutationFn: (text: string) => apiFetch("/vantage/prompts", {method: "POST", body: JSON.stringify({prompt_text: text})}),
    onSuccess: () => {
      setNewPrompt("");
      invalidate();
    },
  });
  const togglePrompt = useMutation({
    mutationFn: (p: {id: number; active: boolean}) =>
      apiFetch(`/vantage/prompts/${p.id}`, {method: "PATCH", body: JSON.stringify({active: p.active})}),
    onSuccess: invalidate,
  });
  const deletePrompt = useMutation({
    mutationFn: (id: number) => apiFetch(`/vantage/prompts/${id}`, {method: "DELETE"}),
    onSuccess: invalidate,
  });

  if (prompts.isLoading || insights.isLoading) return <LoadingState label="Loading AI-visibility panel…"/>;
  if (prompts.error) return <ErrorState message={prompts.error.message}/>;
  if (insights.error) return <ErrorState message={insights.error.message}/>;

  const chartData = (insights.data?.brands ?? []).map((b) => ({
    name: b.name, rate: b.rate == null ? 0 : Number((b.rate * 100).toFixed(1)), focus: b.is_focus,
  }));
  const shareData = (insights.data?.brands ?? [])
    .filter((b) => b.k > 0)
    .map((b) => ({name: b.name, value: b.k, focus: b.is_focus}));

  return (
    <div className="mx-auto grid max-w-[93.75rem] gap-5">
      <PageHeader title="AI listening" subtitle="How ChatGPT, Gemini, Perplexity and Claude answer questions about the brand."
        stat={canEdit ? (
          <div className="text-right">
            <Button type="button" disabled={run.isPending} onClick={() => run.mutate()}>
              {run.isPending ? "Queuing…" : "Run panel now"}
            </Button>
            <p className="mb-0 mt-1 text-xs text-muted-foreground">Costed LLM calls</p>
          </div>
        ) : undefined}/>

      {run.isError && <p role="alert" className="rounded-[0.625rem] border border-danger/30 bg-danger/10 p-3 text-sm text-danger">Run failed — {(run.error as Error).message}</p>}
      {job && <JobConsole key={job} jobId={job} onSettled={invalidate}/>}

      {(insights.data?.headline.length || insights.data?.improvements.length) ? (
        <Card>
          <h2 className="mt-0 text-xl font-semibold">Summary report</h2>
          <ul className="m-0 list-disc space-y-1 pl-5 text-sm">
            {insights.data?.headline.map((line, i) => <li key={i}>{line}</li>)}
          </ul>
          {!!insights.data?.improvements.length && (
            <>
              <h3 className="mb-1 mt-4 text-sm font-semibold text-muted-foreground">What to improve</h3>
              <ul className="m-0 list-disc space-y-1 pl-5 text-sm">
                {insights.data.improvements.map((line, i) => <li key={i}>{line}</li>)}
              </ul>
            </>
          )}
        </Card>
      ) : null}

      <Card>
        <div className="mb-1 flex items-center justify-between">
          <h2 className="m-0 text-xl font-semibold">Mention rate by brand</h2>
          <span className="text-xs text-muted-foreground">{insights.data?.total_responses ?? 0} answers so far</span>
        </div>
        <p className="mt-0 text-sm text-muted-foreground">Share of panel answers that named each brand, with its 95% Wilson interval.</p>
        {!insights.data?.total_responses ? (
          <EmptyState title="No panel runs yet" body={canEdit ? "Run the panel to see how AI assistants describe the brand." : "Ask an admin to run the AI-visibility panel."}/>
        ) : (
          <>
            <div className="grid gap-4 md:grid-cols-[1.3fr_1fr]">
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} layout="vertical" margin={{top: 8, right: 24, left: 8, bottom: 0}}>
                    <CartesianGrid {...GRID} horizontal={false} vertical/>
                    <XAxis type="number" domain={[0, 100]} tick={TICK} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`}/>
                    <YAxis type="category" dataKey="name" width={140} tickLine={false} axisLine={false} tick={{fontSize: 12, fill: "var(--foreground)"}}/>
                    <Tooltip formatter={(v) => [`${v}%`, "mention rate"]} contentStyle={TOOLTIP_STYLE}/>
                    <Bar dataKey="rate" radius={[0, 10, 10, 0]} maxBarSize={22}>
                      {chartData.map((d) => <Cell key={d.name} fill={d.focus ? "var(--chart-1)" : "var(--chart-6)"}/>)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={shareData} dataKey="value" nameKey="name" innerRadius={56} outerRadius={90} paddingAngle={3} cornerRadius={6} stroke="none">
                      {shareData.map((d, i) => <Cell key={d.name} fill={d.focus ? "var(--chart-1)" : SLICE_COLORS[(i + 1) % SLICE_COLORS.length]}/>)}
                    </Pie>
                    <Tooltip formatter={(v, n) => [`${v} mention${v === 1 ? "" : "s"}`, n]} contentStyle={TOOLTIP_STYLE}/>
                  </PieChart>
                </ResponsiveContainer>
                <p className="mt-1 text-center text-xs text-muted-foreground">Share of mentions across brands</p>
              </div>
            </div>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[32.5rem] border-collapse text-left text-sm">
                <thead><tr className="border-b text-xs text-muted-foreground"><th className="py-2">Brand</th><th className="py-2 text-right">Mentions</th><th className="px-6 py-2">95% interval</th><th className="py-2 text-right">Rate</th></tr></thead>
                <tbody>
                  {(insights.data?.brands ?? []).map((b) => (
                    <tr key={b.name} className="border-b last:border-0">
                      <th className={b.is_focus ? "py-3 text-primary dark:text-highlight" : "py-3 font-normal"}>{b.name}</th>
                      <td className="numeric py-3 text-right">{b.k}/{b.n}</td>
                      <td className="px-6 py-3"><MentionRateBar rate={b.rate} wilson={b.wilson}/></td>
                      <td className="numeric py-3 text-right font-semibold">{pct(b.rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Card>

      <Card>
        <h2 className="mt-0 text-xl font-semibold">Visibility gaps</h2>
        <p className="mt-0 text-sm text-muted-foreground">A panel answer that named a competitor but never the focus brand — the clearest &quot;fix this&quot; signal.</p>
        {!insights.data?.visibility_gaps.length ? (
          <p className="py-6 text-center text-sm text-muted-foreground">No gaps found in the answers collected so far.</p>
        ) : (
          <ul className="divide-y">
            {insights.data.visibility_gaps.map((g, i) => (
              <li key={i} className="grid grid-cols-[1fr_auto] gap-3 py-3 text-sm">
                <span>Named <b>{g.competitors_named.join(", ")}</b> — never the focus brand</span>
                <span className="text-right text-xs text-muted-foreground">{g.model} · {g.day}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <h2 className="mt-0 text-xl font-semibold">Panel prompts</h2>
        <p className="mt-0 text-sm text-muted-foreground">Every active prompt is asked of every model on each run. {canEdit ? "" : "Ask an admin to edit these."}</p>
        <ul className="divide-y">
          {(prompts.data?.prompts ?? []).map((p) => (
            <li key={p.id} className="flex items-center gap-3 py-2.5 text-sm">
              <span className={`flex-1 ${p.active ? "" : "text-muted-foreground line-through"}`}>{p.prompt_text}</span>
              {!p.active && <Badge className="text-muted-foreground">off</Badge>}
              {canEdit && (
                <>
                  <Button type="button" variant="outline" className="h-7 text-xs"
                    disabled={togglePrompt.isPending}
                    onClick={() => togglePrompt.mutate({id: p.id, active: !p.active})}>
                    {p.active ? "Turn off" : "Turn on"}
                  </Button>
                  <Button type="button" variant="outline" className="h-7 text-xs text-danger"
                    disabled={deletePrompt.isPending}
                    onClick={() => deletePrompt.mutate(p.id)}>
                    Delete
                  </Button>
                </>
              )}
            </li>
          ))}
        </ul>
        {canEdit && (
          <div className="mt-3 flex gap-2">
            <Input aria-label="New prompt" placeholder="Add a prompt to ask the panel…" value={newPrompt}
              onChange={(e) => setNewPrompt(e.target.value)} className="flex-1"/>
            <Button type="button" disabled={!newPrompt.trim() || addPrompt.isPending}
              onClick={() => addPrompt.mutate(newPrompt.trim())}>
              Add
            </Button>
          </div>
        )}
      </Card>

      <Card>
        <h2 className="mt-0 text-xl font-semibold">Prompts &amp; answers</h2>
        <p className="mt-0 text-sm text-muted-foreground">Every question asked and what each model said, newest first — the raw evidence behind the numbers above.</p>
        {evidence.isLoading ? (
          <LoadingState label="Loading evidence…"/>
        ) : evidence.error ? (
          <ErrorState message={evidence.error.message}/>
        ) : !evidence.data?.responses.length ? (
          <p className="py-6 text-center text-sm text-muted-foreground">No panel answers recorded yet.</p>
        ) : (
          <ul className="divide-y">
            {evidence.data.responses.map((row) => <EvidenceRow key={row.id} row={row}/>)}
          </ul>
        )}
      </Card>
    </div>
  );
}
