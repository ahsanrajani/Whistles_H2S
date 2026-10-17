import {Suspense} from "react";
import {RegulatoryView} from "@/components/regulatory-view";
export default function RegulatoryPage() {return <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}><RegulatoryView/></Suspense>;}
