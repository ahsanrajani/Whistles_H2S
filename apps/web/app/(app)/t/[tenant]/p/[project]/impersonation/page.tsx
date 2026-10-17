import {Suspense} from "react";
import {ImpersonationView} from "@/components/impersonation-view";
export default function ImpersonationPage() {return <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}><ImpersonationView/></Suspense>;}
