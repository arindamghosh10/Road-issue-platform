"use client";

import { useState } from "react";
import type { Format } from "@/lib/format";
import type { MessageKey, T } from "@/lib/i18n";
import { useI18n } from "@/lib/locale";
import type { AreaRow, AuthorityRow, Measures, TicketStatus, TimelineEntry } from "@/lib/types";

function RateMeter({ rate }: { rate: number | null }) {
  const { t, f } = useI18n();
  const pct = Math.round((rate ?? 0) * 100);
  return (
    <div className="meter" title={t("table.resolvedPct", { pct: `${pct}%` })}>
      <div className="meter-track" aria-hidden><div className="meter-fill" style={{ width: `${pct}%` }} /></div>
      <span className="num" style={{ minWidth: 38, textAlign: "right" }}>{f.pct(rate)}</span>
    </div>
  );
}

function MeasureCells({ m }: { m: Measures }) {
  const { f } = useI18n();
  return (
    <>
      <td className="num">{f.count(m.total)}</td>
      <td className="num">{f.count(m.open)}</td>
      <td className="num">{f.count(m.resolved)}</td>
      <td><RateMeter rate={m.resolution_rate} /></td>
      <td className="num">{f.hours(m.avg_resolution_hours)}</td>
      <td className="num">{f.count(m.breaches)}</td>
    </>
  );
}

function MeasureHeads() {
  const { t } = useI18n();
  return (
    <>
      <th className="num">{t("table.reported")}</th>
      <th className="num">{t("table.open")}</th>
      <th className="num">{t("table.resolved")}</th>
      <th>{t("table.rate")}</th>
      <th className="num">{t("table.avgTime")}</th>
      <th className="num">{t("table.breaches")}</th>
    </>
  );
}

/** Leaderboard of areas (best resolution rate first). Rows with sub-areas drill down. */
export function AreaTable({ rows, onDrill }: { rows: AreaRow[]; onDrill: (row: AreaRow) => void }) {
  const { t, f } = useI18n();
  const [showAll, setShowAll] = useState(false);
  if (rows.length === 0) return <p className="muted">{t("table.empty")}</p>;
  const visible = showAll ? rows : rows.slice(0, 10);
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>#</th><th>{t("table.area")}</th><MeasureHeads /></tr></thead>
        <tbody>
          {visible.map((r, i) => (
            <tr key={r.id} className={r.has_children ? "clickable" : undefined}
                onClick={() => r.has_children && onDrill(r)}>
              <td className="muted num">{i + 1}</td>
              <td>
                {r.has_children
                  ? <button type="button" className="crumbs-btn" style={{ background: "none", border: 0, padding: 0, color: "var(--accent-ink)", cursor: "pointer", textAlign: "left" }}
                            aria-label={`${t("table.drill")}: ${r.name}`}
                            onClick={(e) => { e.stopPropagation(); onDrill(r); }}>
                      {r.name} ›
                    </button>
                  : r.name}
                <div className="muted small">{f.level(r.level)}</div>
              </td>
              <MeasureCells m={r} />
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > 10 && (
        <button type="button" className="btn" style={{ marginTop: 10 }} onClick={() => setShowAll(!showAll)}>
          {showAll ? t("table.showTop") : t("table.showAll", { n: rows.length })}
        </button>
      )}
    </div>
  );
}

export function AuthorityTable({ rows }: { rows: AuthorityRow[] }) {
  const { t } = useI18n();
  if (rows.length === 0) return <p className="muted">{t("table.empty")}</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>{t("table.authority")}</th><MeasureHeads /></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}><td>{r.name}</td><MeasureCells m={r} /></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Breadcrumbs({ trail, onPick }: { trail: { id: number | null; name: string }[]; onPick: (index: number) => void }) {
  const { t } = useI18n();
  return (
    <nav className="crumbs" aria-label={t("filters.area")}>
      {trail.map((c, i) => (
        <span key={`${c.id}-${i}`} className="row" style={{ gap: 6 }}>
          {i > 0 && <span className="muted" aria-hidden>›</span>}
          {i === trail.length - 1
            ? <span aria-current="location">{c.name}</span>
            : <button type="button" onClick={() => onPick(i)}>{c.name}</button>}
        </span>
      ))}
    </nav>
  );
}

/** One timeline line in the reader's language. Free text (official notes, the reason
 * a repair photo was refused) is shown as written. */
function eventText(t: T, f: Format, type: string, d: Record<string, unknown>): string {
  const n = (x: unknown) => String(x ?? "?");
  switch (type) {
    case "ticket_created": return t("tl.ticket_created");
    case "report_attached": return t("tl.report_attached", { n: n(d.unique_reporters) });
    case "status_changed": {
      const line = t("tl.status_changed", { status: f.status(d.to_status as TicketStatus) });
      return d.note ? `${line} — ${d.note}` : line;
    }
    case "note": return t("tl.note", { note: n(d.note) });
    case "sighting": return t("tl.sighting");
    case "assigned": return t("tl.assigned", { name: n(d.assigned_to) });
    case "escalated":
      if (d.reason_code === "sla_breached") return t("tl.escalated.sla", { node: n(d.to_node), h: n(d.overdue_h) });
      if (d.reason_code === "fix_disputed") return t("tl.escalated.disputed", { node: n(d.to_node) });
      return t("tl.escalated", { node: n(d.to_node) });
    case "fix_submitted":
      if (d.vision === "passed") return t("tl.fix_submitted.passed");
      if (d.vision === "failed") return t("tl.fix_submitted.failed");
      return t("tl.fix_submitted");
    case "fix_proof_rejected": return t("tl.fix_proof_rejected", { reason: n(d.reason) });
    case "resolved":
      return d.reporters ? t("tl.resolved.counts", { yes: n(d.confirmed), n: n(d.reporters) }) : t("tl.resolved");
    case "reopened":
      return d.reporters ? t("tl.reopened.counts", { d: n(d.disputed), n: n(d.reporters) }) : t("tl.reopened");
    default: return type.replace(/_/g, " ");
  }
}

const ACTORS: Record<string, MessageKey> = { system: "tl.by.system", citizen: "tl.by.citizen", official: "tl.by.official" };

export function Timeline({ entries }: { entries: TimelineEntry[] }) {
  const { t, f } = useI18n();
  if (entries.length === 0) return <p className="muted">{t("tl.empty")}</p>;
  return (
    <ol className="timeline">
      {entries.map((e, i) => (
        <li key={i}>
          <span className="muted small num">{f.date(e.on)}</span>
          <div>
            <div>{eventText(t, f, e.type, e.details)}</div>
            {/* Officials' own names (government view) are shown as they are. */}
            <div className="muted small">{t("tl.by", { who: ACTORS[e.by] ? t(ACTORS[e.by]) : e.by })}</div>
            {typeof e.details.photo === "string" && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={e.details.photo} alt={t("tl.repairPhoto")} style={{ marginTop: 8, maxWidth: 220, borderRadius: 8 }} />
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

export function Photos({ urls }: { urls: string[] }) {
  const { t } = useI18n();
  if (urls.length === 0) return <p className="muted">{t("photos.empty")}</p>;
  return (
    <div className="photos">
      {urls.map((u) => (
        // eslint-disable-next-line @next/next/no-img-element
        <img key={u} src={u} alt={t("photos.alt")} loading="lazy" />
      ))}
    </div>
  );
}
