import type {ContentState} from "@/lib/types";

export const STATE_COLOR: Record<ContentState, string> = {
  draft: "bg-muted text-muted-foreground",
  in_review: "bg-warning/15 text-warning",
  approved: "bg-highlight/15 text-highlight",
  scheduled: "bg-primary/15 text-primary",
  published: "bg-success/15 text-success",
  rejected: "bg-danger/15 text-danger",
};
export const STATES: ContentState[] = ["draft", "in_review", "approved", "scheduled", "published", "rejected"];
export const CHANNELS = ["meta", "facebook", "instagram", "x", "linkedin", "youtube"];
export const isVideoUrl = (url: string) => /\.(mp4|mov)$/i.test(url);

export function MediaThumb({url, className}: {url: string; className: string}) {
  return isVideoUrl(url)
    ? <video src={url} muted className={className}/>
    // eslint-disable-next-line @next/next/no-img-element -- local uploads served from our own /uploads/, an arbitrary-shaped URL
    : <img src={url} alt="" className={className}/>;
}
