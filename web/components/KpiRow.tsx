import { fmtCount, fmtHours, fmtPct } from "@/lib/format";
import { t } from "@/lib/i18n";
import type { Summary } from "@/lib/types";

function Tile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      {note ? <div className="tile-note">{note}</div> : null}
    </div>
  );
}

/** Headline numbers as stat tiles (a number is not a chart). */
export function KpiRow({ s }: { s: Summary | null }) {
  const v = (x: string) => (s ? x : "…");
  return (
    <section className="kpis" aria-label="Key figures">
      <Tile label={t("kpi.reported")} value={v(fmtCount(s?.total ?? 0))}
            note={s ? `${fmtCount(s.verified_reporters)} ${t("kpi.citizens")}` : undefined} />
      <Tile label={t("kpi.open")} value={v(fmtCount(s?.open ?? 0))}
            note={s ? `${fmtCount(s.by_status.acknowledged + s.by_status.in_progress)} being worked on` : undefined} />
      <Tile label={t("kpi.resolved")} value={v(fmtCount(s?.resolved ?? 0))}
            note={s ? `${fmtPct(s.resolution_rate)} ${t("kpi.resolutionRate").toLowerCase()}` : undefined} />
      <Tile label={t("kpi.avgTime")} value={v(fmtHours(s?.avg_resolution_hours))} />
      <Tile label={t("kpi.sla")} value={v(fmtPct(s?.sla_compliance))}
            note={s ? t("kpi.slaHint", { breaches: s.breaches }) : undefined} />
    </section>
  );
}
