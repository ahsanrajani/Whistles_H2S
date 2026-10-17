"use client";

import {
  AgentAvatar, CaseCard, ChannelBadge, MessageBubble, PresenceDot, SentimentPill,
  SlaChip, type Channel, type Presence, type Sentiment,
} from "@/components/care/primitives";
import {Card} from "@/components/ui/card";

const CHANNELS: Channel[] = ["facebook", "instagram", "x", "google_reviews", "youtube", "linkedin", "whatsapp"];
const SENTIMENTS: Sentiment[] = ["pos", "neu", "neg"];
const PRESENCES: Presence[] = ["online", "idle", "offline", "unknown"];

function Row({title, children}: {title: string; children: React.ReactNode}) {
  return (
    <Card className="grid gap-3">
      <h2 className="m-0 text-sm font-semibold text-muted-foreground">{title}</h2>
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </Card>
  );
}

export default function CarePrimitivesPage() {
  return (
    <div className="mx-auto grid max-w-[68.75rem] gap-5">
      <div>
        <p className="mb-0.5 text-sm font-semibold text-primary dark:text-highlight">F0.5</p>
        <h1 className="m-0 text-2xl font-semibold tracking-tight">Care primitives</h1>
        <p className="text-sm text-muted-foreground">
          Shared building blocks for the agent (F1) and supervisor (F2) consoles.
          Studio Duotone tokens only.
        </p>
      </div>

      <Row title="ChannelBadge">
        {CHANNELS.map((c) => <ChannelBadge key={c} channel={c}/>)}
      </Row>

      <Row title="SentimentPill">
        {SENTIMENTS.map((s) => <SentimentPill key={s} sentiment={s}/>)}
      </Row>

      <Row title="SlaChip">
        <SlaChip secondsLeft={1800}/>
        <SlaChip secondsLeft={120}/>
        <SlaChip breached/>
        <SlaChip state="none"/>
      </Row>

      <Row title="PresenceDot">
        {PRESENCES.map((p) => (
          <span key={p} className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            <PresenceDot presence={p}/>{p}
          </span>
        ))}
      </Row>

      <Row title="AgentAvatar">
        <AgentAvatar name="Ayesha Khan" presence="online"/>
        <AgentAvatar name="Bilal Ahmed" presence="idle"/>
        <AgentAvatar name="Chandni" presence="offline" size="sm"/>
        <AgentAvatar name="Dev Ops"/>
      </Row>

      <Card className="grid gap-3">
        <h2 className="m-0 text-sm font-semibold text-muted-foreground">MessageBubble</h2>
        <div className="grid gap-2">
          <MessageBubble direction="inbound" channel="facebook" author="Ayesha Khan"
            at="2026-06-15T09:00:00Z" body="My card keeps getting declined at the ATM."/>
          <MessageBubble direction="outbound" author="Agent · Bilal"
            at="2026-06-15T09:05:00Z" body="Sorry to hear that — can you share the last 4 digits so I can check?"/>
          <MessageBubble direction="note" author="Supervisor"
            at="2026-06-15T09:06:00Z" body="Card flagged by fraud rules this morning — see ticket 4821."/>
        </div>
      </Card>

      <Card className="grid gap-3">
        <h2 className="m-0 text-sm font-semibold text-muted-foreground">CaseCard</h2>
        <div className="grid gap-2 md:grid-cols-2">
          <CaseCard caseId={101} customer="Ayesha Khan" channel="facebook"
            sentiment="neg" sla={{secondsLeft: 90}} waitingSeconds={640}
            assignee="Bilal Ahmed" presence="online"/>
          <CaseCard caseId={102} customer="Omar Farooq" channel="x"
            sentiment="neu" sla={{secondsLeft: 5400}} waitingSeconds={120} active/>
          <CaseCard caseId={103} customer="Sana Malik" channel="google_reviews"
            sentiment="pos" sla={{breached: true}} waitingSeconds={7200}/>
          <CaseCard caseId={104} customer="Hassan Raza" channel="instagram"
            sla={{state: "none"}} waitingSeconds={30} assignee="Chandni" presence="idle"/>
        </div>
      </Card>
    </div>
  );
}
