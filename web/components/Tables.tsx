"use client";

import { useState } from "react";
import { fmtCount, fmtDate, fmtHours, fmtPct, levelLabel } from "@/lib/format";
import { t } from "@/lib/i18n";
import type { AreaRow, AuthorityRow, Measures, TimelineEntry } from "@/lib/types";

function RateMeter({ rate }: { rate: number | null }) {
  const pct = Math.round((rate ?? 0) * 100);
  return (
    <div className="meter" title={`${pct}% resolved`}>
      <div className="meter-track" aria-hidden><div className="meter-fill" style={{ width: `${pct}%` }} /></div>
      <span className="num" style={{ minWidth: 38, textAlign: "right" }}>{fmtPct(rate)}</span>
    </div>
  );
}

function MeasureCells({ m }: { m: Measures }) {
  return (
    <>
      <td className="num">{fmtCount(m.total)}</td>
      <td className="num">{fmtCount(m.open)}</td>
      <td className="num">{fmtCount(m.resolved)}</td>
      <td><RateMeter rate={m.resolution_rate} /></td>
      <td className="num">{fmtHours(m.avg_resolution_hours)}</td>
      <td className="num">{fmtCount(m.breaches)}</td>
    </>
  );
}

function MeasureHeads() {
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
                <div className="muted small">{levelLabel(r.level)}</div>
              </td>
              <MeasureCells m={r} />
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > 10 && (
        <button type="button" className="btn" style={{ marginTop: 10 }} onClick={() => setShowAll(!showAll)}>
          {showAll ? "Show top 10" : `Show all ${rows.length}`}
        </button>
      )}
    </div>
  );
}

export function AuthorityTable({ rows }: { rows: AuthorityRow[] }) {
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
  return (
    <nav className="crumbs" aria-label="Area">
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

const EVENT_TEXT: Record<string, (d: Record<string, unknown>) => string> = {
  ticket_created: () => "Issue verified and ticket opened",
  report_attached: (d) => `Verified report received (${d.unique_reporters} citizen(s) so far)`,
  status_changed: (d) => `Status: ${String(d.to_status).replace("_", " ")}${d.note ? ` — ${d.note}` : ""}`,
  note: (d) => `Note: ${d.note}`,
  sighting: () => "A citizen on site confirmed the issue is still there",
  assigned: (d) => `Assigned to ${d.assigned_to}`,
  escalated: (d) => `Escalated to ${d.to_node} (${d.reason})`,
  fix_submitted: (d) => `Repair photo submitted (vision check: ${d.vision})`,
  fix_proof_rejected: (d) => `Repair photo refused: ${d.reason}`,
  resolved: (d) => `Resolved — ${d.reason}`,
  reopened: (d) => `Reopened — ${d.reason}`,
};

export function Timeline({ entries }: { entries: TimelineEntry[] }) {
  if (entries.length === 0) return <p className="muted">No history yet.</p>;
  return (
    <ol className="timeline">
      {entries.map((e, i) => (
        <li key={i}>
          <span className="muted small num">{fmtDate(e.on)}</span>
          <div>
            <div>{(EVENT_TEXT[e.type] ?? (() => e.type.replace(/_/g, " ")))(e.details)}</div>
            <div className="muted small">by {e.by}</div>
            {typeof e.details.photo === "string" && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={e.details.photo} alt="Repair photo" style={{ marginTop: 8, maxWidth: 220, borderRadius: 8 }} />
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

export function Photos({ urls }: { urls: string[] }) {
  if (urls.length === 0) return <p className="muted">No photos.</p>;
  return (
    <div className="photos">
      {urls.map((u) => (
        // eslint-disable-next-line @next/next/no-img-element
        <img key={u} src={u} alt="Citizen photo (faces and number plates blurred)" loading="lazy" />
      ))}
    </div>
  );
}
