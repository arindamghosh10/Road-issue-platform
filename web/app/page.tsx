"use client";

// Public dashboard (no login): what's reported, what's fixed, and how each area and
// road authority is performing. Everything shown is aggregate or sanitized.

import dynamic from "next/dynamic";
import Link from "next/link";
import { useState } from "react";
import { CategoryBars, TrendChart } from "@/components/Charts";
import { FilterBar } from "@/components/FilterBar";
import { KpiRow } from "@/components/KpiRow";
import { StatusBadge } from "@/components/StatusBadge";
import { AreaTable, AuthorityTable, Breadcrumbs } from "@/components/Tables";
import { filterQuery, publicGet } from "@/lib/api";
import { useI18n } from "@/lib/locale";
import type { AreaRow, AuthorityRow, Category, CategoryRow, Filters, PublicTicket, Summary, TrendPoint } from "@/lib/types";
import { useData } from "@/lib/useData";

// MapLibre needs the browser, so the map is loaded client-side only.
const TicketMap = dynamic(() => import("@/components/TicketMap").then((m) => m.TicketMap), { ssr: false });

type Crumb = { id: number | null; name: string | null };

export default function PublicDashboard() {
  const { t, f } = useI18n();
  const [filters, setFilters] = useState<Filters>({ jurisdictionId: null, category: "", days: null });
  // name null = "All areas", shown in the reader's language.
  const [trail, setTrail] = useState<Crumb[]>([{ id: null, name: null }]);
  const [compare, setCompare] = useState<"district" | "municipality" | "ward">("municipality");
  const key = JSON.stringify(filters);
  const q = filterQuery(filters);
  const parent = trail[trail.length - 1].id;

  const categories = useData<Category[]>("cats", () => publicGet("/categories"));
  const summary = useData<Summary>(key, () => publicGet(`/stats/summary${q}`));
  const tickets = useData<PublicTicket[]>(key, () => publicGet(`/tickets${filterQuery(filters, { limit: 1000 })}`));
  const trend = useData<TrendPoint[]>(key, () => publicGet(`/stats/trends${filterQuery({ ...filters, days: null })}`));
  const cats = useData<CategoryRow[]>(key, () => publicGet(`/stats/categories${filterQuery({ ...filters, category: "" })}`));
  const atRoot = parent === null;
  const areas = useData<AreaRow[]>(`${key}|${parent}|${compare}`, () =>
    publicGet(`/stats/areas${filterQuery({ ...filters, jurisdictionId: null },
      atRoot ? { level: compare } : { parent_id: parent })}`));
  const auths = useData<AuthorityRow[]>(key, () => publicGet(`/stats/authorities${q}`));

  const drill = (row: AreaRow) => {
    setTrail([...trail, { id: row.id, name: row.name }]);
    setFilters({ ...filters, jurisdictionId: row.id });
  };
  const pickCrumb = (i: number) => {
    const next = trail.slice(0, i + 1);
    setTrail(next);
    setFilters({ ...filters, jurisdictionId: next[next.length - 1].id });
  };

  const loadingStyle = (loading: boolean) => ({ opacity: loading ? 0.55 : 1, transition: "opacity .15s" });

  return (
    <div className="stack" style={{ paddingBottom: 24 }}>
      <div className="page-title stack" style={{ gap: 4 }}>
        <h1>{t("app.title")}</h1>
        <p className="ink-2" style={{ margin: 0 }}>{t("app.tagline")}</p>
      </div>

      <FilterBar filters={filters} categories={categories.data ?? []} onChange={setFilters}>
        <div className="field">
          <span>{t("filters.area")}</span>
          <div style={{ minHeight: 36, display: "flex", alignItems: "center" }}>
            <Breadcrumbs trail={trail.map((c) => ({ ...c, name: c.name ?? t("filters.allAreas") }))} onPick={pickCrumb} />
          </div>
        </div>
      </FilterBar>

      {summary.error && <p className="error">{t("common.apiError", { error: summary.error })}</p>}
      <div style={loadingStyle(summary.loading)}><KpiRow s={summary.data} /></div>

      <section className="card" aria-labelledby="map-h">
        <div className="card-head">
          <h2 id="map-h">{t("section.map")}</h2>
          <span className="muted small">{t("public.mapHint", { n: tickets.data?.length ?? 0 })}</span>
        </div>
        <TicketMap tickets={tickets.data ?? []} />
      </section>

      <div className="grid-2">
        <section className="card" aria-labelledby="trend-h" style={loadingStyle(trend.loading)}>
          <div className="card-head"><h2 id="trend-h">{t("section.trend")}</h2><span className="muted small">{t("public.last12")}</span></div>
          <TrendChart data={trend.data ?? []} />
        </section>
        <section className="card" aria-labelledby="cat-h" style={loadingStyle(cats.loading)}>
          <div className="card-head"><h2 id="cat-h">{t("section.categories")}</h2></div>
          {cats.data?.length ? <CategoryBars data={cats.data} /> : <p className="muted">{t("table.empty")}</p>}
        </section>
      </div>

      <section className="card" aria-labelledby="lb-h" style={loadingStyle(areas.loading)}>
        <div className="card-head">
          <h2 id="lb-h">{t("section.leaderboard")}</h2>
          {atRoot ? (
            <div className="segmented" role="group" aria-label={t("public.compare")}>
              {(["district", "municipality", "ward"] as const).map((lv) => (
                <button key={lv} type="button" aria-pressed={compare === lv} onClick={() => setCompare(lv)}>
                  {lv === "district" ? t("public.districts") : lv === "municipality" ? t("public.municipalities") : t("public.wards")}
                </button>
              ))}
            </div>
          ) : <span className="muted small">{t("public.areasInside", { name: trail[trail.length - 1].name ?? "" })}</span>}
        </div>
        <p className="muted small" style={{ marginTop: -4 }}>{t("public.rankHint")}</p>
        <AreaTable rows={areas.data ?? []} onDrill={drill} />
      </section>

      <section className="card" aria-labelledby="auth-h">
        <div className="card-head"><h2 id="auth-h">{t("section.authorities")}</h2>
          <span className="muted small">{t("public.authHint")}</span></div>
        <AuthorityTable rows={auths.data ?? []} />
      </section>

      <section className="card" aria-labelledby="list-h">
        <div className="card-head"><h2 id="list-h">{t("section.urgent")}</h2><span className="muted small">{t("public.urgentHint")}</span></div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>{t("table.ticket")}</th><th>{t("table.type")}</th><th>{t("table.area")}</th><th>{t("table.status")}</th><th className="num">{t("table.citizens")}</th><th>{t("table.reportedOn")}</th></tr></thead>
            <tbody>
              {(tickets.data ?? []).slice(0, 25).map((tk) => (
                <tr key={tk.ref}>
                  <td><Link href={`/tickets/${tk.ref}`}>{tk.ref}</Link></td>
                  <td>{f.category(tk.category, tk.category_name)}</td>
                  <td>{tk.areas[tk.areas.length - 1]?.name ?? "—"}</td>
                  <td><StatusBadge status={tk.status} /></td>
                  <td className="num">{tk.verified_reporters}</td>
                  <td className="num">{f.date(tk.reported_on)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {tickets.data?.length === 0 && <p className="muted">{t("table.empty")}</p>}
        </div>
      </section>
    </div>
  );
}
