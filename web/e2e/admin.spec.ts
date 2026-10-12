import { expect, test, type Page } from "@playwright/test";

const PASSWORD = "roadwatch-demo";

async function signIn(page: Page, email: string, password = PASSWORD) {
  await page.goto("/gov/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test("an organisation admin adds an official, who must set their own password", async ({ page }) => {
  await signIn(page, "admin@demo.roadwatch.in");
  await page.waitForURL("**/gov");
  await page.getByRole("link", { name: "Administration" }).click();
  await page.waitForURL("**/admin**");
  // Organisation admins manage their team and deadlines, not platform tools.
  await expect(page.getByRole("tab", { name: "Team" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Deadlines" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Areas" })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Audit log" })).toHaveCount(0);

  const email = `e2e.${Date.now()}@test.roadwatch.in`;
  await page.locator("#new-name").fill("E2E Ward Officer");
  await page.locator("#new-email").fill(email);
  // Drill down to a ward: West Bengal → Kolkata district → KMC → Ward 1.
  await page.getByLabel("Area 1").selectOption({ label: "West Bengal (State)" });
  await page.getByLabel("Area 2").selectOption({ label: "Kolkata (District)" });
  await page.getByLabel("Area 3").selectOption({ label: "Kolkata Municipal Corporation (Municipality)" });
  await page.getByLabel("Area 4").selectOption({ label: "KMC Ward 1 (Ward)" });
  await page.getByRole("button", { name: "Create account" }).click();

  const temp = await page.getByLabel("Temporary password").innerText();
  expect(temp.length).toBeGreaterThanOrEqual(12);
  const row = page.getByRole("row", { name: new RegExp(email.replace(/\./g, "\\.")) });
  await expect(row.getByText("Must set a password")).toBeVisible();
  await expect(row.getByText(/KMC Ward 1/)).toBeVisible();

  // The new official signs in with the temporary password and is made to change it.
  await page.getByRole("button", { name: "Sign out" }).click();
  await signIn(page, email, temp);
  await page.waitForURL("**/gov/password");
  await page.locator("#pw-current").fill(temp);
  await page.locator("#pw-new").fill("e2e-ward-password");
  await page.locator("#pw-repeat").fill("e2e-ward-password");
  await page.getByRole("button", { name: "Save password" }).click();
  await page.waitForURL("**/gov");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("KMC Ward 1");
});

test("the platform admin lands on administration and can change deadlines", async ({ page }) => {
  await signIn(page, "platform@demo.roadwatch.in");
  await page.waitForURL("**/admin**");
  for (const tab of ["Team", "Deadlines", "Areas", "Report moderation", "Audit log"]) {
    await expect(page.getByRole("tab", { name: tab })).toBeVisible();
  }

  await page.getByRole("tab", { name: "Deadlines" }).click();
  const cell = page.getByLabel("Pothole, Severity 5, hours");
  await cell.fill("6");
  await expect(page.getByText("1 change(s) not saved yet")).toBeVisible();
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();
  await expect(cell).toHaveValue("6");
  // Put the default back so other runs start clean.
  await cell.fill("");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();

  await page.getByRole("tab", { name: "Audit log" }).click();
  await expect(page.getByRole("cell", { name: "deadlines_changed" }).first()).toBeVisible();

  await page.getByRole("tab", { name: "Areas" }).click();
  await expect(page.getByRole("button", { name: /West Bengal/ })).toBeVisible();
  await page.getByRole("tab", { name: "Report moderation" }).click();
  await expect(page.getByRole("heading", { name: "Report moderation" })).toBeVisible();
  await expect(page.locator("body")).not.toContainText(/R-[0-9a-f]{32}/); // never a reporter id
});

test("an ordinary official is turned away from administration", async ({ page }) => {
  await signIn(page, "kmc@demo.roadwatch.in");
  await page.waitForURL("**/gov");
  await expect(page.getByRole("link", { name: "Administration" })).toHaveCount(0);
  await page.goto("/admin");
  await expect(page.getByText("This page is for administrators.")).toBeVisible();
});
