"use client";

// Audit log (platform admin): sign-ins, exports, repair photos, bans and admin changes,
// newest first. Citizens appear only as a pseudonym.

import { useState } from "react";
import { adminGet } from "@/lib/api";
import { useI18n } from "@/lib/locale";
import type { AuditRow } from "@/lib/types";
import { useData } from "@/lib/useData";

// Every action the backend records (grep audit.record / _audit in backend/app).
const ACTIONS = [
  "official_login", "password_change", "official_2fa_enabled", "csv_export", "rate_limited",
  "citizen_login", "official_created", "official_updated", "password_reset", "two_factor_reset",
  "deadlines_changed", "areas_imported", "tenant_created", "authority_created",
  "reporter_banned", "reporter_unbanned",
];

export function AuditTab() {
  const { t, f } = useI18n();
  const [action, setAction] = useState("");
  const [failedOnly, setFailedOnly] = useState(false);
  const rows = useData<AuditRow[]>(`audit|${action}|${failedOnly}`,
    () => adminGet(`/audit?limit=300${action ? `&action=${action}` : ""}${failedOnly ? "&success=false" : ""}`));
  const time = (iso: string) => `${f.date(iso)} ${new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`;

  return (
    <section className="card stack" aria-labelledby="audit-h">
      <div className="card-head" style={{ marginBottom: 0 }}>
        <div className="stack" style={{ gap: 2 }}>
          <h2 id="audit-h">{t("audit.title")}</h2>
          <span className="muted small">{t("audit.hint")}</span>
        </div>
        <div className="row">
          <label className="field">{t("audit.filter")}
            <select className="select" value={action} onChange={(e) => setAction(e.target.value)}>
              <option value="">{t("audit.allActions")}</option>
              {ACTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </label>
          <label className="row small" style={{ gap: 6, alignSelf: "end", minHeight: 36 }}>
            <input type="checkbox" checked={failedOnly} onChange={(e) => setFailedOnly(e.target.checked)} />
            {t("audit.failedOnly")}
          </label>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>{t("audit.col.when")}</th><th>{t("audit.col.action")}</th><th>{t("audit.col.who")}</th>
              <th>{t("audit.col.target")}</th><th>{t("audit.col.ok")}</th><th>{t("audit.col.details")}</th></tr>
          </thead>
          <tbody>
            {(rows.data ?? []).map((a) => (
              <tr key={a.id}>
                <td className="num" style={{ whiteSpace: "nowrap" }}>{time(a.created_at)}</td>
                <td><code className="small">{a.action}</code></td>
                <td className="small">{a.actor_type}{a.actor_id ? <div className="muted">{a.actor_id}</div> : null}</td>
                <td className="small">{a.target ?? "—"}</td>
                <td>{a.success ? t("audit.ok") : <span className="chip chip-off">{t("audit.failed")}</span>}</td>
                <td className="small muted" style={{ maxWidth: 360, overflowWrap: "anywhere" }}>
                  {Object.keys(a.details ?? {}).length ? JSON.stringify(a.details) : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.data?.length === 0 && <p className="muted">{t("audit.empty")}</p>}
      </div>
    </section>
  );
}
