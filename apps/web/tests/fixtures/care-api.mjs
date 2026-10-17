// Isolated UX fixture server. No database, credentials, or provider transport.
import {createServer} from "node:http";

const workspace = {id: 999, slug: "ux-test", name: "Care UX fixture", market: "test", onboarding_step: 99};
const user = {id: 1, name: "Test operator", role: "admin", roles: ["admin"],
  perms: ["care:view", "care:edit", "care:approve", "templates:view"], workspace};
const at = "2026-09-14T08:00:00Z";
export function caseDetail(id) {
  return {
    case: {id, state: id === 202 ? "closed" : "in_progress", channel: "messenger", assignee_id: 1,
      opened_at: at, last_activity_at: at, first_response_at: null, closed_at: id === 202 ? at : null, closure_category: null},
    customer: {id, display_name: `Customer ${id}`, handle: `test-${id}`, platform: "facebook",
      email: `customer${id}@example.test`, phone: null, customer_since: null, preferred_name: null,
      other_handles: null, location: null, country: null, language: null, timezone: null,
      segment: null, account_status: null, vip: false, blocked: false, preferred_channel: null, tags: null, notes: null},
    messages: Array.from({length: 30}, (_, i) => ({direction: i % 2 ? "outbound" : "inbound",
      channel: "messenger", author: i % 2 ? "Test operator" : `Customer ${id}`,
      body: `Message ${i + 1}: Please help me with this request.`, sent_at: `2026-09-14T08:${String(i).padStart(2, "0")}:00Z`,
      platform_ref: `test-${id}-${i}`, permalink: null})),
    notes: [], timeline: [], history: id === 101 ? [{id: 202, state: "closed", channel: "messenger", opened_at: at, closed_at: at}] : [],
  };
}
const article = {id: 7, title: "Account access help", body: "Use the secure account recovery page.",
  published: true, tags: "account", updated_at: at};

const macros = [
  {id: 3, name: "Greeting", category: "general", body: "Hello from a canned response.", shortcut: "hi", description: null,
    is_quick: false, quick_order: 0, actions: [], active: true, updated_at: "2026-09-18T00:00:00Z"},
  {id: 4, name: "Refund ack", category: "apology", body: "We are looking into your refund.", shortcut: "refund", description: null,
    is_quick: true, quick_order: 1, actions: [{type: "set_priority", priority: "high"}], active: true, updated_at: "2026-09-18T00:00:00Z"},
];

// Same wording the API serves (core/routing.py::STRATEGIES) -- the console only renders it.
const strategies = [
  {key: "manual", label: "Manual", description: "Nothing is assigned automatically. New cases wait in the queue until an agent picks one up or a supervisor assigns it."},
  {key: "round_robin", label: "Round robin", description: "Agents take turns in a fixed order, each getting the next case in their turn regardless of how many they already hold."},
  {key: "least_busy", label: "Least busy", description: "The next case goes to the available agent with the fewest open cases."},
  {key: "longest_idle", label: "Longest idle (first in, first out)", description: "The agent who has waited longest since their last case goes next, then joins the back of the line."},
];
let strategy = "least_busy";
const assignmentRule = () => ({strategy, strategies, roles: ["agent", "senior_agent"], available_agents: 2, free_agents: 2, waiting_cases: 3, held_back_cases: 4});

const server = createServer(async (request, response) => {
  const url = new URL(request.url, "http://127.0.0.1:5100");
  const path = url.pathname.replace(/^\/api\/v1/, "");
  response.setHeader("Content-Type", "application/json");
  let data;
  if (path === "/auth/me") data = {user};
  else if (path === "/csrf") data = {token: "fixture-csrf"};
  else if (path === "/workspaces") data = {active: workspace, list: [workspace], can_switch: false};
  else if (path === "/projects") data = {projects: [{id: 1, slug: "social", name: "Social", kind: "social"}], active: "social"};
  else if (path === "/stats") data = {items: 30, mentions: 30, last_run: null};
  else if (path === "/care/session") data = {state: "ready", reason: null};
  else if (path === "/care/heartbeat" || path === "/auth/activity") data = {ok: true};
  else if (path === "/care/agents") data = {agents: [{user_id: 1, username: "Test operator", live: 1, capacity: 5}]};
  else if (path === "/macros") data = {macros: macros};
  else if (path === "/care/roster") data = {agents: [{user_id: 1, username: "Test operator", available: 1, presence: "online", live: 1, capacity: 5}]};
  else if (path === "/care/assignment-rule" && request.method === "PUT") {
    let raw = "";
    for await (const chunk of request) raw += chunk;
    const wanted = JSON.parse(raw || "{}").strategy;
    if (strategies.some((x) => x.key === wanted)) { strategy = wanted; data = assignmentRule(); }
    else { response.statusCode = 400; data = {error: "unknown assignment rule"}; }
  }
  else if (path === "/care/assignment-rule") data = assignmentRule();
  else if (path === "/care/queues") data = {queues: []};
  else if (/^\/care\/cases\/\d+\/macros\/\d+\/preview$/.test(path)) {
    const m = macros.find((x) => x.id === Number(path.split("/").at(-2)));
    data = {macro_id: m.id, name: m.name, text: m.body, actions: m.actions.map((a) => ({...a, summary: "Set priority to high"}))};
  }
  else if (path === "/care/cases") data = {tab: "assigned", cases: [101, 202].map((id) => {
    const c = caseDetail(id);
    return {...c.case, ...{display_name: c.customer.display_name, platform: "facebook", handle: c.customer.handle,
      messages: 30, waiting_seconds: 90, sla_state: "ok", priority: "normal"}};
  })};
  else if (/^\/care\/cases\/\d+$/.test(path)) data = caseDetail(Number(path.split("/").at(-1)));
  else if (path.endsWith("/suggest")) data = {kind: "reply", suggestion: "A long suggested reply for layout verification. ".repeat(80), cached: true, mock: true};
  else if (path.endsWith("/scheduled")) data = {scheduled: []};
  else if (path === "/kb/articles") data = {articles: !url.searchParams.get("q") || "account".includes(url.searchParams.get("q").toLowerCase()) ? [article] : []};
  else if (path === "/kb/articles/7") data = {article, attachments: []};
  else {
    // Unknown mutations must fail, never proxy to the real API.
    response.statusCode = 404;
    data = {error: `No fixture for ${request.method} ${path}`};
  }
  response.end(JSON.stringify(data));
});
server.listen(5100, "127.0.0.1");
