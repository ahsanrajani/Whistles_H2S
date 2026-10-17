"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {apiFetch} from "@/lib/api";
import {useMe, useSeoSuggestions} from "@/hooks/use-api";
import type {SeoSuggestions} from "@/lib/types";
import {can} from "@/lib/permissions";
import {Badge} from "./ui/badge";
import {Button} from "./ui/button";
import {Card} from "./ui/card";
import {ErrorState, LoadingState} from "./states";
import {PageHeader} from "./viewer-components";
import {SearchVisibility} from "./seo/search-visibility";
import {SiteHealth} from "./seo/site-health";
import {TechnicalSeo} from "./seo/technical-seo";

const PRIORITY_STYLE: Record<string, string> = {
  HIGH: "border-danger/40 bg-danger/10 text-danger",
  MEDIUM: "border-warning/40 bg-warning/10 text-warning",
  LOW: "border-muted-foreground/30 text-muted-foreground",
};

function SeoSuggestionsCard({canEdit}: {canEdit: boolean}) {
  const query = useQueryClient();
  const suggestions = useSeoSuggestions();
  const run = useMutation({
    mutationFn: () => apiFetch<SeoSuggestions>("/vantage/seo/suggestions/run", {method: "POST"}),
    onSuccess: () => query.invalidateQueries({queryKey: ["vantage", "seo", "suggestions"]}),
  });
  const row = suggestions.data?.suggestion;

  return (
    <Card>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h2 className="m-0 text-xl font-semibold">SEO suggestions</h2>
        {canEdit && (
          <Button type="button" disabled={run.isPending} onClick={() => run.mutate()}>
            {run.isPending ? "Asking the model…" : row ? "Regenerate" : "Generate suggestions"}
          </Button>
        )}
      </div>
      {run.isError && <p role="alert" className="mt-2 rounded-[0.625rem] border border-danger/30 bg-danger/10 p-3 text-sm text-danger">Failed — {(run.error as Error).message}</p>}
      {suggestions.isLoading ? (
        <LoadingState label="Loading suggestions…"/>
      ) : suggestions.error ? (
        <ErrorState message={suggestions.error.message}/>
      ) : !row ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          {canEdit ? "No suggestions generated yet." : "Ask an admin to generate SEO suggestions."}
        </p>
      ) : row.error ? (
        <p className="mt-3 text-sm text-danger">Last run failed — {row.error}</p>
      ) : (
        <ul className="mt-3 divide-y">
          {row.suggestions.map((s, i) => (
            <li key={i} className="flex items-start gap-3 py-2.5 text-sm">
              <Badge className={PRIORITY_STYLE[s.priority] ?? PRIORITY_STYLE.LOW}>{s.priority}</Badge>
              <span className="flex-1">{s.text}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function SeoView() {
  const me = useMe();
  const canEdit = can(me.data?.user.perms, "admin:edit");

  return (
    <div className="mx-auto grid max-w-[93.75rem] gap-5">
      <PageHeader title="SEO" subtitle="Search visibility, technical SEO and site health for the focus brand — via DataForSEO."/>

      <Card>
        <h2 className="mt-0 text-xl font-semibold">Search visibility</h2>
        <p className="mt-0 text-sm text-muted-foreground">Google results for the brand&apos;s name — whose own site shows up, and who else does.</p>
        <SearchVisibility/>
      </Card>

      <Card>
        <h2 className="mt-0 text-xl font-semibold">Site health &amp; Core Web Vitals</h2>
        <p className="mt-0 text-sm text-muted-foreground">An on-page crawl (100+ checks — canonical tags, duplicate content, broken links, thin content, image alt text…) plus a Lighthouse audit of the homepage.</p>
        <SiteHealth canEdit={canEdit}/>
      </Card>

      <Card>
        <h2 className="mt-0 text-xl font-semibold">Technical SEO</h2>
        <p className="mt-0 text-sm text-muted-foreground">Keyword rankings and backlink profile for the brand&apos;s own domain, via DataForSEO.</p>
        <TechnicalSeo canEdit={canEdit}/>
      </Card>

      <SeoSuggestionsCard canEdit={canEdit}/>
    </div>
  );
}
