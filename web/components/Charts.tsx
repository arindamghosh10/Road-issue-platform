"use client";

// Charts follow the dataviz specs: one y-axis, thin marks (2px lines, bars ≤ 24px with
// 4px rounded data-ends), hairline solid grid, legend for ≥ 2 series plus a direct
// end-label, tooltips where the value leads. Text uses ink tokens, never series colours.

import {
  Bar, BarChart, CartesianGrid, LabelList, Line, LineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { fmtDate } from "@/lib/format";
import type { AgeingBucket, CategoryRow, TrendPoint } from "@/lib/types";
import { useThemeColors } from "@/lib/useThemeColors";

type TipPayload = readonly { name?: string; value?: unknown; color?: string; dataKey?: unknown }[];

function TipBox({ title, rows }: { title: string; rows: { key: string; label: string; value: number; color: string; line?: boolean }[] }) {
  return (
    <div className="tip">
      <div className="muted small">{title}</div>
      {rows.map((r) => (
        <div key={r.key} className="tip-row">
          {r.line
            ? <span className="legend-line" style={{ background: r.color }} aria-hidden />
            : <span className="legend-line" style={{ background: r.color, height: 8, width: 8, borderRadius: 2 }} aria-hidden />}
          <span className="tip-value">{r.value.toLocaleString("en-IN")}</span>
          <span className="ink-2">{r.label}</span>
        </div>
      ))}
    </div>
  );
}

// --- New vs resolved per week (two series, one axis) ----------------------------------

export function TrendChart({ data }: { data: TrendPoint[] }) {
  const c = useThemeColors();
  const series = [
    { key: "new", label: "New issues", color: c["--series-1"] },
    { key: "resolved", label: "Resolved", color: c["--series-2"] },
  ] as const;
  const last = data.length - 1;
  const endLabel = (key: "new" | "resolved", label: string) =>
    function EndLabel(props: { x?: number | string; y?: number | string; index?: number }) {
      if (props.index !== last || props.x == null || props.y == null) return null;
      return (
        <text x={Number(props.x) + 8} y={Number(props.y) + 4} fontSize={12} fill={c["--ink-2"]}>
          {label} {data[last][key]}
        </text>
      );
    };

  return (
    <div>
      <div className="legend" style={{ marginTop: 0, marginBottom: 8 }}>
        {series.map((s) => (
          <span key={s.key} className="legend-item">
            <span className="legend-line" style={{ background: s.color }} aria-hidden />{s.label}
          </span>
        ))}
      </div>
      <div style={{ width: "100%", height: 240 }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 96, bottom: 0, left: -12 }}>
            <CartesianGrid vertical={false} stroke={c["--grid"]} />
            <XAxis dataKey="week" tickFormatter={(w: string) => fmtDate(w).replace(/ \d{4}$/, "")}
                   tick={{ fill: c["--muted"], fontSize: 12 }} axisLine={{ stroke: c["--axis"] }}
                   tickLine={false} minTickGap={24} />
            <YAxis allowDecimals={false} tick={{ fill: c["--muted"], fontSize: 12 }}
                   axisLine={false} tickLine={false} width={40} />
            <Tooltip
              cursor={{ stroke: c["--axis"], strokeWidth: 1 }}
              content={({ active, payload, label }) =>
                active && payload?.length ? (
                  <TipBox title={`Week of ${fmtDate(String(label))}`}
                          rows={series.map((s) => ({
                            key: s.key, label: s.label, color: s.color, line: true,
                            value: Number((payload as TipPayload).find((p) => p.dataKey === s.key)?.value ?? 0),
                          }))} />
                ) : null}
            />
            {series.map((s) => (
              <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={s.color}
                    strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" isAnimationActive={false}
                    dot={false}
                    activeDot={{ r: 4, fill: s.color, stroke: c["--surface"], strokeWidth: 2 }}>
                <LabelList dataKey={s.key} content={endLabel(s.key, s.label)} />
              </Line>
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// --- Single-series bars (one colour for every bar) ---------------------------------------

function BarTip({ active, payload, label, unit }: { active?: boolean; payload?: TipPayload; label?: string; unit: string }) {
  if (!active || !payload?.length) return null;
  return <TipBox title={String(label)} rows={[{ key: "v", label: unit, value: Number(payload[0].value), color: payload[0].color ?? "" }]} />;
}

export function CategoryBars({ data }: { data: CategoryRow[] }) {
  const c = useThemeColors();
  const height = Math.max(120, data.length * 36 + 16);
  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 40, bottom: 0, left: 8 }}>
          <XAxis type="number" hide allowDecimals={false} />
          <YAxis type="category" dataKey="name" width={170} tick={{ fill: c["--ink-2"], fontSize: 13 }}
                 axisLine={{ stroke: c["--axis"] }} tickLine={false} />
          <Tooltip cursor={{ fill: c["--grid"], opacity: 0.4 }}
                   content={(p) => <BarTip {...(p as object)} payload={p.payload as TipPayload} label={String(p.label)} unit="issues reported" />} />
          <Bar dataKey="total" fill={c["--series-1"]} barSize={16} radius={[0, 4, 4, 0]} isAnimationActive={false}>
            <LabelList dataKey="total" position="right" fill={c["--ink-2"]} fontSize={12} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Single-series columns over ordered buckets (status groups, backlog age). */
export function ColumnBars({ data, unit }: { data: AgeingBucket[]; unit: string }) {
  const c = useThemeColors();
  return (
    <div style={{ width: "100%", height: 220 }}>
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 20, right: 8, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke={c["--grid"]} />
          <XAxis dataKey="bucket" tick={{ fill: c["--ink-2"], fontSize: 12 }} axisLine={{ stroke: c["--axis"] }} tickLine={false} />
          <YAxis allowDecimals={false} tick={{ fill: c["--muted"], fontSize: 12 }} axisLine={false} tickLine={false} width={40} />
          <Tooltip cursor={{ fill: c["--grid"], opacity: 0.4 }}
                   content={(p) => <BarTip {...(p as object)} payload={p.payload as TipPayload} label={String(p.label)} unit={unit} />} />
          <Bar dataKey="count" fill={c["--series-1"]} barSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false}>
            <LabelList dataKey="count" position="top" fill={c["--ink-2"]} fontSize={12} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
