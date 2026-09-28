import type { Metadata } from "next";
import "maplibre-gl/dist/maplibre-gl.css";
import "./globals.css";
import { Header } from "@/components/Header";
import { t } from "@/lib/i18n";

export const metadata: Metadata = {
  title: "RoadWatch",
  description: t("app.tagline"),
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Header />
        <div className="notice">
          <div className="container">{t("sample.notice")}</div>
        </div>
        <main className="container">{children}</main>
        <footer className="container footer">
          Reporter identities are never shared with government. Map data © OpenStreetMap
          contributors.
        </footer>
      </body>
    </html>
  );
}
