"use client";

import {useMutation, useQueryClient} from "@tanstack/react-query";
import {ChevronDown, ChevronRight, Eye, ExternalLink, Heart, MessageCircle, Play, Quote, Repeat2, Share2} from "lucide-react";
import dynamic from "next/dynamic";
import {useSearchParams} from "next/navigation";
import {useState} from "react";
import {apiFetch} from "@/lib/api";
import {useMe, useOwnedComments, useOwnedPosts} from "@/hooks/use-api";
import type {OwnedComment, OwnedPost, OwnedPostMedia, OwnedPostMetrics, OwnedPostPlatform} from "@/lib/types";
import {can} from "@/lib/permissions";
import {Link, useTenantRouter as useRouter} from "./tenant-link";
import {Badge} from "./ui/badge";
import {Button} from "./ui/button";
import {Card} from "./ui/card";
import {Input} from "./ui/input";
import {EmptyState, ErrorState, LoadingState} from "./states";
import {PageHeader} from "./viewer-components";
import {TabBar} from "@/components/ui/tab-bar";

// Social moved here from Reports (2026-09-14, Hamza) — same component
// (components/social-tab.tsx), just hosted on the Posts page now. Lazy
// chunk, same as it was as a Reports tab.
const loading = () => <LoadingState label="Loading…"/>;
const SocialTab = dynamic(() => import("./social-tab").then((m) => m.SocialTab), {loading});
const PAGE_TABS = [
  {key: "posts", label: "Posts"},
  {key: "social", label: "Social"},
] as const;

const PLATFORM_LABEL: Record<OwnedPostPlatform, string> = {
  facebook: "Facebook", instagram: "Instagram", linkedin: "LinkedIn", youtube: "YouTube", x: "X",
};
const PLATFORM_CLASS: Record<OwnedPostPlatform, string> = {
  facebook: "border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400",
  instagram: "border-pink-500/30 bg-pink-500/10 text-pink-600 dark:text-pink-400",
  linkedin: "border-sky-600/30 bg-sky-600/10 text-sky-700 dark:text-sky-400",
  youtube: "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
  x: "border-foreground/30 bg-foreground/5 text-foreground",
};
// owned-posts platform -> write-client platform (integrations/write/platforms
// .py _ALIASES resolves facebook/instagram back to the one "meta" client).
const REPLY_SUPPORTED = new Set<OwnedPostPlatform>(["facebook", "instagram", "youtube"]);

function date(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString(undefined, {year: "numeric", month: "short", day: "numeric"});
}

// Icon + count, like the platforms' own under-post action row, instead of a
// plain "42 likes · 3 comments" text line.
const METRIC_ICONS = [
  ["views", Eye], ["likes", Heart], ["comments", MessageCircle],
  ["replies", MessageCircle], ["shares", Share2], ["reposts", Repeat2],
  ["quotes", Quote],
] as const satisfies readonly [keyof OwnedPostMetrics, typeof Eye][];

function MetricsLine({metrics}: {metrics: OwnedPostMetrics | null}) {
  const shown = metrics
    ? METRIC_ICONS.filter(([key]) => metrics[key] != null)
    : [];
  if (!shown.length) return <span className="text-xs text-muted-foreground">No analytics available</span>;
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
      {shown.map(([key, Icon]) => (
        <span key={key} className="numeric inline-flex items-center gap-1">
          <Icon size={13}/>{metrics![key]!.toLocaleString()}
        </span>
      ))}
    </div>
  );
}

/** Real media, rendered like the platform's own feed -- a photo/thumbnail,
 * a directly-playable video (Instagram's Graph API exposes a real file URL;
 * Facebook's doesn't, so a video there is a thumbnail + play badge linking
 * out to watch it there), or a real YouTube iframe embed. */
function PostMedia({media, compact}: {media: OwnedPostMedia | null; compact?: boolean}) {
  if (!media) return null;
  const box = compact ? "aspect-video" : "max-h-[26.25rem]";
  // Compact (the card sits inside a whole-card <a>, e.g. the dashboard
  // widget): a poster + play badge only -- real <video controls>/<iframe>
  // nested inside an anchor is both invalid HTML and unusable (the anchor
  // eats every click). Full playback is for the non-compact Posts page.
  if (!compact && media.type === "youtube") {
    return (
      <div className={`relative mt-2 ${box} w-full overflow-hidden rounded-[0.625rem] bg-muted`}>
        <iframe src={`https://www.youtube.com/embed/${media.video_id}`} title="YouTube video"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen className="absolute inset-0 h-full w-full border-0"/>
      </div>
    );
  }
  if (!compact && media.type === "video" && media.video) {
    // No forced width/aspect here -- a portrait Reel/Story renders at its
    // own narrow-tall shape (like the real app), not stretched to the
    // card's full width. The black background lives on the <video> itself
    // (sized to its own content), not on a full-width wrapper div -- that
    // was the actual bug: a transparent-but-still-100%-wide wrapper with a
    // black background painted the exact "bars" this was meant to remove.
    return (
      <div className="mt-2 flex justify-center">
        <video controls poster={media.image} preload="metadata"
          className="max-h-[70vh] max-w-full rounded-[0.625rem] bg-black">
          <source src={media.video}/>
        </video>
      </div>
    );
  }
  if (media.image) {
    return (
      <div className={`relative mt-2 ${box} w-full overflow-hidden rounded-[0.625rem] bg-muted`}>
        {/* eslint-disable-next-line @next/next/no-img-element -- unpredictable per-brand CDN hosts (Meta/YouTube), not worth a next/image remotePatterns entry per tenant */}
        <img src={media.image} alt="" className="h-full w-full object-cover"/>
        {(media.type === "video" || media.type === "youtube") && (
          <span className="absolute inset-0 grid place-items-center bg-black/20">
            <span className="grid size-12 place-items-center rounded-full bg-black/60 text-white">
              <Play size={20} fill="currentColor"/>
            </span>
          </span>
        )}
      </div>
    );
  }
  return null;
}

function PostRow({post, compact}: {post: OwnedPost; compact?: boolean}) {
  const text = post.title || post.body || "";
  return (
    <a href={post.url ?? undefined} target={post.url ? "_blank" : undefined} rel="noreferrer"
      className={`block py-3 ${post.url ? "cursor-pointer hover:bg-muted/40" : "cursor-default"} -mx-2 rounded-[0.5rem] px-2`}>
      <div className="flex items-center gap-2">
        <Badge className={PLATFORM_CLASS[post.platform]}>{post.platform_label}</Badge>
        {post.author && <span className="text-xs text-muted-foreground">{post.author}</span>}
        <span className="text-xs text-muted-foreground">· {date(post.published_at)}</span>
        {post.url && <ExternalLink size={11} className="ml-auto text-muted-foreground"/>}
      </div>
      <p className={`mb-0 mt-1.5 font-medium ${compact ? "line-clamp-2 text-sm" : "text-sm"}`}>{text || "(no text)"}</p>
      <PostMedia media={post.media} compact/>
      <div className="mt-1.5"><MetricsLine metrics={post.metrics}/></div>
    </a>
  );
}

/** Compact dashboard widget — Overview slots this in next to "Recent stories". */
export function RecentPostsCard() {
  const query = useOwnedPosts({limit: 6});
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <h2 className="mt-0 text-base font-semibold">Recent posts</h2>
        <Link href="/posts" className="text-xs font-semibold text-primary dark:text-highlight">All posts →</Link>
      </div>
      {query.isLoading ? (
        <LoadingState label="Loading posts…"/>
      ) : query.error ? (
        <ErrorState message={query.error.message}/>
      ) : !query.data?.posts.length ? (
        <p className="py-6 text-center text-sm text-muted-foreground">No owned posts collected yet.</p>
      ) : (
        <div className="mt-1 divide-y">{query.data.posts.map((p) => <PostRow key={`${p.source}:${p.external_id}`} post={p} compact/>)}</div>
      )}
    </Card>
  );
}

function CommentRow({comment, platform, canReply, source}: {
  comment: OwnedComment; platform: OwnedPostPlatform; canReply: boolean; source: string;
}) {
  const [replying, setReplying] = useState(false);
  const [text, setText] = useState("");
  const client = useQueryClient();
  const send = useMutation({
    mutationFn: () => apiFetch("/owned-posts/reply", {method: "POST", body: JSON.stringify({
      platform, text, target_ref: comment.external_id,
    })}),
    onSuccess: () => {
      setText(""); setReplying(false);
      client.invalidateQueries({queryKey: ["owned-posts", "comments", source]});
    },
  });
  return (
    <div className={comment.kind === "reply" ? "ml-6 border-l pl-3" : ""}>
      <div className="py-2">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="font-semibold text-foreground">{comment.author ?? "Unknown"}</span>
          <span>· {date(comment.published_at)}</span>
          {comment.url && (
            <a href={comment.url} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 font-semibold text-primary hover:underline dark:text-highlight">
              View original<ExternalLink size={10}/>
            </a>
          )}
        </div>
        <p className="m-0 mt-0.5 text-sm">{comment.body}</p>
        {canReply && !replying && (
          <button type="button" onClick={() => setReplying(true)} className="mt-1 text-xs font-semibold text-primary hover:underline dark:text-highlight">Reply</button>
        )}
        {replying && (
          <div className="mt-1.5 flex gap-1.5">
            <Input aria-label="Reply text" value={text} onChange={(e) => setText(e.target.value)} placeholder="Write a reply…" className="h-8 flex-1 text-xs"/>
            <Button type="button" className="h-8 px-2.5 text-xs" disabled={!text.trim() || send.isPending} onClick={() => send.mutate()}>Send</Button>
            <Button type="button" variant="outline" className="h-8 px-2.5 text-xs" onClick={() => setReplying(false)}>Cancel</Button>
          </div>
        )}
        {send.isError && <p className="mt-1 text-xs text-danger">{(send.error as Error).message}</p>}
      </div>
    </div>
  );
}

function CommentThread({post, canReply}: {post: OwnedPost; canReply: boolean}) {
  const query = useOwnedComments(post.source, post.external_id ?? "", !!post.external_id);
  if (query.isLoading) return <LoadingState label="Loading comments…"/>;
  if (query.error) return <ErrorState message={query.error.message}/>;
  const comments = query.data?.comments ?? [];
  if (!comments.length) return <p className="py-3 text-center text-xs text-muted-foreground">No comments collected for this post yet.</p>;
  return (
    <div className="divide-y border-t">
      {comments.map((c) => (
        <CommentRow key={c.external_id} comment={c} platform={post.platform} canReply={canReply} source={post.source}/>
      ))}
    </div>
  );
}

/** A post row that expands in place to show its real, already-collected
 * comment/reply thread — each linking to the real comment and, for
 * platforms Care can actually reply to, a working reply box. */
function ExpandablePostRow({post, canReply}: {post: OwnedPost; canReply: boolean}) {
  const [open, setOpen] = useState(false);
  const text = post.title || post.body || "";
  return (
    <div className="py-3">
      <button type="button" onClick={() => setOpen((v) => !v)} className="block w-full text-left">
        <div className="flex items-center gap-2">
          {open ? <ChevronDown size={14} className="text-muted-foreground"/> : <ChevronRight size={14} className="text-muted-foreground"/>}
          <Badge className={PLATFORM_CLASS[post.platform]}>{post.platform_label}</Badge>
          {post.author && <span className="text-xs text-muted-foreground">{post.author}</span>}
          <span className="text-xs text-muted-foreground">· {date(post.published_at)}</span>
        </div>
        <p className="mb-0 ml-5 mt-1.5 text-sm font-medium">{text || "(no text)"}</p>
      </button>
      {/* Outside the toggle button -- real <video controls>/<iframe> nested
          inside a <button> is both invalid HTML and unusable (every click
          on the player would toggle the accordion instead). */}
      <div className="ml-5"><PostMedia media={post.media}/></div>
      <div className="ml-5 mt-1.5"><MetricsLine metrics={post.metrics}/></div>
      <div className="ml-5 mt-1.5 flex items-center gap-3">
        {post.url && (
          <a href={post.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline dark:text-highlight">
            View post<ExternalLink size={11}/>
          </a>
        )}
        <button type="button" onClick={() => setOpen((v) => !v)} className="text-xs font-semibold text-muted-foreground hover:text-foreground">
          {open ? "Hide comments" : "Show comments"}
        </button>
      </div>
      {open && <div className="ml-5 mt-2"><CommentThread post={post} canReply={canReply && REPLY_SUPPORTED.has(post.platform)}/></div>}
    </div>
  );
}

const PLATFORMS: OwnedPostPlatform[] = ["facebook", "instagram", "linkedin", "youtube", "x"];

/** Full grid page — every recent owned post, filterable by platform, each
 * expandable to its real comment/reply thread. */
export function OwnedPostsView() {
  const params = useSearchParams();
  const router = useRouter();
  const tab = PAGE_TABS.some((t) => t.key === params.get("tab")) ? params.get("tab")! : "posts";
  const [platform, setPlatform] = useState<OwnedPostPlatform | "">("");
  const query = useOwnedPosts({platform: platform || undefined, limit: 100});
  const me = useMe();
  const canReply = can(me.data?.user.perms, "care:edit");

  function goTab(key: string) {
    const sp = new URLSearchParams(params.toString());
    sp.set("tab", key);
    router.replace(`/posts?${sp}`);
  }

  return (
    <div className="mx-auto grid max-w-[68.75rem] gap-5">
      <PageHeader title="Posts" subtitle="Everything published on Facebook, Instagram, LinkedIn, YouTube and X, with comments and analytics where the platform provides them."/>
      <TabBar label="Posts tabs" items={PAGE_TABS.map((t) => ({key: t.key, label: t.label}))} value={tab} onChange={goTab}/>
      {tab === "social" && <SocialTab/>}
      {tab === "posts" && (
        <>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => setPlatform("")}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium ${platform === "" ? "border-primary bg-primary/10 text-primary dark:text-highlight" : "text-muted-foreground hover:bg-muted"}`}>
              All
            </button>
            {PLATFORMS.map((p) => (
              <button key={p} type="button" onClick={() => setPlatform(p)}
                className={`rounded-full border px-3 py-1.5 text-xs font-medium ${platform === p ? "border-primary bg-primary/10 text-primary dark:text-highlight" : "text-muted-foreground hover:bg-muted"}`}>
                {PLATFORM_LABEL[p]}
              </button>
            ))}
          </div>
          <Card>
            {query.isLoading ? (
              <LoadingState label="Loading posts…"/>
            ) : query.error ? (
              <ErrorState message={query.error.message}/>
            ) : !query.data?.posts.length ? (
              <EmptyState title="No posts yet" body="Connect the owned-channel credentials for this platform and run a collection to populate this feed."/>
            ) : (
              <div className="divide-y">{query.data.posts.map((p) => <ExpandablePostRow key={`${p.source}:${p.external_id}`} post={p} canReply={canReply}/>)}</div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
