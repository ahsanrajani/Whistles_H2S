"use client";

import {useSearchParams} from "next/navigation";
import {useTenantRouter as useRouter} from "@/components/tenant-link";
import {JobsTab} from "@/components/admin-ops/jobs-tab";
import {OwnedAnalyticsTab} from "@/components/admin-ops/owned-analytics-tab";
import {PrecisionTab} from "@/components/admin-ops/precision-tab";
import {RetentionTab} from "@/components/admin-ops/retention-tab";
import {RoutingPolicyTab} from "@/components/admin-ops/routing-policy-tab";
import {SourceHealthTab} from "@/components/admin-ops/source-health-tab";
import {TabBar} from "@/components/ui/tab-bar";

const TABS = [
  {key: "sources", label: "Source health", Body: SourceHealthTab},
  {key: "retention", label: "Retention", Body: RetentionTab},
  {key: "precision", label: "Precision", Body: PrecisionTab},
  {key: "owned", label: "Owned analytics", Body: OwnedAnalyticsTab},
  {key: "routing", label: "Routing policy", Body: RoutingPolicyTab},
  {key: "jobs", label: "Jobs & scheduler", Body: JobsTab},
] as const;

/** F6 — the admin surfaces the backend shipped with no UI. Kept separate from
 * the legacy /admin config page (already at the file-size limit). */
export function AdminOpsView() {
  const params = useSearchParams();
  const router = useRouter();
  const tab = TABS.some((t) => t.key === params.get("tab")) ? params.get("tab")! : "sources";
  const Body = TABS.find((t) => t.key === tab)!.Body;

  return (
    <div className="mx-auto grid max-w-[81.25rem] gap-5">
      <div>
        <p className="mb-0.5 text-sm font-semibold text-primary dark:text-highlight">Operations</p>
        <h1 className="m-0 text-2xl font-semibold tracking-tight">Admin operations</h1>
      </div>
      <TabBar label="Admin ops tabs" items={TABS.map((t) => ({key: t.key, label: t.label}))} value={tab} onChange={(key) => router.replace(`/admin-ops?tab=${key}`)}/>
      <Body/>
    </div>
  );
}
