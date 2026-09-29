// Translations for the citizen app: English, Hindi, Bengali (brief §15).
//
// Pure TypeScript (no React Native imports) so the rules here are unit-tested with
// plain Node. Screens get `t` from useI18n() in ./locale.tsx.
//
// The server sends stable codes (check results, rejection reasons, notification kinds)
// plus values; this file turns them into sentences in the reader's language, falling
// back to the server's English text for anything it doesn't recognise.

import en from "./messages/en.ts";
import hi from "./messages/hi.ts";
import bn from "./messages/bn.ts";

export type MessageKey = keyof typeof en;
export type Dictionary = Record<MessageKey, string>;

export const LOCALES = ["en", "hi", "bn"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "en";
/** Each language's name in its own script, for the language picker. */
export const LOCALE_NAMES: Record<Locale, string> = { en: "English", hi: "हिन्दी", bn: "বাংলা" };

const dictionaries: Record<Locale, Dictionary> = { en, hi, bn };
export const isLocale = (x: unknown): x is Locale => LOCALES.includes(x as Locale);

/** First supported language in the phone's preference list, else English. */
export function pickLocale(languageCodes: (string | null | undefined)[]): Locale {
  for (const code of languageCodes) {
    const base = code?.toLowerCase().split("-")[0];
    if (isLocale(base)) return base;
  }
  return DEFAULT_LOCALE;
}

export type Vars = Record<string, string | number>;
export type T = (key: MessageKey, vars?: Vars) => string;

export function translator(locale: Locale): T {
  const dict = dictionaries[locale];
  return (key, vars = {}) => {
    let text = dict[key] ?? en[key];
    for (const [k, v] of Object.entries(vars)) text = text.split(`{${k}}`).join(String(v));
    return text;
  };
}

const has = (key: string): key is MessageKey => key in en;

/** "22 Jul 2026" / "22 जुल॰ 2026" / "22 জুল, 2026" — month in the reader's language,
 * Latin digits everywhere so ticket numbers and dates read the same in every language. */
export function formatDate(locale: Locale, iso: string): string {
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  try {
    return d.toLocaleDateString(`${locale}-IN-u-nu-latn`, { day: "numeric", month: "short", year: "numeric" });
  } catch {
    return d.toISOString().slice(0, 10); // very old JS engines without Intl
  }
}

// --- Server codes → sentences ----------------------------------------------------------

type Params = Record<string, unknown>;

/** A verification result or rejection reason, by its code. */
export function codeText(t: T, code: string | null | undefined, params: Params = {}, fallback = ""): string {
  if (!code) return fallback;
  if (code === "capture.warnings") {
    const warnings = Array.isArray(params.warnings) ? (params.warnings as string[]) : [];
    const lines = warnings.map((w) => (has(`warn.${w}`) ? t(`warn.${w}` as MessageKey, { m: String(params.gps_m ?? "?") }) : w));
    return lines.join("; ") || fallback;
  }
  if (code === "vision.wrong_category") {
    const cat = `cat.${String(params.category)}`;
    return t("code.vision.wrong_category", { category: has(cat) ? t(cat as MessageKey) : String(params.category) });
  }
  if (code === "low_score") {
    return t("code.low_score", { reason: codeText(t, String(params.weakest ?? ""), params, "…") });
  }
  const key = `code.${code}`;
  if (!has(key)) return fallback;
  return t(key as MessageKey, Object.fromEntries(Object.entries(params).map(([k, v]) => [k, String(v)])));
}

export type CheckIn = { name: string; reason: string; code?: string; params?: Params };

/** A verification check as two lines: what was checked, and what we found. */
export function checkLines(t: T, c: CheckIn): { title: string; detail: string } {
  const titleKey = `check.${c.name}`;
  return {
    title: has(titleKey) ? t(titleKey as MessageKey) : c.name,
    detail: codeText(t, c.code, c.params ?? {}, c.reason),
  };
}

export type NoticeIn = { kind: string; title: string; body: string; ticket_ref: string | null; params?: Params };

/** An inbox notification in the reader's language (server English for unknown kinds). */
export function noticeText(t: T, n: NoticeIn): { title: string; body: string } {
  const ref = n.ticket_ref ?? "";
  const p = n.params ?? {};
  switch (n.kind) {
    case "report_verified":
      return {
        title: t("n.report_verified.title", { ref }),
        body: p.reporters != null ? t("n.report_verified.body", { ref, n: String(p.reporters) })
          : t("n.report_verified.bodyShort", { ref }),
      };
    case "report_rejected":
      return { title: t("n.report_rejected.title"), body: codeText(t, p.reason as string | undefined, p, n.body) };
    case "fix_confirmation_request":
    case "ticket_resolved":
    case "ticket_reopened":
      return { title: t(`n.${n.kind}.title` as MessageKey, { ref }), body: t(`n.${n.kind}.body` as MessageKey) };
    default:
      return { title: n.title, body: n.body };
  }
}

// Citizen-facing API errors are fixed English sentences (backend/app/api/citizen.py,
// identity/service.py, tickets/resolution.py); match them to translations.
const SERVER_ERRORS: Record<string, MessageKey> = {
  "Enter a valid Indian mobile number.": "err.invalidPhone",
  "This account is suspended.": "err.suspended",
  "Too many codes requested. Try again later.": "err.tooManyCodes",
  "Code expired. Request a new one.": "err.codeExpired",
  "Incorrect code.": "err.wrongCode",
  "Sign in required.": "err.signIn",
  "This issue is already resolved.": "err.alreadyResolved",
  "GPS location is too imprecise. Try again outdoors.": "err.gpsImprecise",
  "You already reported this issue.": "err.alreadyReported",
  "You already confirmed this issue.": "err.alreadyConfirmed",
  "This ticket is not waiting for confirmation.": "err.notWaiting",
  "Only citizens who reported this issue can confirm the fix.": "err.onlyReporters",
  "Ticket not found.": "err.notFound",
  "Report not found.": "err.notFound",
};

/** An error to show the citizen, in their language where we know the message. */
export function errorText(t: T, e: unknown): string {
  const status = typeof (e as { status?: unknown })?.status === "number" ? (e as { status: number }).status : null;
  const message = e instanceof Error ? e.message : String(e ?? "");
  if (status === 0) return t("err.network");
  if (SERVER_ERRORS[message]) return t(SERVER_ERRORS[message]);
  if (message.startsWith("You need to be within")) return t("err.tooFar");
  if (status === 429) return t("err.tooMany");
  if (status === 413) return t("err.photoTooBig");
  if (status != null && !message) return t("err.generic", { status });
  return message || t("err.generic", { status: status ?? "?" });
}
