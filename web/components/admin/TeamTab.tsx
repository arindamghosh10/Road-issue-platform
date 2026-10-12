"use client";

// Officials: add accounts (with a one-time temporary password), change where someone
// works, reset passwords and two-factor, deactivate. Government admins see only their
// own organisation; the platform admin can pick any.

import { useState } from "react";
import { adminGet, adminSend } from "@/lib/api";
import { useI18n } from "@/lib/locale";
import type { AuthorityRow2, Me, OfficialRow, Role, TenantRow } from "@/lib/types";
import { useData } from "@/lib/useData";
import { AreaPicker, ConfirmButton, OneTimePassword, OrgSelect } from "./shared";

type Shown = { name: string; password: string; title: string };

export function TeamTab({ me, tenants }: { me: Me; tenants: TenantRow[] }) {
  const { t, f } = useI18n();
  const platform = me.role === "platform_admin";
  const [org, setOrg] = useState<string>(platform ? "" : me.tenant_id ?? "");
  const [version, setVersion] = useState(0);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [shown, setShown] = useState<Shown | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const rows = useData<OfficialRow[]>(`team|${org}|${version}`,
    () => adminGet(`/officials${platform && org ? `?tenant_id=${org}` : ""}`));
  const authorities = useData<AuthorityRow2[]>("authorities", () => adminGet("/authorities"));

  async function act(fn: () => Promise<unknown>, ok?: string) {
    setMsg(null);
    try {
      await fn();
      if (ok) setMsg({ ok: true, text: ok });
      setVersion((v) => v + 1);
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    }
  }

  const roleName = (r: string) => t(`role.${r}` as Parameters<typeof t>[0]);
  const place = (o: OfficialRow) => [o.node ? `${o.node} (${f.level(o.node_level ?? "")})` : null, o.authority]
    .filter(Boolean).join(" · ") || "—";

  return (
    <div className="stack">
      <section className="card stack" aria-labelledby="team-add-h">
        <h2 id="team-add-h">{t("team.add")}</h2>
        {shown
          ? <OneTimePassword {...shown} onDone={() => setShown(null)} />
          : <AddOfficial me={me} tenants={tenants} authorities={authorities.data ?? []}
                         defaultOrg={org}
                         onCreated={(name, password) => {
                           setShown({ name, password, title: t("team.created", { name }) });
                           setVersion((v) => v + 1);
                         }} />}
      </section>

      <section className="card" aria-labelledby="team-h">
        <div className="card-head">
          <div className="stack" style={{ gap: 2 }}>
            <h2 id="team-h">{t("team.title")}</h2>
            <span className="muted small">{t("team.hint")}</span>
          </div>
          {platform && <OrgSelect tenants={tenants} value={org} onChange={setOrg} allowAll />}
        </div>
        {msg && <p className={msg.ok ? "success" : "error"} role="status">{msg.text}</p>}
        {rows.error && <p className="error">{rows.error}</p>}
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>{t("team.col.person")}</th><th>{t("team.col.role")}</th>
                {platform && <th>{t("adm.org")}</th>}
                <th>{t("team.col.place")}</th><th>{t("team.col.status")}</th><th>{t("team.col.actions")}</th></tr>
            </thead>
            <tbody>
              {(rows.data ?? []).map((o) => (
                <tr key={o.id} style={{ opacity: o.is_active ? 1 : 0.6 }}>
                  <td>{o.name}{o.id === me.id && <span className="muted"> ({t("team.you")})</span>}
                    <div className="muted small">{o.email}</div></td>
                  <td>{roleName(o.role)}</td>
                  {platform && <td>{o.tenant ?? <span className="muted">—</span>}</td>}
                  <td>{editing === o.id
                    ? <EditPlacement official={o} authorities={authorities.data ?? []}
                                     onCancel={() => setEditing(null)}
                                     onSave={(patch) => act(async () => {
                                       await adminSend("PATCH", `/officials/${o.id}`, patch);
                                       setEditing(null);
                                     }, t("adm.saved"))} />
                    : place(o)}</td>
                  <td>
                    <div className="stack" style={{ gap: 4, alignItems: "flex-start" }}>
                      {o.is_active ? <span className="chip">{t("team.active")}</span>
                        : <span className="chip chip-off">{t("team.inactive")}</span>}
                      {o.must_change_password && <span className="chip chip-warn">{t("team.mustChange")}</span>}
                      {o.totp_enabled && <span className="chip">{t("team.twofa")}</span>}
                    </div>
                  </td>
                  <td>
                    {o.id !== me.id && (
                      <div className="actions">
                        <button type="button" className="btn" onClick={() => setEditing(o.id)}>{t("team.edit")}</button>
                        <ConfirmButton label={t("team.resetPw")} confirmLabel={t("team.confirm")}
                          onConfirm={() => act(async () => {
                            const r = await adminSend<{ temporary_password: string }>("POST", `/officials/${o.id}/reset-password`);
                            setShown({ name: o.name, password: r.temporary_password, title: t("team.resetDone", { name: o.name }) });
                            window.scrollTo({ top: 0, behavior: "smooth" });
                          })} />
                        {o.totp_enabled && (
                          <ConfirmButton label={t("team.reset2fa")} confirmLabel={t("team.confirm")}
                            onConfirm={() => act(() => adminSend("POST", `/officials/${o.id}/reset-2fa`),
                                                 t("team.2faDone", { name: o.name }))} />
                        )}
                        {o.is_active
                          ? <ConfirmButton label={t("team.deactivate")} confirmLabel={t("team.confirm")}
                              onConfirm={() => act(() => adminSend("PATCH", `/officials/${o.id}`, { is_active: false }),
                                                   t("adm.saved"))} />
                          : <button type="button" className="btn"
                                    onClick={() => act(() => adminSend("PATCH", `/officials/${o.id}`, { is_active: true }),
                                                       t("adm.saved"))}>{t("team.reactivate")}</button>}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.data?.length === 0 && <p className="muted">{t("team.empty")}</p>}
        </div>
      </section>
    </div>
  );
}

function AddOfficial({ me, tenants, authorities, defaultOrg, onCreated }: {
  me: Me; tenants: TenantRow[]; authorities: AuthorityRow2[]; defaultOrg: string;
  onCreated: (name: string, password: string) => void;
}) {
  const { t } = useI18n();
  const platform = me.role === "platform_admin";
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("official");
  const [org, setOrg] = useState(defaultOrg || tenants[0]?.id || "");
  const [nodeId, setNodeId] = useState<number | null>(null);
  const [authorityId, setAuthorityId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const roles: Role[] = platform ? ["official", "gov_admin", "platform_admin"] : ["official", "gov_admin"];

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await adminSend<{ temporary_password: string }>("POST", "/officials", {
        name, email, role,
        tenant_id: platform && role !== "platform_admin" ? org || null : undefined,
        node_id: role === "platform_admin" ? null : nodeId,
        authority_id: role === "platform_admin" || !authorityId ? null : Number(authorityId),
      });
      onCreated(name, r.temporary_password);
      setName(""); setEmail(""); setNodeId(null); setAuthorityId(""); setRole("official");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack" onSubmit={submit}>
      <div className="form-grid">
        <label className="field">{t("team.name")}
          <input id="new-name" className="input" required minLength={2} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field">{t("team.email")}
          <input id="new-email" className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="field">{t("team.role")}
          <select id="new-role" className="select" value={role} onChange={(e) => setRole(e.target.value as Role)}>
            {roles.map((r) => <option key={r} value={r}>{t(`role.${r}` as Parameters<typeof t>[0])}</option>)}
          </select>
        </label>
        {platform && role !== "platform_admin" && <OrgSelect tenants={tenants} value={org} onChange={setOrg} />}
      </div>
      {role !== "platform_admin" && (
        <>
          <AreaPicker value={nodeId} onChange={(id) => setNodeId(id)} label={t("team.area")} />
          <span className="muted small" style={{ marginTop: -8 }}>{t("area.pickHint")}</span>
          <label className="field" style={{ maxWidth: 360 }}>{t("team.authority")}
            <select id="new-authority" className="select" value={authorityId} onChange={(e) => setAuthorityId(e.target.value)}>
              <option value="">{t("team.noAuthority")}</option>
              {authorities.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </label>
        </>
      )}
      {error && <p className="error" role="alert" style={{ margin: 0 }}>{error}</p>}
      <div><button className="btn btn-primary" type="submit" disabled={busy}>{t("team.create")}</button></div>
    </form>
  );
}

function EditPlacement({ official, authorities, onSave, onCancel }: {
  official: OfficialRow; authorities: AuthorityRow2[];
  onSave: (patch: Record<string, unknown>) => void; onCancel: () => void;
}) {
  const { t } = useI18n();
  const [nodeId, setNodeId] = useState<number | null>(null);
  const [authorityId, setAuthorityId] = useState(official.authority_id ? String(official.authority_id) : "");
  return (
    <div className="stack" style={{ gap: 8, minWidth: 260 }}>
      <AreaPicker value={nodeId} onChange={(id) => setNodeId(id)} label={t("team.area")} />
      <select className="select" aria-label={t("team.authority")} value={authorityId}
              onChange={(e) => setAuthorityId(e.target.value)}>
        <option value="">{t("team.noAuthority")}</option>
        {authorities.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
      </select>
      <div className="actions">
        <button type="button" className="btn btn-primary" onClick={() => onSave({
          ...(nodeId !== null ? { node_id: nodeId } : {}),
          ...(authorityId ? { authority_id: Number(authorityId) } : { clear_authority: true }),
        })}>{t("team.save")}</button>
        <button type="button" className="btn" onClick={onCancel}>{t("team.cancel")}</button>
      </div>
    </div>
  );
}
