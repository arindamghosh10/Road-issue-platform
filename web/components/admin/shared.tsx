"use client";

// Pieces shared by the administration tabs.

import { useEffect, useState } from "react";
import { adminGet } from "@/lib/api";
import { useI18n } from "@/lib/locale";
import type { AdminArea, TenantRow } from "@/lib/types";

/** Pick an area by drilling down one level at a time (state → district → … → ward).
 * The value is the deepest area chosen. Starts at the admin's own top area. */
export function AreaPicker({ value, onChange, label }: {
  value: number | null; onChange: (id: number | null, name: string | null) => void; label: string;
}) {
  const { t, f } = useI18n();
  const [levels, setLevels] = useState<AdminArea[][]>([]);
  const [chosen, setChosen] = useState<AdminArea[]>([]);

  useEffect(() => {
    adminGet<AdminArea[]>("/areas").then((top) => setLevels([top])).catch(() => setLevels([]));
  }, []);
  useEffect(() => { if (value === null) setChosen([]); }, [value]);

  async function pick(depth: number, id: string) {
    const area = levels[depth]?.find((a) => String(a.id) === id) ?? null;
    const path = [...chosen.slice(0, depth), ...(area ? [area] : [])];
    setChosen(path);
    onChange(area?.id ?? path[path.length - 1]?.id ?? null, area?.name ?? path[path.length - 1]?.name ?? null);
    const next = levels.slice(0, depth + 1);
    if (area && area.children > 0) next.push(await adminGet<AdminArea[]>(`/areas?parent_id=${area.id}`));
    setLevels(next);
  }

  return (
    <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
      <legend style={{ padding: 0, marginBottom: 4 }}>{label}</legend>
      <div className="row" style={{ gap: 8 }}>
        {levels.map((options, depth) => (
          <select key={depth} className="select" aria-label={`${label} ${depth + 1}`}
                  value={chosen[depth]?.id ?? ""} onChange={(e) => pick(depth, e.target.value)}>
            <option value="">{t("area.choose")}</option>
            {options.map((a) => <option key={a.id} value={a.id}>{a.name} ({f.level(a.level)})</option>)}
          </select>
        ))}
      </div>
    </fieldset>
  );
}

/** Organisation chooser for the platform admin (government admins only have their own). */
export function OrgSelect({ tenants, value, onChange, allowAll = false }: {
  tenants: TenantRow[]; value: string; onChange: (id: string) => void; allowAll?: boolean;
}) {
  const { t } = useI18n();
  return (
    <label className="field" style={{ minWidth: 240 }}>{t("adm.org")}
      <select className="select" value={value} onChange={(e) => onChange(e.target.value)}>
        {allowAll && <option value="">{t("adm.allOrgs")}</option>}
        {tenants.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
      </select>
    </label>
  );
}

/** A temporary password, shown once, with a copy button. */
export function OneTimePassword({ name, password, title, onDone }: {
  name: string; password: string; title: string; onDone: () => void;
}) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  return (
    <div className="otp-box stack" role="status" style={{ gap: 8 }}>
      <strong>{title}</strong>
      <div className="row">
        <code className="otp-code" aria-label={t("team.tempPassword")}>{password}</code>
        <button type="button" className="btn" onClick={() => {
          navigator.clipboard?.writeText(password).then(() => setCopied(true)).catch(() => {});
        }}>{copied ? t("team.copied") : t("team.copy")}</button>
        <button type="button" className="btn btn-primary" onClick={onDone}>{t("team.done")}</button>
      </div>
      <span className="small ink-2">{t("team.tempHint", { name })}</span>
    </div>
  );
}

/** A button that asks for a second click before doing something drastic. */
export function ConfirmButton({ label, confirmLabel, onConfirm, disabled }: {
  label: string; confirmLabel: string; onConfirm: () => void; disabled?: boolean;
}) {
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (!armed) return;
    const timer = setTimeout(() => setArmed(false), 4000);
    return () => clearTimeout(timer);
  }, [armed]);
  return (
    <button type="button" className={armed ? "btn btn-danger" : "btn"} disabled={disabled}
            onClick={() => { if (armed) { setArmed(false); onConfirm(); } else setArmed(true); }}>
      {armed ? confirmLabel : label}
    </button>
  );
}
