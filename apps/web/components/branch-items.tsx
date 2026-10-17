"use client";

import {ExternalLink} from "lucide-react";
import {useSearchParams} from "next/navigation";

import {useBranchItems} from "@/hooks/use-api";
import type {BranchesPage} from "@/lib/types";
import {useTenantRouter as useRouter} from "@/components/tenant-link";
import {Badge} from "./ui/badge";

const PAGE_SIZE = 25;

function issueLabel(key: string, policy: BranchesPage["policy"]) {
  return policy.issues.find(i => i.key === key)?.label ?? key.replace(/_/g, " ");
}

/** Every review / mention behind one branch card, paged. Issue + page live in the URL. */
export function BranchItems({branchKey, period}: {branchKey: string; period: string}) {
  const params = useSearchParams();
  const router = useRouter();
  const issue = params.get("issue") ?? "";
  const page = Math.max(0, Number(params.get("page") ?? 0) || 0);

  const q = new URLSearchParams({period, offset: String(page * PAGE_SIZE), limit: String(PAGE_SIZE)});
  if (issue) q.set("issue", issue);
  const result = useBranchItems(branchKey, q.toString());

  function goto(next: number) {
    const u = new URLSearchParams(params.toString());
    if (next > 0) u.set("page", String(next)); else u.delete("page");
    router.replace(`/branches?${u}`, {scroll: false});
  }

  if (result.isLoading) return <p className="mt-3 text-xs text-muted-foreground">Loading reviews…</p>;
  if (result.error) return <p className="mt-3 text-xs text-danger">{result.error.message}</p>;
  const data = result.data;
  if (!data) return null;
  const pages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  const from = data.total ? data.offset + 1 : 0;
  const to = Math.min(data.offset + data.items.length, data.total);

  return <div className="mt-3">
    <p className="m-0 text-xs text-muted-foreground">
      {data.total ? `${from}–${to} of ${data.total}` : "No items"}
      {issue && <> tagged <span className="font-semibold text-foreground">{issueLabel(issue, data.policy)}</span></>}
    </p>
    {data.items.length > 0 && <ul className="mt-2 divide-y">
      {data.items.map(item => <li key={item.id} className="py-2">
        <div className="flex flex-wrap items-center gap-2 text-[0.6875rem] text-muted-foreground">
          {item.rating != null && <span className="text-warning">{"★".repeat(item.rating)}</span>}
          <span>{item.outlet ?? item.surface}</span>
          <span>· {(item.published_at ?? "").slice(0, 10)}</span>
          {item.issues.map(k => <Badge key={k} className="border-border text-muted-foreground">{issueLabel(k, data.policy)}</Badge>)}
          {item.url && !item.url.startsWith("#") && <a href={item.url} target="_blank" rel="noreferrer" className="ml-auto" aria-label="Open source"><ExternalLink size={11}/></a>}
        </div>
        <p className="m-0 mt-1 text-sm">{item.text}</p>
      </li>)}
    </ul>}
    {pages > 1 && <div className="mt-3 flex items-center gap-2 text-xs">
      <button type="button" disabled={page === 0} onClick={() => goto(page - 1)}
              className="rounded-full border px-2.5 py-1 disabled:opacity-40">Previous</button>
      <span className="numeric text-muted-foreground">Page {page + 1} of {pages}</span>
      <button type="button" disabled={page + 1 >= pages} onClick={() => goto(page + 1)}
              className="rounded-full border px-2.5 py-1 disabled:opacity-40">Next</button>
      {result.isFetching && <span className="text-muted-foreground">…</span>}
    </div>}
  </div>;
}
