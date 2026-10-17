import {expect, test, type Page} from "@playwright/test";

async function signInAsAdmin(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("admin123");
  await page.getByRole("button", {name: /sign in/i}).click();
  await expect(page).toHaveURL(/\/overview/);
}

test("admin config: every section renders and the rule preview responds", async ({page}) => {
  await signInAsAdmin(page);
  await page.getByRole("link", {name: "Admin", exact: true}).first().click();
  await expect(page).toHaveURL(/\/admin/);

  for (const heading of ["Workspaces", "Brands & matching rules", "Users", "API keys", "Sources", "Cost", "Jobs & runs"]) {
    await expect(page.getByRole("heading", {name: heading})).toBeVisible();
  }
  // No section fell back to the error card.
  await expect(page.getByText("We could not load this view")).toHaveCount(0);

  // Open a brand editor; the live match preview should report a count.
  await page.getByRole("button", {name: /Bank Alfalah/}).first().click();
  await expect(page.getByText("Live match preview")).toBeVisible();
  await expect(page.getByText(/match(es)? in \d+ items/)).toBeVisible({timeout: 15_000});
});

test("admin can start a scoring job and watch the console", async ({page}) => {
  await signInAsAdmin(page);
  await page.getByRole("link", {name: "Admin", exact: true}).first().click();
  await expect(page).toHaveURL(/\/admin/);
  await page.getByRole("heading", {name: "Jobs & runs"}).scrollIntoViewIfNeeded();
  await page.getByRole("button", {name: "Score pending"}).click();
  // The job console's own status region — scoped so it can't match a
  // "Failed" table column header elsewhere on the admin page.
  await expect(page.getByRole("status").filter({hasText: /Working…|Complete|Failed/})).toBeVisible({timeout: 15_000});
});

test("admin-only brand-abuse page renders", async ({page}) => {
  await signInAsAdmin(page);
  await page.getByRole("link", {name: "Brand abuse", exact: true}).first().click();
  await expect(page).toHaveURL(/\/impersonation/);
  await expect(page.getByRole("heading", {name: "Brand abuse", level: 1})).toBeVisible();
});

test("onboarding wizard loads its guided page", async ({page}) => {
  await signInAsAdmin(page);
  await page.getByRole("link", {name: "New workspace", exact: true}).first().click();
  await expect(page).toHaveURL(/\/onboarding/);
  await expect(page.getByRole("heading", {name: "New workspace"})).toBeVisible();
  await expect(page.getByText(/Step \d of 5/)).toBeVisible();
});
