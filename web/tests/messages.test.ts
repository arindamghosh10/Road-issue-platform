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
    }
  });
}
