import {Suspense} from "react";
import {AdminOpsView} from "@/components/admin-ops-view";

export default function AdminOpsPage() {
  return (
    <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}>
      <AdminOpsView/>
    </Suspense>
  );
}
