"use client";

import { useI18n } from "@/lib/locale";
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
  const { t, f } = useI18n();
  const v = (x: string) => (s ? x : "…");
  return (
    <section className="kpis" aria-label={t("kpi.label")}>
      <Tile label={t("kpi.reported")} value={v(f.count(s?.total ?? 0))}
            note={s ? t("kpi.citizens", { n: f.count(s.verified_reporters) }) : undefined} />
      <Tile label={t("kpi.open")} value={v(f.count(s?.open ?? 0))}
            note={s ? t("kpi.working", { n: f.count(s.by_status.acknowledged + s.by_status.in_progress) }) : undefined} />
      <Tile label={t("kpi.resolved")} value={v(f.count(s?.resolved ?? 0))}
            note={s ? t("kpi.rate", { pct: f.pct(s.resolution_rate) }) : undefined} />
      <Tile label={t("kpi.avgTime")} value={v(f.hours(s?.avg_resolution_hours))} />
      <Tile label={t("kpi.sla")} value={v(f.pct(s?.sla_compliance))}
            note={s ? t("kpi.slaHint", { n: f.count(s.breaches) }) : undefined} />
    </section>
  );
}
