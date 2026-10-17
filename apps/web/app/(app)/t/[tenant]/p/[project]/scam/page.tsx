import {Suspense} from "react";
import {ScamView} from "@/components/scam-view";
export default function ScamPage() {return <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}><ScamView/></Suspense>;}
