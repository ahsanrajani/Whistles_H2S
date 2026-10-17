"use client";

import {Link} from "@/components/tenant-link";
import {useSearchParams} from "next/navigation";
import {useMe, useReviews} from "@/hooks/use-api";
import {can} from "@/lib/permissions";
import {StoreStatsCard} from "./review-store-card";
import {Card} from "./ui/card";
import {ComparisonChart} from "./comparison-chart";
import {PageHeader, PeriodControl, ThemeCloud} from "./viewer-components";
import {EmptyState, ErrorState, LoadingState} from "./states";

export function ReviewsView() {
  const params = useSearchParams();
  const result = useReviews(params.toString());
  const me = useMe();
  const canEdit = can(me.data?.user.perms, "admin:edit");
  if (result.isLoading) return <LoadingState label="Loading app reviews…"/>;
  if (result.error) return <ErrorState message={result.error.message}/>;
  const data = result.data;
  if (!data) return <EmptyState title="No review data" body="Connect an app-store source and run a collection."/>;
  const reviews = data.reviews;
  const mentionsHref = (filters: Record<string, string>) =>
    `/mentions?${new URLSearchParams({surface: "app_reviews", since: "all",
      ...(data.focus_brand_id != null ? {brand_id: String(data.focus_brand_id)} : {}), ...filters})}`;
  const statsCard = <StoreStatsCard stats={data.store_stats ?? null} canEdit={canEdit}/>;
  if (!reviews) {
    return (
      <div className="grid gap-6">
        <PageHeader title="App reviews" subtitle="Real store-wide ratings, plus collected app reviews for the focus brand." stat={<PeriodControl value={data.period}/>}/>
        {statsCard}
        <EmptyState title="No app-store reviews collected yet" body="Add the App Store or Play Store app identifiers in Admin, then run a collection."/>
      </div>
    );
  }
  const delta = data.deltas.rating?.pct;
  const combined = data.store_stats?.combined;
  const distSource = combined?.histogram ? combined : null;
  const starCount = (star: number) => distSource ? (distSource.histogram?.[String(star) as "1"] ?? 0) : reviews.dist[star - 1];
  const distN = distSource ? [1, 2, 3, 4, 5].reduce((sum, star) => sum + starCount(star), 0) : reviews.overall_n;
  const goodShare = distSource?.good_share ?? reviews.good_share;
  const goodLo = distSource?.good_lo ?? reviews.good_lo;
  const goodHi = distSource?.good_hi ?? reviews.good_hi;

  return (
    <div className="mx-auto grid max-w-[93.75rem] gap-5">
      <PageHeader title="App reviews" subtitle="Real store-wide ratings, plus collected app reviews for the focus brand."
        stat={<div className="flex items-center gap-3">
          <div className="text-right">
            {combined?.rating != null
              ? <>
                  <strong className="numeric text-2xl">{combined.rating.toFixed(1)}★</strong>
                  <p className="m-0 text-xs text-muted-foreground">{combined.count != null ? `${combined.count.toLocaleString()} real store ratings` : "real store average"}</p>
                </>
              : <>
                  <strong className="numeric text-2xl">{reviews.overall_avg.toFixed(1)}★</strong>
                  <p className="m-0 text-xs text-muted-foreground">{reviews.overall_n} collected reviews {delta == null ? "· measuring" : `· ${delta >= 0 ? "+" : ""}${delta.toFixed(1)}`}</p>
                </>}
          </div>
          <PeriodControl value={data.period}/>
        </div>}/>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_.8fr]">
        <Card>
          <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
            <div>
              <h2 className="m-0 text-xl font-semibold">Rating distribution</h2>
              {distSource && <p className="m-0 text-xs text-muted-foreground">App Store + Play Store combined</p>}
            </div>
            {distSource && <span className="numeric text-sm">
              {distSource.rating != null ? `${distSource.rating.toFixed(1)}★` : "unknown"}
              {" · "}
              {distSource.count != null ? `${distSource.count.toLocaleString()} ratings` : "unknown count"}
            </span>}
          </div>
          <div className="grid gap-2">
            {[5, 4, 3, 2, 1].map((star) => (
              <Link key={star} href={mentionsHref({rating: String(star)})}
                className="grid grid-cols-[40px_1fr_48px] items-center gap-3 rounded-[0.5rem] py-1.5 text-sm hover:bg-muted">
                <span className="font-medium">{star}★</span>
                <span className="h-3 overflow-hidden rounded-full bg-muted">
                  <span className="block h-full rounded-full bg-warning" style={{width: `${distN ? (100 * starCount(star)) / distN : 0}%`}}/>
                </span>
                <span className="numeric text-right">{starCount(star).toLocaleString()}</span>
              </Link>
            ))}
          </div>
          <div className="mt-4 flex gap-2 text-xs">
            <Link href={mentionsHref({rating: "low"})} className="rounded-full border border-danger/30 px-2.5 py-1 font-semibold text-danger hover:bg-danger/10">1–2★ ({(starCount(1) + starCount(2)).toLocaleString()})</Link>
            <Link href={mentionsHref({rating: "mid"})} className="rounded-full border px-2.5 py-1 font-semibold text-muted-foreground hover:bg-muted">3★ ({starCount(3).toLocaleString()})</Link>
            <Link href={mentionsHref({rating: "high"})} className="rounded-full border border-success/30 px-2.5 py-1 font-semibold text-success hover:bg-success/10">4–5★ ({(starCount(4) + starCount(5)).toLocaleString()})</Link>
          </div>
          <p className="mt-4 text-sm text-muted-foreground">{(goodShare * 100).toFixed(0)}% rate it 4★ or better · 95% {(goodLo * 100).toFixed(0)}–{(goodHi * 100).toFixed(0)}%</p>
        </Card>

        {statsCard}
      </div>

      <Card>
        <div className="mb-4">
          <h2 className="m-0 text-xl font-semibold">Before / after</h2>
          <p className="text-sm text-muted-foreground">{data.timeline.window}-day rolling rating and star-mix.</p>
        </div>
        <ComparisonChart timeline={data.timeline}/>
      </Card>

      <Card>
        <h2 className="mt-0 text-xl font-semibold">What reviewers mention</h2>
        <ThemeCloud themes={data.themes} extraQuery="&surface=app_reviews"/>
      </Card>

      <div className="grid gap-6 xl:grid-cols-2">
        {reviews.stores.map((store) => {
          const recent = store.recent ?? [];
          return (
          <Card key={store.store}>
            <h2 className="mt-0 text-xl font-semibold">{store.store}</h2>
            <p className="mb-3 text-xs text-muted-foreground">Newest collected reviews for this store, up to 50.</p>
            <div className="max-h-[37.5rem] divide-y overflow-y-auto">
              {recent.map((review, index) => (
                <div key={`${store.store}-${review.when}-${index}`} className="py-4">
                  <div className="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground">
                    <Link href={mentionsHref({rating: String(review.rating), outlet: store.store})} className="text-warning hover:opacity-80" title={`Open all ${review.rating}★ reviews`}>
                      {"★".repeat(review.rating)}<span className="text-muted">{"★".repeat(5 - review.rating)}</span>
                    </Link>
                    <span className="flex items-center gap-2">
                      {review.app && (
                        <span className="flex items-center gap-1.5" title={review.app.name ?? review.app.id}>
                          {review.app.icon
                            // eslint-disable-next-line @next/next/no-img-element
                            ? <img src={review.app.icon} alt="" width={20} height={20} loading="lazy" referrerPolicy="no-referrer" className="size-5 rounded-[0.3125rem]"/>
                            : <span className="grid size-5 place-items-center rounded-[0.3125rem] bg-muted text-[0.625rem] font-semibold">{(review.app.name ?? review.app.id).charAt(0).toUpperCase()}</span>}
                          <span className="max-w-[10rem] truncate">{review.app.name ?? review.app.id}</span>
                        </span>
                      )}
                      {review.when}
                    </span>
                  </div>
                  {review.url
                    ? <a href={review.url} target="_blank" rel="noreferrer" className="mt-2 block text-sm font-medium hover:text-primary">{review.text}</a>
                    : <p className="mb-0 mt-2 text-sm font-medium">{review.text}</p>}
                </div>
              ))}
              {!recent.length && <p className="text-sm text-muted-foreground">No collected reviews for this store yet.</p>}
            </div>
          </Card>
          );
        })}
      </div>
    </div>
  );
}
