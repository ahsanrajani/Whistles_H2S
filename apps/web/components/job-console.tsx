"use client";
import {useQuery, useQueryClient} from "@tanstack/react-query";
import {useEffect, useRef, useState} from "react";
import {apiFetch} from "@/lib/api";
import type {JobStatus} from "@/lib/types";

const DONE = new Set(["done", "failed", "unknown"]);

/**
 * Streams a worker's log via SSE (`/jobs/:id/stream`); falls back to polling
 * `/jobs/:id` when EventSource is unavailable or errors. Refreshes dependent
 * queries once the job settles.
 */
export function JobConsole({jobId, onSettled}: {jobId: string | null; onSettled?: () => void}) {
  const client = useQueryClient();
  const settledFor = useRef<string | null>(null);
  const [sse, setSse] = useState<JobStatus | null>(null);
  // Lazy init: remount via `key={jobId}` at the call site resets this per job.
  const [streaming, setStreaming] = useState(() => typeof window !== "undefined" && "EventSource" in window);

  useEffect(() => {
    if (!jobId || typeof window === "undefined" || !("EventSource" in window)) return;
    const source = new EventSource(`/api/v1/jobs/${jobId}/stream`);
    source.onmessage = (event) => {
      try {
        const next = JSON.parse(event.data) as JobStatus;
        setSse(next);
        if (DONE.has(next.state)) source.close();
      } catch {
        /* ignore malformed frame */
      }
    };
    source.onerror = () => {source.close(); setStreaming(false);};
    return () => source.close();
  }, [jobId]);

  // Poll only while SSE is not carrying the stream.
  const poll = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => apiFetch<JobStatus>(`/jobs/${jobId}`),
    enabled: !!jobId && !streaming,
    refetchInterval: (q) => (q.state.data && DONE.has(q.state.data.state) ? false : 1200),
  });

  const status = sse ?? poll.data ?? null;
  const state = status?.state;
  useEffect(() => {
    if (!jobId || !state || !DONE.has(state) || settledFor.current === jobId) return;
    settledFor.current = jobId;
    client.invalidateQueries();
    onSettled?.();
  }, [jobId, state, client, onSettled]);

  if (!jobId) return null;
  const lines = status?.lines ?? [];
  const running = !state || !DONE.has(state);
  return (
    <div className="overflow-hidden rounded-[0.625rem] border bg-foreground/[.03] dark:bg-black/40">
      <div role="status" className="flex items-center gap-2 border-b px-3 py-2 text-xs font-semibold">
        <span className={running ? "size-2 animate-pulse rounded-full bg-highlight" : state === "failed" ? "size-2 rounded-full bg-danger" : "size-2 rounded-full bg-success"}/>
        {running ? "Working…" : state === "failed" ? "Failed" : "Complete"}
        <span className="ml-2 font-normal text-muted-foreground">{streaming ? "live" : "polling"}</span>
        <span className="numeric ml-auto font-normal text-muted-foreground">{jobId}</span>
      </div>
      <pre className="max-h-64 overflow-auto px-3 py-2 text-xs leading-5 text-muted-foreground">{lines.length ? lines.join("\n") : "queued…"}</pre>
    </div>
  );
}
