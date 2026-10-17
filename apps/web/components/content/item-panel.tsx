"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {ImagePlus, Sparkles, X} from "lucide-react";
import {useState} from "react";
import {useContentItem, useMe} from "@/hooks/use-api";
import {apiFetch} from "@/lib/api";
import {can} from "@/lib/permissions";
import type {ContentMediaUpload, ContentState, ContentSuggestion} from "@/lib/types";
import {cn} from "@/lib/utils";
import {ChannelBadge} from "@/components/care/primitives";
import {EmptyState, ErrorState, LoadingState} from "@/components/states";
import {Button} from "@/components/ui/button";
import {Input} from "@/components/ui/input";
import {Select} from "@/components/ui/select";
import {CompliancePanel} from "./compliance-panel";
import {CHANNELS, MediaThumb, STATE_COLOR} from "./shared";

// ------------------------------------------------------------- ItemPanel
const NEXT_ACTIONS: Record<ContentState, {action: string; label: string}[]> = {
  draft: [{action: "submit", label: "Submit for review"}],
  in_review: [{action: "retract", label: "Retract to draft"}],
  rejected: [{action: "revise", label: "Revise (back to draft)"}, {action: "resubmit", label: "Resubmit"}],
  approved: [{action: "schedule", label: "Schedule"}, {action: "unapprove", label: "Send back to draft"}],
  scheduled: [{action: "publish", label: "Publish now"}, {action: "unschedule", label: "Unschedule"}],
  published: [],
};
const EDITABLE_STATES: ContentState[] = ["draft", "in_review", "rejected"];

export function ItemPanel({id, onClose}: {id: number | null; onClose: () => void}) {
  const query = useQueryClient();
  const me = useMe();
  const canEdit = can(me.data?.user.perms, "templates:edit");
  const canApprove = can(me.data?.user.perms, "templates:approve");
  const detail = useContentItem(id);

  const [title, setTitle] = useState("");
  const [body, setBody] = useState<string | null>(null);
  const [channel, setChannel] = useState(CHANNELS[0]);
  const [media, setMedia] = useState<string[] | null>(null);
  const [scheduledFor, setScheduledFor] = useState("");
  const [note, setNote] = useState("");

  const item = detail.data?.item;
  const bodyText = body ?? item?.body ?? "";
  const editable = id === null || (item ? EDITABLE_STATES.includes(item.state) : false);
  const mediaUrls = media ?? item?.media ?? [];

  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return apiFetch<ContentMediaUpload>("/content/media", {method: "POST", body: form});
    },
    onSuccess: (up) => setMedia([...mediaUrls, up.url]),
  });
  const [assistTopic, setAssistTopic] = useState("");
  const assist = useMutation({
    mutationFn: () => apiFetch<ContentSuggestion>("/content/assist", {method: "POST", body: JSON.stringify({
      topic: assistTopic, draft: bodyText, channel: channel || item?.channel,
    })}),
  });

  const refresh = () => {
    query.invalidateQueries({queryKey: ["content"]});
    if (id != null) query.invalidateQueries({queryKey: ["content", "item", id]});
  };

  const save = useMutation({
    mutationFn: () => {
      const payload = {
        title: title || item?.title, body: bodyText,
        channel: channel || item?.channel, media: mediaUrls,
        scheduled_for: scheduledFor ? new Date(scheduledFor).toISOString() : item?.scheduled_for,
      };
      return id == null
        ? apiFetch<{id: number}>("/content", {method: "POST", body: JSON.stringify(payload)})
        : apiFetch(`/content/${id}`, {method: "PATCH", body: JSON.stringify(payload)});
    },
    onSuccess: () => {refresh(); onClose();},
  });
  const act = useMutation({
    mutationFn: (action: string) => apiFetch(`/content/${id}/transition`, {method: "POST", body: JSON.stringify({action})}),
    onSuccess: refresh,
  });
  const review = useMutation({
    mutationFn: (decision: "approve" | "reject") => apiFetch(`/content/${id}/review`, {method: "POST", body: JSON.stringify({decision, note: note || undefined})}),
    onSuccess: () => {setNote(""); refresh();},
  });
  const remove = useMutation({
    mutationFn: () => apiFetch(`/content/${id}`, {method: "DELETE"}),
    onSuccess: () => {refresh(); onClose();},
  });

  const busy = save.isPending || act.isPending || review.isPending || remove.isPending;
  const nextActions = item ? NEXT_ACTIONS[item.state] : [];

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-end bg-black/40" onClick={onClose}>
      <div className="gp-sheet-right-in h-full w-full max-w-md overflow-y-auto p-5" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="m-0 text-lg font-semibold">{id == null ? "New post" : `Post #${id}`}</h2>
          <button type="button" onClick={onClose} className="text-sm text-muted-foreground hover:text-foreground">Close</button>
        </div>

        {id != null && detail.isLoading && <LoadingState label="Loading…"/>}
        {id != null && detail.error && <ErrorState message={detail.error.message}/>}

        {(id == null || item) && (
          <div className="grid gap-3">
            {item && (
              <span className={cn("w-max rounded-full px-2 py-0.5 text-[0.6875rem] font-semibold", STATE_COLOR[item.state])}>
                {item.state.replaceAll("_", " ")}
              </span>
            )}
            {!editable && <p className="m-0 text-xs text-warning">This item can no longer be edited in its current state.</p>}

            <Input aria-label="Title" placeholder="Title" disabled={!editable}
              defaultValue={item?.title} onChange={(e) => setTitle(e.target.value)} className="text-sm"/>
            <textarea aria-label="Body" placeholder="Post text…" disabled={!editable} rows={5}
              value={bodyText} onChange={(e) => setBody(e.target.value)}
              className="w-full resize-y rounded-[0.625rem] border bg-card p-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-highlight/40 disabled:opacity-60"/>

            {editable && (
              <div className="grid gap-1.5 rounded-[0.625rem] border bg-muted/40 p-2.5">
                <div className="flex items-center gap-1.5">
                  <Sparkles size={12} className="text-muted-foreground"/>
                  <Input aria-label="What's this post about" placeholder="What's this post about? (optional if you already have a draft)"
                    value={assistTopic} onChange={(e) => setAssistTopic(e.target.value)} className="h-8 flex-1 text-xs"/>
                  <Button type="button" className="h-8 shrink-0 text-xs" disabled={assist.isPending || (!assistTopic && !bodyText)}
                    onClick={() => assist.mutate()}>
                    {assist.isPending ? "Thinking…" : "AI caption + hashtags"}
                  </Button>
                </div>
                {assist.isError && <p className="m-0 text-xs text-danger">{(assist.error as Error).message}</p>}
                {assist.data && (
                  <div className="rounded-[0.5rem] border border-highlight/40 bg-highlight/5 p-2 text-xs">
                    <p className="m-0 whitespace-pre-wrap">{assist.data.caption}{assist.data.mock && " · demo"}</p>
                    {assist.data.hashtags.length > 0 && (
                      <p className="m-0 mt-1 text-muted-foreground">{assist.data.hashtags.join(" ")}</p>
                    )}
                    <Button type="button" className="mt-1.5 h-6 text-[0.6875rem]" onClick={() => {
                      const s = assist.data as ContentSuggestion;
                      setBody([s.caption, s.hashtags.join(" ")].filter(Boolean).join("\n\n"));
                    }}>
                      Use this
                    </Button>
                  </div>
                )}
              </div>
            )}

            <div className="flex gap-2">
              <Select aria-label="Channel" disabled={!editable} defaultValue={item?.channel ?? channel}
                onChange={(e) => setChannel(e.target.value)} className="h-9 flex-1 text-sm">
                {CHANNELS.map((c) => <option key={c} value={c}>{c}</option>)}
              </Select>
              <input type="datetime-local" aria-label="Scheduled time" disabled={!editable}
                defaultValue={item?.scheduled_for?.slice(0, 16)}
                onChange={(e) => setScheduledFor(e.target.value)}
                className="h-9 flex-1 rounded-[0.625rem] border bg-card px-2 text-xs disabled:opacity-60"/>
            </div>

            <div className="grid gap-1.5">
              <p className="m-0 text-xs font-semibold text-muted-foreground">Media</p>
              {mediaUrls.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {mediaUrls.map((url) => (
                    <div key={url} className="relative size-16 overflow-hidden rounded-[0.5rem] border bg-muted">
                      <MediaThumb url={url} className="h-full w-full object-cover"/>
                      {editable && (
                        <button type="button" aria-label="Remove media" onClick={() => setMedia(mediaUrls.filter((u) => u !== url))}
                          className="absolute right-0.5 top-0.5 rounded-full bg-black/60 p-0.5 text-white hover:bg-black/80">
                          <X size={10}/>
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {editable && (
                <label className="flex h-9 w-max cursor-pointer items-center gap-1.5 rounded-[0.625rem] border bg-card px-3 text-xs font-semibold hover:bg-muted">
                  <ImagePlus size={14}/>{upload.isPending ? "Uploading…" : "Add picture or video"}
                  <input type="file" accept="image/jpeg,image/png,image/gif,image/webp,video/mp4,video/quicktime" className="hidden"
                    onChange={(e) => {const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = "";}}/>
                </label>
              )}
              {upload.isError && <p className="m-0 text-xs text-danger">{(upload.error as Error).message}</p>}
            </div>

            <div className="rounded-[0.625rem] border bg-muted/40 p-3">
              <p className="mb-1 text-[0.625rem] font-bold uppercase tracking-[.14em] text-muted-foreground">Preview · {channel || item?.channel}</p>
              <ChannelBadge channel={channel || item?.channel || "meta"} className="mb-1.5"/>
              {mediaUrls.length > 0 && (
                <div className="mb-1.5 aspect-video w-full overflow-hidden rounded-[0.5rem] bg-muted">
                  <MediaThumb url={mediaUrls[0]} className="h-full w-full object-cover"/>
                </div>
              )}
              <p className="m-0 whitespace-pre-wrap text-sm">{bodyText || "…"}</p>
            </div>

            <CompliancePanel savedText={item?.body ?? ""} liveText={bodyText} editable={editable} onUseRewrite={setBody}/>

            {canEdit && (
              <Button type="button" disabled={busy || (item != null && !editable)} onClick={() => save.mutate()}>
                {id == null ? "Create draft" : "Save changes"}
              </Button>
            )}

            {item && nextActions.length > 0 && canEdit && (
              <div className="flex flex-wrap gap-1.5 border-t pt-3">
                {nextActions.map((a) => (
                  <Button key={a.action} type="button" variant="outline" className="h-8 text-xs" disabled={busy}
                    onClick={() => act.mutate(a.action)}>{a.label}</Button>
                ))}
              </div>
            )}

            {item?.state === "in_review" && canApprove && (
              <div className="grid gap-1.5 border-t pt-3">
                <p className="m-0 text-xs font-semibold text-muted-foreground">Review decision</p>
                <Input aria-label="Review note" placeholder="Note (for a reject)" value={note} onChange={(e) => setNote(e.target.value)} className="h-8 text-xs"/>
                <div className="flex gap-1.5">
                  <Button type="button" className="h-8 text-xs" disabled={busy} onClick={() => review.mutate("approve")}>Approve</Button>
                  <Button type="button" variant="danger" className="h-8 text-xs" disabled={busy} onClick={() => review.mutate("reject")}>Reject</Button>
                </div>
              </div>
            )}

            {item && ["draft", "rejected"].includes(item.state) && can(me.data?.user.perms, "templates:delete") && (
              <Button type="button" variant="danger" className="h-8 w-max text-xs" disabled={busy} onClick={() => remove.mutate()}>Delete</Button>
            )}

            {(save.error || act.error || review.error || remove.error) && (
              <p className="m-0 text-xs text-danger">
                {((save.error || act.error || review.error || remove.error) as Error).message}
              </p>
            )}

            {detail.data && detail.data.history.length > 0 && (
              <div className="border-t pt-3">
                <h3 className="m-0 mb-1.5 text-xs font-semibold text-muted-foreground">Approval trail</h3>
                <ul className="m-0 grid list-none gap-1 p-0 text-xs">
                  {detail.data.history.map((h, i) => (
                    <li key={i} className="text-muted-foreground">
                      · {h.kind.replaceAll("_", " ")}{h.note ? ` — “${h.note}”` : ""} · {new Date(h.at).toLocaleString()}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
        {id != null && !detail.isLoading && !item && !detail.error && (
          <EmptyState title="Not found" body="This post may have been removed."/>
        )}
      </div>
    </div>
  );
}
