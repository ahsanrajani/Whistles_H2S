"use client";

import {Search} from "lucide-react";
import {useEffect, useRef, useState} from "react";
import {useCareSearch} from "@/hooks/use-api";
import type {CareSearchResult} from "@/lib/types";
import {cn} from "@/lib/utils";

/**
 * F1.10 — global care search. Name / handle / mobile / email / case ref, with
 * autocomplete. Debounced, keyboard navigable. Selecting a result opens the
 * case in the console.
 */
export function CareSearch({onOpenCase}: {onOpenCase: (caseId: number) => void}) {
  const [raw, setRaw] = useState("");
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const [openList, setOpenList] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const id = window.setTimeout(() => setQ(raw.trim()), 180);
    return () => window.clearTimeout(id);
  }, [raw]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpenList(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const results = useCareSearch(q);
  const rows: CareSearchResult[] = results.data?.results ?? [];
  const cursor = Math.min(active, Math.max(0, rows.length - 1));

  function choose(r: CareSearchResult) {
    if (r.case_id != null) onOpenCase(r.case_id);
    setOpenList(false);
    setRaw("");
  }

  return (
    <div ref={boxRef} className="relative w-full max-w-md">
      <div className="flex items-center gap-2 rounded-[0.625rem] border bg-card px-2.5">
        <Search size={15} className="text-muted-foreground"/>
        <input
          aria-label="Search cases"
          value={raw}
          onChange={(e) => {setRaw(e.target.value); setOpenList(true); setActive(0);}}
          onFocus={() => setOpenList(true)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {e.preventDefault(); setActive((a) => Math.min(a + 1, rows.length - 1));}
            else if (e.key === "ArrowUp") {e.preventDefault(); setActive((a) => Math.max(a - 1, 0));}
            else if (e.key === "Enter" && rows[cursor]) {e.preventDefault(); choose(rows[cursor]);}
            else if (e.key === "Escape") setOpenList(false);
          }}
          placeholder="Name, handle, mobile, email, C-123…"
          className="h-9 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        />
      </div>
      {openList && q.length >= 2 && (
        <div role="listbox" aria-label="Search results"
          className="absolute z-40 mt-1 max-h-80 w-full overflow-auto rounded-[0.75rem] border bg-card p-1 shadow-2xl">
          {results.isFetching && rows.length === 0 && (
            <p className="px-3 py-2 text-xs text-muted-foreground">Searching…</p>
          )}
          {!results.isFetching && rows.length === 0 && (
            <p className="px-3 py-2 text-xs text-muted-foreground">No matches.</p>
          )}
          {rows.map((r, i) => (
            <button
              key={`${r.type}-${r.id}`}
              role="option"
              aria-selected={i === cursor}
              onMouseMove={() => setActive(i)}
              onClick={() => choose(r)}
              className={cn(
                "flex w-full items-center gap-2 rounded-[0.5625rem] px-2.5 py-2 text-left text-sm",
                i === cursor ? "bg-primary/10 text-primary dark:text-highlight" : "hover:bg-muted",
              )}>
              <span className="shrink-0 rounded-full border bg-muted px-1.5 py-0.5 text-[0.625rem] font-semibold text-muted-foreground">
                {r.type}
              </span>
              <span className="flex-1 truncate">{r.label}</span>
              {r.detail && <span className="shrink-0 truncate text-[0.6875rem] text-muted-foreground">{r.detail}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
