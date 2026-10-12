"use client";

// Deadlines: hours a ticket may stay unresolved before it escalates, per issue type and
// severity, for one organisation. An empty cell means the RoadWatch default (shown as
// the placeholder). Edits are collected and saved together.

import { useMemo, useState } from "react";
import { adminGet, adminSend } from "@/lib/api";
import { useI18n } from "@/lib/locale";
import type { DeadlineRow, Me, TenantRow } from "@/lib/types";
import { useData } from "@/lib/useData";
import { OrgSelect } from "./shared";

const SEVERITIES = [1, 2, 3, 4, 5];
const MAX_HOURS = 8760;
const cellKey = (category: string, severity: number) => `${category}|${severity}`;

export function DeadlinesTab({ me, tenants }: { me: Me; tenants: TenantRow[] }) {
  const { t, f } = useI18n();
  const platform = me.role === "platform_admin";
  const [org, setOrg] = useState<string>(platform ? tenants[0]?.id ?? "" : me.tenant_id ?? "");
  const [version, setVersion] = useState(0);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const rows = useData<DeadlineRow[]>(org ? `dl|${org}|${version}` : null, () => adminGet(`/tenants/${org}/deadlines`));

  const byCategory = useMemo(() => {
    const out = new Map<string, DeadlineRow[]>();
    for (const r of rows.data ?? []) out.set(r.category, [...(out.get(r.category) ?? []), r]);
    return [...out.entries()];
  }, [rows.data]);

  const original = (r: DeadlineRow) => (r.hours == null ? "" : String(r.hours));
  const changes = (rows.data ?? []).filter((r) => {
    const v = edits[cellKey(r.category, r.severity)];
    return v !== undefined && v !== original(r);
  });
  const invalid = changes.some((r) => {
    const v = edits[cellKey(r.category, r.severity)];
    return v !== "" && !(/^\d+$/.test(v) && Number(v) >= 1 && Number(v) <= MAX_HOURS);
  });

  async function save() {
    setBusy(true);
    setMsg(null);
    try {
      await adminSend("PUT", `/tenants/${org}/deadlines`, {
        changes: changes.map((r) => {
          const v = edits[cellKey(r.category, r.severity)];
          return { category: r.category, severity: r.severity, hours: v === "" ? null : Number(v) };
        }),
      });
      setEdits({});
      setVersion((x) => x + 1);
      setMsg({ ok: true, text: t("adm.saved") });
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card stack" aria-labelledby="dl-h">
      <div className="card-head" style={{ marginBottom: 0 }}>
        <div className="stack" style={{ gap: 2, maxWidth: 720 }}>
          <h2 id="dl-h">{t("dl.title")}</h2>
          <span className="muted small">{t("dl.hint")}</span>
        </div>
        {platform && <OrgSelect tenants={tenants} value={org} onChange={(id) => { setOrg(id); setEdits({}); }} />}
      </div>
      {!org && <p className="muted">{t("dl.noOrg")}</p>}
      {rows.error && <p className="error">{rows.error}</p>}
      {byCategory.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>{t("dl.category")}</th>
                {SEVERITIES.map((s) => <th key={s} className="num">{t("dl.severity", { n: s })}</th>)}</tr>
            </thead>
            <tbody>
              {byCategory.map(([code, cells]) => (
                <tr key={code}>
                  <td>{f.category(code, cells[0].name)}</td>
                  {cells.map((r) => {
                    const k = cellKey(r.category, r.severity);
                    const value = edits[k] ?? original(r);
                    const changed = value !== original(r);
                    return (
                      <td key={k} className="num">
                        <input className={`input dl-input${changed ? " changed" : ""}`} inputMode="numeric"
                               aria-label={`${f.category(code, r.name)}, ${t("dl.severity", { n: r.severity })}, ${t("dl.hours")}`}
                               placeholder={String(r.default_hours)} value={value}
                               onChange={(e) => setEdits({ ...edits, [k]: e.target.value.trim() })} />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {invalid && <p className="error" role="alert">{t("dl.invalid")}</p>}
      {msg && <p className={msg.ok ? "success" : "error"} role="status">{msg.text}</p>}
      <div className="row">
        <button type="button" className="btn btn-primary" disabled={busy || changes.length === 0 || invalid}
                onClick={save}>{t("dl.save")}</button>
        {changes.length > 0 && (
          <>
            <button type="button" className="btn" onClick={() => setEdits({})}>{t("dl.reset")}</button>
            <span className="muted small">{t("dl.changed", { n: changes.length })}</span>
          </>
        )}
      </div>
    </section>
  );
}
