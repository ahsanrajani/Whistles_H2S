import {OverviewView} from "@/components/overview-view";
import {Suspense} from "react";
export default function OverviewPage() {return <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}><OverviewView/></Suspense>;}
