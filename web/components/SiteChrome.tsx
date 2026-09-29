"use client";

import { useI18n } from "@/lib/locale";

export function SiteNotice() {
  const { t } = useI18n();
  return (
    <div className="notice">
      <div className="container">{t("sample.notice")}</div>
    </div>
  );
}

export function SiteFooter() {
  const { t } = useI18n();
  return <footer className="container footer">{t("footer")}</footer>;
}
