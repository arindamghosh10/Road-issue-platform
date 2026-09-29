import { defineConfig } from "@playwright/test";

// End-to-end tests against a running stack:
//   API on :8000 with the sample seed + demo tickets (python -m app.seed && python -m app.seed.demo)
//   web on :3000 (npm run build && npm start)
// CHROMIUM_PATH lets you point at a pre-installed browser instead of `playwright install`.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  use: {
    baseURL: process.env.WEB_URL ?? "http://localhost:3000",
    launchOptions: process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {},
  },
  reporter: [["list"]],
});
