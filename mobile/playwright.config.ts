import { defineConfig } from "@playwright/test";

// Drives the app's WEB build in Chromium at phone size, with a fake camera and GPS.
// Setup (see README "Testing"):
//   API on :8000 with TASKS_EAGER=true, CORS_ORIGINS including http://localhost:8081,
//   its log written to $API_LOG (the OTP stub prints codes there);
//   `npx expo export --platform web` served on :8081 with SPA fallback.
export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  use: {
    baseURL: process.env.APP_URL ?? "http://localhost:8081",
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
    geolocation: { latitude: 22.5431, longitude: 88.3552, accuracy: 8 }, // a Kolkata street
    permissions: ["geolocation", "camera"],
    launchOptions: {
      executablePath: process.env.CHROMIUM_PATH || undefined,
      args: [
        "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
        // A fresh synthetic "pothole" per run (python -m app.seed.photos fake-camera.mjpeg),
        // otherwise the duplicate-photo check rightly rejects the repeated test pattern.
        ...(process.env.FAKE_CAMERA ? [`--use-file-for-fake-video-capture=${process.env.FAKE_CAMERA}`] : []),
      ],
    },
  },
  reporter: [["list"]],
});
