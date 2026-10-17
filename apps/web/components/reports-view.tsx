"use client";

import dynamic from "next/dynamic";
import {useSearchParams} from "next/navigation";
import {useTenantRouter as useRouter} from "@/components/tenant-link";
import {LoadingState} from "@/components/states";
import {TabBar} from "@/components/ui/tab-bar";

// F7.2 — each tab is its own chunk, fetched only when opened, rather than
// shipping every tab on first load of /reports. Care & SLA, Social, CSAT &
// complaints and MIS moved out to Social care/Supervisor and Posts
// (2026-09-14, Hamza) — same components, just hosted on different pages now.
const loading = () => <LoadingState label="Loading…"/>;
const TABS = [
  {key: "metrics", label: "Metrics", Body: dynamic(() => import("@/components/reports/metrics-tab").then((m) => m.MetricsTab), {loading})},
  {key: "schedules", label: "Schedules", Body: dynamic(() => import("@/components/reports/schedules-tab").then((m) => m.SchedulesTab), {loading})},
] as const;

/** F5.1 — the report shell (date range / compare / group-by / export /
 * schedule) is shared via components/reports/report-shell.tsx; F5.2-F5.7 are
 * one tab each below, all built on it. */
export function ReportsView() {
  const params = useSearchParams();
  const router = useRouter();
  const tab = TABS.some((t) => t.key === params.get("tab")) ? params.get("tab")! : "metrics";
  const Body = TABS.find((t) => t.key === tab)!.Body;

  return (
    <div className="mx-auto grid max-w-[87.5rem] gap-5">
      <div>
        <p className="mb-0.5 text-sm font-semibold text-primary dark:text-highlight">Analytics</p>
        <h1 className="m-0 text-2xl font-semibold tracking-tight">Reports</h1>
      </div>
      <TabBar label="Report tabs" items={TABS.map((t) => ({key: t.key, label: t.label}))} value={tab}
        onChange={(key) => {const sp = new URLSearchParams(); sp.set("tab", key); router.replace(`/reports?${sp}`);}}/>
      <Body/>
    </div>
  );
}
