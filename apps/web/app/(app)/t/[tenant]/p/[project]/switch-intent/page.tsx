import {Suspense} from "react";
import {SwitchIntentView} from "@/components/switch-intent-view";
export default function SwitchIntentPage() {return <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}><SwitchIntentView/></Suspense>;}
