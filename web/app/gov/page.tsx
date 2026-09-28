"use client";

// Government dashboard: everything is scoped by the API to the official's own area
// (their node and everything below it, plus roads their authority owns).

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useState } from "react";
import { CategoryBars, ColumnBars, TrendChart } from "@/components/Charts";
import { FilterBar } from "@/components/FilterBar";
import { KpiRow } from "@/components/KpiRow";
import { StatusBadge } from "@/components/StatusBadge";
import { AreaTable, Breadcrumbs } from "@/components/Tables";
import { downloadCsv, filterQuery, govGet, publicGet } from "@/lib/api";
import { fmtSlaLeft, levelLabel } from "@/lib/format";
import { t } from "@/lib/i18n";
import type {
  AgeingBucket, AreaRow, Category, CategoryRow, Filters, GovTicket, NotificationItem, Summary, TrendPoint,
} from "@/lib/types";
import { useData } from "@/lib/useData";
import { useOfficial } from "@/lib/useOfficial";

const TicketMap = dynamic(() => import("@/components/TicketMap").then((m) => m.TicketMap), { ssr: false });

type Crumb = { id: number | null; name: string };

function SlaCell({ hours, status }: { hours: number | null; status: GovTicket["status"] }) {
  if (status === "fix_submitted") return <span className="muted">paused (citizens checking)</span>;
  if (hours == null) return <span>—</span>;
  const overdue = hours < 0;
  const soon = !overdue && hours < 24;
  return (
    <span style={{ color: overdue ? "var(--danger-text)" : undefined, fontWeight: overdue || soon ? 600 : 400 }}>
      {overdue ? "⚠ " : soon ? "◷ " : ""}{fmtSlaLeft(hours)}
    </span>
  );
}

export default function GovDashboard() {
  const { me, logout } = useOfficial();
  const [filters, setFilters] = useState<Filters>({ jurisdictionId: null, category: "", days: null });
  const [trail, setTrail] = useState<Crumb[]>([]);
  const [exportError, setExportError] = useState<string | null>(null);

  useEffect(() => {
    if (me && trail.length === 0) setTrail([{ id: me.node_id, name: me.node ?? "My area" }]);
  }, [me, trail.length]);

  const ready = me ? JSON.stringify(filters) : null;
  const q = filterQuery(filters);
  const parent = trail.length ? trail[trail.length - 1].id : null;

  const categories = useData<Category[]>(me ? "cats" : null, () => publicGet("/categories"));
  const summary = useData<Summary>(ready, () => govGet(`/stats/summary${q}`));
  const queue = useData<GovTicket[]>(ready, () => govGet(`/tickets${filterQuery(filters, { limit: 500 })}`));
  const trend = useData<TrendPoint[]>(ready, () => govGet(`/stats/trends${filterQuery({ ...filters, days: null })}`));
  const ageing = useData<AgeingBucket[]>(ready, () => govGet(`/stats/ageing${filterQuery({ ...filters, days: null })}`));
  const cats = useData<CategoryRow[]>(ready, () => govGet(`/stats/categories${filterQuery({ ...filters, category: "" })}`));
  const areas = useData<AreaRow[]>(ready && trail.length ? `${ready}|${parent}` : null, () =>
    govGet(`/stats/areas${filterQuery({ ...filters, jurisdictionId: null }, { parent_id: parent })}`));
  const inbox = useData<NotificationItem[]>(me ? "inbox" : null, () => govGet("/notifications?unread_only=true"));

  if (!me) return <p className="page-title muted">Loading…</p>;

  const drill = (row: AreaRow) => {
    setTrail([...trail, { id: row.id, name: row.name }]);
    setFilters({ ...filters, jurisdictionId: row.id });
  };
  const pickCrumb = (i: number) => {
    const next = trail.slice(0, i + 1);
    setTrail(next);
    setFilters({ ...filters, jurisdictionId: i === 0 ? null : next[next.length - 1].id });
  };

  return (
    <div className="stack" style={{ paddingBottom: 24 }}>
      <div className="page-title row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div className="stack" style={{ gap: 2 }}>
          <h1>{me.node ?? "All areas"}</h1>
          <span className="ink-2 small">
            {me.name} · {me.node_level ? levelLabel(me.node_level) : me.role}
            {(inbox.data?.length ?? 0) > 0 && <> · <strong>{inbox.data!.length}</strong> unread notification(s)</>}
          </span>
        </div>
        <div className="row">
          <button className="btn" type="button" onClick={() => downloadCsv(filters).catch((e) => setExportError(e.message))}>
            {t("gov.export")}
          </button>
          <button className="btn" type="button" onClick={logout}>{t("nav.logout")}</button>
        </div>
      </div>
      {exportError && <p className="error">{exportError}</p>}

      <FilterBar filters={filters} categories={categories.data ?? []} onChange={setFilters}>
        <div className="field">
          <span>{t("filters.area")}</span>
          <div style={{ minHeight: 36, display: "flex", alignItems: "center" }}>
            <Breadcrumbs trail={trail} onPick={pickCrumb} />
          </div>
        </div>
      </FilterBar>

      <KpiRow s={summary.data} />

      <section className="card" aria-labelledby="queue-h">
        <div className="card-head">
          <h2 id="queue-h">{t("section.queue")}</h2>
          <span className="muted small">{queue.data?.length ?? 0} open · most urgent first</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Ticket</th><th>Type</th><th>Ward / area</th><th>Status</th>
                <th className="num">Severity</th><th className="num">Citizens</th><th>Deadline</th><th>Assigned</th></tr>
            </thead>
            <tbody>
              {(queue.data ?? []).map((tk) => (
                <tr key={tk.ref}>
                  <td><Link href={`/gov/tickets/${tk.ref}`}>{tk.ref}</Link></td>
                  <td>{tk.category_name}</td>
                  <td>{tk.areas[tk.areas.length - 1]?.name ?? "—"}
                    {tk.escalation_level > 0 && <div className="muted small">escalated to {tk.responsible_area}</div>}</td>
                  <td><StatusBadge status={tk.status} /></td>
                  <td className="num">{tk.severity}</td>
                  <td className="num">{tk.verified_reporters}</td>
                  <td><SlaCell hours={tk.sla_hours_left} status={tk.status} /></td>
                  <td>{tk.assigned_to ?? <span className="muted">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {queue.data?.length === 0 && <p className="muted">Nothing open in this area. 🎉</p>}
        </div>
      </section>

      <section className="card" aria-labelledby="gmap-h">
        <div className="card-head"><h2 id="gmap-h">{t("section.map")}</h2></div>
        <TicketMap tickets={queue.data ?? []} linkBase="/gov/tickets" />
      </section>

      <section className="card" aria-labelledby="drill-h">
        <div className="card-head">
          <h2 id="drill-h">{t("section.leaderboard")}</h2>
          <span className="muted small">areas inside {trail[trail.length - 1]?.name}</span>
        </div>
        <AreaTable rows={areas.data ?? []} onDrill={drill} />
      </section>

      <div className="grid-2">
        <section className="card" aria-labelledby="gtrend-h">
          <div className="card-head"><h2 id="gtrend-h">{t("section.trend")}</h2></div>
          <TrendChart data={trend.data ?? []} />
        </section>
        <section className="card" aria-labelledby="age-h">
          <div className="card-head"><h2 id="age-h">{t("section.ageing")}</h2></div>
          <ColumnBars data={ageing.data ?? []} unit="open issues" />
        </section>
      </div>

      <section className="card" aria-labelledby="gcat-h">
        <div className="card-head"><h2 id="gcat-h">{t("section.categories")}</h2></div>
        {cats.data?.length ? <CategoryBars data={cats.data} /> : <p className="muted">{t("table.empty")}</p>}
      </section>
    </div>
  );
}
