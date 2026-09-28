// Minimal i18n structure (brief §15): every user-facing label goes through t().
// English ships now; Hindi ("hi") and Bengali ("bn") dictionaries can be added as
// files in ./messages with the same keys, then selected by a language switcher.

import en from "./messages/en";

export type MessageKey = keyof typeof en;
const dictionaries: Record<string, Partial<Record<MessageKey, string>>> = { en };
let current = "en";

export function setLocale(locale: string) {
  if (dictionaries[locale]) current = locale;
}

export function t(key: MessageKey, vars: Record<string, string | number> = {}): string {
  let text = dictionaries[current][key] ?? en[key];
  for (const [k, v] of Object.entries(vars)) text = text.replace(`{${k}}`, String(v));
  return text;
}
