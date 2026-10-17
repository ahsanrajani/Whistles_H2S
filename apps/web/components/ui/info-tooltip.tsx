import {Info} from "lucide-react";
import type {ReactNode} from "react";
import {cn} from "@/lib/utils";

/**
 * Hamza, 2026-09-11: "all the tool-tips/one liner explanations should live
 * neatly concealed behind an i icon in the circle, shown upon hover only" --
 * the one place a one-line explanation next to a control/heading should live
 * instead of sitting in the layout as its own line of muted text. CSS-only
 * (DESIGN.md: no animation library) -- :hover and :focus-within both reveal
 * it, so it's reachable by keyboard (Tab to the icon), not just a mouse.
 */
export function InfoTooltip({children, label = "More info"}: {children: ReactNode; label?: string}) {
  return (
    <span className="group/tip relative inline-flex">
      <button
        type="button"
        aria-label={label}
        className="inline-flex size-4 items-center justify-center rounded-full text-muted-foreground/70 outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-highlight/40"
      >
        <Info size={14}/>
      </button>
      <span
        role="tooltip"
        className={cn(
          "pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 w-max max-w-64 -translate-x-1/2 rounded-[0.5rem]",
          "border bg-card px-2.5 py-1.5 text-xs font-normal normal-case tracking-normal text-foreground shadow-lg",
          "opacity-0 transition-opacity duration-150 group-hover/tip:opacity-100 group-focus-within/tip:opacity-100",
        )}
      >
        {children}
      </span>
    </span>
  );
}
