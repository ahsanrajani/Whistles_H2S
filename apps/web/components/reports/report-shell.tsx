"use client";

import {useMutation} from "@tanstack/react-query";
import {useState} from "react";
import {useSearchParams} from "next/navigation";
import {useTenantHref, useTenantRouter as useRouter} from "@/components/tenant-link";
import {apiFetch} from "@/lib/api";
import type {Measure as MeasureT} from "@/lib/types";
import {Button} from "@/components/ui/button";
import {Input} from "@/components/ui/input";

/** URL-backed date range (F5.1), shared by every report tab. Defaults to the
 * trailing 30 days, like the rest of the app's PeriodControl surfaces. */
export function useReportRange() {
  const params = useSearchParams();
  const router = useRouter();
  const end = params.get("end") ?? new Date().toISOString().slice(0, 10);
  const start = params.get("start") ?? (() => {
    const d = new Date();
    d.setDate(d.getDate() - 29);
    return d.toISOString().slice(0, 10);
  })();

  function setRange(next: {start?: string; end?: string}) {
    const sp = new URLSearchParams(params.toString());
    if (next.start) sp.set("start", next.start);
    if (next.end) sp.set("end", next.end);
    router.replace(`?${sp}`);
  }
  return {start, end, setRange};
}

export function RangePicker({start, end, onChange}: {start: string; end: string; onChange: (next: {start?: string; end?: string}) => void}) {
  return (
    <div className="flex items-center gap-2">
      <input type="date" aria-label="Start date" value={start} onChange={(e) => onChange({start: e.target.value})}
        className="h-9 rounded-[0.625rem] border bg-card px-2 text-xs"/>
      <span className="text-xs text-muted-foreground">to</span>
      <input type="date" aria-label="End date" value={end} onChange={(e) => onChange({end: e.target.value})}
        className="h-9 rounded-[0.625rem] border bg-card px-2 text-xs"/>
    </div>
  );
}

/** A Wilson-scored proportion renders its interval; a count renders as a plain
 * number. `null` renders "no data" — never a fabricated 0 (build plan §0.4). */
export function Measure({m, digits = 1, suffix = ""}: {m: MeasureT | null | undefined; digits?: number; suffix?: string}) {
  if (!m || m.value == null) return <span className="text-muted-foreground">no data</span>;
  if (m.kind === "proportion" && m.wilson) {
    const [lo, hi] = m.wilson;
    return (
      <span>
        <span className="numeric font-semibold">{(m.value * 100).toFixed(digits)}%</span>
        <span className="ml-1 text-xs text-muted-foreground">({(lo * 100).toFixed(digits)}–{(hi * 100).toFixed(digits)}%)</span>
      </span>
    );
  }
  return <span className="numeric font-semibold">{m.value.toLocaleString(undefined, {maximumFractionDigits: digits})}{suffix}</span>;
}

/** CSV / Excel / PDF export links + a "Schedule" entry point for one report
 * kind (F5.1 / F5.7). `params` are the report_delivery query params. */
export function ExportBar({kind, params}: {kind: string; params: Record<string, string>}) {
  const href = useTenantHref();
  const [openSchedule, setOpenSchedule] = useState(false);
  const qs = new URLSearchParams({kind, ...params}).toString();

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {(["csv", "xlsx", "pdf"] as const).map((f) => (
        <a key={f} download href={href(`/api/v1/reports/export?${qs}&format=${f}`)}
          className="rounded-[0.5rem] border bg-card px-2.5 py-1.5 text-xs font-semibold hover:bg-muted">
          {f.toUpperCase()}
        </a>
      ))}
      <Button type="button" variant="outline" className="h-8 text-xs" onClick={() => setOpenSchedule(true)}>Schedule…</Button>
      {openSchedule && <ScheduleDialog kind={kind} params={params} onClose={() => setOpenSchedule(false)}/>}
    </div>
  );
}

function ScheduleDialog({kind, params, onClose}: {kind: string; params: Record<string, string>; onClose: () => void}) {
  const [name, setName] = useState(`${kind} report`);
  const [cron, setCron] = useState("0 7 * * 1");
  const [format, setFormat] = useState("pdf");
  const [recipients, setRecipients] = useState("");

  const save = useMutation({
    mutationFn: () => apiFetch("/reports/schedules", {
      method: "POST",
      body: JSON.stringify({
        name, kind, cron, format,
        params: {source: params.source, metric: params.metric},
        recipients: recipients.split(",").map((r) => r.trim()).filter(Boolean),
      }),
    }),
    onSuccess: onClose,
  });

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40" onClick={onClose}>
      <div className="w-full max-w-sm rounded-card border bg-card p-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="m-0 mb-3 text-sm font-semibold">Schedule this report</h3>
        <div className="grid gap-2">
          <Input aria-label="Schedule name" value={name} onChange={(e) => setName(e.target.value)} className="h-9 text-sm"/>
          <Input aria-label="Cron expression" value={cron} onChange={(e) => setCron(e.target.value)} className="h-9 text-xs"
            placeholder="0 7 * * 1 (Mondays 07:00 UTC)"/>
          <select aria-label="Format" value={format} onChange={(e) => setFormat(e.target.value)}
            className="h-9 rounded-[0.625rem] border bg-card px-2 text-sm">
            {["pdf", "xlsx", "csv"].map((f) => <option key={f} value={f}>{f.toUpperCase()}</option>)}
          </select>
          <Input aria-label="Recipients" value={recipients} onChange={(e) => setRecipients(e.target.value)}
            placeholder="email@bank.test, ops@bank.test" className="h-9 text-xs"/>
          <div className="flex gap-2">
            <Button type="button" disabled={!recipients.trim() || save.isPending} onClick={() => save.mutate()}>Save</Button>
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          </div>
          {save.isError && <span className="text-xs text-danger">{(save.error as Error).message}</span>}
        </div>
      </div>
    </div>
  );
}
