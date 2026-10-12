import type { Metadata } from "next";
import { cookies, headers } from "next/headers";
import "maplibre-gl/dist/maplibre-gl.css";
import "./globals.css";
import { Header } from "@/components/Header";
import { SiteFooter, SiteNotice } from "@/components/SiteChrome";
import { isLocale, LOCALE_COOKIE, negotiateLocale, translator, type Locale } from "@/lib/i18n";
import { I18nProvider } from "@/lib/locale";

/** The visitor's language: their saved choice, else their browser's preference. */
async function requestLocale(): Promise<Locale> {
  const saved = (await cookies()).get(LOCALE_COOKIE)?.value;
  if (isLocale(saved)) return saved;
  return negotiateLocale((await headers()).get("accept-language"));
}

export async function generateMetadata(): Promise<Metadata> {
  const t = translator(await requestLocale());
  return { title: t("app.name"), description: t("app.tagline") };
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await requestLocale();
  return (
    <html lang={locale}>
      <body>
        <I18nProvider initial={locale}>
          <Header />
          <SiteNotice />
          <main className="container">{children}</main>
          <SiteFooter />
        </I18nProvider>
      </body>
    </html>
  );
}
