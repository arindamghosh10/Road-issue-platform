"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { StatusBadge } from "@/components/StatusBadge";
import { Photos, Timeline } from "@/components/Tables";
import { publicGet } from "@/lib/api";
import { useI18n } from "@/lib/locale";
import type { PublicTicket, TimelineEntry } from "@/lib/types";
import { useData } from "@/lib/useData";

export default function PublicTicketPage() {
  const { ref } = useParams<{ ref: string }>();
  const ticket = useData<PublicTicket>(ref, () => publicGet(`/tickets/${encodeURIComponent(ref)}`));
  const timeline = useData<TimelineEntry[]>(ref, () => publicGet(`/tickets/${encodeURIComponent(ref)}/timeline`));
  const tk = ticket.data;
  const { t, f } = useI18n();

  if (ticket.error) return <div className="page-title"><p className="error">{ticket.error}</p><Link href="/">{t("ticket.back")}</Link></div>;
  if (!tk) return <p className="page-title muted">{t("common.loading")}</p>;

  return (
    <div className="stack" style={{ paddingBottom: 24 }}>
      <div className="page-title stack" style={{ gap: 6 }}>
        <Link href="/" className="small">← {t("ticket.back")}</Link>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h1>{f.category(tk.category, tk.category_name)} <span className="muted" style={{ fontWeight: 400 }}>· {tk.ref}</span></h1>
          <StatusBadge status={tk.status} />
        </div>
        <div className="crumbs ink-2">
          {tk.areas.map((a, i) => (
            <span key={a.id}>{i > 0 && "› "}{a.name} <span className="muted small">({f.level(a.level)})</span></span>
          ))}
        </div>
      </div>

      <section className="kpis" aria-label={t("ticket.facts")}>
        <div className="tile"><div className="tile-label">{t("ticket.verified")}</div><div className="tile-value">{f.num(tk.verified_reporters)}</div>
          <div className="tile-note">{t("ticket.merged", { n: tk.report_count })}{tk.also_seen ? ` · ${t("ticket.alsoSeen", { n: tk.also_seen })}` : ""}</div></div>
        <div className="tile"><div className="tile-label">{t("ticket.severity")}</div><div className="tile-value">{f.num(tk.severity)} / {f.num(5)}</div></div>
        <div className="tile"><div className="tile-label">{t("ticket.deadline")}</div><div className="tile-value" style={{ fontSize: 20 }}>{f.date(tk.sla_due_on)}</div>
          {tk.escalation_level > 0 && <div className="tile-note">{t("ticket.escalated", { n: tk.escalation_level })}</div>}</div>
        <div className="tile"><div className="tile-label">{t("ticket.responsible")}</div><div className="tile-value" style={{ fontSize: 18 }}>{tk.responsible_area ?? "—"}</div>
          <div className="tile-note">{t("ticket.authority")}: {tk.authority ?? "—"}</div></div>
      </section>

      <div className="grid-2">
        <section className="card" aria-labelledby="photos-h">
          <div className="card-head"><h2 id="photos-h">{t("section.photos")}</h2>
            <span className="muted small">{t("ticket.photosHint")}</span></div>
          <Photos urls={tk.photos} />
        </section>
        <section className="card" aria-labelledby="tl-h">
          <div className="card-head"><h2 id="tl-h">{t("section.timeline")}</h2>
            <span className="muted small">{t("ticket.reportedOn", { date: f.date(tk.reported_on) })}</span></div>
          <Timeline entries={timeline.data ?? []} />
        </section>
      </div>
    </div>
  );
}
