"use client";

import {useMutation} from "@tanstack/react-query";
import {useState} from "react";
import {apiFetch} from "@/lib/api";
import {useCrawlPages, useCrawlReport} from "@/hooks/use-api";
import type {CrawlRunQueued} from "@/lib/types";
import {Badge} from "../ui/badge";
import {Button} from "../ui/button";
import {EmptyState, ErrorState, LoadingState} from "../states";
import {ScoreRing} from "./score-ring";

// Google's own published Core Web Vitals thresholds (web.dev) -- not
// invented here, just applied to the real measured value.
const CWV_THRESHOLDS: Record<string, [number, number]> = {
  lcp_ms: [2500, 4000], cls: [0.1, 0.25], tbt_ms: [200, 600],
  fcp_ms: [1800, 3000], speed_index_ms: [3400, 5800], tti_ms: [3800, 7300],
};
const CWV_LABEL: Record<string, string> = {
  lcp_ms: "Largest Contentful Paint", cls: "Cumulative Layout Shift",
  tbt_ms: "Total Blocking Time", fcp_ms: "First Contentful Paint",
  speed_index_ms: "Speed Index", tti_ms: "Time to Interactive",
};

function cwvBand(metric: string, value: number): "good" | "needs-improvement" | "poor" {
  const t = CWV_THRESHOLDS[metric];
  if (!t) return "good";
  return value <= t[0] ? "good" : value <= t[1] ? "needs-improvement" : "poor";
}
const BAND_CLS = {
  good: "border-success/30 bg-success/10 text-success",
  "needs-improvement": "border-warning/40 bg-warning/10 text-warning",
  poor: "border-danger/40 bg-danger/10 text-danger",
};

function fmtCwv(metric: string, value: number): string {
  return metric === "cls" ? value.toFixed(3) : `${(value / 1000).toFixed(1)}s`;
}

const CHECK_LABEL: Record<string, string> = {
  no_description: "Missing meta description", no_title: "Missing title tag",
  no_h1_tag: "Missing H1", no_image_alt: "Images without alt text",
  no_image_title: "Images without title", no_favicon: "Missing favicon",
  duplicate_title: "Duplicate titles", duplicate_description: "Duplicate descriptions",
  duplicate_content: "Duplicate content", broken_links: "Broken links",
  broken_resources: "Broken resources", title_too_long: "Title too long",
  title_too_short: "Title too short", low_content_rate: "Thin content",
  high_loading_time: "Slow-loading pages", is_redirect: "Redirects",
  is_4xx_code: "4xx errors", is_5xx_code: "5xx errors",
};
const CRITICAL_CHECKS = new Set(["is_4xx_code", "is_5xx_code", "broken_links", "broken_resources"]);
// Site-wide totals from DataForSEO's page_metrics, not entries in a page's
// own checks{} object -- there is no per-page list to drill into for these
// (live-confirmed: the API rejects a checks.* filter on them), so they
// render as a plain count with no click-to-expand.
const NON_DRILLABLE_CHECKS = new Set(["broken_links", "duplicate_content", "duplicate_title", "duplicate_description"]);

function IssueRow({check, n, taskId}: {check: string; n: number; taskId: string | null}) {
  const [open, setOpen] = useState(false);
  const drillable = !NON_DRILLABLE_CHECKS.has(check);
  const pages = useCrawlPages(taskId, check, drillable && open);
  if (!drillable) {
    return (
      <li className="border-t py-1 first:border-t-0">
        <div className="flex w-full items-center justify-between gap-2 text-sm">
          <span>{CHECK_LABEL[check] ?? check}</span>
          <span className="numeric font-semibold">{n}</span>
        </div>
      </li>
    );
  }
  return (
    <li className="border-t py-1 first:border-t-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={!taskId}
        className="flex w-full items-center justify-between gap-2 bg-transparent p-0 text-left text-sm disabled:cursor-default"
        title={taskId ? "Show affected pages" : "Re-run the site crawl to see affected pages"}
      >
        <span className={taskId ? "underline decoration-dotted underline-offset-2" : undefined}>
          {CHECK_LABEL[check] ?? check}
        </span>
        <span className="numeric font-semibold">{n}</span>
      </button>
      {open && (
        <div className="mt-1.5 rounded-card border bg-muted/30 p-2 text-xs">
          {pages.isLoading && <p className="m-0 text-muted-foreground">Loading pages…</p>}
          {pages.error && <p className="m-0 text-danger">{(pages.error as Error).message}</p>}
          {pages.data && pages.data.pages.length === 0 && (
            <p className="m-0 text-muted-foreground">No pages returned for this check.</p>
          )}
          {pages.data && pages.data.pages.length > 0 && (
            <ul className="m-0 list-none space-y-1 p-0">
              {pages.data.pages.map((p, i) => (
                <li key={i} className="flex items-center justify-between gap-2 truncate">
                  <span className="truncate" title={p.url ?? undefined}>{p.url ?? "—"}</span>
                  {p.status_code != null && <span className="numeric shrink-0 text-muted-foreground">{p.status_code}</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}

function IssueList({title, issues, taskId}: {title: string; issues: [string, number][]; taskId: string | null}) {
  if (!issues.length) return null;
  return (
    <div className="flex-1">
      <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h4>
      <ul className="m-0 list-none space-y-1 p-0 text-sm">
        {issues.map(([check, n]) => (
          <IssueRow key={check} check={check} n={n} taskId={taskId}/>
        ))}
      </ul>
    </div>
  );
}

/** One wide panel for the focus brand only (Hamza, 2026-09-12) instead of the
 * small multi-brand card grid this used to be a 1-of-N slot in. */
const PAGE_COUNT_OPTIONS = [30, 60, 90] as const;

export function SiteHealth({canEdit}: {canEdit: boolean}) {
  const query = useCrawlReport();
  const [queued, setQueued] = useState(false);
  const [maxPages, setMaxPages] = useState<number>(30);
  // Runs on the background worker (takes several minutes) -- this just
  // enqueues it. No live progress panel here; results show up in this
  // panel once the run finishes and the page is refreshed.
  const run = useMutation({
    mutationFn: () => apiFetch<CrawlRunQueued>("/vantage/seo/crawl/run", {method: "POST", body: JSON.stringify({max_pages: maxPages})}),
    onSuccess: () => setQueued(true),
  });
  if (query.isLoading) return <LoadingState label="Loading site health…"/>;
  if (query.error) return <ErrorState message={query.error.message}/>;
  const brand = query.data?.brands.find((b) => b.is_focus) ?? query.data?.brands[0];
  const issues = brand ? Object.entries(brand.checks).filter(([, n]) => n > 0) : [];
  const critical = issues.filter(([check]) => CRITICAL_CHECKS.has(check)).sort((a, b) => b[1] - a[1]);
  const rest = issues.filter(([check]) => !CRITICAL_CHECKS.has(check)).sort((a, b) => b[1] - a[1]);

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <p className="m-0 text-xs text-muted-foreground">{query.data?.day ? `Last crawled ${query.data.day}` : "Never run yet"} — an on-page crawl (up to {maxPages} pages, 100+ checks) plus a Lighthouse Core Web Vitals audit of the homepage. Takes 1–3 minutes.</p>
        {canEdit && (
          <div className="flex items-center gap-2">
            <select value={maxPages} disabled={run.isPending}
                    onChange={(e) => setMaxPages(Number(e.target.value))}
                    className="rounded-card border bg-background px-2 py-1.5 text-sm">
              {PAGE_COUNT_OPTIONS.map((n) => (
                <option key={n} value={n}>{n} pages</option>
              ))}
            </select>
            <Button type="button" disabled={run.isPending} onClick={() => run.mutate()}>
              {run.isPending ? "Queuing…" : queued ? "Queued" : "Run site crawl"}
            </Button>
          </div>
        )}
      </div>
      {!brand ? (
        <EmptyState title="No crawl yet" body={canEdit ? "Run the site crawl to pull on-page checks and Core Web Vitals for the focus brand's domain." : "Ask an admin to run the site crawl."}/>
      ) : (
        <div>
          <div className="mb-5 flex flex-wrap items-center gap-6">
            {brand.onpage_score != null && <ScoreRing score={brand.onpage_score} label="on-page score"/>}
            {brand.pages_crawled != null && (
              <div className="rounded-card border p-4 text-center">
                <p className="numeric m-0 text-3xl font-bold">{brand.pages_crawled}</p>
                <p className="m-0 text-xs text-muted-foreground">pages crawled</p>
              </div>
            )}
            {Object.keys(brand.scores).length > 0 && (
              <div className="flex flex-wrap items-center gap-6">
                {(["performance", "accessibility", "best_practices", "seo"] as const)
                  .filter((cat) => brand.scores[cat] != null)
                  .map((cat) => (
                    <ScoreRing key={cat} score={brand.scores[cat]} size={72}
                              label={cat.replace("_", " ")}/>
                  ))}
              </div>
            )}
          </div>

          {Object.keys(brand.cwv).length > 0 && (
            <div className="mb-5 flex flex-wrap gap-2">
              {Object.entries(brand.cwv).map(([metric, value]) => (
                <Badge key={metric} className={BAND_CLS[cwvBand(metric, value)]}>
                  {CWV_LABEL[metric] ?? metric}: {fmtCwv(metric, value)}
                </Badge>
              ))}
            </div>
          )}

          {issues.length > 0 ? (
            <div className="flex flex-col gap-5 sm:flex-row">
              <IssueList title="Critical" issues={critical} taskId={brand.task_id}/>
              <IssueList title="Needs attention" issues={rest} taskId={brand.task_id}/>
            </div>
          ) : (
            <p className="m-0 text-sm text-muted-foreground">No crawl data on file.</p>
          )}
        </div>
      )}
    </div>
  );
}
