// Translations (brief §15): English, Hindi, Bengali. Every user-facing label goes
// through t(). Components get t (and locale-aware formatters) from useI18n() in
// ./locale.tsx; the chosen language lives per visitor, in a cookie, never in a
// module-level variable (the server renders many visitors at once).
//
// Adding a language: copy messages/en.ts, translate, add it below. TypeScript refuses
// to build if a dictionary is missing a key.

// Explicit .ts extensions so the plain-Node tests (npm test) can load this file.
import en from "./messages/en.ts";
import hi from "./messages/hi.ts";
import bn from "./messages/bn.ts";

export type MessageKey = keyof typeof en;
export type Dictionary = Record<MessageKey, string>;

export const LOCALES = ["en", "hi", "bn"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "en";
export const LOCALE_COOKIE = "rw_lang";

/** Each language's name in its own script, for the language menu. */
export const LOCALE_NAMES: Record<Locale, string> = { en: "English", hi: "हिन्दी", bn: "বাংলা" };

const dictionaries: Record<Locale, Dictionary> = { en, hi, bn };

export const isLocale = (x: unknown): x is Locale => LOCALES.includes(x as Locale);

/** Pick a language from an Accept-Language header ("bn-IN,bn;q=0.9,en;q=0.8"). */
export function negotiateLocale(header: string | null | undefined): Locale {
  for (const part of (header ?? "").split(",")) {
    const code = part.split(";")[0].trim().toLowerCase().split("-")[0];
    if (isLocale(code)) return code;
  }
  return DEFAULT_LOCALE;
}

export type Vars = Record<string, string | number>;
export type T = (key: MessageKey, vars?: Vars) => string;

/** Bengali is written with Bengali digits (০–৯); English and Hindi use 0–9. Codes
 * people type or search (ticket refs like RW-9UGWCYX5, phone numbers) are never
 * converted: only numbers passed to t() as numbers, and formatter output. */
const BENGALI_DIGITS = "০১২৩৪৫৬৭৮৯";
export function localizeDigits(locale: Locale, text: string): string {
  return locale === "bn" ? text.replace(/[0-9]/g, (d) => BENGALI_DIGITS[Number(d)]) : text;
}

export function translator(locale: Locale): T {
  const dict = dictionaries[locale];
  return (key, vars = {}) => {
    let text = dict[key] ?? en[key];
    for (const [k, v] of Object.entries(vars)) {
      text = text.replaceAll(`{${k}}`, typeof v === "number" ? localizeDigits(locale, String(v)) : v);
    }
    return text;
  };
}

/** Intl locale for dates and numbers: month names in the reader's language; Bengali
 * digits for Bengali, Latin digits for English and Hindi. */
export const intlLocale = (locale: Locale) => `${locale}-IN-u-nu-${locale === "bn" ? "beng" : "latn"}`;
