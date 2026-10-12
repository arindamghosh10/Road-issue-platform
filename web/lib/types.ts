// Mirrors the backend response models (backend/app/api/views.py, stats.py, gov.py).
// None of these carry citizen identity: only aggregates and sanitized photos.

export type TicketStatus =
  | "open"
  | "acknowledged"
  | "in_progress"
  | "fix_submitted"
  | "resolved"
  | "reopened";

export interface Area {
  id: number;
  name: string;
  level: string;
}

export interface PublicTicket {
  ref: string;
  category: string;
  category_name: string;
  status: TicketStatus;
  severity: number;
  lat: number;
  lon: number;
  verified_reporters: number;
  report_count: number;
  also_seen: number; // "I see this too" confirmations on site (no photo)
  reported_on: string;
  sla_due_on: string | null;
  resolved_on: string | null;
  escalation_level: number;
  responsible_area: string | null;
  authority: string | null;
  areas: Area[];
  photos: string[];
}

export interface GovTicket extends PublicTicket {
  priority: number;
  sla_due_at: string | null;
  sla_hours_left: number | null;
  assigned_to: string | null;
  created_at: string;
  fix_submitted_at: string | null;
}

export interface TimelineEntry {
  type: string;
  on: string;
  by: string;
  details: Record<string, unknown>;
}

export interface Measures {
  total: number;
  open: number;
  resolved: number;
  breaches: number;
  resolution_rate: number | null;
  avg_resolution_hours: number | null;
  sla_compliance: number | null;
  verified_reporters: number;
}

export interface Summary extends Measures {
  by_status: Record<TicketStatus, number>;
}

export interface AreaRow extends Measures {
  id: number;
  name: string;
  level: string;
  has_children: boolean;
}

export interface AuthorityRow extends Measures {
  id: number;
  name: string;
  type: string;
}

export interface CategoryRow {
  code: string;
  name: string;
  total: number;
  open: number;
  resolved: number;
}

export interface TrendPoint {
  week: string;
  new: number;
  resolved: number;
}

export interface AgeingBucket {
  bucket: string;
  count: number;
}

export interface Category {
  code: string;
  name: string;
}

export interface Me {
  id: string;
  name: string;
  email: string;
  role: string;
  node_id: number | null;
  node: string | null;
  node_level: string | null;
  authority_id: number | null;
  totp_enabled: boolean;
  must_change_password: boolean;
  tenant_id: string | null;
  tenant: string | null;
}

// --- Administration ---------------------------------------------------------------

export type Role = "official" | "gov_admin" | "platform_admin";
export const isAdmin = (me: Me | null) => me?.role === "gov_admin" || me?.role === "platform_admin";

export interface TenantRow { id: string; name: string; root_node_id: number; root_node: string; root_level: string; officials: number }
export interface DeadlineRow { category: string; name: string; severity: number; default_hours: number; hours: number | null }
export interface AdminArea {
  id: number; name: string; level: string; lgd_code: string; parent_id: number | null;
  is_sample: boolean; has_boundary: boolean; children: number; tenant: string | null;
}
export interface AuthorityRow2 { id: number; name: string; type: string; jurisdiction_id: number | null; area: string | null }
export interface OfficialRow {
  id: string; name: string; email: string; role: Role; tenant_id: string | null; tenant: string | null;
  node_id: number | null; node: string | null; node_level: string | null;
  authority_id: number | null; authority: string | null;
  is_active: boolean; totp_enabled: boolean; must_change_password: boolean; created_on: string;
}
export interface ModerationRow {
  report_id: string; ticket_ref: string | null; category: string; status: "under_verification" | "verified" | "rejected";
  verification_score: number | null; rejection_reason: string | null; received_on: string;
  sender: { reports: number; verified: number; rejected: number; banned: boolean };
}
export interface AuditRow {
  id: number; created_at: string; actor_type: string; actor_id: string | null; action: string;
  target: string | null; success: boolean; details: Record<string, unknown>;
}

export interface GovTicketDetail {
  ticket: GovTicket;
  timeline: TimelineEntry[];
  confirmations: { reporters: number; yes: number; no: number; partly: number };
}

export interface Assignee {
  id: string;
  name: string;
}

export interface NotificationItem {
  id: number;
  kind: string;
  title: string;
  body: string;
  ticket_ref: string | null;
  created_at: string;
  read: boolean;
}

export interface Filters {
  jurisdictionId: number | null;
  category: string;
  days: number | null;
}
