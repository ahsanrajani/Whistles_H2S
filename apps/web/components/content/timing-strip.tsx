import type {ContentInsights, TimingBucket} from "@/lib/types";

type Timing = ContentInsights["timing"];

// 1.0 = the brand's own median; cap the colour scale at 2x so one outlier does not wash out the rest.
// Capped well below solid so the captions stay readable on the strongest cell in light and dark.
const heat = (ratio: number | null) => (ratio === null ? 0.04 : 0.08 + 0.4 * Math.min(ratio / 2, 1));

function Strip({title, buckets, best}: {title: string; buckets: TimingBucket[]; best?: TimingBucket | null}) {
  return (
    <div className="grid gap-1">
      <p className="m-0 text-[0.6875rem] font-semibold text-muted-foreground">{title}</p>
      <div className="grid gap-1" style={{gridTemplateColumns: `repeat(${buckets.length}, minmax(0, 1fr))`}}>
        {buckets.map((b) => (
          <div key={b.label} className="relative overflow-hidden rounded-[0.4375rem] border px-1.5 py-1.5 text-center"
            title={b.ratio === null ? `${b.label}: no posts` : `${b.label}: ${b.ratio}x the usual engagement across ${b.posts} post(s)`}>
            <span aria-hidden className="absolute inset-0 bg-primary" style={{opacity: heat(b.ratio)}}/>
            <span className="relative block text-[0.6875rem] font-semibold">{b.label}</span>
            <span className="numeric relative block text-[0.625rem]">{b.ratio === null ? "—" : `${b.ratio}x`}</span>
            <span className="relative block text-[0.5625rem] text-foreground/70">{b.posts} post{b.posts === 1 ? "" : "s"}{best?.label === b.label ? " · best" : ""}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** When the audience reacts, as a multiple of the brand's own median engagement. */
export function TimingStrip({timing}: {timing: Timing}) {
  if (!timing.available || !timing.by_weekday || !timing.by_daypart) {
    return <p className="m-0 text-xs text-muted-foreground">{timing.note ?? "Not enough post history for timing hints yet."}</p>;
  }
  return (
    <div className="grid gap-3">
      <Strip title="By weekday" buckets={timing.by_weekday} best={timing.best_weekday}/>
      <Strip title="By time of day" buckets={timing.by_daypart} best={timing.best_daypart}/>
      <p className="m-0 text-[0.6875rem] text-muted-foreground">
        Engagement relative to the median post · {timing.tz} · {timing.posts} posts. Darker is stronger; “—” means no posts in that slot.
      </p>
    </div>
  );
}
