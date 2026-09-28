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

export const CATEGORIES = [
  { code: "pothole", label: "Pothole", icon: "◉" },
  { code: "bridge_leak", label: "Bridge leak", icon: "💧" },
  { code: "bridge_crack", label: "Bridge crack", icon: "⚡" },
  { code: "broken_railing", label: "Broken railing", icon: "⛓" },
  { code: "broken_divider", label: "Broken divider", icon: "▥" },
  { code: "missing_signage", label: "Missing sign", icon: "⚠" },
  { code: "waterlogging", label: "Waterlogging", icon: "≋" },
  { code: "road_cave_in", label: "Road cave-in", icon: "▼" },
  { code: "other", label: "Other", icon: "…" },
] as const;

export type TicketStatus = "open" | "acknowledged" | "in_progress" | "fix_submitted" | "resolved" | "reopened";
export type ReportStatus = "under_verification" | "verified" | "rejected";

/** Status → reserved colour + icon + words (never colour alone). */
export function ticketStatusView(s: TicketStatus): { label: string; icon: string; color: string } {
  switch (s) {
    case "resolved": return { label: "Resolved", icon: "✓", color: "#0ca30c" };
    case "fix_submitted": return { label: "Fix awaiting your check", icon: "?", color: "#fab219" };
    case "acknowledged": return { label: "Acknowledged", icon: "⚒", color: "#ec835a" };
    case "in_progress": return { label: "Being fixed", icon: "⚒", color: "#ec835a" };
    case "reopened": return { label: "Reopened", icon: "!", color: "#d03b3b" };
    default: return { label: "Open", icon: "!", color: "#d03b3b" };
  }
}

export function reportStatusView(s: ReportStatus): { label: string; icon: string; color: string } {
  switch (s) {
    case "verified": return { label: "Verified", icon: "✓", color: "#0ca30c" };
    case "rejected": return { label: "Not verified", icon: "✕", color: "#d03b3b" };
    default: return { label: "Checking…", icon: "…", color: "#fab219" };
  }
}

export function formatDate(iso: string): string {
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;
}

/** Plain-language names for the server's verification checks. */
export const CHECK_NAMES: Record<string, string> = {
  capture_integrity: "Photo taken live in the app",
  location: "Location is inside a covered area",
  vision: "Photo shows the reported damage",
  duplicate_image: "Photo not submitted before",
};
