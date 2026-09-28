import type { TicketStatus } from "./types";
import { t, type MessageKey } from "./i18n";

const compact = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });
const whole = new Intl.NumberFormat("en-IN");

export const fmtCount = (n: number) => (n >= 10_000 ? compact.format(n) : whole.format(n));

export const fmtPct = (ratio: number | null | undefined) =>
  ratio == null ? "—" : `${Math.round(ratio * 100)}%`;

export function fmtHours(hours: number | null | undefined): string {
  if (hours == null) return "—";
  if (hours < 1) return "< 1 h";
  if (hours < 48) return `${Math.round(hours)} h`;
  return `${(hours / 24).toFixed(hours < 240 ? 1 : 0)} days`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso.length === 10 ? `${iso}T00:00:00` : iso).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function fmtSlaLeft(hours: number | null): string {
  if (hours == null) return "—";
  if (hours < 0) return `${fmtHours(-hours)} overdue`;
  return `${fmtHours(hours)} left`;
}

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

export const statusLabel = (s: TicketStatus) => t(`status.${s}` as MessageKey);
export const groupLabel = (g: StatusGroup) => t(`statusGroup.${g}` as MessageKey);

export const levelLabel = (level: string) =>
  ({ state: "State", district: "District", municipality: "Municipality", ward: "Ward",
     block: "Block", gram_panchayat: "Gram panchayat" })[level] ?? level;
