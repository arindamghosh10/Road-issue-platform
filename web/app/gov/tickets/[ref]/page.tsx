"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { Photos, Timeline } from "@/components/Tables";
import { govGet, govPost } from "@/lib/api";
import { fmtDate, fmtSlaLeft, statusLabel } from "@/lib/format";
import { t } from "@/lib/i18n";
import type { Assignee, GovTicketDetail, TicketStatus } from "@/lib/types";
import { useData } from "@/lib/useData";
import { useOfficial } from "@/lib/useOfficial";

// Mirrors MANUAL_TRANSITIONS in backend/app/tickets/lifecycle.py (the API enforces it).
const NEXT: Partial<Record<TicketStatus, TicketStatus[]>> = {
  open: ["acknowledged", "in_progress"],
  acknowledged: ["in_progress"],
  reopened: ["acknowledged", "in_progress"],
};
const CAN_FIX: TicketStatus[] = ["open", "acknowledged", "in_progress", "reopened"];

function getPosition(): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) =>
    navigator.geolocation.getCurrentPosition(resolve, reject, { enableHighAccuracy: true, timeout: 15000 }));
}

export default function GovTicketPage() {
  const { ref } = useParams<{ ref: string }>();
  const { me } = useOfficial();
  const [version, setVersion] = useState(0);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [notePublic, setNotePublic] = useState(false);
  const [assignee, setAssignee] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);

  const detail = useData<GovTicketDetail>(me ? `${ref}|${version}` : null, () => govGet(`/tickets/${encodeURIComponent(ref)}`));
  const assignees = useData<Assignee[]>(me ? ref : null, () => govGet(`/tickets/${encodeURIComponent(ref)}/assignees`));

  async function act(fn: () => Promise<unknown>, success: string) {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
      setMsg({ ok: true, text: success });
      setVersion((v) => v + 1);
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function submitFix() {
    if (!photo) return;
    await act(async () => {
      const pos = await getPosition().catch(() => {
        throw new Error("Location is needed: allow location access and take the photo at the site.");
      });
      const form = new FormData();
      form.set("photo", photo);
      form.set("lat", String(pos.coords.latitude));
      form.set("lon", String(pos.coords.longitude));
      form.set("captured_at", new Date().toISOString());
      form.set("capture_source", "in_app_camera");
      await govPost(`/tickets/${encodeURIComponent(ref)}/fix-proof`, form);
      setPhoto(null);
    }, "Repair photo accepted. The original reporters have been asked to confirm the fix.");
  }

  if (detail.error) return <div className="page-title"><p className="error">{detail.error}</p><Link href="/gov">Back</Link></div>;
  const d = detail.data;
  if (!d) return <p className="page-title muted">Loading…</p>;
  const tk = d.ticket;
  const c = d.confirmations;

  return (
    <div className="stack" style={{ paddingBottom: 24 }}>
      <div className="page-title stack" style={{ gap: 6 }}>
        <Link href="/gov" className="small">← Work queue</Link>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h1>{tk.category_name} <span className="muted" style={{ fontWeight: 400 }}>· {tk.ref}</span></h1>
          <StatusBadge status={tk.status} />
        </div>
        <div className="ink-2">{tk.areas.map((a) => a.name).join(" › ")} · {t("ticket.authority")}: {tk.authority ?? "—"}</div>
      </div>

      <section className="kpis" aria-label="Ticket facts">
        <div className="tile"><div className="tile-label">Verified citizens</div><div className="tile-value">{tk.verified_reporters}</div>
          <div className="tile-note">{tk.report_count} report(s)</div></div>
        <div className="tile"><div className="tile-label">Severity · priority</div><div className="tile-value">{tk.severity} / 5</div>
          <div className="tile-note">priority score {tk.priority}</div></div>
        <div className="tile"><div className="tile-label">{t("ticket.deadline")}</div>
          <div className="tile-value" style={{ fontSize: 20 }}>{tk.status === "fix_submitted" ? "Paused" : fmtSlaLeft(tk.sla_hours_left)}</div>
          <div className="tile-note">{fmtDate(tk.sla_due_at)} · answerable: {tk.responsible_area}</div></div>
        <div className="tile"><div className="tile-label">Fix confirmations</div>
          {tk.status === "fix_submitted" || c.yes + c.no + c.partly > 0 ? (
            <>
              <div className="tile-value">{c.yes} of {c.reporters}</div>
              <div className="tile-note">{c.no} said no · {c.partly} said partly</div>
            </>
          ) : (
            <>
              <div className="tile-value" style={{ fontSize: 18 }}>Not requested yet</div>
              <div className="tile-note">asked after a repair photo is accepted</div>
            </>
          )}</div>
      </section>

      {msg && <p className={msg.ok ? "success" : "error"} role="status">{msg.text}</p>}

      <div className="grid-2">
        <section className="card stack" aria-labelledby="act-h">
          <h2 id="act-h">Actions</h2>
          <div className="row">
            {(NEXT[tk.status] ?? []).map((s) => (
              <button key={s} className="btn btn-primary" disabled={busy} type="button"
                      onClick={() => act(() => govPost(`/tickets/${encodeURIComponent(ref)}/status`, { status: s }), `Marked ${statusLabel(s).toLowerCase()}.`)}>
                Mark {statusLabel(s).toLowerCase()}
              </button>
            ))}
            {!NEXT[tk.status]?.length && <span className="muted small">No manual status change available now.</span>}
          </div>

          <div className="row" style={{ alignItems: "end" }}>
            <label className="field" style={{ flex: 1 }}>Assign to
              <select className="select" value={assignee} onChange={(e) => setAssignee(e.target.value)}>
                <option value="">{tk.assigned_to ? `Currently: ${tk.assigned_to}` : "Choose an official"}</option>
                {(assignees.data ?? []).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </label>
            <button className="btn" type="button" disabled={busy || !assignee}
                    onClick={() => act(() => govPost(`/tickets/${encodeURIComponent(ref)}/assign`, { official_id: assignee }), "Assigned.")}>
              Assign
            </button>
          </div>

          <div className="stack" style={{ gap: 6 }}>
            <label className="field">Add a note
              <textarea className="textarea" value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)} />
            </label>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <label className="row small" style={{ gap: 6 }}>
                <input type="checkbox" checked={notePublic} onChange={(e) => setNotePublic(e.target.checked)} />
                Show on the public timeline
              </label>
              <button className="btn" type="button" disabled={busy || !note.trim()}
                      onClick={() => act(async () => {
                        await govPost(`/tickets/${encodeURIComponent(ref)}/notes`, { text: note, public: notePublic });
                        setNote("");
                      }, "Note added.")}>
                Add note
              </button>
            </div>
          </div>

          {CAN_FIX.includes(tk.status) && (
            <div className="stack" style={{ gap: 6, borderTop: "1px solid var(--grid)", paddingTop: 12 }}>
              <h2>Submit repair photo</h2>
              <p className="muted small" style={{ margin: 0 }}>
                Take the photo at the site after the repair (within 50 m). On a phone this opens the camera.
                The vision model compares it with the citizen&apos;s photo, then the original reporters are asked to confirm.
              </p>
              <input type="file" accept="image/*" capture="environment" aria-label="Repair photo"
                     onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
              <div><button className="btn btn-primary" type="button" disabled={busy || !photo} onClick={submitFix}>
                Submit repair photo
              </button></div>
            </div>
          )}
        </section>

        <section className="card" aria-labelledby="gtl-h">
          <div className="card-head"><h2 id="gtl-h">{t("section.timeline")}</h2></div>
          <Timeline entries={d.timeline} />
        </section>
      </div>

      <section className="card" aria-labelledby="gph-h">
        <div className="card-head"><h2 id="gph-h">{t("section.photos")}</h2><span className="muted small">sanitized citizen photos</span></div>
        <Photos urls={tk.photos} />
      </section>
    </div>
  );
}
