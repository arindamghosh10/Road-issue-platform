"use client";

// Areas (platform admin): browse the state → district → municipality → ward tree,
// import real boundaries from GeoJSON, turn an area into an organisation (a government
// client that sees everything inside it), and add road authorities.

import { useState } from "react";
import { ApiError, adminGet, adminSend } from "@/lib/api";
import { useI18n } from "@/lib/locale";
import type { AdminArea, AuthorityRow2 } from "@/lib/types";
import { useData } from "@/lib/useData";
import { Breadcrumbs } from "@/components/Tables";

type Crumb = { id: number | null; name: string | null }; // null name: "All states", translated
const AUTHORITY_TYPES = ["municipal", "state_pwd", "state_highways", "nhai", "cantonment", "other"] as const;

export function AreasTab({ onTenantsChanged }: { onTenantsChanged: () => void }) {
  const { t, f } = useI18n();
  const [trail, setTrail] = useState<Crumb[]>([{ id: null, name: null }]);
  const [version, setVersion] = useState(0);
  const [msg, setMsg] = useState<{ ok: boolean; text: string; list?: string[] } | null>(null);
  const [orgFor, setOrgFor] = useState<AdminArea | null>(null);
  const parent = trail[trail.length - 1];
  const areas = useData<AdminArea[]>(`areas|${parent.id}|${version}`,
    () => adminGet(parent.id == null ? "/areas" : `/areas?parent_id=${parent.id}`));

  return (
    <div className="stack">
      <section className="card stack" aria-labelledby="ar-h">
        <div className="stack" style={{ gap: 2 }}>
          <h2 id="ar-h">{t("ar.title")}</h2>
          <span className="muted small">{t("ar.hint")}</span>
        </div>
        <Breadcrumbs trail={trail.map((c) => ({ ...c, name: c.name ?? t("ar.top") }))} onPick={(i) => setTrail(trail.slice(0, i + 1))} />
        {msg && (
          <div className={msg.ok ? "success" : "error"} role="status">
            {msg.text}
            {msg.list && <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>{msg.list.map((e) => <li key={e}>{e}</li>)}</ul>}
          </div>
        )}
        {orgFor && (
          <CreateOrg area={orgFor} onCancel={() => setOrgFor(null)} onCreated={() => {
            setOrgFor(null);
            setMsg({ ok: true, text: t("ar.orgCreated") });
            setVersion((v) => v + 1);
            onTenantsChanged();
          }} />
        )}
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>{t("ar.col.name")}</th><th>{t("ar.col.level")}</th><th>{t("ar.col.code")}</th>
                <th>{t("ar.col.boundary")}</th><th>{t("adm.org")}</th><th className="num">{t("ar.col.children")}</th><th /></tr>
            </thead>
            <tbody>
              {(areas.data ?? []).map((a) => (
                <tr key={a.id}>
                  <td>{a.children > 0
                    ? <button type="button" className="crumbs-btn" style={{ background: "none", border: 0, padding: 0,
                        color: "var(--accent-ink)", cursor: "pointer", textAlign: "left" }}
                        onClick={() => setTrail([...trail, { id: a.id, name: a.name }])}>{a.name} ›</button>
                    : a.name}
                    {a.is_sample && <> <span className="chip chip-warn">{t("ar.sample")}</span></>}</td>
                  <td>{f.level(a.level)}</td>
                  <td><code className="small">{a.lgd_code}</code></td>
                  <td>{a.has_boundary ? t("ar.yes") : <span className="chip chip-off">{t("ar.no")}</span>}</td>
                  <td>{a.tenant ?? <span className="muted">—</span>}</td>
                  <td className="num">{f.num(a.children)}</td>
                  <td>{!a.tenant && <button type="button" className="btn" onClick={() => setOrgFor(a)}>{t("ar.newOrg")}</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <ImportBoundaries onDone={(text, ok, list) => { setMsg({ ok, text, list }); if (ok) setVersion((v) => v + 1); }} />
      <Authorities area={parent.id == null ? null : { id: parent.id, name: parent.name ?? "" }} />
    </div>
  );
}

function CreateOrg({ area, onCreated, onCancel }: { area: AdminArea; onCreated: () => void; onCancel: () => void }) {
  const { t, f } = useI18n();
  const [name, setName] = useState(area.name);
  const [error, setError] = useState<string | null>(null);
  return (
    <form className="otp-box stack" style={{ gap: 8 }} onSubmit={async (e) => {
      e.preventDefault();
      try {
        await adminSend("POST", "/tenants", { name, root_node_id: area.id });
        onCreated();
      } catch (err) { setError((err as Error).message); }
    }}>
      <strong>{t("ar.newOrgFor", { area: `${area.name} (${f.level(area.level)})` })}</strong>
      <span className="small ink-2">{t("ar.newOrgHint")}</span>
      <div className="row">
        <label className="field" style={{ flex: 1, minWidth: 240 }}>{t("ar.orgName")}
          <input id="org-name" className="input" required minLength={2} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <button type="submit" className="btn btn-primary">{t("ar.createOrg")}</button>
        <button type="button" className="btn" onClick={onCancel}>{t("team.cancel")}</button>
      </div>
      {error && <p className="error" role="alert" style={{ margin: 0 }}>{error}</p>}
    </form>
  );
}

function ImportBoundaries({ onDone }: { onDone: (text: string, ok: boolean, list?: string[]) => void }) {
  const { t } = useI18n();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <section className="card stack" aria-labelledby="imp-h">
      <h2 id="imp-h">{t("ar.import")}</h2>
      <p className="muted small" style={{ margin: 0, maxWidth: 760 }}>{t("ar.importHint")}</p>
      <div className="row">
        <input type="file" accept=".geojson,.json,application/geo+json,application/json" aria-label={t("ar.file")}
               onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <button type="button" className="btn btn-primary" disabled={!file || busy} onClick={async () => {
          if (!file) return;
          setBusy(true);
          const form = new FormData();
          form.set("file", file);
          try {
            const r = await adminSend<{ created: number; updated: number }>("POST", "/areas/import", form);
            onDone(t("ar.imported", { created: r.created, updated: r.updated }), true);
          } catch (e) {
            const errors = (e instanceof ApiError && Array.isArray((e.detail as { errors?: unknown })?.errors))
              ? (e.detail as { errors: string[] }).errors : undefined;
            onDone(errors ? t("ar.importFailed") : (e as Error).message, false, errors);
          } finally {
            setBusy(false);
          }
        }}>{t("ar.upload")}</button>
      </div>
    </section>
  );
}

function Authorities({ area }: { area: { id: number; name: string } | null }) {
  const { t } = useI18n();
  const [version, setVersion] = useState(0);
  const [name, setName] = useState("");
  const [type, setType] = useState<string>("municipal");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const rows = useData<AuthorityRow2[]>(`auth|${version}`, () => adminGet("/authorities"));
  return (
    <section className="card stack" aria-labelledby="au-h">
      <div className="stack" style={{ gap: 2 }}>
        <h2 id="au-h">{t("au.title")}</h2>
        <span className="muted small">{t("au.hint")}</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>{t("au.name")}</th><th>{t("au.type")}</th><th>{t("au.area")}</th></tr></thead>
          <tbody>
            {(rows.data ?? []).map((a) => (
              <tr key={a.id}><td>{a.name}</td><td>{t(`aut.${a.type}` as Parameters<typeof t>[0])}</td><td>{a.area ?? "—"}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      {area ? (
        <form className="row" style={{ alignItems: "end" }} onSubmit={async (e) => {
          e.preventDefault();
          try {
            await adminSend("POST", "/authorities", { name, type, jurisdiction_id: area.id });
            setName("");
            setVersion((v) => v + 1);
            setMsg({ ok: true, text: t("adm.saved") });
          } catch (err) { setMsg({ ok: false, text: (err as Error).message }); }
        }}>
          <label className="field" style={{ minWidth: 260 }}>{t("au.name")}
            <input id="auth-name" className="input" required minLength={2} value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="field">{t("au.type")}
            <select id="auth-type" className="select" value={type} onChange={(e) => setType(e.target.value)}>
              {AUTHORITY_TYPES.map((x) => <option key={x} value={x}>{t(`aut.${x}` as Parameters<typeof t>[0])}</option>)}
            </select>
          </label>
          <button type="submit" className="btn btn-primary">{t("au.add", { area: area.name })}</button>
        </form>
      ) : <p className="muted small" style={{ margin: 0 }}>{t("au.needArea")}</p>}
      {msg && <p className={msg.ok ? "success" : "error"} role="status">{msg.text}</p>}
    </section>
  );
}
