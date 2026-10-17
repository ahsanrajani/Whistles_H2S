import {Suspense} from "react";
import {BranchesView} from "@/components/branches-view";
export default function BranchesPage() {return <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}><BranchesView/></Suspense>;}
