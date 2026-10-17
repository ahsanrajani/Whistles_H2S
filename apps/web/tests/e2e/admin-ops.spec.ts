import {expect, test, type Page} from "@playwright/test";

async function signIn(page: Page, username: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", {name: /sign in/i}).click();
  await expect(page).toHaveURL(/\/t\/[^/]+\/p\/[^/]+\/overview/);
}

test("F6 admin operations: every tab renders", async ({page}) => {
  await signIn(page, "admin", "admin123");
  await page.getByRole("link", {name: "Admin operations", exact: true}).first().click();
  await expect(page).toHaveURL(/\/admin-ops/);
  await expect(page.getByRole("heading", {name: "Admin operations", level: 1})).toBeVisible();

  for (const label of ["Source health", "Retention", "Precision", "Owned analytics", "Routing policy", "Jobs & scheduler"]) {
    await page.getByRole("button", {name: label, exact: true}).click();
    await expect(page.getByRole("button", {name: label, exact: true})).toHaveAttribute("aria-current", "page");
  }
  await expect(page.getByText("We could not load this view")).toHaveCount(0);
});

test("F6 routing policy: edit and save a threshold", async ({page}) => {
  await signIn(page, "admin", "admin123");
  await page.getByRole("link", {name: "Admin operations", exact: true}).first().click();
  await page.getByRole("button", {name: "Routing policy", exact: true}).click();

  const field = page.getByLabel("Default agent capacity");
  await expect(field).toBeVisible();
  await field.fill("7");
  await page.getByRole("button", {name: "Save policy"}).click();
  await expect(page.getByText("Saved.")).toBeVisible();
});
