import {Suspense} from "react";
import {SentimentView} from "@/components/sentiment-view";
export default function SentimentPage() {return <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}><SentimentView/></Suspense>;}
