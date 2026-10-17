import {Suspense} from "react";
import {ReviewView} from "@/components/review-view";
export default function ReviewPage() {return <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}><ReviewView/></Suspense>;}
