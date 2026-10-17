"use client";
import {useMutation, useQueryClient} from "@tanstack/react-query";
import {Check, ExternalLink, Upload, X} from "lucide-react";
import {Link} from "@/components/tenant-link";
import {useState} from "react";
import {apiFetch, ApiError} from "@/lib/api";
import {useReview} from "@/hooks/use-api";
import type {BranchComplaintUploadResult, ReviewMention} from "@/lib/types";
import {Badge} from "./ui/badge";
import {Button} from "./ui/button";
import {Card} from "./ui/card";
import {EmptyState, ErrorState, LoadingState} from "./states";

function CalibrationTable({rows}: {rows: import("@/lib/types").CalibrationRow[]}) {
  if (!rows.length) return <p className="p-4 text-sm text-muted-foreground">No matches yet — run a collection.</p>;
  return (
    <table className="w-full text-left text-sm">
      <thead><tr className="border-b text-xs text-muted-foreground"><th className="p-4">Rule</th><th className="p-4 text-right">Matches</th><th className="p-4 text-right">Labelled</th><th className="p-4">Progress to sample target</th><th className="p-4 text-right">Precision so far</th></tr></thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.rule} className="border-b last:border-0">
            <td className="p-4"><code className="rounded bg-muted px-1.5 py-0.5 text-xs">{row.rule}</code>{" "}
              {row.gated && <Badge className="border-warning/40 text-warning">gated</Badge>}{" "}
              {row.met && <Badge className="border-success/40 text-success">target met</Badge>}
            </td>
            <td className="numeric p-4 text-right">{row.n}</td>
            <td className="numeric p-4 text-right">{row.labelled} / {row.target}</td>
            <td className="p-4">
              <div className="h-2 min-w-32 rounded-full bg-muted">
                <div className="h-2 rounded-full bg-primary" style={{width: `${row.target ? Math.min(100, (100 * row.labelled) / row.target) : 0}%`}}/>
              </div>
            </td>
            <td className="numeric p-4 text-right">
              {row.precision == null ? <span className="text-muted-foreground">unmeasured</span>
                : <><strong>{(row.precision * 100).toFixed(1)}%</strong> <span className="text-muted-foreground">±{(((row.hi ?? 0) - (row.lo ?? 0)) * 50).toFixed(1)}</span></>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function VerdictRow({row, onDone}: {row: ReviewMention; onDone: (verdict: "yes" | "no") => void}) {
  const label = useMutation({
    mutationFn: (verdict: "yes" | "no") => apiFetch(`/review/${row.id}/${verdict}`, {method: "POST"}),
  });
  return (
    <li className="border-b py-4 last:border-0">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span className="font-bold text-primary dark:text-highlight">{row.brand}</span>
        <span>{row.surface} · {row.outlet ?? row.source} · {row.language ?? "unknown"}</span>
        <Badge className={row.needs_review ? "border-warning/40 text-warning" : "text-muted-foreground"}>{row.rule}</Badge>
      </div>
      <p className="mt-2 text-sm font-medium leading-6">
        {row.url ? <a href={row.url} target="_blank" rel="noreferrer" className="hover:text-primary">{row.text.slice(0, 280)} <ExternalLink className="inline size-3"/></a> : row.text.slice(0, 280)}
      </p>
      <div className="mt-3 flex gap-2">
        <Button className="h-8 px-3 text-xs" disabled={label.isPending} onClick={() => label.mutateAsync("yes").then(() => onDone("yes"))}><Check className="size-3.5"/>Really {row.brand}</Button>
        <Button variant="outline" className="h-8 px-3 text-xs" disabled={label.isPending} onClick={() => label.mutateAsync("no").then(() => onDone("no"))}><X className="size-3.5"/>False match</Button>
      </div>
    </li>
  );
}

function BranchComplaintUpload() {
  const client = useQueryClient();
  const [result, setResult] = useState<BranchComplaintUploadResult | null>(null);
  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return apiFetch<BranchComplaintUploadResult>("/review/branch-complaints/upload", {method: "POST", body: form});
    },
    onSuccess: (data) => {
      setResult(data);
      if (data.inserted) {
        client.invalidateQueries({queryKey: ["review"]});
        client.invalidateQueries({queryKey: ["branches"]});
      }
    },
  });
  return (
    <div className="flex flex-col items-end gap-2">
      <label className="flex h-9 w-max cursor-pointer items-center gap-1.5 rounded-[0.625rem] border bg-card px-3 text-xs font-semibold hover:bg-muted">
        <Upload size={14}/>{upload.isPending ? "Uploading…" : "Upload branch complaints (CSV)"}
        <input type="file" accept=".csv,text/csv" className="hidden"
          onChange={(e) => {const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = "";}}/>
      </label>
      {upload.isError && <p className="m-0 max-w-[40ch] text-right text-xs text-danger">{(upload.error as ApiError).message}</p>}
      {result && (
        <p className="m-0 max-w-[40ch] text-right text-xs text-muted-foreground">
          <span className="font-semibold text-foreground">{result.inserted}</span> inserted
          {result.skipped > 0 && <>, <span className="font-semibold text-warning">{result.skipped}</span> skipped</>}
          {result.errors.length > 0 && <> — {result.errors.slice(0, 3).map((e) => `row ${e.row}: ${e.reason}`).join("; ")}{result.errors.length > 3 ? "…" : ""}</>}
        </p>
      )}
    </div>
  );
}

export function ReviewView() {
  const query = useReview();
  const client = useQueryClient();
  const [labelledCount, setLabelledCount] = useState(0);
  const [resolved, setResolved] = useState<Set<number>>(new Set());

  if (query.isLoading) return <LoadingState label="Loading the calibration queue…"/>;
  if (query.error) return <ErrorState message={query.error.message}/>;
  const data = query.data!;
  const pending = data.batch.filter((row) => !resolved.has(row.id));

  function markDone(id: number) {
    setResolved((current) => new Set(current).add(id));
    setLabelledCount((count) => count + 1);
    client.invalidateQueries({queryKey: ["review"]});
    client.invalidateQueries({queryKey: ["overview"]});
  }

  return (
    <div className="mx-auto grid max-w-[87.5rem] gap-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-1 text-sm font-semibold text-primary dark:text-highlight">Precision measurement</p>
          <h1 className="m-0 text-3xl font-semibold tracking-tight md:text-4xl">Calibration queue</h1>
          <p className="text-muted-foreground">{pending.length} in this batch · <span className="numeric font-semibold text-foreground">{labelledCount}</span> labelled this session</p>
        </div>
        <BranchComplaintUpload/>
      </div>
      <Card className="max-w-[74ch] text-sm text-muted-foreground">
        Every collected mention is already live in <Link href="/mentions" className="font-semibold text-primary dark:text-highlight">Mentions</Link>. This
        queue only measures per-rule precision — it holds the ambiguous matches (gated patterns first, plus a slice of <code>exact_name</code> for a floor).
        Identity sources (app-store reviews, owned social) are the brand by construction and never appear here. To pull a bad match out of the client view,
        use <strong>Hide</strong> on its row in Mentions.
      </Card>
      <Card className="p-0"><CalibrationTable rows={data.calibration}/></Card>
      <Card>
        {pending.length ? (
          <ul className="divide-y">{pending.map((row) => <VerdictRow key={row.id} row={row} onDone={() => markDone(row.id)}/>)}</ul>
        ) : (
          <EmptyState title="Nothing left to label" body="Either every rule has been worked, or a collection has not run yet."/>
        )}
      </Card>
    </div>
  );
}
