// Pure helpers with no React Native imports, so they can be unit-tested with plain Node
// (see tests/logic.test.ts).

/** Canonical Indian mobile number: "+91" + 10 digits starting 6–9. Mirrors the backend. */
export function normalizePhone(input: string): string | null {
  let digits = input.replace(/\D/g, "");
  if (digits.length === 12 && digits.startsWith("91")) digits = digits.slice(2);
  else if (digits.length === 11 && digits.startsWith("0")) digits = digits.slice(1);
  if (digits.length !== 10 || !"6789".includes(digits[0])) return null;
  return `+91${digits}`;
}

export function formatDistance(metres: number): string {
  if (metres < 1000) return `${Math.round(metres / 10) * 10} m`;
  return `${(metres / 1000).toFixed(metres < 10_000 ? 1 : 0)} km`;
}

/** GPS quality as the citizen should understand it. Matches the backend thresholds. */
export function gpsQuality(accuracyM: number | null | undefined): "good" | "weak" | "too-poor" {
  if (accuracyM == null || accuracyM > 150) return "too-poor";
  return accuracyM > 50 ? "weak" : "good";
}

// Chip order on the report screen. Labels are translated: see messages/*.ts "cat.*".
export const CATEGORIES = [
  { code: "pothole", icon: "◉" },
  { code: "bridge_leak", icon: "💧" },
  { code: "bridge_crack", icon: "⚡" },
  { code: "broken_railing", icon: "⛓" },
  { code: "broken_divider", icon: "▥" },
  { code: "missing_signage", icon: "⚠" },
  { code: "waterlogging", icon: "≋" },
  { code: "road_cave_in", icon: "▼" },
  { code: "other", icon: "…" },
] as const;

export type TicketStatus = "open" | "acknowledged" | "in_progress" | "fix_submitted" | "resolved" | "reopened";
export type ReportStatus = "under_verification" | "verified" | "rejected";

/** Status → reserved colour + icon + words (never colour alone). `key` is the
 * translation key for the words. */
export function ticketStatusView(s: TicketStatus): { key: `ts.${TicketStatus}`; icon: string; color: string } {
  switch (s) {
    case "resolved": return { key: "ts.resolved", icon: "✓", color: "#0ca30c" };
    case "fix_submitted": return { key: "ts.fix_submitted", icon: "?", color: "#fab219" };
    case "acknowledged": return { key: "ts.acknowledged", icon: "⚒", color: "#ec835a" };
    case "in_progress": return { key: "ts.in_progress", icon: "⚒", color: "#ec835a" };
    case "reopened": return { key: "ts.reopened", icon: "!", color: "#d03b3b" };
    default: return { key: "ts.open", icon: "!", color: "#d03b3b" };
  }
}

export function reportStatusView(s: ReportStatus): { key: `rs.${ReportStatus}`; icon: string; color: string } {
  switch (s) {
    case "verified": return { key: "rs.verified", icon: "✓", color: "#0ca30c" };
    case "rejected": return { key: "rs.rejected", icon: "✕", color: "#d03b3b" };
    default: return { key: "rs.under_verification", icon: "…", color: "#fab219" };
  }
}
