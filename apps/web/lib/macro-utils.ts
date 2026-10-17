import type {MacroAction, MacroPriority, MacroStatus, MacroTrigger} from "@/lib/types";

// Display-only helpers for the macro admin UI. What a macro *does* (rendering,
// running actions, firing rules) is all server-side; this only labels it.

export const MACRO_CATEGORIES = ["greeting", "apology", "follow-up", "closure", "general"];
export const STATUSES: MacroStatus[] = ["open", "assigned", "in_progress", "internal_hold", "pending_approval", "closed"];
export const PRIORITIES: MacroPriority[] = ["low", "normal", "high", "urgent"];
export const CLOSURE_CATEGORIES = ["resolved", "no_response", "duplicate", "not_actionable", "escalated", "spam"];
export const MAX_QUICK = 8;
export const MAX_ACTIONS = 10;

export const PLACEHOLDERS: {key: string; label: string}[] = [
  {key: "customer.first_name", label: "First name"},
  {key: "customer.name", label: "Full name"},
  {key: "customer.handle", label: "Handle"},
  {key: "agent.name", label: "Agent"},
  {key: "case.id", label: "Case #"},
];

export const CHANNELS: {key: string; label: string}[] = [
  {key: "facebook", label: "Facebook comments"},
  {key: "instagram", label: "Instagram comments"},
  {key: "messenger", label: "Messenger DMs"},
  {key: "instagram_dm", label: "Instagram DMs"},
];

export const ACTION_LABEL: Record<MacroAction["type"], string> = {
  set_status: "Set status",
  assign: "Assign",
  add_note: "Add internal note",
  set_priority: "Set priority",
  add_tags: "Add tags",
};

export const humanize = (s: string) => s.replaceAll("_", " ");

export function newAction(type: MacroAction["type"]): MacroAction {
  switch (type) {
    case "set_status": return {type, status: "in_progress"};
    case "assign": return {type, mode: "self"};
    case "add_note": return {type, body: ""};
    case "set_priority": return {type, priority: "high"};
    default: return {type: "add_tags", tags: []};
  }
}

export function describeAction(a: MacroAction, agentName?: (id: number) => string): string {
  switch (a.type) {
    case "set_status": return `Set status to ${humanize(a.status)}${a.closure_category ? ` (${humanize(a.closure_category)})` : ""}`;
    case "assign":
      return a.mode === "self" ? "Assign to me"
        : a.mode === "auto" ? "Assign to next available agent"
        : `Assign to ${a.user_id != null ? (agentName?.(a.user_id) ?? `agent #${a.user_id}`) : "an agent"}`;
    case "add_note": return "Add internal note";
    case "set_priority": return `Set priority to ${a.priority}`;
    default: return `Add tags: ${a.tags.join(", ") || "—"}`;
  }
}

const mins = (n: number) => (n % 60 === 0 && n >= 60 ? `${n / 60} hr` : `${n} min`);

export function describeTrigger(t: MacroTrigger): string {
  switch (t.type) {
    case "new_case": return "A new case opens";
    case "sla_breach": return "SLA is breached";
    case "no_response": return `No agent reply for ${mins(t.minutes)}`;
    case "unassigned_for": return `Unassigned for ${mins(t.minutes)}`;
    default: return `Customer message mentions ${t.words.map((w) => `“${w}”`).join(" / ")}`;
  }
}

/** Sample render of a body for the editor's preview line. The real render (with
 * the customer's actual details) is done by the server when a macro is picked. */
export function sampleRender(body: string): string {
  const sample: Record<string, string> = {
    "customer.first_name": "Sara", "customer.name": "Sara Khan", "customer.handle": "sara.khan",
    "agent.name": "Ali", "case.id": "1042",
  };
  return body.replace(/\{\{\s*([A-Za-z_.]+)\s*(?:\|([^{}]*))?\}\}/g, (m, key: string) => sample[key] ?? m);
}
