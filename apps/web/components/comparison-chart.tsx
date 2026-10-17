"use client";

import {Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis} from "recharts";
import {fmtDay, GRID, TICK, TOOLTIP_STYLE} from "@/components/charts/chart-kit";
import type {RatingTimeline} from "@/lib/types";

// 1★ … 5★ — CVD-safe ramp from danger through warning to success.
const STAR_COLOR: Record<string, string> = {
  "1": "#F43F5E", "2": "#FB923C", "3": "#F59E0B", "4": "#A3B18A", "5": "#10B981",
};

/**
 * Two panels sharing an X axis: (left) rolling mean daily rating, (right)
 * rolling share of new ratings by star.
 */
export function ComparisonChart({timeline}: {timeline: RatingTimeline}) {
  if (!timeline.has_data) {
    return <p className="py-20 text-center text-sm text-muted-foreground">Not enough dated reviews for a rolling view yet.</p>;
  }
  const rows = timeline.axis.map((date, i) => ({
    date,
    avg: timeline.roll_avg[i],
    n: timeline.roll_n[i],
    s1: timeline.roll_share["1"][i], s2: timeline.roll_share["2"][i],
    s3: timeline.roll_share["3"][i], s4: timeline.roll_share["4"][i],
    s5: timeline.roll_share["5"][i],
  }));

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <figure className="m-0">
        <figcaption className="mb-2 text-xs font-semibold text-muted-foreground">
          {timeline.window}-day rolling average of daily rating (1–5)
        </figcaption>
        <div className="h-56 w-full">
          <ResponsiveContainer>
            <AreaChart data={rows} margin={{top: 8, right: 12, left: -20, bottom: 0}}>
              <CartesianGrid {...GRID}/>
              <XAxis dataKey="date" tick={TICK} tickFormatter={fmtDay} minTickGap={34} tickLine={false} axisLine={false} tickMargin={8}/>
              <YAxis domain={[1, 5]} ticks={[1, 2, 3, 4, 5]} tick={TICK} tickLine={false} axisLine={false} width={40}/>
              <Tooltip contentStyle={TOOLTIP_STYLE}
                formatter={(v) => [Number(v).toFixed(2), "rolling rating"]}/>
              <Area type="monotone" dataKey="avg" stroke="var(--chart-1)" fill="var(--chart-1)" fillOpacity={0.14} strokeWidth={2.75} connectNulls/>

            </AreaChart>
          </ResponsiveContainer>
        </div>
      </figure>

      <figure className="m-0">
        <figcaption className="mb-2 text-xs font-semibold text-muted-foreground">
          {timeline.window}-day rolling share of new ratings, by star
        </figcaption>
        <div className="h-56 w-full">
          <ResponsiveContainer>
            <AreaChart data={rows} margin={{top: 8, right: 12, left: -20, bottom: 0}} stackOffset="expand">
              <CartesianGrid {...GRID}/>
              <XAxis dataKey="date" tick={TICK} tickFormatter={fmtDay} minTickGap={34} tickLine={false} axisLine={false} tickMargin={8}/>
              <YAxis domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} tick={TICK} tickLine={false} axisLine={false} width={40}/>
              <Tooltip contentStyle={TOOLTIP_STYLE}
                formatter={(v, n) => [`${(Number(v) * 100).toFixed(0)}%`, `${String(n).replace("s", "")}★`]}/>
              {["s1", "s2", "s3", "s4", "s5"].map((k) => (
                <Area key={k} type="monotone" dataKey={k} stackId="share"
                  stroke={STAR_COLOR[k.slice(1)]} fill={STAR_COLOR[k.slice(1)]} fillOpacity={0.75} strokeWidth={0} connectNulls/>
              ))}

            </AreaChart>
          </ResponsiveContainer>
        </div>
      </figure>
    </div>
  );
}
