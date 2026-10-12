"use client";

// Choose a new password. Required after an administrator creates the account or resets
// its password; the API refuses everything else until it's done.

import { useRouter } from "next/navigation";
import { useState } from "react";
import { govPost, setToken } from "@/lib/api";
import { useI18n } from "@/lib/locale";
import { homeFor, useOfficial } from "@/lib/useOfficial";

export default function ChangePassword() {
  const { me } = useOfficial();
  const { t } = useI18n();
  const router = useRouter();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (next !== repeat) { setError(t("pw.mismatch")); return; }
    setBusy(true);
    setError(null);
    try {
      const r = await govPost<{ access_token: string }>("/auth/password",
        { current_password: current, new_password: next });
      setToken(r.access_token);
      if (me) router.replace(homeFor({ ...me, must_change_password: false }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!me) return <p className="page-title muted">{t("common.loading")}</p>;
  return (
    <div style={{ maxWidth: 420, margin: "48px auto" }}>
      <form className="card stack" onSubmit={submit} aria-labelledby="pw-h">
        <h1 id="pw-h">{t("pw.title")}</h1>
        {me.must_change_password && <p className="ink-2" style={{ margin: 0 }}>{t("pw.forced")}</p>}
        <p className="muted small" style={{ margin: 0 }}>{me.email}</p>
        <label className="field">{t("pw.current")}
          <input id="pw-current" className="input" type="password" autoComplete="current-password" required
                 value={current} onChange={(e) => setCurrent(e.target.value)} />
        </label>
        <label className="field">{t("pw.new")}
          <input id="pw-new" className="input" type="password" autoComplete="new-password" required minLength={10}
                 value={next} onChange={(e) => setNext(e.target.value)} />
        </label>
        <label className="field">{t("pw.repeat")}
          <input id="pw-repeat" className="input" type="password" autoComplete="new-password" required
                 value={repeat} onChange={(e) => setRepeat(e.target.value)} />
        </label>
        <p className="muted small" style={{ margin: 0 }}>{t("pw.rule")}</p>
        {error && <p className="error" role="alert" style={{ margin: 0 }}>{error}</p>}
        <button className="btn btn-primary" type="submit" disabled={busy}>{t("pw.save")}</button>
      </form>
    </div>
  );
}
