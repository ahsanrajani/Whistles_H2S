import {Suspense} from "react";
import {OwnedPostsView} from "@/components/owned-posts";
export default function PostsPage() {return <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-muted"/>}><OwnedPostsView/></Suspense>;}
