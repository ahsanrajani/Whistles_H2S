"use client";

import {
  AtSign, Clock, ExternalLink, Facebook, Instagram, Linkedin, MapPin, MessageCircle,
  StickyNote, Youtube,
} from "lucide-react";
import type {ReactNode} from "react";
import {Link} from "@/components/tenant-link";
import {cn} from "@/lib/utils";

/**
 * Shared care display primitives (F0.5). Used by the agent console (F1) and the
 * supervisor console (F2). Studio Duotone tokens only — no hardcoded colour.
 */

// ---------------------------------------------------------------- ChannelBadge
export type Channel =
  | "facebook" | "instagram" | "x" | "google_reviews" | "youtube"
  | "linkedin" | "whatsapp" | string;

const CHANNEL_META: Record<string, {label: string; Icon: typeof AtSign}> = {
  facebook: {label: "Facebook", Icon: Facebook},
  instagram: {label: "Instagram", Icon: Instagram},
  x: {label: "X", Icon: AtSign},
  google_reviews: {label: "Google", Icon: MapPin},
  youtube: {label: "YouTube", Icon: Youtube},
  linkedin: {label: "LinkedIn", Icon: Linkedin},
  whatsapp: {label: "WhatsApp", Icon: MessageCircle},
};

export function ChannelBadge({channel, className}: {channel: Channel; className?: string}) {
  const meta = CHANNEL_META[channel] ?? {label: channel || "Channel", Icon: MessageCircle};
  const Icon = meta.Icon;
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border bg-muted px-2 py-0.5 text-[0.6875rem] font-semibold text-muted-foreground", className)}>
      <Icon size={12}/>{meta.label}
    </span>
  );
}

// ---------------------------------------------------------------- SentimentPill
export type Sentiment = "pos" | "neu" | "neg";

const SENTIMENT_META: Record<Sentiment, {label: string; cls: string}> = {
  pos: {label: "Positive", cls: "border-success/30 text-success"},
  neu: {label: "Neutral", cls: "text-muted-foreground"},
  neg: {label: "Negative", cls: "border-danger/30 text-danger"},
};

export function SentimentPill({sentiment, className}: {sentiment: Sentiment; className?: string}) {
  const meta = SENTIMENT_META[sentiment];
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[0.6875rem] font-semibold", meta.cls, className)}>
      {meta.label}
    </span>
  );
}

// -------------------------------------------------------------------- SlaChip
export type SlaState = "ok" | "at_risk" | "breached" | "none";

function slaState(input: {state?: SlaState; secondsLeft?: number | null; breached?: boolean}): SlaState {
  if (input.state) return input.state;
  if (input.breached) return "breached";
  if (input.secondsLeft == null) return "none";
  if (input.secondsLeft <= 0) return "breached";
  return input.secondsLeft <= 300 ? "at_risk" : "ok";
}

function humanDuration(seconds: number): string {
  const s = Math.abs(Math.round(seconds));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  if (s < 86400) return `${Math.round(s / 3600)}h`;
  return `${Math.round(s / 86400)}d`;
}

const SLA_CLS: Record<SlaState, string> = {
  ok: "border-success/30 text-success",
  at_risk: "border-warning/40 text-warning",
  breached: "border-danger/40 text-danger",
  none: "text-muted-foreground",
};

export function SlaChip({state, secondsLeft, breached, className}: {
  state?: SlaState; secondsLeft?: number | null; breached?: boolean; className?: string;
}) {
  const resolved = slaState({state, secondsLeft, breached});
  const label =
    resolved === "breached" ? "SLA breached"
    : resolved === "none" ? "No SLA"
    : `SLA ${humanDuration(secondsLeft ?? 0)}`;
  return (
    <span aria-live="polite" className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[0.6875rem] font-semibold", SLA_CLS[resolved], className)}>
      <Clock size={12}/>{label}
    </span>
  );
}

// ----------------------------------------------------------------- PresenceDot
export type Presence = "online" | "idle" | "offline" | "unknown";

const PRESENCE_CLS: Record<Presence, string> = {
  online: "bg-success",
  idle: "bg-warning",
  offline: "bg-muted-foreground/40",
  unknown: "border border-border bg-transparent",
};

export function PresenceDot({presence, className}: {presence: Presence; className?: string}) {
  return (
    <span
      role="img"
      aria-label={`${presence} presence`}
      className={cn("inline-block size-2 rounded-full", PRESENCE_CLS[presence], className)}
    />
  );
}

// ----------------------------------------------------------------- AgentAvatar
function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function AgentAvatar({name, presence, size = "md", className}: {
  name: string; presence?: Presence; size?: "sm" | "md"; className?: string;
}) {
  const box = size === "sm" ? "size-6 text-[0.625rem]" : "size-8 text-xs";
  return (
    <span className={cn("relative inline-flex shrink-0", className)}>
      <span className={cn("inline-flex items-center justify-center rounded-full bg-primary/10 font-semibold text-primary dark:text-highlight", box)}>
        {initials(name)}
      </span>
      {presence && (
        <PresenceDot
          presence={presence}
          className="absolute -bottom-0.5 -right-0.5 ring-2 ring-card"
        />
      )}
    </span>
  );
}

// ---------------------------------------------------------------- MessageBubble
export type MessageDirection = "inbound" | "outbound" | "note";

export function MessageBubble({direction, body, author, at, channel, permalink, className}: {
  direction: MessageDirection;
  body: string;
  author?: string | null;
  at?: string | null;
  channel?: Channel;
  permalink?: string | null;
  className?: string;
}) {
  if (direction === "note") {
    return (
      <div className={cn("rounded-card border border-warning/40 bg-warning/10 p-3", className)}>
        <div className="mb-1 flex items-center gap-1.5 text-[0.6875rem] font-bold uppercase tracking-[.14em] text-warning">
          <StickyNote size={12}/>Internal note
        </div>
        <p className="m-0 whitespace-pre-wrap text-sm">{body}</p>
        <Meta author={author} at={at}/>
      </div>
    );
  }
  const outbound = direction === "outbound";
  return (
    <div className={cn("flex", outbound ? "justify-end" : "justify-start", className)}>
      <div className={cn(
        "max-w-[80%] rounded-card border p-3",
        outbound ? "bg-primary/10" : "bg-card",
      )}>
        {channel && (
          <div className="mb-1.5 flex items-center gap-1.5">
            <ChannelBadge channel={channel}/>
            {permalink && (
              <a href={permalink} target="_blank" rel="noreferrer"
                className="inline-flex items-center gap-1 text-[0.6875rem] font-semibold text-primary hover:underline dark:text-highlight"
                title="Open the source comment/post/review">
                View original<ExternalLink size={11}/>
              </a>
            )}
          </div>
        )}
        <p className="m-0 whitespace-pre-wrap text-sm">{body}</p>
        <Meta author={author} at={at}/>
      </div>
    </div>
  );
}

function Meta({author, at}: {author?: string | null; at?: string | null}) {
  if (!author && !at) return null;
  return (
    <p className="m-0 mt-1.5 text-[0.6875rem] text-muted-foreground">
      {author ?? "—"}{at ? ` · ${new Date(at).toLocaleString()}` : ""}
    </p>
  );
}

// -------------------------------------------------------------------- CaseCard
export type CasePriority = "high" | "elevated" | "normal";

export type CaseCardProps = {
  caseId: number;
  customer: string;
  channel: Channel;
  sentiment?: Sentiment;
  sla?: {state?: SlaState; secondsLeft?: number | null; breached?: boolean};
  priority?: CasePriority;
  waitingSeconds?: number | null;
  assignee?: string | null;
  presence?: Presence;
  href?: string;
  active?: boolean;
  onSelect?: () => void;
};

const PRIORITY_BORDER: Record<CasePriority, string> = {
  high: "border-l-4 border-l-danger",
  elevated: "border-l-4 border-l-warning",
  normal: "",
};

export function CaseCard(props: CaseCardProps) {
  const {
    caseId, customer, channel, sentiment, sla, priority = "normal", waitingSeconds,
    assignee, presence, href, active, onSelect,
  } = props;

  const inner: ReactNode = (
    <div className={cn(
      "flex flex-col gap-2 rounded-card border p-3 text-left transition-colors",
      PRIORITY_BORDER[priority],
      active ? "border-primary/40 bg-primary/5" : "bg-card hover:bg-muted",
    )}>
      <div className="flex items-center gap-2">
        <span className="numeric text-xs font-semibold text-muted-foreground">C-{caseId}</span>
        <span className="truncate text-sm font-semibold">{customer}</span>
        {assignee
          ? <AgentAvatar name={assignee} presence={presence} size="sm" className="ml-auto"/>
          : <span className="ml-auto text-[0.6875rem] font-semibold text-warning">Unassigned</span>}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <ChannelBadge channel={channel}/>
        {sentiment && <SentimentPill sentiment={sentiment}/>}
        {sla && <SlaChip {...sla}/>}
        {waitingSeconds != null && (
          <span className="numeric ml-auto text-[0.6875rem] text-muted-foreground">
            waiting {humanDuration(waitingSeconds)}
          </span>
        )}
      </div>
    </div>
  );

  if (href) return <Link href={href} onClick={onSelect} aria-current={active ? "page" : undefined} className="block">{inner}</Link>;
  if (onSelect) return <button type="button" onClick={onSelect} aria-current={active ? "true" : undefined} className="block w-full">{inner}</button>;
  return inner;
}
