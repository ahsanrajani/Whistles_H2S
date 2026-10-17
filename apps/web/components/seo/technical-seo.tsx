"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {useState} from "react";
import {apiFetch} from "@/lib/api";
import {useSeoReport} from "@/hooks/use-api";
import type {SeoRunResult} from "@/lib/types";
import {Button} from "../ui/button";
import {EmptyState, ErrorState, LoadingState} from "../states";

/** One wide panel for the focus brand only (Hamza, 2026-09-12) instead of the
 * small multi-brand card grid this used to be a 1-of-N slot in. */
export function TechnicalSeo({canEdit}: {canEdit: boolean}) {
  const query = useSeoReport();
  const qc = useQueryClient();
  const [lastRun, setLastRun] = useState<SeoRunResult | null>(null);
  const run = useMutation({
    mutationFn: () => apiFetch<SeoRunResult>("/vantage/seo/run", {method: "POST"}),
    onSuccess: (data) => {
      setLastRun(data);
      qc.invalidateQueries({queryKey: ["vantage", "seo"]});
    },
  });
  if (query.isLoading) return <LoadingState label="Loading SEO report…"/>;
  if (query.error) return <ErrorState message={query.error.message}/>;
  const brand = query.data?.brands.find((b) => b.is_focus) ?? query.data?.brands[0];
  const bl = brand?.backlinks;
  const maxVolume = Math.max(1, ...(brand?.keywords.map((k) => k.search_volume ?? 0) ?? [0]));

  return (
    <div>
      {canEdit && (
        <div className="mb-4 flex items-center justify-end">
          <Button type="button" disabled={run.isPending} onClick={() => run.mutate()}>
            {run.isPending ? "Running…" : "Run SEO report"}
          </Button>
        </div>
      )}
      {run.isError && <p role="alert" className="mb-4 rounded-[0.625rem] border border-danger/30 bg-danger/10 p-3 text-sm text-danger">Run failed — {(run.error as Error).message}</p>}
      {lastRun && (
        <p role="status" className="mb-4 rounded-[0.625rem] border border-success/30 bg-success/10 p-3 text-sm text-success">
          Pulled {lastRun.keywords_pulled} keyword(s) and {lastRun.backlinks_pulled} backlink summary(ies).
          {lastRun.errors.length > 0 && ` ${lastRun.errors.length} error(s) — see log.`}
        </p>
      )}
      {!brand ? (
        <EmptyState title="No SEO report yet" body={canEdit ? "Run the SEO report to pull keyword rankings and backlinks for the focus brand's domain." : "Ask an admin to run the SEO report."}/>
      ) : (
        <div>
          <div className="mb-5 grid grid-cols-3 gap-3">
            <div className="rounded-card border p-4 text-center">
              <p className="numeric m-0 text-3xl font-bold">{bl?.backlinks ?? "—"}</p>
              <p className="m-0 text-xs text-muted-foreground">backlinks</p>
            </div>
            <div className="rounded-card border p-4 text-center">
              <p className="numeric m-0 text-3xl font-bold">{bl?.referring_domains ?? "—"}</p>
              <p className="m-0 text-xs text-muted-foreground">referring domains</p>
            </div>
            <div className="rounded-card border p-4 text-center">
              <p className="numeric m-0 text-3xl font-bold">{bl?.rank ?? "—"}</p>
              <p className="m-0 text-xs text-muted-foreground">domain rank</p>
            </div>
          </div>

          {brand.keywords.length ? (
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="text-muted-foreground">
                  <th className="pb-1.5 font-normal">Keyword</th>
                  <th className="w-1/3 pb-1.5 font-normal">Volume</th>
                  <th className="pb-1.5 text-right font-normal">Rank</th>
                </tr>
              </thead>
              <tbody>
                {brand.keywords.map((k) => (
                  <tr key={k.keyword} className="border-t">
                    <td className="py-1.5 pr-2">{k.url ? <a href={k.url} target="_blank" rel="noreferrer" className="text-primary hover:underline dark:text-highlight">{k.keyword}</a> : k.keyword}</td>
                    <td className="py-1.5 pr-2">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 flex-1 rounded-full bg-muted">
                          <div className="h-1.5 rounded-full bg-primary dark:bg-highlight" style={{width: `${((k.search_volume ?? 0) / maxVolume) * 100}%`}}/>
                        </div>
                        <span className="numeric w-14 shrink-0 text-right text-xs text-muted-foreground">{k.search_volume?.toLocaleString() ?? "—"}</span>
                      </div>
                    </td>
                    <td className="numeric py-1.5 text-right">{k.rank ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="m-0 text-sm text-muted-foreground">No keyword data on file.</p>
          )}
        </div>
      )}
    </div>
  );
}
