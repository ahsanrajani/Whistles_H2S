"use client";

import {ShieldCheck, Sparkles} from "lucide-react";
import {useState} from "react";
import {useComplianceCheck} from "@/hooks/use-api";
import {cn} from "@/lib/utils";
import {Button} from "@/components/ui/button";
import {SEVERITY_STYLE} from "./format";

/** Rule-based pre-approval check of a draft. `savedText` is checked on open;
 * "Check this draft" re-checks whatever is in the editor right now. */
export function CompliancePanel({savedText, liveText, editable, onUseRewrite}: {
  savedText: string; liveText: string; editable: boolean; onUseRewrite: (text: string) => void;
}) {
  const [checked, setChecked] = useState<string | null>(null);
  const [wantRewrite, setWantRewrite] = useState(false);
  const text = checked ?? savedText;
  const result = useComplianceCheck(text, wantRewrite);
  const stale = checked !== null && liveText !== checked;
  const data = result.data;

  return (
    <div className="grid gap-2 rounded-[0.625rem] border bg-muted/40 p-3" aria-live="polite">
      <div className="flex flex-wrap items-center gap-2">
        <ShieldCheck size={14} className="text-muted-foreground"/>
        <h3 className="m-0 text-xs font-semibold text-muted-foreground">Compliance check</h3>
        {data && (
          <span className={cn("rounded-full px-2 py-0.5 text-[0.6875rem] font-semibold", SEVERITY_STYLE[data.severity].className)}>
            {SEVERITY_STYLE[data.severity].label} · score {data.score}
          </span>
        )}
        <Button type="button" variant="outline" className="ml-auto h-7 text-[0.6875rem]"
          disabled={!liveText.trim()} onClick={() => {setChecked(liveText); setWantRewrite(false);}}>
          {stale ? "Re-check edited draft" : "Check this draft"}
        </Button>
      </div>

      {!text.trim() && <p className="m-0 text-xs text-muted-foreground">Write the post text, then check it before sending for review.</p>}
      {result.isLoading && text.trim() && <p className="m-0 text-xs text-muted-foreground">Checking…</p>}
      {result.isError && <p className="m-0 text-xs text-danger">{(result.error as Error).message}</p>}
      {stale && <p className="m-0 text-[0.6875rem] text-warning">The text changed since this check.</p>}

      {data && data.findings.length === 0 && (
        <p className="m-0 text-xs text-muted-foreground">
          No rule matched.{data.awareness_context && " Read as customer-awareness copy, so naming a scam channel is allowed; a phone number or link would still be flagged."}
        </p>
      )}
      {data && data.findings.map((f) => (
        <div key={f.key} className="rounded-[0.5rem] border bg-card p-2 text-xs">
          <p className="m-0 font-semibold">{f.label} <span className="font-normal text-muted-foreground">· weight {f.weight}</span></p>
          <p className="m-0 mt-0.5 text-muted-foreground">Matched: {f.matches.map((m) => `“${m}”`).join(", ")}</p>
          <p className="m-0 mt-0.5">{f.guidance}</p>
        </div>
      ))}

      {data && data.related_notices.length > 0 && (
        <div className="text-xs">
          <p className="m-0 mb-0.5 font-semibold text-muted-foreground">Related regulator notices</p>
          <ul className="m-0 grid list-none gap-0.5 p-0">
            {data.related_notices.map((n) => (
              <li key={n.id}>
                {n.url
                  ? <a href={n.url} target="_blank" rel="noreferrer" className="text-primary underline dark:text-highlight">{n.title}</a>
                  : n.title}
                <span className="text-muted-foreground"> · {n.regulator}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {data && data.findings.length > 0 && editable && !data.rewrite && (
        <Button type="button" variant="outline" className="h-7 w-max text-[0.6875rem]" disabled={result.isFetching}
          onClick={() => setWantRewrite(true)}>
          <Sparkles size={12} className="mr-1"/>{result.isFetching ? "Writing…" : "Suggest safer wording"}
        </Button>
      )}
      {data?.rewrite && (
        <div className="rounded-[0.5rem] border border-highlight/40 bg-highlight/5 p-2 text-xs">
          <p className="m-0 whitespace-pre-wrap">{data.rewrite.text}</p>
          <p className="m-0 mt-1 text-[0.6875rem] text-muted-foreground">
            {data.rewrite.mock ? "Offline suggestion (no AI key set)." : "Suggested by Gemini."} Advice only; the score above does not change.
          </p>
          <Button type="button" className="mt-1.5 h-6 text-[0.6875rem]" onClick={() => onUseRewrite(data.rewrite!.text)}>Use this wording</Button>
        </div>
      )}

      {data && (
        <details className="text-[0.6875rem] text-muted-foreground">
          <summary className="cursor-pointer">How this is scored</summary>
          <p className="m-0 mt-1">Each rule has a fixed weight; the score is the sum of the rules that match. No model scores anything.</p>
          <p className="m-0 mt-1">Bands: {data.policy.bands.map((b) => `${b.label} ≥ ${b.min_score}`).join(" · ")}</p>
          <ul className="m-0 mt-1 grid list-none gap-0.5 p-0">
            {data.policy.rules.map((r) => <li key={r.key}>{r.label} · {r.weight}</li>)}
          </ul>
        </details>
      )}
    </div>
  );
}
