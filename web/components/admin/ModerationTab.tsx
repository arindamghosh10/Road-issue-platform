"use client";

// Report moderation (platform admin): recent reports with an anonymous history of
// whoever sent each one. Banning acts on "the sender of this report"; nobody here ever
// sees who that is.

import { useState } from "react";
import Link from "next/link";
import { adminGet, adminSend } from "@/lib/api";
import { useI18n } from "@/lib/locale";
import type { ModerationRow } from "@/lib/types";
import { useData } from "@/lib/useData";

const FILTERS = ["", "rejected", "verified"] as const;

export function ModerationTab() {
  const { t, f } = useI18n();
  const [status, setStatus] = useState<(typeof FILTERS)[number]>("");
  const [version, setVersion] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [withdraw, setWithdraw] = useState(true);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const rows = useData<ModerationRow[]>(`mod|${status}|${version}`,
    () => adminGet(`/reports?limit=200${status ? `&status=${status}` : ""}`));

  async function ban(row: ModerationRow) {
    setMsg(null);
    try {
      const r = await adminSend<{ reports_withdrawn: number }>("POST", `/reports/${row.report_id}/ban-sender`,
        { reason, withdraw_reports: withdraw });
      setMsg({ ok: true, text: t("mod.bannedDone", { n: r.reports_withdrawn }) });
      setOpen(null); setReason("");
      setVersion((v) => v + 1);
    } catch (e) { setMsg({ ok: false, text: (e as Error).message }); }
  }
  async function unban(row: ModerationRow) {
    setMsg(null);
    try {
      await adminSend("POST", `/reports/${row.report_id}/unban-sender`, { reason });
      setMsg({ ok: true, text: t("mod.unbannedDone") });
      setOpen(null); setReason("");
      setVersion((v) => v + 1);
    } catch (e) { setMsg({ ok: false, text: (e as Error).message }); }
  }

  return (
    <section className="card stack" aria-labelledby="mod-h">
      <div className="card-head" style={{ marginBottom: 0 }}>
        <div className="stack" style={{ gap: 2, maxWidth: 720 }}>
          <h2 id="mod-h">{t("mod.title")}</h2>
          <span className="muted small">{t("mod.hint")}</span>
        </div>
        <div className="segmented" role="group" aria-label={t("mod.filter")}>
          {FILTERS.map((x) => (
            <button key={x || "all"} type="button" aria-pressed={status === x} onClick={() => setStatus(x)}>
              {x === "" ? t("mod.all") : t(`mod.rs.${x}`)}
            </button>
          ))}
        </div>
      </div>
      {msg && <p className={msg.ok ? "success" : "error"} role="status">{msg.text}</p>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>{t("mod.col.received")}</th><th>{t("table.type")}</th><th>{t("mod.col.result")}</th>
              <th className="num">{t("mod.col.score")}</th><th>{t("table.ticket")}</th><th>{t("mod.col.sender")}</th><th /></tr>
          </thead>
          <tbody>
            {(rows.data ?? []).map((r) => (
              <tr key={r.report_id}>
                <td className="num">{f.date(r.received_on)}</td>
                <td>{f.category(r.category)}</td>
                <td>{t(`mod.rs.${r.status}`)}
                  {r.rejection_reason && <div className="muted small">{r.rejection_reason}</div>}</td>
                <td className="num">{r.verification_score == null ? "—" : f.num(Math.round(r.verification_score * 100) / 100)}</td>
                <td>{r.ticket_ref ? <Link href={`/tickets/${r.ticket_ref}`}>{r.ticket_ref}</Link> : "—"}</td>
                <td>{t("mod.senderStats", { n: r.sender.reports, v: r.sender.verified, r: r.sender.rejected })}
                  {r.sender.banned && <> <span className="chip chip-off">{t("mod.banned")}</span></>}</td>
                <td>
                  {open === r.report_id ? (
                    <div className="stack" style={{ gap: 6, minWidth: 260 }}>
                      <input className="input" aria-label={t("mod.reason")} placeholder={t("mod.reason")}
                             value={reason} onChange={(e) => setReason(e.target.value)} />
                      {!r.sender.banned && (
                        <label className="row small" style={{ gap: 6 }}>
                          <input type="checkbox" checked={withdraw} onChange={(e) => setWithdraw(e.target.checked)} />
                          {t("mod.withdraw")}
                        </label>
                      )}
                      <div className="actions">
                        <button type="button" className={r.sender.banned ? "btn btn-primary" : "btn btn-danger"}
                                disabled={reason.trim().length < 5}
                                onClick={() => (r.sender.banned ? unban(r) : ban(r))}>
                          {r.sender.banned ? t("mod.unban") : t("mod.confirmBan")}
                        </button>
                        <button type="button" className="btn" onClick={() => setOpen(null)}>{t("team.cancel")}</button>
                      </div>
                    </div>
                  ) : (
                    <button type="button" className="btn" onClick={() => { setOpen(r.report_id); setReason(""); }}>
                      {r.sender.banned ? t("mod.unban") : t("mod.ban")}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.data?.length === 0 && <p className="muted">{t("mod.empty")}</p>}
      </div>
    </section>
  );
}
