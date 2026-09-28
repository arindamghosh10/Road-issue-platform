import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const API = process.env.API_URL ?? "http://localhost:8000";
const API_LOG = process.env.API_LOG ?? "";
const PHONE_LAST4 = String(Date.now()).slice(-4);
const PHONE = `98312 1${PHONE_LAST4}`;
const REPORTER_ID = /R-[0-9a-f]{32}/;

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Mobile number").fill(PHONE);
  await page.getByRole("button", { name: "Send code" }).click();
  await expect(page.getByText("Enter the 6-digit code")).toBeVisible();
  await page.waitForTimeout(500);
  const matches = readFileSync(API_LOG, "utf8").match(new RegExp(`code for \\*+${PHONE_LAST4} is (\\d{6})`, "g"));
  expect(matches, "OTP stub code not found in API log").toBeTruthy();
  await page.getByLabel("One-time code").fill(matches!.pop()!.slice(-6));
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
}

test("citizen journey: camera report → verified → nearby → 'Is it fixed?' → resolved", async ({ page, request }) => {
  test.skip(!API_LOG, "set API_LOG to the API's log file (OTP stub codes are printed there)");
  await signIn(page);
  const allow = page.getByRole("button", { name: "Allow camera and location" });
  if (await allow.isVisible({ timeout: 3000 }).catch(() => false)) await allow.click();

  await page.getByRole("button", { name: "Take photo" }).waitFor({ timeout: 15000 });
  await page.waitForTimeout(2000); // fake camera stream warm-up
  await page.getByRole("button", { name: "Take photo" }).click();
  await expect(page.getByText("What's the problem?")).toBeVisible();
  await expect(page.getByText(/Location recorded/)).toBeVisible();
  await page.getByRole("radio", { name: "Pothole" }).click();
  await page.getByRole("button", { name: "Submit report" }).click();
  await expect(page.getByText("Thank you!")).toBeVisible({ timeout: 30000 });
  await expect(page.getByText("Photo taken live in the app")).toBeVisible();

  await page.getByText("My reports").last().click();
  await expect(page.getByText(/issue RW-/).first()).toBeVisible();
  await page.getByText("Nearby").last().click();
  await expect(page.getByText(/you reported this/).first()).toBeVisible({ timeout: 15000 });
  expect(await page.locator("body").innerText()).not.toMatch(REPORTER_ID);

  // The authority submits a repair photo for this citizen's ticket (acting as the KMC official).
  const token = await page.evaluate(() => localStorage.getItem("roadwatch_citizen_token"));
  const mine = await (await request.get(`${API}/api/v1/citizen/reports`, { headers: { Authorization: `Bearer ${token}` } })).json();
  const ref: string = mine[0].ticket_ref;
  const ticket = await (await request.get(`${API}/api/v1/public/tickets/${ref}`)).json();
  const login = await (await request.post(`${API}/api/v1/gov/auth/login`,
    { data: { email: "kmc@demo.roadwatch.in", password: "roadwatch-demo" } })).json();
  const photo = readFileSync(join(__dirname, "fix-photo.jpg"));
  const fix = await request.post(`${API}/api/v1/gov/tickets/${ref}/fix-proof`, {
    headers: { Authorization: `Bearer ${login.access_token}` },
    multipart: {
      photo: { name: "fix.jpg", mimeType: "image/jpeg", buffer: photo },
      lat: String(ticket.lat), lon: String(ticket.lon),
      captured_at: new Date().toISOString(), capture_source: "in_app_camera",
    },
  });
  expect(fix.status(), await fix.text()).toBe(200);

  await page.getByText("Inbox").last().click();
  await expect(page.getByText("Is it fixed?", { exact: true })).toBeVisible({ timeout: 15000 });
  await page.getByRole("button", { name: "Yes, fixed" }).first().click();
  await expect(page.getByText(/^Thanks/)).toBeVisible();
  const after = await (await request.get(`${API}/api/v1/public/tickets/${ref}`)).json();
  expect(["resolved", "fix_submitted"]).toContain(after.status); // resolved once ≥ 50% said yes
});
