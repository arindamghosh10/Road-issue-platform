// Run: npm test  (Node's built-in test runner; no extra dependencies)
import assert from "node:assert/strict";
import { test } from "node:test";
import { formatDistance, gpsQuality, normalizePhone, reportStatusView, ticketStatusView } from "../src/lib/logic.ts";

test("normalizePhone accepts common Indian formats (same rules as the backend)", () => {
  for (const raw of ["9876543210", "+91 98765 43210", "09876543210", "91-9876543210"]) {
    assert.equal(normalizePhone(raw), "+919876543210");
  }
  for (const bad of ["12345", "5876543210", "+1 415 555 0100", ""]) {
    assert.equal(normalizePhone(bad), null);
  }
});

test("gpsQuality uses the backend's thresholds", () => {
  assert.equal(gpsQuality(8), "good");
  assert.equal(gpsQuality(50), "good");
  assert.equal(gpsQuality(80), "weak");
  assert.equal(gpsQuality(151), "too-poor");
  assert.equal(gpsQuality(null), "too-poor");
});

test("formatDistance", () => {
  assert.equal(formatDistance(42), "40 m");
  assert.equal(formatDistance(1480), "1.5 km");
  assert.equal(formatDistance(23000), "23 km");
});

test("every status has an icon and words, not colour alone", () => {
  for (const s of ["open", "acknowledged", "in_progress", "fix_submitted", "resolved", "reopened"] as const) {
    const v = ticketStatusView(s);
    assert.ok(v.icon && v.key && v.color);
  }
  for (const s of ["under_verification", "verified", "rejected"] as const) {
    const v = reportStatusView(s);
    assert.ok(v.icon && v.key && v.color);
  }
});
