"use client";

import {Check, ChevronDown} from "lucide-react";
import {Children, Fragment, isValidElement, useEffect, useMemo, useRef, useState, type ChangeEvent, type ReactElement, type ReactNode, type SelectHTMLAttributes} from "react";
import {createPortal} from "react-dom";
import {cn} from "@/lib/utils";

type Opt = {value: string; label: ReactNode; disabled: boolean};

const LAYOUT = /^(flex-|grow|shrink|basis-|w-|min-w-|max-w-|col-span-|self-|order-|m[trblxy]?-)/;
function splitClass(className?: string) {
  const outer: string[] = [], inner: string[] = [];
  for (const token of (className ?? "").split(/\s+/).filter(Boolean)) (LAYOUT.test(token) ? outer : inner).push(token);
  return {outer: outer.join(" "), inner: inner.join(" "), fill: outer.some((t) => t === "w-full" || t.startsWith("flex-"))};
}

/** Flatten <option> children (including fragments and mapped arrays) into a list. */
function parseOptions(children: ReactNode): Opt[] {
  const out: Opt[] = [];
  const walk = (nodes: ReactNode) => Children.forEach(nodes, (child) => {
    if (!isValidElement(child)) return;
    const el = child as ReactElement<{value?: string | number; disabled?: boolean; children?: ReactNode}>;
    if (el.type === Fragment) return walk(el.props.children);
    if (el.type === "option") {
      const label = el.props.children;
      out.push({value: String(el.props.value ?? (typeof label === "string" ? label : "")), label, disabled: !!el.props.disabled});
    }
  });
  walk(children);
  return out;
}

/**
 * A rounded, animated dropdown over a real <select>.
 *
 * The native <select> stays in the DOM (visually hidden, still labelled and focusable) and is the
 * source of truth: keyboard users, forms, autofill and Playwright's selectOption all keep working.
 * The pill + glass menu is the pointer experience. Choosing an option writes the native select and
 * dispatches a genuine `change` event, so every existing `onChange={(e) => ... e.target.value}`
 * handler runs unchanged. The menu uses the shadcn enter animation (fade + zoom-95 + slide) and
 * the chevron rotates in step with it.
 */
export function Select({className, children, value, defaultValue, onChange, disabled, ...rest}: SelectHTMLAttributes<HTMLSelectElement>) {
  const options = useMemo(() => parseOptions(children), [children]);
  const nativeRef = useRef<HTMLSelectElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const [inner, setInner] = useState<string>(String(defaultValue ?? options[0]?.value ?? ""));
  const current = value !== undefined ? String(value) : inner;
  const [open, setOpen] = useState(false);
  const [closing, setClosing] = useState(false);
  const [box, setBox] = useState<{left: number; width: number; top?: number; bottom?: number; maxH: number}>({left: 0, width: 0, maxH: 280});
  const selected = options.find((o) => o.value === current) ?? options[0];
  const cls = splitClass(className);

  function openMenu() {
    // measured here (an event handler), not in an effect, so the menu mounts already positioned
    const r = triggerRef.current!.getBoundingClientRect();
    const below = window.innerHeight - r.bottom - 12, above = r.top - 12;
    const flip = below < 220 && above > below;
    setBox(flip ? {left: r.left, width: r.width, bottom: window.innerHeight - r.top + 8, maxH: Math.min(300, above)}
                : {left: r.left, width: r.width, top: r.bottom + 8, maxH: Math.min(300, below)});
    setOpen(true);
  }

  const close = () => {
    if (!open) return;
    setClosing(true);
    window.setTimeout(() => {setOpen(false); setClosing(false);}, 130);
  };

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!triggerRef.current?.contains(t) && !document.getElementById("gp-select-menu")?.contains(t)) close();
    };
    const key = (e: KeyboardEvent) => {if (e.key === "Escape") close();};
    const move = () => close();
    document.addEventListener("mousedown", away); document.addEventListener("keydown", key);
    window.addEventListener("resize", move); window.addEventListener("scroll", move, true);
    return () => {
      document.removeEventListener("mousedown", away); document.removeEventListener("keydown", key);
      window.removeEventListener("resize", move); window.removeEventListener("scroll", move, true);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function choose(next: string) {
    const el = nativeRef.current;
    if (el && next !== current) {
      // React tracks the value property itself, so go through the prototype setter to fire onChange for real.
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!.call(el, next);
      el.dispatchEvent(new Event("change", {bubbles: true}));
    }
    close();
    triggerRef.current?.focus({preventScroll: true});
  }

  return (
    <div className={cn("gp-select relative inline-block max-w-full shrink-0", cls.outer)} data-open={open && !closing}>
      <select ref={nativeRef} {...rest} disabled={disabled} value={current}
        onChange={(e: ChangeEvent<HTMLSelectElement>) => {setInner(e.target.value); onChange?.(e);}}
        className="peer sr-only">
        {children}
      </select>
      <button type="button" tabIndex={-1} aria-hidden="true" disabled={disabled}
        ref={triggerRef} onClick={() => (open ? close() : openMenu())}
        className={cn(
          "flex h-10 w-full items-center justify-between gap-2 rounded-full border bg-card pl-4 pr-3 text-left text-sm shadow-[inset_0_1px_0_rgba(255,255,255,.45)] hover:bg-muted disabled:opacity-60",
          "peer-focus-visible:ring-2 peer-focus-visible:ring-primary peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-transparent",
          open && !closing && "border-primary/60 shadow-[0_0_0_0.25rem_color-mix(in_oklab,var(--primary)_16%,transparent)]",
          cls.inner)}>
        <span className="truncate">{selected?.label}</span>
        <ChevronDown size={15} className="gp-select-chev shrink-0 text-muted-foreground"/>
      </button>
      {open && typeof document !== "undefined" && createPortal(
        <div id="gp-select-menu" role="listbox"
          style={{position: "fixed", left: box.left, minWidth: box.width, top: box.top, bottom: box.bottom, maxHeight: box.maxH, zIndex: 80}}
          className={cn("gp-menu-in overflow-y-auto rounded-[1.375rem] p-1.5 text-foreground",
            box.bottom !== undefined && "origin-bottom-left",
            closing && "pointer-events-none opacity-0 scale-95 transition-all duration-[130ms] ease-in")}>
          {options.map((o) => (
            <div key={o.value} role="option" aria-selected={o.value === current} data-disabled={o.disabled || undefined}
              className={cn("gp-option", o.disabled && "pointer-events-none opacity-40")}
              onMouseDown={(e) => e.preventDefault()} onClick={() => choose(o.value)}>
              <span className="truncate">{o.label}</span>
              {o.value === current && <Check size={14} className="shrink-0"/>}
            </div>
          ))}
        </div>, document.body)}
    </div>
  );
}
