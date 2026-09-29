import type { TicketStatus } from "./types";
import { intlLocale, type Locale, type MessageKey, type T } from "./i18n";

// Four status groups, each tied to a reserved status colour + an icon + a label, so
// colour never carries the meaning alone (dataviz: status colours are reserved).
export type StatusGroup = "open" | "working" | "checking" | "resolved";

export function statusGroup(s: TicketStatus): StatusGroup {
  if (s === "resolved") return "resolved";
  if (s === "fix_submitted") return "checking";
  if (s === "acknowledged" || s === "in_progress") return "working";
  return "open";
}

export const STATUS_GROUPS: { key: StatusGroup; color: string; icon: string }[] = [
  { key: "open", color: "var(--status-critical)", icon: "!" },
  { key: "working", color: "var(--status-serious)", icon: "⚒" },
  { key: "checking", color: "var(--status-warning)", icon: "?" },
  { key: "resolved", color: "var(--status-good)", icon: "✓" },
];

// Concrete hex for places CSS variables can't reach (MapLibre paint properties).
export const STATUS_HEX: Record<StatusGroup, string> = {
  open: "#d03b3b",
  working: "#ec835a",
  checking: "#fab219",
  resolved: "#0ca30c",
};

const KNOWN_LEVELS = new Set(["state", "district", "municipality", "ward", "block", "gram_panchayat"]);
const KNOWN_CATEGORIES = new Set([
  "pothole", "waterlogging", "broken_divider", "missing_signage", "broken_railing",
  "bridge_leak", "bridge_crack", "road_cave_in", "other",
]);

/** Locale-aware formatters. Get them from useI18n() rather than building your own. */
export function makeFormat(locale: Locale, t: T) {
  const il = intlLocale(locale);
  const compact = new Intl.NumberFormat(il, { notation: "compact", maximumFractionDigits: 1 });
  const whole = new Intl.NumberFormat(il);

  const hours = (h: number | null | undefined): string => {
    if (h == null) return "—";
    if (h < 1) return t("time.lt1h");
    if (h < 48) return t("time.hours", { n: Math.round(h) });
    return t("time.days", { n: (h / 24).toFixed(h < 240 ? 1 : 0) });
  };

  return {
    count: (n: number) => (n >= 10_000 ? compact.format(n) : whole.format(n)),
    pct: (ratio: number | null | undefined) => (ratio == null ? "—" : `${Math.round(ratio * 100)}%`),
    hours,
    date(iso: string | null | undefined, opts: { year?: boolean } = {}): string {
      if (!iso) return "—";
      return new Date(iso.length === 10 ? `${iso}T00:00:00` : iso).toLocaleDateString(il, {
        day: "numeric", month: "short", ...(opts.year === false ? {} : { year: "numeric" }),
      });
    },
    slaLeft(h: number | null): string {
      if (h == null) return "—";
      return h < 0 ? t("time.overdue", { t: hours(-h) }) : t("time.left", { t: hours(h) });
    },
    status: (s: TicketStatus) => t(`status.${s}` as MessageKey),
    group: (g: StatusGroup) => t(`statusGroup.${g}` as MessageKey),
    level: (level: string) => (KNOWN_LEVELS.has(level) ? t(`level.${level}` as MessageKey) : level),
    /** Category name in the reader's language; the API's English name for unknown codes. */
    category: (code: string, fallback?: string) =>
      KNOWN_CATEGORIES.has(code) ? t(`cat.${code}` as MessageKey) : (fallback ?? code),
  };
}

export type Format = ReturnType<typeof makeFormat>;
