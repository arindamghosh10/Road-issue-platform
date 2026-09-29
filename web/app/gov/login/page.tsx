"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { API_URL, setToken } from "@/lib/api";
import { useI18n } from "@/lib/locale";

export default function GovLogin() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { t } = useI18n();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/gov/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, totp_code: totp || null }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : t("gov.login.failed"));
      setToken(body.access_token);
      router.replace("/gov");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 400, margin: "48px auto" }}>
      <form className="card stack" onSubmit={submit} aria-labelledby="login-h">
        <h1 id="login-h">{t("gov.login.title")}</h1>
        <p className="muted small" style={{ margin: 0 }}>
          {t("gov.login.demo")} <code>kmc@demo.roadwatch.in</code> / <code>roadwatch-demo</code>
        </p>
        <label className="field">{t("gov.login.email")}
          <input className="input" type="email" autoComplete="username" required value={email}
                 onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="field">{t("gov.login.password")}
          <input className="input" type="password" autoComplete="current-password" required value={password}
                 onChange={(e) => setPassword(e.target.value)} />
        </label>
        <label className="field">{t("gov.login.totp")}
          <input className="input" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={totp}
                 onChange={(e) => setTotp(e.target.value)} />
        </label>
        {error && <p className="error" role="alert" style={{ margin: 0 }}>{error}</p>}
        <button className="btn btn-primary" type="submit" disabled={busy}>{t("gov.login.submit")}</button>
      </form>
    </div>
  );
}
