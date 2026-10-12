"use client";

// Administration. Government admins: their organisation's team and deadlines. The
// platform admin (RoadWatch operator) also: areas and organisations, report moderation
// and the audit log. The API enforces all of this; the tabs only mirror it.

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AreasTab } from "@/components/admin/AreasTab";
import { AuditTab } from "@/components/admin/AuditTab";
import { DeadlinesTab } from "@/components/admin/DeadlinesTab";
import { ModerationTab } from "@/components/admin/ModerationTab";
import { TeamTab } from "@/components/admin/TeamTab";
import { adminGet } from "@/lib/api";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/locale";
import { isAdmin, type TenantRow } from "@/lib/types";
import { useData } from "@/lib/useData";
import { useOfficial } from "@/lib/useOfficial";

const TABS = ["team", "deadlines", "areas", "reports", "audit"] as const;
type Tab = (typeof TABS)[number];
const PLATFORM_ONLY: Tab[] = ["areas", "reports", "audit"];

function Admin() {
  const { me, logout } = useOfficial();
  const { t } = useI18n();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [tenantsVersion, setTenantsVersion] = useState(0);
  const admin = isAdmin(me);
  const tenants = useData<TenantRow[]>(admin ? `tenants|${tenantsVersion}` : null, () => adminGet("/tenants"));

  if (!me) return <p className="page-title muted">{t("common.loading")}</p>;
  if (!admin) {
    return (
      <div className="page-title stack">
        <p>{t("adm.notAllowed")}</p>
        <Link href="/gov">{t("adm.backToDashboard")}</Link>
      </div>
    );
  }
  const platform = me.role === "platform_admin";
  const tabs = TABS.filter((x) => platform || !PLATFORM_ONLY.includes(x));
  const requested = params.get("tab") as Tab | null;
  const tab: Tab = requested && tabs.includes(requested) ? requested : "team";
  const go = (x: Tab) => router.replace(`${pathname}?tab=${x}`, { scroll: false });

  return (
    <div className="stack" style={{ paddingBottom: 24 }}>
      <div className="page-title row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div className="stack" style={{ gap: 2 }}>
          <h1>{t("adm.title")}</h1>
          <span className="ink-2 small">
            {me.name} · {platform ? t("adm.platform") : t("adm.orgAdmin", { org: me.tenant ?? "—" })}
          </span>
        </div>
        <div className="row">
          {!platform && <Link className="btn" href="/gov">{t("adm.backToDashboard")}</Link>}
          <button className="btn" type="button" onClick={logout}>{t("nav.logout")}</button>
        </div>
      </div>

      <div className="tabs" role="tablist" aria-label={t("adm.title")}>
        {tabs.map((x) => (
          <button key={x} type="button" role="tab" id={`tab-${x}`} aria-selected={tab === x}
                  aria-controls="admin-panel" onClick={() => go(x)}>
            {t(`adm.tab.${x}` as MessageKey)}
          </button>
        ))}
      </div>

      <div id="admin-panel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
        {tenants.error && <p className="error">{tenants.error}</p>}
        {tab === "team" && <TeamTab me={me} tenants={tenants.data ?? []} />}
        {tab === "deadlines" && tenants.data && <DeadlinesTab me={me} tenants={tenants.data} />}
        {tab === "areas" && <AreasTab onTenantsChanged={() => setTenantsVersion((v) => v + 1)} />}
        {tab === "reports" && <ModerationTab />}
        {tab === "audit" && <AuditTab />}
      </div>
    </div>
  );
}

export default function AdminPage() {
  return <Suspense><Admin /></Suspense>;
}
