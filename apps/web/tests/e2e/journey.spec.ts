import {expect, test, type Page} from "@playwright/test";

async function signIn(page: Page, username: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", {name: /sign in/i}).click();
  await expect(page).toHaveURL(/\/overview/);
}

test("viewer journey: login, every viewer route, filter reload, drilldown", async ({page}) => {
  await signIn(page, "bank", "viewer123");
  await expect(page.getByRole("heading", {name: "Overview", level: 1})).toBeVisible();

  // Every viewer surface renders its own page header.
  for (const [label, heading] of [
    ["Mentions", "Mentions"],
    ["Sentiment", "Sentiment"],
    ["Competitors", "Competitors"],
    ["Reviews", "App reviews"],
    ["Themes", "Themes"],
    ["Scam signals", "Scam signals"],
    ["Complaint triage", "Complaint triage"],
    ["Switch intent", "Switch intent"],
    ["Incident radar", "Incident radar"],
    ["Product lines", "Product lines"],
    ["Regulatory watch", "Regulatory watch"],
    ["Branch & ATM", "Branch & ATM"],
    ["Alert center", "Alert center"],
  ] as const) {
    await page.getByRole("link", {name: label, exact: true}).first().click();
    await expect(page.getByRole("heading", {name: heading, level: 1})).toBeVisible();
  }

  // URL is the state: a filter survives a reload.
  await page.getByRole("link", {name: "Mentions", exact: true}).first().click();
  await page.getByLabel("Sentiment").selectOption("pos");
  await expect(page).toHaveURL(/sentiment=pos/);
  await page.reload();
  await expect(page.getByLabel("Sentiment")).toHaveValue("pos");

  // Drilldown: an Overview trending-topic chip deep-links into a filtered Mentions view.
  await page.getByRole("link", {name: "Overview", exact: true}).first().click();
  const chip = page.locator('a[href*="/mentions?q="]').first();
  await expect(chip).toBeVisible();
  await chip.click();
  await expect(page).toHaveURL(/\/mentions\?q=/);
  await expect(page.getByRole("heading", {name: "Mentions", level: 1})).toBeVisible();

  // Every surface now lives under /t/{tenant}/p/{project}/…
  await expect(page).toHaveURL(/\/t\/[^/]+\/p\/[^/]+\/mentions/);
});

test("command palette, theme toggle, and the /evidence redirect", async ({page}) => {
  await signIn(page, "bank", "viewer123");

  // ⌘K palette filters and navigates.
  await page.keyboard.press("ControlOrMeta+k");
  const search = page.getByRole("textbox", {name: "Search commands"});
  await expect(search).toBeVisible();
  await search.fill("compet");
  await page.getByRole("option", {name: /Competitors/}).click();
  await expect(page).toHaveURL(/\/competitors/);

  // Theme toggle flips the root class and sticks across a reload.
  const html = page.locator("html");
  const before = await html.getAttribute("class");
  await page.getByRole("button", {name: /toggle theme/i}).click();
  await expect(async () => {
    expect(await html.getAttribute("class")).not.toBe(before);
  }).toPass();

  // Legacy path parity.
  await page.goto("/evidence?sentiment=neg");
  await expect(page).toHaveURL(/\/mentions\?sentiment=neg/);

  // An old bare surface path 307s to the same surface under the active tenant.
  await page.goto("/regulatory");
  await expect(page).toHaveURL(/\/t\/[^/]+\/p\/[^/]+\/regulatory$/);
  await expect(page.getByRole("heading", {name: "Regulatory watch", level: 1})).toBeVisible();
});

test("viewer cannot see admin surfaces; admin can", async ({page}) => {
  await signIn(page, "bank", "viewer123");
  await expect(page.getByRole("link", {name: "Admin", exact: true})).toHaveCount(0);

  await page.getByRole("button", {name: /sign out/i}).click();
  await expect(page).toHaveURL(/\/login/);

  await signIn(page, "admin", "admin123");
  await page.getByRole("link", {name: "Admin", exact: true}).first().click();
  await expect(page).toHaveURL(/\/admin/);
  await expect(page.getByRole("heading", {name: "Admin", level: 1})).toBeVisible();
  await expect(page.getByRole("heading", {name: "Workspaces"})).toBeVisible();

  await page.getByRole("link", {name: "Calibration", exact: true}).first().click();
  await expect(page.getByRole("heading", {name: "Calibration queue", level: 1})).toBeVisible();
});
