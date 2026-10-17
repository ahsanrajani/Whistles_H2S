import {Suspense} from "react";
import {KnowledgeView} from "@/components/knowledge-view";

export default function KnowledgePage() {
  return (
    <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}>
      <KnowledgeView/>
    </Suspense>
  );
}
