import {Suspense} from "react";
import {VantageView} from "@/components/vantage-view";
export default function VantagePage() {return <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}><VantageView/></Suspense>;}
