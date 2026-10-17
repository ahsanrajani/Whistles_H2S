import {Suspense} from "react";
import {TriageView} from "@/components/triage-view";
export default function TriagePage() {return <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}><TriageView/></Suspense>;}
