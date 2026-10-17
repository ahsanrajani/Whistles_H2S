import {Suspense} from "react";
import {ReviewsView} from "@/components/reviews-view";
export default function ReviewsPage() {return <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}><ReviewsView/></Suspense>;}
