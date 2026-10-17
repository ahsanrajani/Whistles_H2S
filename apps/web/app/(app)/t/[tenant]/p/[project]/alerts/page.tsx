import {Suspense} from "react";
import {AlertsView} from "@/components/alerts-view";
export default function AlertsPage() {return <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}><AlertsView/></Suspense>;}
