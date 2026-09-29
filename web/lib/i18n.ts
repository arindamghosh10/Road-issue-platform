// Translations (brief §15): English, Hindi, Bengali. Every user-facing label goes
// through t(). Components get t (and locale-aware formatters) from useI18n() in
// ./locale.tsx; the chosen language lives per visitor, in a cookie, never in a
// module-level variable (the server renders many visitors at once).
//
// Adding a language: copy messages/en.ts, translate, add it below. TypeScript refuses
// to build if a dictionary is missing a key.

import en from "./messages/en";
import hi from "./messages/hi";
import bn from "./messages/bn";

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

export function translator(locale: Locale): T {
  const dict = dictionaries[locale];
  return (key, vars = {}) => {
    let text = dict[key] ?? en[key];
    for (const [k, v] of Object.entries(vars)) text = text.replaceAll(`{${k}}`, String(v));
    return text;
  };
}

/** Intl locale: Hindi/Bengali month names, but Latin digits everywhere so numbers,
 * ticket refs and charts read the same in every language. */
export const intlLocale = (locale: Locale) => `${locale}-IN-u-nu-latn`;
