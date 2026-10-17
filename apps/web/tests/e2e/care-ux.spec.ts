import {expect, test, type Page} from "@playwright/test";

// These tests require the fixture-only config; never run against the live stack.
test.skip(({baseURL}) => baseURL !== "http://127.0.0.1:3100", "Use playwright.care-ux.config.ts");
const care = "/t/ux-test/p/social/care?case=101&tab=assigned&sort=new";
const contextTab = (page: Page, name: string) => page.getByRole("tablist", {name: "Case context"}).getByRole("tab", {name: new RegExp(`^${name}`, "i")});

test.beforeEach(async ({context, page}) => {
  await page.route("**/_next/image?*", (route) => route.fulfill({path: "../api/static/brand/mark.png", contentType: "image/png"}));
  await context.addCookies([{name: "session", value: "fixture-only", domain: "127.0.0.1", path: "/"}]);
  await page.setViewportSize({width: 1600, height: 900});
});

test("context tabs preserve drafts, support keys and insert a published article", async ({page}) => {
  await page.goto(care);
  const draft = page.getByRole("textbox", {name: "Reply text"});
  await draft.fill("Existing reply");
  await contextTab(page, "Customer").click();
  await page.getByRole("button", {name: "Edit", exact: true}).click();
  await page.getByRole("textbox", {name: "Full name", exact: true}).fill("Unsaved profile edit");
  await contextTab(page, "Customer").focus();
  await page.keyboard.press("ArrowRight");
  await expect(contextTab(page, "History")).toHaveAttribute("aria-selected", "true");
  await expect(page).toHaveURL(/context=history/);
  await expect(page.getByRole("tabpanel", {name: /History/}).getByRole("button", {name: /C-202/})).toBeVisible();
  await page.keyboard.press("End");
  await expect(contextTab(page, "Knowledge")).toBeFocused();
  await page.getByRole("textbox", {name: "Search knowledge articles"}).fill("missing");
  await expect(page.getByText("No published articles match your search.", {exact: true})).toBeVisible();
  await page.getByRole("textbox", {name: "Search knowledge articles"}).fill("account");
  await page.getByRole("button", {name: /Account access help/}).click();
  await page.getByRole("region", {name: "Article preview"}).getByRole("button", {name: "Insert into reply", exact: true}).click();
  await expect(draft).toHaveValue("Existing reply\n\nUse the secure account recovery page.");
  await contextTab(page, "Customer").click();
  await expect(page.getByRole("textbox", {name: "Full name", exact: true})).toHaveValue("Unsaved profile edit");
  await expect(page).toHaveURL(/tab=assigned&sort=new/);
  await page.getByRole("button", {name: "Cancel", exact: true}).click();
  await expect(page.getByText("customer101@example.test", {exact: true})).toBeVisible();
});

test("history navigation isolates case edits and closed-case reply controls", async ({page}) => {
  await page.goto(care);
  await page.getByRole("textbox", {name: "Reply text"}).fill("Must not leak");
  await page.getByRole("button", {name: "Edit", exact: true}).click();
  await page.getByRole("textbox", {name: "Full name", exact: true}).fill("Wrong customer");
  await contextTab(page, "History").click();
  await page.getByRole("tabpanel", {name: /History/}).getByRole("button", {name: /C-202/}).click();
  await expect(page).toHaveURL(/case=202/);
  await expect(page.getByRole("textbox", {name: "Reply text"})).toHaveCount(0);
  await contextTab(page, "Customer").click();
  await expect(page.getByRole("textbox", {name: "Full name", exact: true})).toHaveCount(0);
  await expect(page.getByText("customer202@example.test", {exact: true})).toBeVisible();
  await contextTab(page, "Knowledge").click();
  await page.getByRole("button", {name: /Account access help/}).click();
  await expect(page.getByRole("region", {name: "Article preview"}).getByRole("button", {name: "Insert into reply", exact: true})).toBeDisabled();
  await page.getByRole("region", {name: "Case list"}).getByRole("button", {name: /Customer 101/}).click();
  await expect(page.getByRole("textbox", {name: "Reply text"})).toHaveValue("");
});

test("existing composer routes retain DM payloads, CSRF and failed drafts", async ({page}) => {
  const payloads: Record<string, unknown>[] = [];
  await page.route("**/api/v1/care/cases/101/reply", async (route) => {
    expect(route.request().headers()["x-csrf-token"]).toBe("fixture-csrf");
    payloads.push(route.request().postDataJSON());
    await route.fulfill({status: 400, json: {error: "Fixture delivery failure"}});
  });
  await page.goto(care);
  await expect(page.getByRole("tab", {name: "Public reply"})).toHaveCount(0);
  await page.getByRole("button", {name: "Macros", exact: true}).click();
  await page.getByRole("menuitem", {name: /Greeting/}).click();
  const draft = page.getByRole("textbox", {name: "Reply text"});
  await expect(draft).toHaveValue("Hello from a canned response.");
  await page.getByRole("button", {name: "Send", exact: true}).click();
  await expect(page.getByRole("alert").filter({hasText: "Couldn't send the reply"})).toBeVisible();
  await expect(page.getByText("Fixture delivery failure")).toHaveCount(0);
  await expect(draft).toHaveValue("Hello from a canned response.");
  expect(payloads[0]).toMatchObject({channel_mode: "dm", target_ref: "test-101", platform: "facebook", hold: false});
  await page.getByRole("button", {name: "More send options"}).click();
  await page.getByRole("menuitem", {name: "Hold for approval"}).click();
  await expect.poll(() => payloads.length).toBe(2);
  expect(payloads[1].hold).toBe(true);
  await page.getByRole("button", {name: "note", exact: true}).click();
  await expect(page.getByRole("textbox", {name: "Internal note"})).toBeVisible();
  await page.getByRole("button", {name: "transition", exact: true}).click();
  await expect(page.getByRole("combobox", {name: "New state"})).toBeVisible();
});

test("quick macro in the Send dropdown sends its text, keeps the draft and runs its actions", async ({page}) => {
  const replies: Record<string, unknown>[] = [];
  const applies: Record<string, unknown>[] = [];
  await page.route("**/api/v1/care/cases/101/reply", async (route) => {
    replies.push(route.request().postDataJSON());
    await route.fulfill({json: {ok: true, state: "sent"}});
  });
  await page.route("**/api/v1/care/cases/101/macros/4/apply", async (route) => {
    applies.push(route.request().postDataJSON());
    await route.fulfill({json: {ok: true, results: [{index: 0, type: "set_priority", ok: true}]}});
  });
  await page.goto(care);
  const draft = page.getByRole("textbox", {name: "Reply text"});
  await draft.fill("Half-written thought");
  await page.getByRole("button", {name: "More send options"}).click();
  await expect(page.getByRole("menuitem", {name: /Greeting/})).toHaveCount(0); // only pinned macros here
  await page.getByRole("menuitem", {name: /^Refund ack/}).click();
  await expect(page.getByText(/1 action applied/)).toBeVisible();
  expect(replies[0]).toMatchObject({text: "We are looking into your refund.", hold: false});
  expect(applies).toEqual([{}]);
  await expect(draft).toHaveValue("Half-written thought");
});

test("a picked macro lists its actions and only ticked ones run on send", async ({page}) => {
  const applies: Record<string, unknown>[] = [];
  await page.route("**/api/v1/care/cases/101/reply", (route) => route.fulfill({json: {ok: true, state: "sent"}}));
  await page.route("**/api/v1/care/cases/101/macros/4/apply", async (route) => {
    applies.push(route.request().postDataJSON());
    await route.fulfill({json: {ok: true, results: []}});
  });
  await page.goto(care);
  const draft = page.getByRole("textbox", {name: "Reply text"});
  await draft.fill("/refund");
  await page.getByRole("option", {name: /Refund ack/}).click();
  await expect(draft).toHaveValue("We are looking into your refund.");
  await page.getByRole("checkbox", {name: "Set priority to high"}).uncheck();
  await page.getByRole("button", {name: "Send", exact: true}).click();
  await expect(page.getByText("Sent.")).toBeVisible();
  expect(applies).toHaveLength(0); // the only action was un-ticked
});

test("a reply the platform refuses counts as sent and its macro completes", async ({page}) => {
  const applies: Record<string, unknown>[] = [];
  await page.route("**/api/v1/care/cases/101/reply", (route) =>
    route.fulfill({json: {ok: false, state: "failed", error: "(#10) This message is being sent outside the allowed window."}}));
  await page.route("**/api/v1/care/cases/101/macros/4/apply", async (route) => {
    applies.push(route.request().postDataJSON());
    await route.fulfill({json: {ok: true, results: [{index: 0, type: "set_priority", ok: true}]}});
  });
  await page.goto(care);
  const draft = page.getByRole("textbox", {name: "Reply text"});
  await draft.fill("/refund");
  await page.getByRole("option", {name: /Refund ack/}).click();
  await page.getByRole("button", {name: "Send", exact: true}).click();
  await expect(page.getByText("Sent.")).toBeVisible();
  await expect(page.getByText(/1 action applied/)).toBeVisible();
  await expect(page.getByText(/not sent|not delivered|allowed window|\(#10\)/)).toHaveCount(0);            // no delivery warning, no raw Meta error
  expect(applies).toEqual([{indexes: [0]}]);
  await expect(draft).toHaveValue("");                              // draft cleared, macro chip gone
  await expect(page.getByText("Set priority to high")).toHaveCount(0);
});

for (const [width, height] of [[1600, 900], [1280, 720], [768, 1024], [390, 844]]) {
  test(`thread remains readable with a long suggestion at ${width}x${height}`, async ({page}, testInfo) => {
    await page.setViewportSize({width, height});
    await page.goto(care);
    await expect(page.getByText(/AI suggested reply/)).toBeVisible();
    const thread = page.getByRole("region", {name: "Message thread"});
    const box = await thread.boundingBox();
    expect(box!.height).toBeGreaterThanOrEqual(190);
    expect(box!.width).toBeGreaterThan(250);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await contextTab(page, "History").click();
    await expect(page.getByRole("tabpanel", {name: /History/}).getByRole("button", {name: /C-202/})).toBeVisible();
    await contextTab(page, "Customer").click();
    await expect(contextTab(page, "Customer")).toHaveAttribute("aria-selected", "true");
    if (width === 1600) await page.getByRole("button", {name: "Toggle theme"}).click();
    await page.screenshot({path: testInfo.outputPath(`care-${width}.png`), fullPage: true});
    if (width < 1024) {
      await page.getByRole("button", {name: "Back to cases"}).click();
      await expect(page.getByRole("region", {name: "Case list"})).toBeVisible();
      await page.getByRole("region", {name: "Case list"}).getByRole("button", {name: /Customer 101/}).click();
      await expect(thread).toBeVisible();
    }
  });
}

test("supervisor picks the auto-assignment rule and each choice explains itself on hover", async ({page}) => {
  await page.goto("/t/ux-test/p/social/care/supervisor?tab=roster");
  const card = page.getByTestId("assignment-rule");
  await expect(card.getByRole("heading", {name: "Auto-assignment"})).toBeVisible();
  await expect(card.getByText("2 available")).toBeVisible();
  await expect(card.getByText("3 waiting")).toBeVisible();
  await expect(card.getByText("4 older left unassigned")).toBeVisible();
  const least = card.getByRole("radio", {name: "Least busy"});
  await expect(least).toHaveAttribute("aria-checked", "true");

  const robin = card.getByRole("radio", {name: "Round robin"});
  const tip = card.getByRole("tooltip").filter({hasText: "take turns"});
  await expect(tip).toHaveCSS("opacity", "0");
  await robin.hover();
  await expect(tip).toHaveCSS("opacity", "1");
  await page.mouse.move(0, 0);
  await expect(tip).toHaveCSS("opacity", "0");
  await robin.focus();                                      // keyboard users get the same text
  await expect(tip).toHaveCSS("opacity", "1");

  await robin.click();
  await expect(robin).toHaveAttribute("aria-checked", "true");
  await expect(least).toHaveAttribute("aria-checked", "false");
  await expect(page.getByTestId("assignment-rule-description")).toContainText("take turns");
  await page.reload();                                       // it persisted server-side
  await expect(page.getByTestId("assignment-rule").getByRole("radio", {name: "Round robin"})).toHaveAttribute("aria-checked", "true");
});
