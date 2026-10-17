import {Suspense} from "react";
import {SeoView} from "@/components/seo-view";
export default function SeoPage() {return <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}><SeoView/></Suspense>;}
