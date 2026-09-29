"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LOCALE_NAMES, LOCALES, isLocale } from "@/lib/i18n";
import { useI18n } from "@/lib/locale";

export function Header() {
  const path = usePathname();
  const isGov = path.startsWith("/gov");
  const { t, locale, setLocale } = useI18n();
  return (
    <header className="header">
      <div className="container header-inner">
        <Link href="/" className="brand">
          <span className="brand-mark" aria-hidden>R</span>
          {t("app.name")}
        </Link>
        <nav className="nav" aria-label={t("nav.main")}>
          <Link href="/" aria-current={!isGov ? "page" : undefined}>{t("nav.public")}</Link>
          <Link href="/gov" aria-current={isGov ? "page" : undefined}>{t("nav.gov")}</Link>
          <label className="lang">
            <span className="sr-only">{t("nav.language")}</span>
            <select className="select lang-select" value={locale} aria-label={t("nav.language")}
                    onChange={(e) => isLocale(e.target.value) && setLocale(e.target.value)}>
              {LOCALES.map((l) => (
                <option key={l} value={l} lang={l}>{LOCALE_NAMES[l]}</option>
              ))}
            </select>
          </label>
        </nav>
      </div>
    </header>
  );
}
