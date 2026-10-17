import {Suspense} from "react";
import {ProductLinesView} from "@/components/product-lines-view";
export default function ProductLinesPage() {return <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}><ProductLinesView/></Suspense>;}
