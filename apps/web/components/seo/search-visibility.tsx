"use client";

import {useVantageSeo} from "@/hooks/use-api";
import {Badge} from "../ui/badge";
import {EmptyState, ErrorState, LoadingState} from "../states";

/** Own-brand only (Hamza, 2026-09-12): a Venn stops making sense with one
 * circle, so the focus brand gets a stat row instead of the SVG that used to
 * compare it against competitors. */
export function SearchVisibility() {
  const query = useVantageSeo();
  if (query.isLoading) return <LoadingState label="Loading search visibility…"/>;
  if (query.error) return <ErrorState message={query.error.message}/>;
  const data = query.data;
  if (!data || !data.total_results) {
    return <EmptyState title="No SERP data yet" body="Runs a DataForSEO brand-name search each collection pass — check back after the next collection run."/>;
  }
  const focus = data.brands.find((b) => b.is_focus);
  const bestRank = focus?.own_domains.length
    ? Math.min(...focus.own_domains.map((d) => d.best_rank))
    : null;

  return (
    <div>
      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div className="rounded-card border p-4 text-center">
          <p className="numeric m-0 text-3xl font-bold">{focus?.own_domains.length ?? 0}</p>
          <p className="m-0 text-xs text-muted-foreground">own domain{focus?.own_domains.length === 1 ? "" : "s"} ranking</p>
        </div>
        <div className="rounded-card border p-4 text-center">
          <p className="numeric m-0 text-3xl font-bold">{bestRank ?? "—"}</p>
          <p className="m-0 text-xs text-muted-foreground">best rank</p>
        </div>
        <div className="rounded-card border p-4 text-center">
          <p className="numeric m-0 text-3xl font-bold">{data.total_results}</p>
          <p className="m-0 text-xs text-muted-foreground">results collected</p>
        </div>
      </div>

      {focus && (
        <div className="mb-5">
          <h3 className="mb-1.5 text-sm font-semibold text-primary dark:text-highlight">{focus.name}</h3>
          {focus.own_domains.length ? (
            <ul className="m-0 list-none space-y-1 p-0 text-sm">
              {focus.own_domains.map((d) => (
                <li key={d.domain} className="flex items-center justify-between gap-2">
                  <a href={d.sample_url ?? undefined} target="_blank" rel="noreferrer" className="truncate text-primary hover:underline dark:text-highlight">{d.domain}</a>
                  <span className="numeric whitespace-nowrap text-xs text-muted-foreground">rank #{d.best_rank} · {d.appearances} appearance{d.appearances === 1 ? "" : "s"}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="m-0 text-xs text-muted-foreground">No own domain found ranking in the results collected so far — worth investigating.</p>
          )}
        </div>
      )}

      {data.third_party.length > 0 && (
        <div>
          <h3 className="mb-1.5 text-sm font-semibold text-muted-foreground">Shared / third-party visibility</h3>
          <p className="mt-0 text-xs text-muted-foreground">Pages that rank for this brand-name search but aren&apos;t the brand&apos;s own site — social profiles, directories, press.</p>
          <div className="flex flex-wrap gap-1.5">
            {data.third_party.slice(0, 20).map((d) => (
              <Badge key={d.domain} className="bg-muted text-muted-foreground">{d.domain} · #{d.best_rank}</Badge>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
