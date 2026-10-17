"use client";

import {useState} from "react";
import {useSearchParams} from "next/navigation";
import {useTenantRouter} from "@/components/tenant-link";
import {useCareCase} from "@/hooks/use-api";
import {cn} from "@/lib/utils";
import {Card} from "@/components/ui/card";
import {ErrorState, LoadingState} from "@/components/states";
import {CustomerProfile} from "./customer-profile";
import {KnowledgePanel} from "./knowledge-panel";
import {ThreadPane} from "./thread-pane";

const TABS = ["customer", "history", "knowledge"] as const;
type ContextTab = typeof TABS[number];

// Remounted by case ID: drafts and customer edits cannot cross conversations.
export function CaseWorkspace({caseId, onOpenCase}: {
  caseId: number | null; onOpenCase: (id: number) => void;
}) {
  const [draft, setDraft] = useState("");
  const [inserted, setInserted] = useState(false);
  const detail = useCareCase(caseId);
  const params = useSearchParams();
  const router = useTenantRouter();
  const tab = TABS.includes(params.get("context") as ContextTab)
    ? params.get("context") as ContextTab : "customer";

  function selectTab(next: ContextTab) {
    const sp = new URLSearchParams(params.toString());
    if (next === "customer") sp.delete("context"); else sp.set("context", next);
    router.replace(`/care?${sp}`, {scroll: false});
  }

  const history = detail.data?.history ?? [];
  return (
    <div className="grid min-w-0 items-start gap-4 2xl:grid-cols-[minmax(0,1fr)_300px]">
      <ThreadPane caseId={caseId} draft={draft} onDraftChange={setDraft}/>
      <Card aria-label="Case context" className="min-w-0 overflow-hidden p-0">
        <div role="tablist" aria-label="Case context" className="flex border-b">
          {TABS.map((name, index) => (
            <button key={name} type="button" role="tab" id={`context-tab-${name}`}
              aria-selected={tab === name} aria-controls={`context-panel-${name}`}
              tabIndex={tab === name ? 0 : -1}
              onClick={() => selectTab(name)}
              onKeyDown={(event) => {
                let next = index;
                if (event.key === "ArrowRight") next = (index + 1) % TABS.length;
                else if (event.key === "ArrowLeft") next = (index + TABS.length - 1) % TABS.length;
                else if (event.key === "Home") next = 0;
                else if (event.key === "End") next = TABS.length - 1;
                else return;
                event.preventDefault();
                selectTab(TABS[next]);
                document.getElementById(`context-tab-${TABS[next]}`)?.focus();
              }}
              className={cn("min-w-0 flex-1 border-b-2 px-2 py-3 text-xs font-semibold capitalize focus-visible:outline-2 focus-visible:outline-highlight",
                tab === name ? "border-primary text-primary dark:text-highlight" : "border-transparent text-muted-foreground hover:bg-muted")}>
              {name[0].toUpperCase() + name.slice(1)}{name === "history" && detail.data ? ` (${history.length})` : ""}
            </button>
          ))}
        </div>
        {TABS.map((name) => (
          <div key={name} role="tabpanel" id={`context-panel-${name}`}
            aria-labelledby={`context-tab-${name}`} hidden={tab !== name} tabIndex={0}
            className="max-h-[max(520px,calc(100dvh-20rem))] overflow-y-auto overscroll-contain p-4">
            {caseId == null ? <p className="m-0 text-sm text-muted-foreground">Select a case to see its context.</p>
              : detail.isLoading ? <LoadingState label="Loading case context…"/>
              : detail.error ? <ErrorState message={detail.error.message}/>
              : detail.data && <>
                {name === "customer" && <CustomerProfile caseId={caseId}/>}
                {name === "history" && <div className="grid gap-2">
                  <h2 className="m-0 text-sm font-semibold">Previous cases</h2>
                  {history.length === 0 && <p className="text-sm text-muted-foreground">No previous cases available.</p>}
                  {history.map((item) => <button key={item.id} type="button" onClick={() => onOpenCase(item.id)}
                    className="grid gap-1 rounded-[0.625rem] border p-3 text-left text-xs hover:bg-muted">
                    <span className="flex flex-wrap justify-between gap-2 font-semibold">
                      <span>C-{item.id}</span><span>{item.state.replaceAll("_", " ")}</span>
                    </span>
                    <span className="text-muted-foreground">{item.channel ?? "Unknown channel"} · {new Date(item.opened_at).toLocaleDateString()}</span>
                  </button>)}
                </div>}
                {name === "knowledge" && <>
                  <KnowledgePanel enabled={tab === "knowledge"}
                    canInsert={detail.data.case.state !== "closed"}
                    onInsert={(body) => {
                      setDraft((previous) => previous.trim() ? `${previous}\n\n${body}` : body);
                      setInserted(true);
                    }}/>
                  {inserted && <p role="status" className="text-xs text-success">Article inserted into the reply draft.</p>}
                </>}
              </>}
          </div>
        ))}
      </Card>
    </div>
  );
}
