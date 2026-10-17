import {Suspense} from "react";
import {IncidentsView} from "@/components/incidents-view";
export default function IncidentsPage() {return <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}><IncidentsView/></Suspense>;}
