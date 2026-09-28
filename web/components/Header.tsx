"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { t } from "@/lib/i18n";

export function Header() {
  const path = usePathname();
  const isGov = path.startsWith("/gov");
  return (
    <header className="header">
      <div className="container header-inner">
        <Link href="/" className="brand">
          <span className="brand-mark" aria-hidden>R</span>
          {t("app.name")}
        </Link>
        <nav className="nav" aria-label="Main">
          <Link href="/" aria-current={!isGov ? "page" : undefined}>{t("nav.public")}</Link>
          <Link href="/gov" aria-current={isGov ? "page" : undefined}>{t("nav.gov")}</Link>
        </nav>
      </div>
    </header>
  );
}
