import {Suspense} from "react";
import {ReportsView} from "@/components/reports-view";

export default function ReportsPage() {
  return (
    <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}>
      <ReportsView/>
    </Suspense>
  );
}
