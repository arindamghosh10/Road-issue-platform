// Run: npm test. Checks the Hindi and Bengali translations and the rules that turn the
// server's codes into sentences.
import assert from "node:assert/strict";
import { test } from "node:test";
import en from "../src/lib/messages/en.ts";
import hi from "../src/lib/messages/hi.ts";
import bn from "../src/lib/messages/bn.ts";
import { checkLines, codeText, distanceText, errorText, formatDate, localizeDigits, noticeText, pickLocale, translator } from "../src/lib/i18n.ts";

const placeholders = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

for (const [name, dict] of [["hi", hi], ["bn", bn]] as const) {
  test(`${name}: every key translated, same placeholders as English, no English left over`, () => {
    assert.deepEqual(Object.keys(dict).sort(), Object.keys(en).sort());
    for (const [key, text] of Object.entries(en)) {
      const tr = (dict as Record<string, string>)[key];
      assert.ok(tr.trim(), `${name} ${key} is empty`);
      assert.deepEqual(placeholders(tr), placeholders(text), `${name} ${key} placeholders`);
      // Anything longer than a word should differ from English (brand names aside).
      if (text.split(" ").length > 2 && !text.includes("RoadWatch")) assert.notEqual(tr, text, `${name} ${key} untranslated`);
    }
  });
}

test("the phone's language picks the app language", () => {
  assert.equal(pickLocale(["bn-IN", "en-IN"]), "bn");
  assert.equal(pickLocale(["hi"]), "hi");
  assert.equal(pickLocale(["ta-IN", "en-GB"]), "en");
  assert.equal(pickLocale([null]), "en");
});

test("verification results are shown by code, in the reader's language", () => {
  const t = translator("hi");
  const check = { name: "capture_integrity", reason: "device attestation not checked (stub)",
                  code: "capture.warnings", params: { warnings: ["attestation_unchecked", "gps_weak"], gps_m: 72 } };
  const line = checkLines(t, check);
  assert.equal(line.title, hi["check.capture_integrity"]);
  assert.equal(line.detail, `${hi["warn.attestation_unchecked"]}; ${hi["warn.gps_weak"].replace("{m}", "72")}`);

  assert.equal(codeText(t, "capture.too_old", { hours: 24 }), "तस्वीर 24 घंटे से ज़्यादा पुरानी है।");
  assert.equal(codeText(t, "vision.wrong_category", { category: "pothole" }), "तस्वीर में “गड्ढा” नहीं दिखता।");
  assert.ok(codeText(t, "low_score", { weakest: "location.no_road_data" }).includes(hi["code.location.no_road_data"]));
  // Unknown or missing codes fall back to the server's English text.
  assert.equal(codeText(t, "something.new", {}, "Server text"), "Server text");
  assert.equal(checkLines(t, { name: "location", reason: "Old report text" }).detail, "Old report text");
});

test("notifications are rebuilt from their kind", () => {
  const t = translator("bn");
  const v = noticeText(t, { kind: "report_verified", title: "x", body: "y", ticket_ref: "RW-ABC", params: { reporters: 3 } });
  assert.equal(v.title, "অভিযোগ যাচাই হয়েছে: RW-ABC");
  assert.ok(v.body.includes("RW-ABC") && v.body.includes("৩"));
  const r = noticeText(t, { kind: "report_rejected", title: "x", body: "English reason", ticket_ref: null,
                            params: { reason: "duplicate.seen" } });
  assert.equal(r.body, bn["code.duplicate.seen"]);
  const unknown = noticeText(t, { kind: "future_kind", title: "Title", body: "Body", ticket_ref: null });
  assert.deepEqual(unknown, { title: "Title", body: "Body" });
});

test("known server errors are translated; unknown ones are shown as sent", () => {
  const t = translator("hi");
  const err = (status: number, message: string) => Object.assign(new Error(message), { status });
  assert.equal(errorText(t, err(0, "")), hi["err.network"]);
  assert.equal(errorText(t, err(400, "Incorrect code.")), hi["err.wrongCode"]);
  assert.equal(errorText(t, err(422, "You need to be within 150 m of the issue to confirm it.")), hi["err.tooFar"]);
  assert.equal(errorText(t, err(429, "Too many attempts. Please wait and try again.")), hi["err.tooMany"]);
  assert.equal(errorText(t, err(500, "")), "कुछ गड़बड़ हो गई (500)।");
  assert.equal(errorText(t, err(418, "Brand new message")), "Brand new message");
});

test("dates: month names in the reader's language; Bengali digits for Bengali", () => {
  assert.match(formatDate("en", "2026-07-22"), /22 Jul 2026/);
  const hiDate = formatDate("hi", "2026-07-22");
  assert.match(hiDate, /22/);
  assert.match(hiDate, /2026/);
  const bnDate = formatDate("bn", "2026-07-22");
  assert.match(bnDate, /২২/);
  assert.match(bnDate, /২০২৬/);
  assert.doesNotMatch(bnDate, /[0-9]/);
});

test("Bengali numbers use Bengali digits; ticket refs and English/Hindi don't change", () => {
  const bnT = translator("bn");
  assert.equal(bnT("near.count", { n: 12 }), "১.৫ কিমির মধ্যে ১২টি সমস্যা, সবচেয়ে কাছেরটি আগে");
  // A ticket ref is a string: it is left exactly as typed.
  assert.equal(bnT("n.report_verified.title", { ref: "RW-9UGWCYX5" }), "অভিযোগ যাচাই হয়েছে: RW-9UGWCYX5");
  assert.equal(codeText(bnT, "capture.too_old", { hours: 24 }), "ছবিটি ২৪ ঘণ্টার বেশি পুরনো।");
  assert.equal(translator("hi")("near.count", { n: 12 }), "1.5 किमी के अंदर 12 समस्याएँ, सबसे पास वाली पहले");
  assert.equal(localizeDigits("bn", "1.5 km"), "১.৫ km");
  assert.equal(distanceText(bnT, 1480), "১.৫ কিমি");
  assert.equal(distanceText(bnT, 42), "৪০ মি");
  assert.equal(distanceText(translator("en"), 23000), "23 km");
  assert.equal(localizeDigits("en", "1.5 km"), "1.5 km");
  for (const text of Object.values(bn)) assert.doesNotMatch(text, /[0-9]/, `Latin digit in: ${text}`);
});
