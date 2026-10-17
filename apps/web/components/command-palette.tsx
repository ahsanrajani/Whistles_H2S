"use client";
import * as Dialog from "@radix-ui/react-dialog";
import {Command, LogOut, MoonStar, Search} from "lucide-react";
import {useTheme} from "next-themes";
import {useRouter} from "next/navigation";
import {useMemo, useState, type ComponentType} from "react";
import {useCareSearch} from "@/hooks/use-api";
import {cn} from "@/lib/utils";

type IconType = ComponentType<{size?: number | string; className?: string}>;
type NavItem = {href: string; label: string; icon: IconType};
type WorkspaceItem = {id: number; name: string; market: string};
type FilterItem = {href: string; label: string};

type PaletteAction =
  | {kind: "route"; id: string; label: string; hint?: string; icon?: IconType; href: string}
  | {kind: "workspace"; id: string; label: string; hint?: string; workspaceId: number}
  | {kind: "command"; id: string; label: string; hint?: string; icon?: IconType; run: () => void};

type BodyProps = {
  close: () => void;
  nav: NavItem[];
  workspaces: WorkspaceItem[];
  canSwitch: boolean;
  recentFilters: FilterItem[];
  careSearchBase: string | null;
  onSwitchWorkspace: (id: number) => void;
  onSignOut: () => void;
};

function PaletteBody({close, nav, workspaces, canSwitch, recentFilters, careSearchBase, onSwitchWorkspace, onSignOut}: BodyProps) {
  const router = useRouter();
  const {resolvedTheme, setTheme} = useTheme();
  const [queryText, setQueryText] = useState("");
  const [active, setActive] = useState(0);
  const [seenQuery, setSeenQuery] = useState("");

  const careHits = useCareSearch(queryText, careSearchBase != null);

  const actions = useMemo<PaletteAction[]>(() => {
    const out: PaletteAction[] = nav.map((item) => ({
      kind: "route", id: `nav:${item.href}`, label: item.label, hint: "Page", icon: item.icon, href: item.href,
    }));
    if (canSwitch) {
      for (const workspace of workspaces) {
        out.push({kind: "workspace", id: `ws:${workspace.id}`, label: workspace.name, hint: `Workspace · ${workspace.market}`, workspaceId: workspace.id});
      }
    }
    for (const filter of recentFilters) {
      out.push({kind: "route", id: `filter:${filter.href}`, label: filter.label, hint: "Recent filter", href: filter.href});
    }
    out.push({
      kind: "command", id: "cmd:theme", label: `Switch to ${resolvedTheme === "dark" ? "light" : "dark"} theme`,
      hint: "Command", icon: MoonStar, run: () => setTheme(resolvedTheme === "dark" ? "light" : "dark"),
    });
    out.push({kind: "command", id: "cmd:signout", label: "Sign out", hint: "Command", icon: LogOut, run: onSignOut});
    return out;
  }, [nav, workspaces, canSwitch, recentFilters, resolvedTheme, setTheme, onSignOut]);

  const careActions = useMemo<PaletteAction[]>(() => {
    if (!careSearchBase || !careHits.data) return [];
    return careHits.data.results
      .filter((r) => r.case_id != null)
      .slice(0, 6)
      .map((r) => ({
        kind: "route" as const, id: `care:${r.type}:${r.id}`, label: r.label,
        hint: `Case · ${r.type}`, href: `${careSearchBase}/care?case=${r.case_id}`,
      }));
  }, [careSearchBase, careHits.data]);

  const filtered = useMemo(() => {
    const needle = queryText.trim().toLowerCase();
    if (!needle) return actions;
    const matched = actions.filter((action) => `${action.label} ${action.hint ?? ""}`.toLowerCase().includes(needle));
    return [...careActions, ...matched];
  }, [actions, careActions, queryText]);

  // Reset the cursor when the query changes (render-phase state adjustment).
  if (queryText !== seenQuery) {setSeenQuery(queryText); setActive(0);}
  const cursor = Math.min(active, Math.max(0, filtered.length - 1));

  function choose(action: PaletteAction) {
    close();
    if (action.kind === "route") router.push(action.href);
    else if (action.kind === "workspace") onSwitchWorkspace(action.workspaceId);
    else action.run();
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "ArrowDown") {event.preventDefault(); setActive(Math.min(cursor + 1, filtered.length - 1));}
    else if (event.key === "ArrowUp") {event.preventDefault(); setActive(Math.max(cursor - 1, 0));}
    else if (event.key === "Enter" && filtered[cursor]) {event.preventDefault(); choose(filtered[cursor]);}
  }

  return (
    <div onKeyDown={onKeyDown} className="flex min-h-0 flex-col">
      <div className="flex items-center gap-2 border-b px-3">
        <Search size={16} className="text-muted-foreground"/>
        <input
          autoFocus
          value={queryText}
          onChange={(event) => setQueryText(event.target.value)}
          placeholder="Jump to a page, workspace, filter, or command…"
          aria-label="Search commands"
          className="h-12 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        />
        <kbd className="hidden text-[0.625rem] text-muted-foreground sm:block">esc</kbd>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-1.5" role="listbox" aria-label="Results">
        {filtered.length === 0 && <p className="px-3 py-6 text-center text-sm text-muted-foreground">No matches.</p>}
        {filtered.map((action, index) => {
          const Icon = "icon" in action ? action.icon : undefined;
          return (
            <button
              key={action.id}
              role="option"
              aria-selected={index === cursor}
              onMouseMove={() => setActive(index)}
              onClick={() => choose(action)}
              className={cn("flex w-full items-center gap-3 rounded-[0.625rem] px-3 py-2.5 text-left text-sm", index === cursor ? "bg-primary/10 text-primary dark:text-highlight" : "hover:bg-muted")}>
              {Icon ? <Icon size={16}/> : <Command size={16} className="opacity-40"/>}
              <span className="flex-1 truncate">{action.label}</span>
              {action.hint && <span className="shrink-0 text-[0.6875rem] text-muted-foreground">{action.hint}</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function CommandPalette({
  open, onOpenChange, nav, workspaces, canSwitch, recentFilters, careSearchBase, onSwitchWorkspace, onSignOut,
}: {open: boolean; onOpenChange: (next: boolean) => void} & Omit<BodyProps, "close">) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="gp-overlay-in fixed inset-0 z-50 bg-black/50"/>
        <Dialog.Content className="gp-pop-in fixed left-1/2 top-[12%] z-50 flex max-h-[76vh] w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 flex-col overflow-hidden rounded-card border bg-card shadow-2xl">
          <Dialog.Title className="sr-only">Command palette</Dialog.Title>
          <PaletteBody
            close={() => onOpenChange(false)}
            nav={nav}
            workspaces={workspaces}
            canSwitch={canSwitch}
            recentFilters={recentFilters}
            careSearchBase={careSearchBase}
            onSwitchWorkspace={onSwitchWorkspace}
            onSignOut={onSignOut}
          />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
