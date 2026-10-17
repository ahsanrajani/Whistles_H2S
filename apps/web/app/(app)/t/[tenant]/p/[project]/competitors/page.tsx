import {Suspense} from "react";
import {CompetitorsView} from "@/components/competitors-view";
export default function CompetitorsPage() {return <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}><CompetitorsView/></Suspense>;}
