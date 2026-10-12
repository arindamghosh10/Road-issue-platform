// Run: npm test. Every Hindi/Bengali string exists, keeps English's {placeholders},
// and isn't English left behind.
import assert from "node:assert/strict";
import { test } from "node:test";
import en from "../lib/messages/en.ts";
import hi from "../lib/messages/hi.ts";
import bn from "../lib/messages/bn.ts";

const placeholders = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

for (const [name, dict] of [["hi", hi], ["bn", bn]] as const) {
  test(`${name}: complete, same placeholders as English, actually translated`, () => {
    assert.deepEqual(Object.keys(dict).sort(), Object.keys(en).sort());
    for (const [key, text] of Object.entries(en)) {
      const tr = (dict as Record<string, string>)[key];
      assert.ok(tr.trim(), `${name} ${key} is empty`);
      assert.deepEqual(placeholders(tr), placeholders(text), `${name} ${key} placeholders`);
      if (text.split(" ").length > 2 && !text.includes("RoadWatch")) assert.notEqual(tr, text, `${name} ${key} untranslated`);
      if (name === "bn") assert.doesNotMatch(tr, /[0-9]/, `bn ${key} should use Bengali digits`);
    }
  });
}

test("Bengali numbers and dates use Bengali digits; ticket refs are left alone", async () => {
  const { translator } = await import("../lib/i18n.ts");
  const { makeFormat } = await import("../lib/format.ts");
  const t = translator("bn");
  const f = makeFormat("bn", t);
  assert.equal(t("public.mapHint", { n: 83 }), "৮৩টি সমস্যা দেখানো হচ্ছে · বিস্তারিত দেখতে একটিতে ক্লিক করুন");
  assert.equal(f.pct(0.43), "৪৩%");
  assert.equal(f.hours(127), "৫.৩ দিন");
  assert.doesNotMatch(f.date("2026-07-22"), /[0-9]/);
  assert.equal(t("gt.currently", { name: "RW-9UGWCYX5" }), "এখন: RW-9UGWCYX5");
  const hiF = makeFormat("hi", translator("hi"));
  assert.equal(hiF.pct(0.43), "43%");
});
