"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {useState} from "react";
import {CalendarClock, RefreshCw, Sparkles, X} from "lucide-react";
import {apiFetch} from "@/lib/api";
import {applyMacro, previewMacro, useCareScheduled, useCareSuggestReply, useKbArticles, useMacros} from "@/hooks/use-api";
import type {CareSuggestion, KbArticleDetail, Macro, MacroApplyResult} from "@/lib/types";
import {cn} from "@/lib/utils";
import {Button} from "@/components/ui/button";
import {Input} from "@/components/ui/input";
import {Select} from "@/components/ui/select";
import {MacroChips, MacroPicker, SlashList, useSlashMenu, type AppliedMacro} from "./macro-picker";
import {SendFeedback, SendSplitButton, type SendOutcome} from "./send-menu";

/**
 * F1.4 reply composer. Channel selector (public comment vs DM), page selector
 * (defaults to the originating platform), macro picker + /shortcut, KB article
 * attach, and a Send split button (pinned quick macros, hold-for-approval,
 * schedule). File attach needs the write-transport
 * upload step and is intentionally out of scope here.
 */
// A case whose channel is already a DM inbox (Messenger / Instagram Direct)
// has no public comment to reply to at all -- there's nothing for a
// "Public reply" choice to mean. Hamza: "why is there a public response/
// private reply option [on a DM case]?"
const DM_ONLY_CHANNELS = new Set(["messenger", "instagram_dm"]);

export function ReplyComposer({
  caseId, platform, channel, targetRef, pages, onDone, value, onValueChange,
}: {
  caseId: number;
  platform: string;
  channel?: string | null;
  targetRef?: string | null;
  pages?: string[];
  onDone?: () => void;
  value?: string;
  onValueChange?: (text: string) => void;
}) {
  const query = useQueryClient();
  const dmOnly = !!channel && DM_ONLY_CHANNELS.has(channel);
  const [localText, setLocalText] = useState("");
  const text = value ?? localText;
  const setText = onValueChange ?? setLocalText;
  const [mode, setMode] = useState<"public" | "dm">(dmOnly ? "dm" : "public");
  const [page, setPage] = useState(platform);
  const [kbQ, setKbQ] = useState("");
  const macroList = useMacros();
  const allMacros = macroList.data?.macros ?? [];
  const quickMacros = allMacros.filter((m) => m.is_quick);
  const [applied, setApplied] = useState<AppliedMacro | null>(null);
  const [showSchedule, setShowSchedule] = useState(false);
  const kb = useKbArticles(kbQ);

  const [when, setWhen] = useState("");
  const scheduled = useCareScheduled(caseId);
  const cancelScheduled = useMutation({
    mutationFn: (aid: number) =>
      apiFetch(`/care/cases/${caseId}/scheduled/${aid}/cancel`, {method: "POST"}),
    onSuccess: () => scheduled.refetch(),
  });
  const schedule = useMutation({
    mutationFn: () =>
      apiFetch(`/care/cases/${caseId}/schedule`, {
        method: "POST",
        body: JSON.stringify({
          text, platform: page, at: new Date(when).toISOString(),
          target_ref: targetRef ?? undefined,
        }),
      }),
    onSuccess: () => {
      setText("");
      setApplied(null);
      setWhen("");
      setShowSchedule(false);
      scheduled.refetch();
      query.invalidateQueries({queryKey: ["care", "case", caseId]});
    },
  });

  const [manualSuggestion, setManualSuggestion] = useState<CareSuggestion | null>(null);
  const [dismissed, setDismissed] = useState(false);
  // Loads the moment this case is opened (key={case.id} on the parent
  // remounts this per case) -- server-cached, see hooks/use-api.ts. A manual
  // AI-assist click (any kind) or a dismiss takes over the display without
  // needing an effect to sync it (Next 16 lint forbids setState-in-effect).
  const autoSuggest = useCareSuggestReply(caseId, !dismissed && manualSuggestion === null);
  const suggestion = manualSuggestion ?? (dismissed ? null : autoSuggest.data ?? null);

  const assist = useMutation({
    mutationFn: (opts: {kind: "reply" | "grammar" | "tone" | "brand_voice"; force?: boolean}) =>
      apiFetch<CareSuggestion>(
        `/care/cases/${caseId}/suggest`,
        {method: "POST", body: JSON.stringify({kind: opts.kind, draft: text || undefined, force: opts.force})},
      ),
    onSuccess: (data) => setManualSuggestion(data),
  });

  const postReply = (body: string, hold: boolean) =>
    apiFetch<{ok: boolean; state: string}>(`/care/cases/${caseId}/reply`, {
      method: "POST",
      body: JSON.stringify({
        text: body,
        platform: page,
        channel_mode: mode,
        // Root-caused 2026-09-11 (Chase C-116): this used to fabricate
        // `dm:${caseId}` whenever targetRef was null (always, for the
        // normal Care thread -- it's only ever passed a real value from a
        // reply-to-one-specific-comment flow). That fake id permanently
        // shadowed care.py reply()'s own correct fallback (the customer's
        // real Messenger/Instagram PSID from the case's customer row),
        // which is the whole reason every DM reply attempt failed against
        // the real Send API -- Meta correctly rejected a made-up
        // recipient id. Passing the real targetRef through unmodified (or
        // nothing) lets that backend fallback actually do its job.
        target_ref: targetRef ?? undefined,
        hold,
      }),
    });
  // A macro's actions run once the reply request is accepted, whatever the platform
  // then does with it: a refused send (e.g. Meta's 24-hour window) counts as sent, so
  // the draft is cleared and the macro completes. A failed action never undoes the send.
  const runMacro = (id: number, indexes?: number[]): Promise<MacroApplyResult> =>
    applyMacro(caseId, id, indexes).catch((e: Error) => ({ok: false, results: [{index: -1, type: "macro", ok: false, error: e.message}]}));

  const send = useMutation<SendOutcome, Error, {hold: boolean; quick?: Macro}>({
    mutationFn: async ({hold, quick}) => {
      if (quick) {
        // One-click quick macro: send its text (the draft is left alone) and run its actions.
        const p = await previewMacro(caseId, quick.id);
        const sent = p.text.trim() ? await postReply(p.text, false) : null;
        const ran = quick.actions.length ? await runMacro(quick.id) : null;
        return {state: sent?.state ?? null, ran, label: quick.name};
      }
      const res = await postReply(text, hold);
      const indexes = applied?.actions.map((_, i) => i).filter((i) => !applied.off.includes(i)) ?? [];
      const ran = applied && indexes.length ? await runMacro(applied.macro.id, indexes) : null;
      return {state: res.state, ran, label: applied?.macro.name};
    },
    onSuccess: (out, vars) => {
      if (!vars.quick) {
        setText("");
        setApplied(null);
      }
      query.invalidateQueries({queryKey: ["care", "case", caseId]});
      query.invalidateQueries({queryKey: ["care", "cases"]});
      onDone?.();
    },
  });

  // Picking a macro drops its rendered text into the draft (replacing an empty
  // draft or a half-typed "/shortcut", otherwise appended) and lists its actions.
  const pick = useMutation({
    mutationFn: (m: Macro) => previewMacro(caseId, m.id),
    onSuccess: (p, m) => {
      const draft = /^\/[a-z0-9_-]*$/i.test(text.trim()) ? "" : text;
      if (p.text) setText(draft.trim() ? `${draft}\n\n${p.text}` : p.text);
      else if (!draft.trim()) setText("");
      setApplied({macro: m, actions: p.actions, off: []});
    },
  });
  const slash = useSlashMenu(text, allMacros, (m) => pick.mutate(m));

  function append(chunk: string) {
    setText(text.trim() ? `${text}\n\n${chunk}` : chunk);
  }

  const attachArticle = useMutation({
    mutationFn: (id: number) => query.fetchQuery({
      queryKey: ["kb", "article", id],
      queryFn: () => apiFetch<KbArticleDetail>(`/kb/articles/${id}`),
    }),
    onSuccess: (detail) => append(detail.article.body),
  });

  const pageOptions = [...new Set([platform, ...(pages ?? [])].filter(Boolean))];
  // Suggested text stays separate from the draft; Tab still accepts it.
  const showGhost = suggestion?.kind === "reply" && !manualSuggestion && !text.trim();

  return (
    <div className="grid gap-2 border-t pt-3">
      <div className="flex flex-wrap items-center gap-2">
        {dmOnly ? (
          <span className="rounded-[0.5625rem] border bg-card px-2.5 py-1 text-xs font-semibold text-muted-foreground">
            Direct message
          </span>
        ) : (
          <div role="tablist" aria-label="Reply channel" className="flex rounded-[0.5625rem] border bg-card p-0.5">
            {(["public", "dm"] as const).map((m) => (
              <button
                key={m}
                type="button"
                role="tab"
                aria-selected={mode === m}
                onClick={() => setMode(m)}
                className={cn(
                  "rounded-[0.4375rem] px-2.5 py-1 text-xs font-semibold",
                  mode === m ? "bg-primary/10 text-primary dark:text-highlight" : "text-muted-foreground",
                )}>
                {m === "public" ? "Public reply" : "Direct message"}
              </button>
            ))}
          </div>
        )}
        {pageOptions.length > 1 && (
          <Select aria-label="Page" className="h-8 max-w-40 text-xs" value={page}
            onChange={(e) => setPage(e.target.value)}>
            {pageOptions.map((p) => <option key={p} value={p}>{p}</option>)}
          </Select>
        )}
        <MacroPicker macros={allMacros} loading={macroList.isLoading} busy={pick.isPending} onPick={(m) => pick.mutate(m)}/>
        {pick.isError && <span role="alert" className="text-xs text-danger">Couldn&apos;t load macro — {pick.error.message}</span>}
      </div>

      <div className="grid">
        <textarea
          aria-label="Reply text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (slash.onKeyDown(e)) return;
            if (e.key === "Tab" && showGhost) {
              e.preventDefault();
              setText(suggestion!.suggestion);
              return;
            }
            // Hamza: "enter key should be send, shift+enter for new line."
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              if (text.trim() && !send.isPending) send.mutate({hold: false});
            }
          }}
          rows={3}
          placeholder={mode === "dm" ? "Write a direct message…" : "Write a public reply…"}
          className="col-start-1 row-start-1 w-full resize-y rounded-[0.625rem] border bg-card p-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-highlight/40"
        />
      </div>
      <SlashList matches={slash.matches} index={slash.index} onPick={slash.onPick}/>
      {applied && (
        <MacroChips applied={applied} onClear={() => setApplied(null)}
          onToggle={(i) => setApplied({...applied, off: applied.off.includes(i) ? applied.off.filter((x) => x !== i) : [...applied.off, i]})}/>
      )}
      {showGhost && (
        <div className="grid gap-2 rounded-[0.625rem] border border-primary/20 bg-primary/5 p-2.5">
        <p tabIndex={0} aria-label="Suggested reply preview"
          className="m-0 max-h-28 overflow-y-auto whitespace-pre-wrap text-sm [overflow-wrap:anywhere]">{suggestion.suggestion}</p>
        <p className="m-0 flex flex-wrap items-center gap-1.5 text-[0.6875rem] text-muted-foreground">
          <Sparkles size={11}/>AI suggested reply{suggestion.mock ? " · demo" : ""}{suggestion.cached ? " · cached" : ""}
          {" — press "}<kbd className="rounded border bg-muted px-1 py-0.5 text-[0.625rem] font-semibold">Tab</kbd>{" to use it"}
          <button type="button" aria-label="Regenerate suggestion" disabled={assist.isPending}
            onClick={() => assist.mutate({kind: "reply", force: true})}
            className="ml-auto text-muted-foreground hover:text-foreground disabled:opacity-50">
            <RefreshCw size={12}/>
          </button>
        </p>
        <button type="button" onClick={() => setText(suggestion.suggestion)}
          className="w-max text-xs font-semibold text-primary hover:underline">Use suggestion</button>
        </div>
      )}

      <div className="grid gap-1.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="inline-flex items-center gap-1 text-[0.6875rem] font-semibold text-muted-foreground">
            <Sparkles size={12}/>AI assist
          </span>
          {(["reply", "grammar", "tone", "brand_voice"] as const).map((k) => (
            <button key={k} type="button" disabled={assist.isPending}
              onClick={() => {setDismissed(false); assist.mutate({kind: k});}}
              className="rounded-[0.4375rem] border bg-card px-2 py-0.5 text-[0.6875rem] font-semibold capitalize hover:bg-muted disabled:opacity-50">
              {k.replace("_", " ")}
            </button>
          ))}
        </div>
        {!suggestion && autoSuggest.isLoading && (
          <p className="m-0 flex items-center gap-1.5 text-[0.6875rem] text-muted-foreground">
            <RefreshCw size={11} className="animate-spin"/>Loading a suggested reply…
          </p>
        )}
        {!suggestion && autoSuggest.isError && (
          <p className="m-0 text-[0.6875rem] text-danger">
            Couldn&apos;t load a suggestion — {(autoSuggest.error as Error).message}
          </p>
        )}
        {suggestion && !showGhost && (
          <div className="grid gap-1.5 rounded-[0.625rem] border-l-2 border-l-highlight bg-muted/40 py-2 pl-3 pr-2.5">
            <div className="flex items-center justify-between gap-2">
              <span className="inline-flex items-center gap-1 text-[0.625rem] font-bold uppercase tracking-[.14em] text-muted-foreground">
                <Sparkles size={11} className="text-highlight"/>
                {suggestion.kind.replace("_", " ")}{suggestion.mock ? " · demo" : ""}{suggestion.cached ? " · cached" : ""}
              </span>
              <span className="flex items-center gap-2.5">
                {suggestion.kind === "reply" && (
                  <button type="button" aria-label="Regenerate suggestion" disabled={assist.isPending}
                    onClick={() => assist.mutate({kind: "reply", force: true})}
                    className="text-muted-foreground hover:text-foreground disabled:opacity-50">
                    <RefreshCw size={12}/>
                  </button>
                )}
                <button type="button" aria-label="Dismiss suggestion" onClick={() => {setManualSuggestion(null); setDismissed(true);}}
                  className="text-muted-foreground hover:text-foreground">
                  <X size={12}/>
                </button>
              </span>
            </div>
            <p tabIndex={0} className="m-0 max-h-36 overflow-y-auto whitespace-pre-wrap text-sm">{suggestion.suggestion}</p>
            <Button type="button" className="h-7 w-max text-xs"
              onClick={() => {
                setText(suggestion.suggestion);
                setManualSuggestion(null);
                setDismissed(true);
              }}>
              Insert into reply
            </Button>
          </div>
        )}
      </div>

      <details className="text-xs">
        <summary className="cursor-pointer text-muted-foreground">Attach a KB article</summary>
        <div className="mt-2 grid gap-1.5">
          <Input aria-label="Search knowledge base" value={kbQ} placeholder="Search…"
            onChange={(e) => setKbQ(e.target.value)} className="h-8 text-xs"/>
          {kb.isLoading && <p role="status">Loading articles?</p>}
          {kb.error && <p role="alert" className="text-danger">{kb.error.message}</p>}
          {kb.data?.articles.length === 0 && <p>No published articles match your search.</p>}
          {attachArticle.error && <p role="alert" className="text-danger">Could not attach article: {attachArticle.error.message}</p>}
          <div className="grid max-h-32 gap-1 overflow-auto">
            {(kb.data?.articles ?? []).slice(0, 8).map((a) => (
              <button key={a.id} type="button" disabled={attachArticle.isPending} onClick={() => attachArticle.mutate(a.id)}
                className="rounded-[0.5rem] px-2 py-1 text-left hover:bg-muted">
                {a.title}
              </button>
            ))}
          </div>
        </div>
      </details>

      {(scheduled.data?.scheduled.length ?? 0) > 0 && (
        <div className="grid gap-1 rounded-[0.625rem] border bg-muted/40 p-2 text-xs">
          <span className="font-semibold text-muted-foreground">Scheduled</span>
          {scheduled.data!.scheduled.map((m) => (
            <div key={m.outbound_action_id} className="flex items-center gap-2">
              <CalendarClock size={12} className="shrink-0 text-muted-foreground"/>
              <span className="truncate">{m.text}</span>
              <span className="numeric ml-auto shrink-0 text-muted-foreground">
                {m.scheduled_for ? new Date(m.scheduled_for).toLocaleString() : "—"}
              </span>
              <button type="button" aria-label="Cancel scheduled message"
                onClick={() => cancelScheduled.mutate(m.outbound_action_id)}
                className="shrink-0 rounded p-0.5 text-muted-foreground hover:text-danger">
                <X size={12}/>
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="sticky bottom-0 z-10 flex flex-wrap items-center gap-2 border-t bg-card py-2">
        <SendSplitButton canSend={!!text.trim()} pending={send.isPending} quick={quickMacros}
          onSend={() => send.mutate({hold: false})} onHold={() => send.mutate({hold: true})}
          onSchedule={() => setShowSchedule(true)}
          onQuick={(m) => send.mutate({hold: false, quick: m})}
          onQuickEdit={(m) => pick.mutate(m)}/>
        {showSchedule && (
          <span className="gp-rise flex items-center gap-1.5">
            <input type="datetime-local" aria-label="Schedule time" value={when} autoFocus
              onChange={(e) => setWhen(e.target.value)}
              className="h-9 rounded-[0.625rem] border bg-card px-2 text-xs"/>
            <Button type="button" variant="outline" disabled={!text.trim() || !when || schedule.isPending}
              onClick={() => schedule.mutate()}>
              Schedule
            </Button>
            <button type="button" aria-label="Cancel scheduling" onClick={() => {setShowSchedule(false); setWhen("");}}
              className="text-muted-foreground hover:text-foreground"><X size={14}/></button>
          </span>
        )}
        {send.isPending && <span role="status" className="text-xs text-muted-foreground">Sending…</span>}
        {send.isError && <span role="alert" className="text-xs text-danger">Couldn&apos;t send the reply. Your draft was kept; try again.</span>}
        {send.isSuccess && <SendFeedback outcome={send.data}/>}
        {schedule.error && <span role="alert" className="text-xs text-danger">{schedule.error.message}</span>}
        {schedule.isSuccess && <span role="status" className="text-xs text-success">Scheduled.</span>}
      </div>
    </div>
  );
}
