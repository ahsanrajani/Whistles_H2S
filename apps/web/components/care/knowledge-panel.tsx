"use client";

import {useQuery} from "@tanstack/react-query";
import {useState} from "react";
import {apiFetch} from "@/lib/api";
import type {KbArticles} from "@/lib/types";
import {useKbArticle} from "@/hooks/use-api";
import {ErrorState, LoadingState} from "@/components/states";
import {Button} from "@/components/ui/button";
import {Input} from "@/components/ui/input";

export function KnowledgePanel({enabled, canInsert, onInsert}: {
  enabled: boolean; canInsert: boolean; onInsert: (body: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const list = useQuery({
    queryKey: ["kb", "articles", search, false],
    queryFn: () => apiFetch<KbArticles>(`/kb/articles?q=${encodeURIComponent(search)}`),
    enabled,
  });
  const detail = useKbArticle(selected);

  return <div className="grid gap-3">
    <h2 className="m-0 text-sm font-semibold">Knowledge base</h2>
    <Input aria-label="Search knowledge articles" placeholder="Search published articles…" value={search}
      onChange={(event) => {setSearch(event.target.value); setSelected(null);}}/>
    {list.isLoading && <LoadingState label="Loading articles…"/>}
    {list.error && <ErrorState message={list.error.message}/>}
    {list.data?.articles.length === 0 && <p className="m-0 text-sm text-muted-foreground">No published articles match your search.</p>}
    <div className="grid gap-2">
      {list.data?.articles.map((article) => <button key={article.id} type="button"
        aria-expanded={selected === article.id} onClick={() => setSelected(selected === article.id ? null : article.id)}
        className="grid gap-1 rounded-[0.625rem] border p-3 text-left text-sm hover:bg-muted">
        <span className="font-semibold">{article.title}</span>
        {article.tags && <span className="text-xs text-muted-foreground">{article.tags}</span>}
      </button>)}
    </div>
    {selected != null && <section aria-label="Article preview" className="grid gap-2 rounded-[0.625rem] border bg-muted/30 p-3">
      {detail.isLoading && <LoadingState label="Loading article…"/>}
      {detail.error && <ErrorState message={detail.error.message}/>}
      {detail.data && <>
        <h3 className="m-0 text-sm font-semibold">{detail.data.article.title}</h3>
        <p className="m-0 whitespace-pre-wrap text-sm [overflow-wrap:anywhere]">{detail.data.article.body}</p>
        <Button type="button" className="h-auto whitespace-normal text-xs" disabled={!canInsert || !detail.data.article.published}
          onClick={() => onInsert(detail.data!.article.body)}>Insert into reply</Button>
        {!canInsert && <p className="m-0 text-xs text-muted-foreground">Reopen this case to compose a reply.</p>}
      </>}
    </section>}
  </div>;
}
