"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {useState} from "react";
import {useSearchParams} from "next/navigation";
import {useTenantRouter as useRouter} from "@/components/tenant-link";
import {useKbArticle, useKbArticles, useMe} from "@/hooks/use-api";
import {apiFetch} from "@/lib/api";
import {can} from "@/lib/permissions";
import {cn} from "@/lib/utils";
import {EmptyState, ErrorState, LoadingState} from "@/components/states";
import {Button} from "@/components/ui/button";
import {Card} from "@/components/ui/card";
import {Input} from "@/components/ui/input";
import {AutoMacrosTab} from "@/components/macros/auto-macros-tab";
import {MacrosTab} from "@/components/macros/macros-tab";
import {TabBar} from "@/components/ui/tab-bar";

const TABS = [
  {key: "articles", label: "Articles"},
  {key: "macros", label: "Macros"},
  {key: "auto", label: "Auto macros"},
] as const;

export function KnowledgeView() {
  const params = useSearchParams();
  const router = useRouter();
  const me = useMe();
  const canAuthor = can(me.data?.user.perms, "templates:edit");
  // Auto macros are authored by team leads / supervisors / admins; "templates" is the pre-macros URL.
  const tabs = TABS.filter((t) => t.key !== "auto" || canAuthor);
  const raw = params.get("tab") === "templates" ? "macros" : params.get("tab");
  const tab = tabs.some((t) => t.key === raw) ? raw! : "articles";

  return (
    <div className="mx-auto grid max-w-[81.25rem] gap-5">
      <div>
        <p className="mb-0.5 text-sm font-semibold text-primary dark:text-highlight">Care enablement</p>
        <h1 className="m-0 text-2xl font-semibold tracking-tight">Knowledge</h1>
      </div>
      <TabBar label="Knowledge tabs" items={tabs.map((t) => ({key: t.key, label: t.label}))} value={tab}
        onChange={(key) => {const sp = new URLSearchParams(params.toString()); sp.set("tab", key); router.replace(`/knowledge?${sp}`);}}/>
      {tab === "articles" ? <ArticlesTab/> : tab === "macros" ? <MacrosTab/> : <AutoMacrosTab/>}
    </div>
  );
}

// ---------------------------------------------------------------- Articles
function ArticlesTab() {
  const me = useMe();
  const query = useQueryClient();
  const canEdit = can(me.data?.user.perms, "templates:edit");
  const canDelete = can(me.data?.user.perms, "templates:delete");

  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const [drafts, setDrafts] = useState(false);
  const list = useKbArticles(q, drafts && canEdit);

  const refresh = () => query.invalidateQueries({queryKey: ["kb"]});

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(280px,340px)_1fr]">
      <div className="grid content-start gap-2">
        <div className="flex gap-2">
          <Input aria-label="Search articles" value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Search…" className="h-9 flex-1 text-sm"/>
          {canEdit && (
            <Button type="button" variant="outline" className="h-9 px-3 text-xs" onClick={() => setSelected(0)}>New</Button>
          )}
        </div>
        {canEdit && (
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <input type="checkbox" checked={drafts} onChange={(e) => setDrafts(e.target.checked)}/>Show drafts
          </label>
        )}
        {list.isLoading && <LoadingState label="Loading articles…"/>}
        {list.error && <ErrorState message={list.error.message}/>}
        {list.data && list.data.articles.length === 0 && (
          <EmptyState title="No articles" body="Nothing matches — or none authored yet."/>
        )}
        {list.data?.articles.map((a) => (
          <button key={a.id} type="button" onClick={() => setSelected(a.id)}
            className={cn("grid gap-1 rounded-[0.625rem] border p-2.5 text-left text-sm",
              a.id === selected ? "border-primary/40 bg-primary/5" : "bg-card hover:bg-muted")}>
            <span className="flex items-center gap-2 font-medium">
              {a.title}
              {!a.published && <span className="rounded-full border px-1.5 py-0.5 text-[0.625rem] font-semibold text-muted-foreground">draft</span>}
            </span>
            {a.tags && <span className="text-[0.6875rem] text-muted-foreground">{a.tags}</span>}
          </button>
        ))}
      </div>

      {selected === null ? (
        <Card className="grid place-items-center text-sm text-muted-foreground">Select an article.</Card>
      ) : selected === 0 ? (
        <ArticleEditor id={null} onSaved={(id) => {refresh(); setSelected(id);}} onCancel={() => setSelected(null)}/>
      ) : (
        <ArticleDetail id={selected} canEdit={canEdit} canDelete={canDelete}
          onChanged={refresh} onDeleted={() => {refresh(); setSelected(null);}}/>
      )}
    </div>
  );
}

function ArticleDetail({id, canEdit, canDelete, onChanged, onDeleted}: {
  id: number; canEdit: boolean; canDelete: boolean; onChanged: () => void; onDeleted: () => void;
}) {
  const detail = useKbArticle(id);
  const [editing, setEditing] = useState(false);
  const [fname, setFname] = useState("");
  const [furl, setFurl] = useState("");

  const setPublished = useMutation({
    mutationFn: (published: boolean) => apiFetch(`/kb/articles/${id}`, {method: "PUT", body: JSON.stringify({published})}),
    onSuccess: () => {detail.refetch(); onChanged();},
  });
  const remove = useMutation({
    mutationFn: () => apiFetch(`/kb/articles/${id}`, {method: "DELETE"}),
    onSuccess: onDeleted,
  });
  const addAttach = useMutation({
    mutationFn: () => apiFetch(`/kb/articles/${id}/attachments`, {method: "POST", body: JSON.stringify({filename: fname, url: furl})}),
    onSuccess: () => {setFname(""); setFurl(""); detail.refetch();},
  });

  if (detail.isLoading) return <LoadingState label="Loading…"/>;
  if (detail.error) return <ErrorState message={detail.error.message}/>;
  const d = detail.data;
  if (!d) return <EmptyState title="Not found" body="This article may have been removed."/>;

  if (editing) {
    return <ArticleEditor id={id} initial={d.article} onSaved={() => {setEditing(false); detail.refetch(); onChanged();}} onCancel={() => setEditing(false)}/>;
  }

  return (
    <Card className="grid content-start gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="m-0 flex-1 text-lg font-semibold">{d.article.title}</h2>
        {!d.article.published && <span className="rounded-full border px-2 py-0.5 text-[0.6875rem] font-semibold text-muted-foreground">draft</span>}
        {canEdit && (
          <>
            <Button type="button" variant="outline" className="h-8 text-xs" onClick={() => setEditing(true)}>Edit</Button>
            <Button type="button" variant="outline" className="h-8 text-xs"
              onClick={() => setPublished.mutate(!d.article.published)}>
              {d.article.published ? "Unpublish" : "Publish"}
            </Button>
          </>
        )}
        {canDelete && (
          <Button type="button" variant="danger" className="h-8 text-xs" onClick={() => remove.mutate()}>Delete</Button>
        )}
      </div>
      {d.article.tags && <p className="m-0 text-xs text-muted-foreground">{d.article.tags}</p>}
      <p className="m-0 whitespace-pre-wrap text-sm">{d.article.body}</p>
      <div className="border-t pt-3">
        <h3 className="m-0 mb-1.5 text-xs font-semibold text-muted-foreground">Attachments</h3>
        {d.attachments.length === 0 && <p className="m-0 text-xs text-muted-foreground">None.</p>}
        <ul className="m-0 grid list-none gap-1 p-0 text-xs">
          {d.attachments.map((at) => (
            <li key={at.id}><a href={at.url} target="_blank" rel="noreferrer" className="text-primary dark:text-highlight">{at.filename}</a></li>
          ))}
        </ul>
        {canEdit && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Input aria-label="Attachment filename" value={fname} onChange={(e) => setFname(e.target.value)} placeholder="filename" className="h-8 flex-1 text-xs"/>
            <Input aria-label="Attachment URL" value={furl} onChange={(e) => setFurl(e.target.value)} placeholder="https://…" className="h-8 flex-1 text-xs"/>
            <Button type="button" className="h-8 text-xs" disabled={!fname || !furl} onClick={() => addAttach.mutate()}>Add</Button>
          </div>
        )}
      </div>
    </Card>
  );
}

function ArticleEditor({id, initial, onSaved, onCancel}: {
  id: number | null;
  initial?: {title: string; body: string; tags: string; published: boolean};
  onSaved: (id: number) => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [body, setBody] = useState(initial?.body ?? "");
  const [tags, setTags] = useState(initial?.tags ?? "");
  const [published, setPublished] = useState(initial?.published ?? false);

  const save = useMutation<{id?: number}>({
    mutationFn: () =>
      id == null
        ? apiFetch<{id: number}>("/kb/articles", {method: "POST", body: JSON.stringify({title, body, tags, published})})
        : apiFetch<{ok: boolean}>(`/kb/articles/${id}`, {method: "PUT", body: JSON.stringify({title, body, tags, published})}).then(() => ({})),
    onSuccess: (r) => onSaved(r.id ?? id!),
  });

  return (
    <Card className="grid content-start gap-2">
      <Input aria-label="Article title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" className="text-sm"/>
      <Input aria-label="Article tags" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="tags, comma separated" className="h-9 text-sm"/>
      <textarea aria-label="Article body" value={body} onChange={(e) => setBody(e.target.value)} rows={12}
        className="w-full resize-y rounded-[0.625rem] border bg-card p-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-highlight/40"/>
      <label className="flex items-center gap-1.5 text-xs">
        <input type="checkbox" checked={published} onChange={(e) => setPublished(e.target.checked)}/>Published
      </label>
      <div className="flex gap-2">
        <Button type="button" disabled={!title.trim() || save.isPending} onClick={() => save.mutate()}>Save</Button>
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
        {save.isError && <span className="text-xs text-danger">{(save.error as Error).message}</span>}
      </div>
    </Card>
  );
}
