import {expect, test, type Page} from "@playwright/test";

async function signIn(page: Page, username: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", {name: /sign in/i}).click();
  await expect(page).toHaveURL(/\/t\/[^/]+\/p\/[^/]+\/overview/);
}

test("F1.1 agent console: five tabs, three panes, URL-driven selection", async ({page}) => {
  await signIn(page, "admin", "admin123");
  const base = new URL(page.url()).pathname.replace(/\/overview$/, "");

  await page.getByRole("link", {name: "Care console", exact: true}).first().click();
  await expect(page).toHaveURL(new RegExp(`${base.replace(/[/]/g, "\\/")}\\/care`));
  await expect(page.getByRole("heading", {name: "Agent console", level: 1})).toBeVisible();

  for (const label of ["Queue", "All Assigned", "Assigned to Me", "Internal Hold", "All Closed"]) {
    await expect(page.getByRole("button", {name: new RegExp(`^${label}`)})).toBeVisible();
  }

  // Switching a tab is URL state.
  await page.getByRole("button", {name: /^All Closed/}).click();
  await expect(page).toHaveURL(/tab=closed/);
  await expect(page.getByText("Select a case to open the thread.")).toBeVisible();
});

test("F2 supervisor console: four tabs render", async ({page}) => {
  await signIn(page, "admin", "admin123");
  await page.getByRole("link", {name: "Supervisor", exact: true}).first().click();
  await expect(page).toHaveURL(/\/care\/supervisor/);
  await expect(page.getByRole("heading", {name: "Supervisor console", level: 1})).toBeVisible();

  await page.getByRole("button", {name: "Queues"}).click();
  await expect(page).toHaveURL(/tab=queues/);
  await page.getByRole("button", {name: "Approvals"}).click();
  await expect(page).toHaveURL(/tab=approvals/);
  await page.getByRole("button", {name: "Performance"}).click();
  await expect(page).toHaveURL(/tab=performance/);
  // export controls present
  await expect(page.getByRole("link", {name: "CSV"})).toBeVisible();
});

test("F7.5 care state machine: open a case, add a note, transition it, reply", async ({page}) => {
  await signIn(page, "admin", "admin123");

  // This demo tenant has no seeded care cases at all (it was built for the
  // listening surfaces, not the helpdesk) — go through the same inbound path
  // a real channel webhook uses (POST /care/cases/ingest) so this test is
  // self-contained rather than depending on data that may not exist.
  const csrf = await (await page.request.get("/api/v1/csrf")).json() as {token: string};
  const handle = `e2e-${Date.now()}`;
  const ingest = await page.request.post("/api/v1/care/cases/ingest", {
    headers: {"X-CSRF-Token": csrf.token},
    data: {platform: "facebook", body: "e2e seed message", display_name: `E2E ${handle}`, handle},
  });
  const caseId = (await ingest.json()).case_id as number;

  // Open the thread straight from its URL — the case-list query has its own
  // refetch cadence and a just-ingested row can lag it by more than a test
  // is willing to wait. The console reads ?case= and opens that thread.
  const base = new URL(page.url()).pathname.replace(/\/overview$/, "");
  await page.goto(`${base}/care?case=${caseId}`);
  const thread = page.locator("main");
  await expect(thread.getByText(`C-${caseId}`).first()).toBeVisible({timeout: 30_000});

  // Transition first, to whatever the backend's state machine (core/cases.py
  // _TRANSITIONS) actually allows from wherever this case happens to be —
  // closed -> open is the only edge out of closed; in_progress -> internal_hold
  // and everything else (open/assigned/internal_hold/pending_approval) ->
  // in_progress cover the rest. Needed first (not just exercised) because the
  // reply composer doesn't render at all for a closed case.
  const statePill = thread.locator("div.border-b.pb-3 span").nth(2);
  const before = ((await statePill.textContent()) ?? "").trim().toLowerCase();
  const target = before.includes("closed") ? "open" : before === "in progress" ? "internal_hold" : "in_progress";
  await page.getByRole("button", {name: "transition", exact: true}).click();
  await page.getByLabel("New state").selectOption(target);
  await page.getByRole("button", {name: "Apply"}).click();
  await expect(statePill).toHaveText(target.replaceAll("_", " "), {timeout: 15_000});

  // Internal note — appears in the thread immediately on success.
  await page.getByRole("button", {name: "note", exact: true}).click();
  const noteText = `e2e note ${Date.now()}`;
  await page.getByLabel("Internal note").fill(noteText);
  await page.getByRole("button", {name: "Add note"}).click();
  await expect(thread.getByText(noteText)).toBeVisible({timeout: 15_000});

  // Reply — never silently disappears: Sent. confirms, or an inline error
  // (role=alert) would appear instead and the draft would stay in the box.
  const replyText = `e2e reply ${Date.now()}`;
  await page.getByLabel("Reply text").fill(replyText);
  await page.getByRole("button", {name: "Send", exact: true}).click();
  await expect(page.getByText("Sent.")).toBeVisible({timeout: 15_000});
  await expect(thread.getByText(replyText)).toBeVisible();
});

test("F0.5 care primitives demo renders every primitive", async ({page}) => {
  await signIn(page, "admin", "admin123");
  const base = new URL(page.url()).pathname.replace(/\/overview$/, "");

  await page.goto(`${base}/care/primitives`);
  await expect(page.getByRole("heading", {name: "Care primitives", level: 1})).toBeVisible();

  for (const section of ["ChannelBadge", "SentimentPill", "SlaChip", "PresenceDot", "AgentAvatar", "MessageBubble", "CaseCard"]) {
    await expect(page.getByRole("heading", {name: section, exact: true})).toBeVisible();
  }

  // A couple of concrete instances
  await expect(page.getByText("SLA breached").first()).toBeVisible();
  await expect(page.getByText("Internal note").first()).toBeVisible();
  await expect(page.getByText("C-101").first()).toBeVisible();
  await expect(page.getByText("Unassigned").first()).toBeVisible();
});
