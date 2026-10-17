import {expect, test, type Page} from "@playwright/test";

async function signIn(page: Page, username: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", {name: /sign in/i}).click();
  await expect(page).toHaveURL(/\/t\/[^/]+\/p\/[^/]+\/overview/);
}

test("F4 content calendar: month/week toggle, filters, new-post panel", async ({page}) => {
  await signIn(page, "admin", "admin123");
  await page.getByRole("link", {name: "Content calendar", exact: true}).first().click();
  await expect(page).toHaveURL(/\/content/);
  await expect(page.getByRole("heading", {name: "Content calendar", level: 1})).toBeVisible();

  await page.getByRole("button", {name: "week", exact: true}).click();
  await expect(page).toHaveURL(/view=week/);
  await page.getByRole("button", {name: "month", exact: true}).click();
  await expect(page).toHaveURL(/view=month/);

  await page.getByRole("button", {name: "New post"}).click();
  await expect(page.getByRole("heading", {name: "New post"})).toBeVisible();
  await expect(page.getByLabel("Title")).toBeEnabled();
  await page.getByText("Close").click();
});

test("F7.5 content calendar: drag a draft item to another day", async ({page}) => {
  await signIn(page, "admin", "admin123");
  await page.getByRole("link", {name: "Content calendar", exact: true}).first().click();
  await expect(page).toHaveURL(/\/content/);

  // Week view gives each day a taller drop target. Only "draft" items are
  // draggable-and-accepted by design (once in_review/approved/scheduled/
  // published, the API rejects the move) — STATE_COLOR's draft chips are the
  // only ones styled bg-muted, so that combination picks one deterministically.
  await page.getByRole("button", {name: "week", exact: true}).click();
  await expect(page).toHaveURL(/view=week/);
  const dayCells = page.locator("div.min-h-40");
  const cellCount = await dayCells.count();
  let sourceIndex = -1;
  for (let i = 0; i < cellCount; i++) {
    if (await dayCells.nth(i).locator('button[draggable="true"].bg-muted').count()) {sourceIndex = i; break;}
  }
  test.skip(sourceIndex === -1, "No draft item scheduled this week to drag.");

  const sourceCell = dayCells.nth(sourceIndex);
  const chip = sourceCell.locator('button[draggable="true"].bg-muted').first();
  const title = (await chip.textContent())?.trim();
  const targetCell = dayCells.nth((sourceIndex + 1) % cellCount);

  await chip.dragTo(targetCell);

  // Never silently disappears the other way either: a rejected move restores
  // the item and surfaces a role=alert banner instead of just vanishing.
  await expect(page.getByRole("alert")).toHaveCount(0);
  if (title) await expect(targetCell.getByText(title, {exact: false})).toBeVisible({timeout: 15_000});
});
