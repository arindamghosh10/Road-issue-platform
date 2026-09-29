import { expect, test, type Page } from "@playwright/test";

const REPORTER_ID = /R-[0-9a-f]{32}/;

async function expectNoIdentity(page: Page) {
  const text = await page.locator("body").innerText();
  expect(text).not.toMatch(REPORTER_ID);
  expect(text).not.toMatch(/\+91\d{10}|\b9000\d{6}\b/); // demo phone numbers
}

async function govLogin(page: Page, who: string) {
  await page.goto("/gov/login");
  await page.getByLabel("Email").fill(`${who}@demo.roadwatch.in`);
  await page.getByLabel("Password").fill("roadwatch-demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/gov");
  await expect(page.getByRole("heading", { name: "Work queue" })).toBeVisible();
}

test("public dashboard shows figures, leaderboard and drill-down", async ({ page }) => {
  await page.goto("/");
  const kpis = page.getByLabel("Key figures");
  await expect(kpis.getByText("Issues reported")).toBeVisible();
  await expect(kpis.locator(".tile-value").first()).not.toHaveText("…");

  const board = page.locator("section", { has: page.getByRole("heading", { name: "How each area is doing" }) });
  await expect(board.getByText("Kolkata Municipal Corporation")).toBeVisible();
  await board.getByRole("button", { name: "Wards" }).click();
  await expect(board.getByText(/KMC Ward \d+/).first()).toBeVisible();

  await board.getByRole("button", { name: "Municipalities" }).click();
  await board.getByRole("button", { name: /Show areas inside: Kolkata Municipal Corporation/ }).click();
  await expect(page.getByRole("navigation", { name: "Area" }).getByText("Kolkata Municipal Corporation")).toBeVisible();
  await expect(board.getByText(/KMC Ward \d+/).first()).toBeVisible();
  await expectNoIdentity(page);
});

test("public ticket page shows sanitized photos and history, no identity", async ({ page }) => {
  await page.goto("/");
  const first = page.locator("table a[href^='/tickets/']").first();
  const ref = await first.innerText();
  await first.click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText(ref);
  await expect(page.getByRole("heading", { name: "History" })).toBeVisible();
  await expect(page.locator(".photos img").first()).toBeVisible();
  await expectNoIdentity(page);
});

test("government sign-in rejects a wrong password", async ({ page }) => {
  await page.goto("/gov/login");
  await page.getByLabel("Email").fill("kmc@demo.roadwatch.in");
  await page.getByLabel("Password").fill("wrong");
  await page.getByRole("button", { name: "Sign in" }).click();
  // (Next.js also renders a route-announcer with role="alert", so filter by text.)
  await expect(page.getByRole("alert").filter({ hasText: "Wrong email or password" })).toBeVisible();
});

test("government dashboard is scoped to the official's area", async ({ page }) => {
  await govLogin(page, "kmc");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Kolkata Municipal Corporation");
  const queue = page.locator("section", { has: page.getByRole("heading", { name: "Work queue" }) });
  await expect(queue.locator("tbody a").first()).toBeVisible(); // wait for the queue to load
  const areas = await queue.locator("tbody tr td:nth-child(3)").allInnerTexts();
  expect(areas.length).toBeGreaterThan(0);
  for (const a of areas) expect(a).toMatch(/^KMC Ward \d+/); // nothing from Howrah or elsewhere
  await expectNoIdentity(page);

  await queue.locator("tbody a").first().click();
  await expect(page.getByRole("heading", { name: "Actions" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "History" })).toBeVisible();
  await expectNoIdentity(page);
});

test("a ward officer sees only their own ward", async ({ page }) => {
  await govLogin(page, "kmc.ward001");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("KMC Ward 1");
  const queue = page.locator("section", { has: page.getByRole("heading", { name: "Work queue" }) });
  await expect(queue.locator("tbody a, p.muted").first()).toBeVisible();
  for (const a of await queue.locator("tbody tr td:nth-child(3)").allInnerTexts()) {
    expect(a).toMatch(/^KMC Ward 1\b/);
  }
});

test("language menu switches to Hindi and Bengali and remembers the choice", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Most urgent issues" })).toBeVisible();

  await page.getByLabel("Language").selectOption("hi");
  await expect(page.getByRole("heading", { name: "सबसे ज़रूरी समस्याएँ" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "hi");
  await expect(page.getByLabel("मुख्य आँकड़े").getByText("दर्ज समस्याएँ")).toBeVisible();
  // Category names come from the translation, not the API's English.
  await expect(page.getByRole("cell", { name: "गड्ढा" }).first()).toBeVisible();

  // The choice survives a reload, and the server renders it straight away.
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "hi");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("सड़क और पुल की समस्याएँ: क्या दर्ज हुआ, क्या ठीक हुआ");

  await page.getByLabel("भाषा").selectOption("bn");
  await expect(page.getByRole("heading", { name: "সবচেয়ে জরুরি সমস্যা" })).toBeVisible();
  const ref = await page.locator("table a[href^='/tickets/']").first().innerText();
  await page.goto(`/tickets/${ref}`);
  await expect(page.getByRole("heading", { name: "ইতিহাস" })).toBeVisible();
  await expectNoIdentity(page);
});

test("a Bengali browser gets Bengali on the first visit", async ({ browser }) => {
  const context = await browser.newContext({ locale: "bn-IN" });
  const page = await context.newPage();
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("lang", "bn");
  await expect(page.getByRole("heading", { name: "সবচেয়ে জরুরি সমস্যা" })).toBeVisible();
  await context.close();
});
