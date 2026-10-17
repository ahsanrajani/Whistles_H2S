import {Suspense} from "react";
import {CareConsoleView} from "@/components/care/console-view";

export default function CarePage() {
  return (
    <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}>
      <CareConsoleView/>
    </Suspense>
  );
}
