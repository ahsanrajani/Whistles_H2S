"use client";

import {
  Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import {ChartTooltip, GRID, TICK, TrendChart} from "@/components/charts/chart-kit";
import {AlertTriangle, Users2} from "lucide-react";
import {Badge} from "@/components/ui/badge";
import {Card} from "@/components/ui/card";
import {cn} from "@/lib/utils";

/**
 * Supervisor analytics overview -- Hamza handed over a full HTML mockup
 * ("need something like this for the care console, admin/supervisor
 * section") and asked for it built with dummy data: real volume isn't
 * there yet to compute most of this honestly (occupancy/utilization,
 * predictive forecasts, 14-day sentiment trend, compliance watchlist --
 * none of that exists as a real pipeline today). No on-screen "demo data"
 * label per Hamza's follow-up ("remove this bar") -- the caveat lives here
 * in code instead. Swap DEMO for a real fetch hook per-section as each
 * backing metric actually gets built; nothing
 * here should quietly start looking real.
 */

const tick = TICK;
const grid = <CartesianGrid {...GRID}/>;
const legend = <Legend iconType="circle" iconSize={8} wrapperStyle={{fontSize: 12, paddingTop: 10}}/>;
const barTip = <Tooltip content={<ChartTooltip heading={String}/>} cursor={{fill: "var(--muted)", opacity: 0.5}}/>;

function Kpi({label, value, sub, tone}: {label: string; value: string; sub?: string; tone?: "success" | "warning" | "danger"}) {
  return (
    <div className="rounded-[0.625rem] bg-muted/40 p-3">
      <p className="m-0 text-xs text-muted-foreground">{label}</p>
      <p className="numeric m-0 mt-1 text-2xl font-semibold">{value}</p>
      {sub && <p className={cn("m-0 mt-1 text-xs",
        tone === "success" ? "text-success" : tone === "warning" ? "text-warning" : tone === "danger" ? "text-danger" : "text-muted-foreground")}>
        {sub}
      </p>}
    </div>
  );
}

function SectionHead({title}: {title: string}) {
  return <h2 className="mb-1 mt-6 text-lg font-semibold tracking-tight first:mt-0">{title}</h2>;
}

// --- demo dataset -------------------------------------------------------
// Sized for a small social-care desk (about five agents, roughly sixty interactions a day), so the numbers read
// as a believable operation next to the seeded cases rather than a contact centre.
const CHANNEL_QUEUE = [
  {channel: "Facebook", waiting: 2, oldest: "9m", sla: 91},
  {channel: "Instagram", waiting: 1, oldest: "6m", sla: 96},
  {channel: "X / Twitter", waiting: 1, oldest: "8m", sla: 88},
  {channel: "LinkedIn", waiting: 1, oldest: "4m", sla: 98},
  {channel: "YouTube", waiting: 0, oldest: "—", sla: 99},
];
const HOURLY_VOLUME = ["8a", "9a", "10a", "11a", "12p", "1p", "2p", "3p", "4p", "5p", "6p", "7p", "8p"].map((hour, i) => ({
  hour,
  received: [2, 4, 5, 7, 6, 7, 8, 7, 6, 5, 4, 3, 2][i],
  resolved: [2, 3, 5, 6, 6, 7, 7, 6, 6, 5, 4, 3, 2][i],
}));
const SENTIMENT_TREND = Array.from({length: 14}, (_, i) => ({
  day: String(i + 1),
  positive: [31, 33, 30, 34, 36, 35, 33, 32, 34, 31, 26, 28, 30, 33][i],
  neutral: [50, 49, 52, 48, 47, 49, 50, 51, 48, 50, 47, 48, 49, 49][i],
  negative: [19, 18, 18, 18, 17, 16, 17, 17, 18, 19, 27, 24, 21, 18][i],
}));
const AGENT_STATUS = [
  {agent: "hira.agent", status: "On case", tone: "success" as const, load: "3 / 8", closed: 6, frt: "3m 04s"},
  {agent: "bilal.agent", status: "On case", tone: "success" as const, load: "2 / 8", closed: 5, frt: "4m 51s"},
  {agent: "sana.agent", status: "Available", tone: "highlight" as const, load: "1 / 8", closed: 7, frt: "2m 38s"},
  {agent: "omar.agent", status: "Break · 14m", tone: "warning" as const, load: "0 / 8", closed: 3, frt: "6m 12s"},
  {agent: "zainab.senior", status: "On case", tone: "success" as const, load: "3 / 6", closed: 6, frt: "3m 40s"},
];
const ISSUE_DRIVERS = [
  {label: "Card declined", n: 31}, {label: "App login failure", n: 27},
  {label: "ATM cash retained", n: 18}, {label: "Loan status query", n: 13},
  {label: "Branch service", n: 9},
];
const COMPLIANCE = [
  {label: "Regulatory complaints open", n: 3}, {label: "Breaching TAT in 24h", n: 1, danger: true},
  {label: "PII exposed in public thread", n: 0}, {label: "Phishing / fake page reports", n: 5},
  {label: "Case exports today", n: 2}, {label: "Profiles blocked this week", n: 2},
];
const STATE_BY_AGENT = [
  {agent: "hira.agent", Engaged: 326, "Wrap-up": 54, Available: 38, Break: 42, Offline: 20},
  {agent: "bilal.agent", Engaged: 298, "Wrap-up": 61, Available: 52, Break: 45, Offline: 24},
  {agent: "sana.agent", Engaged: 241, "Wrap-up": 44, Available: 121, Break: 48, Offline: 26},
  {agent: "omar.agent", Engaged: 196, "Wrap-up": 38, Available: 84, Break: 86, Offline: 76},
  {agent: "zainab.senior", Engaged: 341, "Wrap-up": 72, Available: 26, Break: 31, Offline: 10},
];
const CONCURRENCY = HOURLY_VOLUME.map((h, i) => ({
  hour: h.hour,
  concurrency: [0.6, 1.0, 1.4, 1.8, 1.6, 2.0, 2.2, 2.0, 1.8, 1.4, 1.1, 0.8, 0.5][i],
  queueDepth: [1, 2, 3, 4, 4, 5, 5, 4, 3, 3, 2, 1, 1][i],
}));
const LIFECYCLE = [
  {label: "Queued", value: "66", sub: "avg wait 4m 12s", tone: "default"},
  {label: "Assigned", value: "62", sub: "93.9% of queued", tone: "default"},
  {label: "On hold", value: "6", sub: "avg 3h 41m", tone: "warning"},
  {label: "Collaboration", value: "3", sub: "avg 52m to reply", tone: "warning"},
  {label: "Closed", value: "55", sub: "83.3% of queued", tone: "success"},
  {label: "Reopened", value: "3", sub: "5.5% of closed", tone: "default"},
];
const HOLD_REASONS = [
  {reason: "Awaiting branch confirmation", cases: 3, wait: "6h 12m"},
  {reason: "Awaiting fraud team", cases: 2, wait: "2h 48m"},
  {reason: "Awaiting customer documents", cases: 2, wait: "9h 05m"},
  {reason: "Awaiting IT / app team", cases: 1, wait: "4h 33m"},
  {reason: "Supervisor approval", cases: 1, wait: "41m"},
];
const FLOW_QUALITY: {label: string; n: string; danger?: boolean}[] = [
  {label: "Cases merged (duplicate prevented)", n: "9"}, {label: "Merge accuracy (sampled)", n: "96.1%"},
  {label: "Reassigned at least once", n: "7"}, {label: "Reassigned 3+ times (ping-pong)", n: "1"},
  {label: "Reopened within 24h", n: "3"}, {label: "Escalated to complaint register", n: "2"},
];
const COVERAGE_BY_CHANNEL = [
  {channel: "Facebook", eligible: 38, actioned: 36, missed: 2, coverage: 94.7},
  {channel: "Instagram", eligible: 30, actioned: 29, missed: 1, coverage: 96.7},
  {channel: "X / Twitter", eligible: 24, actioned: 22, missed: 2, coverage: 91.7},
  {channel: "LinkedIn", eligible: 12, actioned: 12, missed: 0, coverage: 100},
  {channel: "YouTube", eligible: 8, actioned: 8, missed: 0, coverage: 100},
];
const PREDICTIVE = [
  {label: "SLA breaches predicted", value: "2", sub: "Next 60 minutes", conf: "Confidence 0.81 · model v4.2", tone: "warning"},
  {label: "Cases at escalation risk", value: "2", sub: "Sentiment declining mid-case", conf: "Confidence 0.74 · model v4.2", tone: "warning"},
  {label: "Negative spike probability", value: "24%", sub: "Next 4h, app login topic", conf: "Confidence 0.68 · model v2.1", tone: "default"},
  {label: "Staffing gap", value: "−1", sub: "Agent short, 14:00–16:00", conf: "Erlang-A forecast · MAPE 7.4%", tone: "warning"},
  {label: "Predicted CSAT", value: "4.1", sub: "End of day, vs 4.3 actual now", conf: "Confidence 0.77 · model v3.0", tone: "default"},
  {label: "Forecast volume", value: "74", sub: "Full day, 12% above 4-week avg", conf: "Confidence 0.86 · MAPE 5.1%", tone: "default"},
];
const FORECAST = HOURLY_VOLUME.map((h, i) => ({
  hour: h.hour,
  actual: i <= 5 ? h.received : null,
  forecast: [2, 4, 5, 7, 7, 8, 9, 8, 7, 6, 4, 3, 2][i],
  scheduled: [4, 6, 8, 8, 6, 8, 8, 8, 8, 8, 6, 4, 3][i],
}));

const SLA_TONE = (sla: number) => (sla >= 90 ? "success" : sla >= 80 ? "warning" : "danger");
const toneText: Record<string, string> = {
  success: "text-success", warning: "text-warning", danger: "text-danger",
  highlight: "text-highlight", default: "text-foreground",
};

export function SupervisorAnalytics() {
  return (
    <div className="grid gap-4">
      <div className="grid grid-cols-2 gap-2 rounded-[0.75rem] border bg-card p-3 sm:grid-cols-3 lg:grid-cols-6">
        <Kpi label="Interactions today" value="66" sub="↗ 8% vs yesterday" tone="success"/>
        <Kpi label="In queue now" value="5" sub="Oldest waiting 9m"/>
        <Kpi label="Avg first response" value="4m 12s" sub="Target 5m · p90 11m"/>
        <Kpi label="SLA compliance" value="94.2%" sub="1 at risk in 15m" tone="success"/>
        <Kpi label="Avg handling time" value="9m 47s" sub="Excl. hold time"/>
        <Kpi label="CSAT" value="4.3 / 5" sub="58 responses"/>
      </div>

      <Card>
        <h3 className="m-0 mb-2 text-sm font-semibold">Queue health by channel</h3>
        <table className="w-full border-collapse text-left text-sm">
          <thead><tr className="border-b text-xs text-muted-foreground">
            <th className="py-2">Channel</th><th className="py-2 text-right">Waiting</th>
            <th className="py-2 text-right">Oldest</th><th className="py-2 pl-3">SLA</th>
          </tr></thead>
          <tbody>
            {CHANNEL_QUEUE.map((r) => (
              <tr key={r.channel} className="border-b last:border-0">
                <td className="py-2.5">{r.channel}</td>
                <td className="numeric py-2.5 text-right">{r.waiting}</td>
                <td className="numeric py-2.5 text-right text-muted-foreground">{r.oldest}</td>
                <td className="py-2.5 pl-3">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
                      <div className={cn("h-full rounded-full",
                        SLA_TONE(r.sla) === "success" ? "bg-success" : SLA_TONE(r.sla) === "warning" ? "bg-warning" : "bg-danger")}
                        style={{width: `${r.sla}%`}}/>
                    </div>
                    <span className="text-xs text-muted-foreground">{r.sla}% within SLA</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card>
        <h3 className="m-0 mb-2 text-sm font-semibold">Interaction volume by hour</h3>
        <div className="h-56 w-full">
          <ResponsiveContainer>
            <BarChart data={HOURLY_VOLUME} margin={{top: 8, right: 12, left: -20, bottom: 0}}>
              {grid}
              <XAxis dataKey="hour" tick={tick}/>
              <YAxis tick={tick}/>
              {barTip}
              {legend}
              <Bar dataKey="received" name="Received" fill="var(--chart-1)" radius={[6, 6, 0, 0]} maxBarSize={18}/>
              <Bar dataKey="resolved" name="Resolved" fill="var(--chart-2)" radius={[6, 6, 0, 0]} maxBarSize={18}/>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card>
        <h3 className="m-0 mb-2 text-sm font-semibold">Sentiment trend — last 14 days</h3>
        <TrendChart data={SENTIMENT_TREND} xKey="day" xFormat={(v) => `Day ${v}`} yDomain={[0, 60]} semantic height="13rem"
          format={(v) => `${Math.round(Number(v))}%`}
          series={[{key: "positive", label: "Positive", color: "var(--success)", focus: true}, {key: "neutral", label: "Neutral", color: "var(--muted-foreground)"},
            {key: "negative", label: "Negative", color: "var(--danger)"}]}/>
        <div className="mt-3 flex items-start gap-2 rounded-[0.625rem] bg-warning/10 p-3">
          <AlertTriangle size={16} className="mt-0.5 shrink-0 text-warning"/>
          <div>
            <p className="m-0 text-sm font-semibold text-warning">Anomaly detected — mobile app login</p>
            <p className="m-0 mt-0.5 text-xs text-warning">Negative mentions up 85% vs 14-day baseline, concentrated 13:00–15:00</p>
          </div>
        </div>
      </Card>

      <Card>
        <h3 className="m-0 mb-2 text-sm font-semibold">Agent status board</h3>
        <table className="w-full border-collapse text-left text-sm">
          <thead><tr className="border-b text-xs text-muted-foreground">
            <th className="py-2">Agent</th><th className="py-2">Status</th>
            <th className="py-2 text-right">Load</th><th className="py-2 text-right">Closed · FRT</th>
          </tr></thead>
          <tbody>
            {AGENT_STATUS.map((a) => (
              <tr key={a.agent} className="border-b last:border-0">
                <td className="py-2.5">{a.agent}</td>
                <td className="py-2.5"><Badge className={toneText[a.tone]}>{a.status}</Badge></td>
                <td className="numeric py-2.5 text-right">{a.load}</td>
                <td className="numeric py-2.5 text-right text-muted-foreground">{a.closed} · {a.frt}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <h3 className="m-0 mb-2 text-sm font-semibold">Top issue drivers</h3>
          <div className="grid gap-2.5">
            {ISSUE_DRIVERS.map((d) => (
              <div key={d.label}>
                <div className="flex items-center justify-between text-sm"><span>{d.label}</span><span className="numeric text-muted-foreground">{d.n}</span></div>
                <div className="mt-1 h-1 overflow-hidden rounded-full bg-muted">
                  <div className="h-full rounded-full bg-primary" style={{width: `${(d.n / ISSUE_DRIVERS[0].n) * 100}%`}}/>
                </div>
              </div>
            ))}
          </div>
        </Card>
        <Card>
          <h3 className="m-0 mb-2 text-sm font-semibold">Compliance watchlist</h3>
          <table className="w-full border-collapse text-left text-sm">
            <tbody>
              {COMPLIANCE.map((c) => (
                <tr key={c.label} className="border-b last:border-0">
                  <td className="py-2 text-muted-foreground">{c.label}</td>
                  <td className={cn("numeric py-2 text-right", c.danger && "font-semibold text-danger")}>{c.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      <SectionHead title="Agent activity and utilization"/>
      <div className="grid grid-cols-2 gap-2 rounded-[0.75rem] border bg-card p-3 sm:grid-cols-3 lg:grid-cols-6">
        <Kpi label="Occupancy" value="78.4%" sub="Engaged ÷ logged-in time"/>
        <Kpi label="Utilization" value="64.1%" sub="Concurrency-weighted"/>
        <Kpi label="Schedule adherence" value="91.2%" sub="1 agent below 80%" tone="warning"/>
        <Kpi label="Idle while queue deep" value="6m" sub="Across 1 agent today" tone="warning"/>
        <Kpi label="Avg concurrent load" value="1.6 / 8" sub="Peak 2.2 at 14:00"/>
        <Kpi label="Wrap-up time" value="1m 22s" sub="18% of handling time"/>
      </div>

      <Card>
        <h3 className="m-0 mb-2 text-sm font-semibold">Time in state by agent — shift to date</h3>
        <div className="h-72 w-full">
          <ResponsiveContainer>
            <BarChart data={STATE_BY_AGENT} layout="vertical" margin={{top: 8, right: 12, left: 8, bottom: 0}}>
              {grid}
              <XAxis type="number" tick={tick} tickFormatter={(v) => `${v}m`}/>
              <YAxis type="category" dataKey="agent" tick={tick} width={90}/>
              <Tooltip content={<ChartTooltip heading={String} format={(v) => `${v} min`}/>} cursor={{fill: "var(--muted)", opacity: 0.5}}/>
              {legend}
              <Bar dataKey="Engaged" stackId="s" fill="var(--chart-1)"/>
              <Bar dataKey="Wrap-up" stackId="s" fill="var(--chart-4)"/>
              <Bar dataKey="Available" stackId="s" fill="var(--chart-3)"/>
              <Bar dataKey="Break" stackId="s" fill="var(--chart-5)"/>
              <Bar dataKey="Offline" stackId="s" fill="var(--chart-6)" radius={[0, 6, 6, 0]}/>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card>
        <h3 className="m-0 mb-2 text-sm font-semibold">Concurrency vs queue depth — today</h3>
        <TrendChart data={CONCURRENCY} xKey="hour" xFormat={String} height="13rem" allowDecimals
          format={(v) => (Number.isInteger(Number(v)) ? String(v) : Number(v).toFixed(1))}
          series={[{key: "concurrency", label: "Avg concurrent cases / agent", focus: true}, {key: "queueDepth", label: "Queue depth"}]}/>
        <p className="m-0 mt-2 text-xs text-muted-foreground">Concurrency caps out before queue depth peaks — the constraint is headcount, not agent capacity.</p>
      </Card>

      <SectionHead title="Case lifecycle"/>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {LIFECYCLE.map((s) => (
          <div key={s.label} className={cn("rounded-[0.625rem] border-l-[0.1875rem] bg-muted/40 p-3",
            s.tone === "success" ? "border-l-success" : s.tone === "warning" ? "border-l-warning"
            : s.tone === "danger" ? "border-l-danger" : "border-l-primary")}>
            <p className="m-0 text-xs text-muted-foreground">{s.label}</p>
            <p className="numeric m-0 mt-1 text-xl font-semibold">{s.value}</p>
            <p className="m-0 mt-0.5 text-[0.6875rem] text-muted-foreground">{s.sub}</p>
          </div>
        ))}
      </div>

      <Card>
        <h3 className="m-0 mb-1 text-sm font-semibold">Where the time goes — average per case</h3>
        <div className="mt-2 flex h-8 w-full overflow-hidden rounded-[0.375rem]">
          {[
            {label: "Waiting in queue", min: 4, color: "#F59E0B"}, {label: "Agent engaged", min: 10, color: "#6D5EF6"},
            {label: "On hold", min: 98, color: "var(--accent)"}, {label: "Awaiting collaboration", min: 52, color: "var(--accent-2)"},
            {label: "Awaiting customer", min: 94, color: "#94A3B8"},
          ].map((seg) => (
            <div key={seg.label} title={`${seg.label}: ${seg.min}m`} style={{width: `${(seg.min / 258) * 100}%`, background: seg.color}}/>
          ))}
        </div>
        <p className="m-0 mt-2 text-xs text-muted-foreground">Handling time is 9m 47s but total case duration averages 4h 18m — the gap is hold and collaboration, not agent effort.</p>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <h3 className="m-0 mb-2 text-sm font-semibold">Hold and collaboration reasons</h3>
          <table className="w-full border-collapse text-left text-sm">
            <thead><tr className="border-b text-xs text-muted-foreground">
              <th className="py-2">Reason</th><th className="py-2 text-right">Cases</th><th className="py-2 text-right">Avg wait</th>
            </tr></thead>
            <tbody>
              {HOLD_REASONS.map((h) => (
                <tr key={h.reason} className="border-b last:border-0">
                  <td className="py-2">{h.reason}</td>
                  <td className="numeric py-2 text-right">{h.cases}</td>
                  <td className="numeric py-2 text-right text-muted-foreground">{h.wait}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card>
          <h3 className="m-0 mb-2 text-sm font-semibold">Flow quality</h3>
          <table className="w-full border-collapse text-left text-sm">
            <tbody>
              {FLOW_QUALITY.map((f) => (
                <tr key={f.label} className="border-b last:border-0">
                  <td className="py-2 text-muted-foreground">{f.label}</td>
                  <td className={cn("numeric py-2 text-right", f.danger && "font-semibold text-danger")}>{f.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      <SectionHead title="Coverage and missed interactions"/>
      <div className="grid grid-cols-2 gap-2 rounded-[0.75rem] border bg-card p-3 sm:grid-cols-3 lg:grid-cols-6">
        <Kpi label="Eligible inbound" value="74" sub="After spam and bot filtering"/>
        <Kpi label="Actioned" value="94.6%" sub="70 of 74"/>
        <Kpi label="Never actioned" value="4" sub="5.4% of eligible" tone="warning"/>
        <Kpi label="Expired mentions" value="1" sub="Past reply window" tone="warning"/>
        <Kpi label="Negative left standing" value="2" sub="9.4k cumulative reach" tone="warning"/>
        <Kpi label="Public page response rate" value="92%" sub="Platform-reported"/>
      </div>

      <Card>
        <h3 className="m-0 mb-2 text-sm font-semibold">Coverage by channel</h3>
        <table className="w-full border-collapse text-left text-sm">
          <thead><tr className="border-b text-xs text-muted-foreground">
            <th className="py-2">Channel</th><th className="py-2 text-right">Eligible</th>
            <th className="py-2 text-right">Actioned</th><th className="py-2 text-right">Missed</th><th className="py-2">Coverage</th>
          </tr></thead>
          <tbody>
            {COVERAGE_BY_CHANNEL.map((r) => (
              <tr key={r.channel} className="border-b last:border-0">
                <td className="py-2.5">{r.channel}</td>
                <td className="numeric py-2.5 text-right">{r.eligible.toLocaleString()}</td>
                <td className="numeric py-2.5 text-right">{r.actioned.toLocaleString()}</td>
                <td className={cn("numeric py-2.5 text-right", r.missed > 50 && "font-semibold text-danger")}>{r.missed}</td>
                <td className="py-2.5">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
                      <div className={cn("h-full rounded-full", r.coverage >= 95 ? "bg-success" : "bg-warning")} style={{width: `${r.coverage}%`}}/>
                    </div>
                    <span className="text-xs text-muted-foreground">{r.coverage}%</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="m-0 mt-3 text-xs text-muted-foreground">Missed items are counted against what the channel API delivered, not against what reached the queue — ingestion failures surface here, not as silence.</p>
      </Card>

      <SectionHead title="Predictive outlook"/>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {PREDICTIVE.map((p) => (
          <div key={p.label} className={cn("rounded-[0.625rem] border-l-[0.1875rem] bg-muted/40 p-3",
            p.tone === "danger" ? "border-l-danger" : p.tone === "warning" ? "border-l-warning" : "border-l-border")}>
            <p className="m-0 text-xs text-muted-foreground">{p.label}</p>
            <p className="numeric m-0 mt-1 text-xl font-semibold">{p.value}</p>
            <p className="m-0 mt-0.5 text-[0.6875rem] text-muted-foreground">{p.sub}</p>
            <p className="m-0 mt-1 text-[0.625rem] text-muted-foreground/70">{p.conf}</p>
          </div>
        ))}
      </div>

      <Card>
        <h3 className="m-0 mb-2 text-sm font-semibold">Forecast demand vs scheduled capacity</h3>
        <TrendChart data={FORECAST} xKey="hour" xFormat={String} height="14rem"
          series={[{key: "actual", label: "Actual received", focus: true}, {key: "forecast", label: "Forecast demand"}, {key: "scheduled", label: "Scheduled capacity"}]}/>
        <div className="mt-3 flex items-start gap-2 rounded-[0.625rem] bg-danger/10 p-3">
          <Users2 size={16} className="mt-0.5 shrink-0 text-danger"/>
          <div>
            <p className="m-0 text-sm font-semibold text-danger">Capacity shortfall forecast — 14:00 to 16:00</p>
            <p className="m-0 mt-0.5 text-xs text-danger">Demand exceeds scheduled capacity by ~2 interactions. One additional agent or a deflection rule would cover it.</p>
          </div>
        </div>
      </Card>
    </div>
  );
}
