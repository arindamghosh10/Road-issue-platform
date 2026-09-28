import { STATUS_GROUPS, statusGroup, statusLabel } from "@/lib/format";
import type { TicketStatus } from "@/lib/types";

/** Status = reserved colour + icon + text label, so it never relies on colour alone. */
export function StatusBadge({ status }: { status: TicketStatus }) {
  const g = STATUS_GROUPS.find((x) => x.key === statusGroup(status))!;
  return (
    <span className="badge">
      <span className="badge-dot" style={{ background: g.color }} aria-hidden>{g.icon}</span>
      {statusLabel(status)}
    </span>
  );
}
