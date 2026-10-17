import {Suspense} from "react";
import {SupervisorView} from "@/components/care/supervisor-view";

export default function SupervisorPage() {
  return (
    <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}>
      <SupervisorView/>
    </Suspense>
  );
}
