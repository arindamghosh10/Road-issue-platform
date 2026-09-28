"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { StatusBadge } from "@/components/StatusBadge";
import { Photos, Timeline } from "@/components/Tables";
import { publicGet } from "@/lib/api";
import { fmtDate, levelLabel } from "@/lib/format";
import { t } from "@/lib/i18n";
import type { PublicTicket, TimelineEntry } from "@/lib/types";
import { useData } from "@/lib/useData";

export default function PublicTicketPage() {
  const { ref } = useParams<{ ref: string }>();
  const ticket = useData<PublicTicket>(ref, () => publicGet(`/tickets/${encodeURIComponent(ref)}`));
  const timeline = useData<TimelineEntry[]>(ref, () => publicGet(`/tickets/${encodeURIComponent(ref)}/timeline`));
  const tk = ticket.data;

  if (ticket.error) return <div className="page-title"><p className="error">{ticket.error}</p><Link href="/">{t("ticket.back")}</Link></div>;
  if (!tk) return <p className="page-title muted">Loading…</p>;

  return (
    <div className="stack" style={{ paddingBottom: 24 }}>
      <div className="page-title stack" style={{ gap: 6 }}>
        <Link href="/" className="small">← {t("ticket.back")}</Link>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h1>{tk.category_name} <span className="muted" style={{ fontWeight: 400 }}>· {tk.ref}</span></h1>
          <StatusBadge status={tk.status} />
        </div>
        <div className="crumbs ink-2">
          {tk.areas.map((a, i) => (
            <span key={a.id}>{i > 0 && "› "}{a.name} <span className="muted small">({levelLabel(a.level)})</span></span>
          ))}
        </div>
      </div>

      <section className="kpis" aria-label="Ticket facts">
        <div className="tile"><div className="tile-label">Verified citizens</div><div className="tile-value">{tk.verified_reporters}</div>
          <div className="tile-note">{tk.report_count} report(s) merged{tk.also_seen ? ` · ${tk.also_seen} more saw it on site` : ""}</div></div>
        <div className="tile"><div className="tile-label">Severity</div><div className="tile-value">{tk.severity} / 5</div></div>
        <div className="tile"><div className="tile-label">{t("ticket.deadline")}</div><div className="tile-value" style={{ fontSize: 20 }}>{fmtDate(tk.sla_due_on)}</div>
          {tk.escalation_level > 0 && <div className="tile-note">{t("ticket.escalated", { n: tk.escalation_level })}</div>}</div>
        <div className="tile"><div className="tile-label">{t("ticket.responsible")}</div><div className="tile-value" style={{ fontSize: 18 }}>{tk.responsible_area ?? "—"}</div>
          <div className="tile-note">{t("ticket.authority")}: {tk.authority ?? "—"}</div></div>
      </section>

      <div className="grid-2">
        <section className="card" aria-labelledby="photos-h">
          <div className="card-head"><h2 id="photos-h">{t("section.photos")}</h2>
            <span className="muted small">faces and number plates are blurred</span></div>
          <Photos urls={tk.photos} />
        </section>
        <section className="card" aria-labelledby="tl-h">
          <div className="card-head"><h2 id="tl-h">{t("section.timeline")}</h2>
            <span className="muted small">reported {fmtDate(tk.reported_on)}</span></div>
          <Timeline entries={timeline.data ?? []} />
        </section>
      </div>
    </div>
  );
}
