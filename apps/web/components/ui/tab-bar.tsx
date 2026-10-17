"use client";

import {useLayoutEffect, useRef} from "react";
import {cn} from "@/lib/utils";

export type TabItem = {key: string; label: string; badge?: string | number};

/**
 * Pill tab bar with a single indicator that glides to the active tab (shared-layout style, CSS only).
 * The indicator is positioned imperatively from measured offsets, so a tab change animates a
 * transform instead of re-rendering, and it follows resizes. `mode="page"` marks the active tab with
 * aria-current (route-driven tabs); `mode="tab"` uses role=tab / aria-selected.
 */
export function TabBar({items, value, onChange, label, mode = "page", className}: {
  items: TabItem[]; value: string; onChange: (key: string) => void; label: string; mode?: "page" | "tab"; className?: string;
}) {
  const bar = useRef<HTMLElement>(null);
  const pill = useRef<HTMLSpanElement>(null);

  useLayoutEffect(() => {
    const place = () => {
      const active = bar.current?.querySelector<HTMLElement>('[data-active="true"]');
      const p = pill.current;
      if (!active || !p) return;
      p.style.width = `${active.offsetWidth}px`;
      p.style.height = `${active.offsetHeight}px`;
      p.style.transform = `translate(${active.offsetLeft}px, ${active.offsetTop}px)`;
      p.style.opacity = "1";
    };
    place();
    const ro = new ResizeObserver(place);
    if (bar.current) ro.observe(bar.current);
    document.fonts?.ready.then(place).catch(() => {});
    return () => ro.disconnect();
  }, [value, items.length]);

  return (
    <nav ref={bar} aria-label={label} role={mode === "tab" ? "tablist" : undefined} className={cn("gp-tabbar", className)}>
      <span ref={pill} aria-hidden="true" className="gp-tab-pill"/>
      {items.map((t) => {
        const active = t.key === value;
        return (
          <button key={t.key} type="button" data-active={active} onClick={() => onChange(t.key)}
            {...(mode === "tab" ? {role: "tab", "aria-selected": active} : {"aria-current": active ? "page" : undefined})}
            className="gp-tab">
            {t.label}{t.badge !== undefined && <span className="ml-1.5 text-xs opacity-70">{t.badge}</span>}
          </button>
        );
      })}
    </nav>
  );
}
