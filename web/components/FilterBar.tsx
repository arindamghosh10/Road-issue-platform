"use client";

import { t } from "@/lib/i18n";
import type { Category, Filters } from "@/lib/types";

const PERIODS: (number | null)[] = [null, 7, 30, 90, 365];

/** One filter row above everything it scopes: period first, then category. */
export function FilterBar({
  filters,
  categories,
  onChange,
  children,
}: {
  filters: Filters;
  categories: Category[];
  onChange: (f: Filters) => void;
  children?: React.ReactNode;
}) {
  return (
    <div className="filters" role="group" aria-label="Filters">
      <div className="field">
        <span>{t("filters.period")}</span>
        <div className="segmented">
          {PERIODS.map((d) => (
            <button key={d ?? "all"} type="button" aria-pressed={filters.days === d}
                    onClick={() => onChange({ ...filters, days: d })}>
              {d == null ? t("filters.allTime") : `${d}d`}
            </button>
          ))}
        </div>
      </div>
      <label className="field">
        <span>{t("filters.category")}</span>
        <select className="select" value={filters.category}
                onChange={(e) => onChange({ ...filters, category: e.target.value })}>
          <option value="">{t("filters.allCategories")}</option>
          {categories.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
        </select>
      </label>
      {children}
    </div>
  );
}
