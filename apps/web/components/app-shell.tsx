"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {Activity, BarChart3, BellRing, Bot, BookOpen, Building2, CalendarDays, ChevronDown, ClipboardCheck, DoorOpen, FileBarChart, GaugeCircle, Headset, HeartPulse, Landmark, Layers, ListChecks, LogOut, Menu, MessageSquareText, Search, Settings, Shapes, Share2, ShieldAlert, ShieldQuestion, Sparkles, Star, Trophy, Wrench} from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import {usePathname, useRouter, useSearchParams} from "next/navigation";
import {useEffect, useLayoutEffect, useRef, useState, type ReactNode} from "react";
import {useStats, useWorkspaces} from "@/hooks/use-api";
import {useIdleLogout} from "@/hooks/use-idle-logout";
import {apiFetch, clearCsrf} from "@/lib/api";
import type {User} from "@/lib/types";
import {can, featureEnabled, navVisible} from "@/lib/permissions";
import {cn} from "@/lib/utils";
import {AgentStatusControl} from "@/components/care/agent-status";
import {BrandMark} from "@/components/brand-mark";
import {Button} from "@/components/ui/button";
import {CommandPalette} from "@/components/command-palette";
import {TenantSwitcher} from "@/components/tenant-switcher";

type NavItem = {href: string; label: string; icon: typeof BarChart3};

// Hamza: "can we segmentize these? eg social care, social listening etc" --
// grouped for the sidebar only; every route/permission is unchanged, this
// is purely how the same flat list is presented. null label = no header
// (Overview sits alone at the top, same as before).
const NAV_GROUPS: {label: string | null; items: NavItem[]}[] = [
  {label: null, items: [
    {href: "/overview", label: "Overview", icon: BarChart3},
  ]},
  {label: "Social Care", items: [
    {href: "/care", label: "Care console", icon: Headset},
    {href: "/care/supervisor", label: "Supervisor", icon: GaugeCircle},
    {href: "/knowledge", label: "Knowledge", icon: BookOpen},
    {href: "/content", label: "Content calendar", icon: CalendarDays},
  ]},
  {label: "Social Listening", items: [
    {href: "/vantage", label: "AI listening", icon: Bot},
    {href: "/posts", label: "Posts", icon: Share2},
    {href: "/mentions", label: "Mentions", icon: MessageSquareText},
    {href: "/sentiment", label: "Sentiment", icon: HeartPulse},
    {href: "/competitors", label: "Competitors", icon: Trophy},
    {href: "/reviews", label: "Reviews", icon: Star},
    {href: "/themes", label: "Themes", icon: Shapes},
    {href: "/reports", label: "Reports", icon: FileBarChart},
  ]},
  {label: "Risk & Compliance", items: [
    {href: "/scam", label: "Scam signals", icon: ShieldAlert},
    {href: "/triage", label: "Complaint triage", icon: ListChecks},
    {href: "/switch-intent", label: "Switch intent", icon: DoorOpen},
    {href: "/incidents", label: "Incident radar", icon: Activity},
    {href: "/product-lines", label: "Product lines", icon: Layers},
    {href: "/regulatory", label: "Regulatory watch", icon: Landmark},
    {href: "/branches", label: "Branch & ATM", icon: Building2},
    {href: "/alerts", label: "Alert center", icon: BellRing},
  ]},
];
const baseNav = NAV_GROUPS.flatMap(g => g.items);
const adminNav = [
  {href: "/impersonation", label: "Brand abuse", icon: ShieldQuestion},
  {href: "/admin", label: "Admin", icon: Settings},
  {href: "/admin-ops", label: "Admin operations", icon: Wrench},
  {href: "/review", label: "Calibration", icon: ClipboardCheck},
  {href: "/onboarding", label: "New workspace", icon: Sparkles},
];
const ThemeToggle = dynamic(() => import("@/components/theme-toggle"), {ssr: false, loading: () => <span className="inline-block size-10" aria-hidden="true"/>});

export function AppShell({initialUser, tenant, project, children}: {initialUser: User; tenant: string; project: string; children: ReactNode}) {
  const base = `/t/${tenant}/p/${project}`;
  const pathname = usePathname(); const searchParams = useSearchParams(); const search = searchParams.toString(); const router = useRouter(); const query = useQueryClient();
  const [palette, setPalette] = useState(false); const [mobile, setMobile] = useState(false);
  const [recentFilters, setRecentFilters] = useState<{href: string; label: string}[]>([]);
  // Hamza: "can the sections be collapsable?" -- per-viewer preference, not
  // app state, so localStorage rather than anything server-side. Starts all
  // expanded (matches the pre-collapse behaviour) on the server and on a
  // fresh client; the effect below is the one place this reads the saved
  // choice back in, same established pattern as recentFilters just above.
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        const saved = JSON.parse(localStorage.getItem("guru-nav-collapsed") ?? "{}") as Record<string, boolean>;
        setCollapsed(saved);
      } catch { /* private browsing / storage blocked -- stay expanded */ }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);
  function toggleGroup(label: string) {
    const next = {...collapsed, [label]: !collapsed[label]};
    setCollapsed(next);
    try { localStorage.setItem("guru-nav-collapsed", JSON.stringify(next)); } catch { /* ignore */ }
  }
  const navRef = useRef<HTMLElement>(null);
  const pillRef = useRef<HTMLSpanElement>(null);
  const workspaces = useWorkspaces();
  const stats = useStats();
  const visibleBase = baseNav.filter(item => navVisible(initialUser.perms, item.href, initialUser.features));
  const visibleAdmin = adminNav.filter(item => navVisible(initialUser.perms, item.href, initialUser.features));
  const visibleGroups = NAV_GROUPS
    .map(g => ({label: g.label, items: g.items.filter(item => navVisible(initialUser.perms, item.href, initialUser.features))}))
    .filter(g => g.items.length > 0);
  const currentSlug = pathname.startsWith(base) ? (pathname.slice(base.length) || "/overview") : "/overview";
  const featureBlocked = !featureEnabled(initialUser.features, currentSlug);
  const nav = [...visibleBase, ...visibleAdmin].map(item => ({...item, href: `${base}${item.href}`}));
  useEffect(() => {const key = (event: KeyboardEvent) => {if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {event.preventDefault(); setPalette(true);} else if (event.key === "Escape") setMobile(false);}; addEventListener("keydown", key); return () => removeEventListener("keydown", key);}, []);
  useEffect(() => {const timer = window.setTimeout(() => {try {const saved = JSON.parse(localStorage.getItem("guru-recent-filters") ?? "[]") as {href:string;label:string}[]; const current = pathname === `${base}/mentions` && search ? {href:`${pathname}?${search}`, label:decodeURIComponent(search).replaceAll("&", " · ").replaceAll("=", ": ")} : null; const next = current ? [current, ...saved.filter(item => item.href !== current.href)].slice(0,5) : saved.slice(0,5); setRecentFilters(next); if (current) localStorage.setItem("guru-recent-filters", JSON.stringify(next));} catch {setRecentFilters([]);}}, 0); return () => window.clearTimeout(timer);}, [pathname, search, base]);
  const switcher = useMutation({
    mutationFn: (ws_id: number) => apiFetch("/workspace/switch", {method: "POST", body: JSON.stringify({ws_id})}),
    onSuccess: async (_data, ws_id) => {
      const slug = workspaces.data?.list.find(w => w.id === ws_id)?.slug;
      await query.invalidateQueries();
      if (slug && slug !== tenant) router.replace(`/t/${slug}/p/${project}/overview`);
      else router.refresh();
    },
  });
  // Keep the URL tenant and the server session workspace in step.
  useEffect(() => {
    const active = workspaces.data?.active;
    if (!active || active.slug === tenant) return;
    const match = workspaces.data?.list.find(w => w.slug === tenant);
    if (match && workspaces.data?.can_switch) switcher.mutate(match.id);
    else router.replace(`/t/${active.slug}/p/${project}/overview`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaces.data, tenant, project]);
  async function logout() {
    // Hamza: "not available when logging out" -- must go out before the
    // session itself does, or this 401s against a session that's already gone.
    if (initialUser.perms.includes("care:view")) {
      await apiFetch("/care/session", {method: "POST", body: JSON.stringify({state: "not_ready"})}).catch(() => {});
    }
    await apiFetch("/auth/logout", {method: "POST"}); clearCsrf(); query.clear(); router.replace("/login"); router.refresh();
  }
  // Hamza: "auth needs to be improved (logout after 20 mins of inactivity)".
  useIdleLogout(logout);

  // The sidebar's active pill is one element that glides to the current link. It is positioned from measured
  // offsets and re-placed whenever the route, a group's open state or the drawer changes.
  useLayoutEffect(() => {
    const place = () => {
      const active = navRef.current?.querySelector<HTMLElement>('[aria-current="page"]');
      const pill = pillRef.current;
      if (!pill) return;
      if (!active) {pill.style.opacity = "0"; return;}
      pill.style.height = `${active.offsetHeight}px`;
      pill.style.transform = `translateY(${active.offsetTop}px)`;
      pill.style.opacity = "1";
    };
    place();
    const timer = window.setTimeout(place, 320);          // again once a collapsing group has finished moving
    const ro = new ResizeObserver(place);
    if (navRef.current) ro.observe(navRef.current);
    return () => {window.clearTimeout(timer); ro.disconnect();};
  }, [pathname, collapsed, mobile]);

  const exactOnly = new Set([`${base}/overview`, `${base}/care`]);
  const renderLink = (item: {href: string; label: string; icon: typeof BarChart3}) => {const Icon = item.icon; const active = pathname === item.href || (!exactOnly.has(item.href) && pathname.startsWith(`${item.href}/`)); return <Link key={item.href} href={item.href} onClick={() => setMobile(false)} aria-current={active ? "page" : undefined} className="gp-nav-link"><Icon size={18}/>{item.label}</Link>;};
  const prefixed = (items: typeof baseNav) => items.map(item => ({...item, href: `${base}${item.href}`}));
  // Hamza: "can the sections be collapsable?"
  const groupHeader = (label: string) => {
    const isCollapsed = !!collapsed[label];
    return <button type="button" onClick={() => toggleGroup(label)} aria-expanded={!isCollapsed}
      className="mb-1 mt-5 flex w-full items-center gap-1 rounded-full px-3 py-1 text-[0.625rem] font-bold uppercase tracking-[.16em] text-white/45 hover:text-white/80">
      <ChevronDown size={12} className={cn("shrink-0 transition-transform duration-300 ease-out", isCollapsed && "-rotate-90")}/>
      {label}
    </button>;
  };
  const group = (label: string | null, items: {href: string; label: string; icon: typeof BarChart3}[]) => {
    const open = !label || !collapsed[label];
    return <div key={label ?? "_top"}>{label && groupHeader(label)}<div className="gp-collapse" data-open={open}><div className="grid gap-0.5">{prefixed(items).map(renderLink)}</div></div></div>;
  };
  const sidebar = <>
    <div className="flex h-24 shrink-0 items-center gap-3 px-6"><BrandMark size={32}/><div className="leading-tight"><div className="text-xl font-bold tracking-tight">Whistles</div></div></div>
    <nav ref={navRef} aria-label="Primary" className="relative grid min-h-0 flex-1 content-start gap-1 overflow-y-auto px-3 pb-3">
      <span ref={pillRef} aria-hidden="true" className="gp-nav-pill"/>
      {visibleGroups.map(g => group(g.label, g.items))}
      {visibleAdmin.length > 0 && group("Admin", visibleAdmin)}
    </nav>
    <div className="m-3 mt-auto rounded-[1.375rem] border border-white/10 bg-white/[.06] p-4 text-xs text-white/60 shadow-[inset_0_1px_0_rgba(255,255,255,.08)]">
      <div className="mb-1 flex items-center gap-2 text-white/85"><span className="size-2 rounded-full bg-accent shadow-[0_0_0.625rem_var(--accent)]"/><span className="font-semibold">{initialUser.role === "admin" ? "Administrator" : "Viewer"}</span></div>
      {stats.data ? <span className="numeric">{stats.data.items.toLocaleString()} items · {stats.data.mentions.toLocaleString()} mentions{stats.data.last_run ? ` · last run ${stats.data.last_run.slice(0, 10)}` : ""}</span> : "—"}
    </div>
  </>;
  return <div className="min-h-screen lg:grid lg:grid-cols-[296px_1fr]"><a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-full focus:border focus:bg-card focus:px-4 focus:py-2 focus:text-sm">Skip to content</a><aside className="gp-sheet-in sticky top-0 hidden h-screen p-4 lg:block"><div className="gp-sidebar">{sidebar}</div></aside>{mobile && <div className="gp-overlay-in fixed inset-0 z-40 lg:hidden" onClick={() => setMobile(false)}><aside className="gp-sheet-in h-full w-[18.75rem] p-3" onClick={event => event.stopPropagation()}><div className="gp-sidebar">{sidebar}</div></aside></div>}<div className="min-w-0"><header className="gp-topbar flex h-[4.5rem] items-center gap-3 px-4 md:px-6"><Button variant="ghost" className="size-10 p-0 lg:hidden" onClick={() => setMobile(true)} aria-label="Open navigation" aria-expanded={mobile}><Menu/></Button><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{workspaces.data?.active?.name ?? initialUser.workspace?.name ?? "Workspace"}</p><p className="text-xs text-muted-foreground">{initialUser.role === "admin" ? "Administrator" : "Viewer"}</p></div><TenantSwitcher/>{can(initialUser.perms, "care:view") && <AgentStatusControl/>}<Button variant="outline" className="hidden min-w-48 justify-start text-muted-foreground md:flex" onClick={() => setPalette(true)} aria-keyshortcuts="Meta+K Control+K"><Search size={16}/>Jump to… <kbd className="ml-auto rounded-full bg-muted px-2 py-0.5 text-[0.625rem] font-semibold">⌘K</kbd></Button><ThemeToggle/><Button variant="ghost" className="size-10 p-0" aria-label="Sign out" onClick={logout}><LogOut/></Button></header><main id="main" className="gp-rise p-4 md:p-6">{featureBlocked ? <FeatureOff workspace={workspaces.data?.active?.name ?? initialUser.workspace?.name} isAdmin={initialUser.role === "admin"}/> : children}</main></div>
    <CommandPalette open={palette} onOpenChange={setPalette} nav={nav}
      workspaces={workspaces.data?.list ?? []} canSwitch={!!workspaces.data?.can_switch}
      recentFilters={recentFilters}
      careSearchBase={can(initialUser.perms, "care:view") ? base : null}
      onSwitchWorkspace={id => switcher.mutate(id)} onSignOut={logout}/>
  </div>;
}

function FeatureOff({workspace, isAdmin}: {workspace?: string; isAdmin: boolean}) {
  return (
    <div role="status" className="rounded-card mx-auto max-w-md p-8 text-center">
      <h1 className="text-lg font-semibold">This area is turned off</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        It has been disabled for {workspace ?? "this workspace"}.
        {isAdmin ? " Re-enable it in Admin → Features." : " Ask an administrator to re-enable it."}
      </p>
    </div>
  );
}
