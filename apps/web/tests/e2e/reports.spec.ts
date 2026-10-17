import {expect, test, type Page} from "@playwright/test";

async function signIn(page: Page, username: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", {name: /sign in/i}).click();
  await expect(page).toHaveURL(/\/t\/[^/]+\/p\/[^/]+\/overview/);
}

test("F5 reports: every tab renders", async ({page}) => {
  await signIn(page, "admin", "admin123");
  await page.getByRole("link", {name: "Reports", exact: true}).first().click();
  await expect(page).toHaveURL(/\/reports/);
  await expect(page.getByRole("heading", {name: "Reports", level: 1})).toBeVisible();

  for (const label of ["Metrics", "Care & SLA", "Social", "CSAT & complaints", "MIS", "Schedules"]) {
    await page.getByRole("button", {name: label, exact: true}).click();
    await expect(page.getByRole("button", {name: label, exact: true})).toHaveAttribute("aria-current", "page");
  }
  await expect(page.getByText("We could not load this view")).toHaveCount(0);
});
