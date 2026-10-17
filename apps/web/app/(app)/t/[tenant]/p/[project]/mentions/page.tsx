import {MentionsView} from "@/components/mentions-view";
import {Suspense} from "react";
export default function MentionsPage() {return <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}><MentionsView/></Suspense>;}
