"use client";

// Ticket map with MapLibre GL (open source) and free OpenFreeMap vector tiles (no key).
// Markers are clustered; each ticket is coloured by its status group, and the legend
// below pairs every colour with an icon and a label.

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import type { GeoJSONSource, Map as MlMap, StyleSpecification } from "maplibre-gl";
import { STATUS_GROUPS, STATUS_HEX, statusGroup } from "@/lib/format";
import { useI18n } from "@/lib/locale";
import type { PublicTicket } from "@/lib/types";

const STYLE_URL = process.env.NEXT_PUBLIC_MAP_STYLE ?? "https://tiles.openfreemap.org/styles/positron";
const KOLKATA: [number, number] = [88.3639, 22.5726];

function cssVar(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

async function loadStyle(): Promise<StyleSpecification | string> {
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 4000);
    const res = await fetch(STYLE_URL, { signal: ctrl.signal });
    clearTimeout(timer);
    if (res.ok) return STYLE_URL;
  } catch {
    /* offline: fall through */
  }
  // No base map available: plain background so markers still render.
  return { version: 8, sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": cssVar("--surface-2", "#eeede8") } }] };
}

function toGeoJSON(tickets: PublicTicket[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: tickets.map((t) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [t.lon, t.lat] },
      properties: { ref: t.ref, category: t.category_name, code: t.category, status: t.status,
                    group: statusGroup(t.status), reporters: t.verified_reporters },
    })),
  };
}

export function TicketMap({ tickets, linkBase = "/tickets" }: { tickets: PublicTicket[]; linkBase?: string }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MlMap | null>(null);
  const ready = useRef(false);
  const latest = useRef(tickets);
  // Map event handlers are registered once; they read the current language through this ref.
  const { t, f } = useI18n();
  const i18n = useRef({ t, f });
  useEffect(() => { i18n.current = { t, f }; }, [t, f]);
  const router = useRouter();
  latest.current = tickets;

  useEffect(() => {
    let disposed = false;
    (async () => {
      const [{ default: maplibregl }, style] = await Promise.all([import("maplibre-gl"), loadStyle()]);
      if (disposed || !el.current) return;
      const m = new maplibregl.Map({ container: el.current, style, center: KOLKATA, zoom: 10.5,
                                     attributionControl: { compact: true } });
      map.current = m;
      m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      const hasGlyphs = typeof style === "string";
      const ring = cssVar("--surface", "#fcfcfb"); // 2px surface ring around every marker

      m.on("load", () => {
        m.addSource("tickets", { type: "geojson", data: toGeoJSON(latest.current),
                                 cluster: true, clusterRadius: 40, clusterMaxZoom: 15 });
        m.addLayer({ id: "clusters", type: "circle", source: "tickets", filter: ["has", "point_count"],
          paint: { "circle-color": "#2a78d6", "circle-opacity": 0.85,
                   "circle-radius": ["step", ["get", "point_count"], 14, 10, 18, 50, 24],
                   "circle-stroke-width": 2, "circle-stroke-color": ring } });
        if (hasGlyphs) {
          m.addLayer({ id: "cluster-count", type: "symbol", source: "tickets", filter: ["has", "point_count"],
            layout: { "text-field": ["get", "point_count_abbreviated"], "text-size": 12,
                      "text-font": ["Noto Sans Bold"] },
            paint: { "text-color": "#ffffff" } });
        }
        m.addLayer({ id: "points", type: "circle", source: "tickets", filter: ["!", ["has", "point_count"]],
          paint: {
            "circle-color": ["match", ["get", "group"],
              "open", STATUS_HEX.open, "working", STATUS_HEX.working,
              "checking", STATUS_HEX.checking, STATUS_HEX.resolved],
            "circle-radius": 7, "circle-stroke-width": 2, "circle-stroke-color": ring,
          } });

        const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12 });
        m.on("mouseenter", "points", (e) => {
          m.getCanvas().style.cursor = "pointer";
          const f = e.features?.[0];
          if (!f) return;
          const p = f.properties as Record<string, string>;
          // Build with textContent: labels are data, never HTML.
          const box = document.createElement("div");
          const title = document.createElement("strong");
          const { t: tr, f: fm } = i18n.current;
          title.textContent = `${fm.category(p.code, p.category)} · ${p.ref}`;
          const line = document.createElement("div");
          line.textContent = tr("map.popup", { status: fm.status(p.status as PublicTicket["status"]), n: p.reporters });
          box.append(title, line);
          popup.setLngLat((f.geometry as GeoJSON.Point).coordinates as [number, number]).setDOMContent(box).addTo(m);
        });
        m.on("mouseleave", "points", () => { m.getCanvas().style.cursor = ""; popup.remove(); });
        m.on("click", "points", (e) => {
          const ref = e.features?.[0]?.properties?.ref;
          if (ref) router.push(`${linkBase}/${ref}`);
        });
        m.on("click", "clusters", async (e) => {
          const f = e.features?.[0];
          if (!f) return;
          const zoom = await (m.getSource("tickets") as GeoJSONSource).getClusterExpansionZoom(f.properties.cluster_id);
          m.easeTo({ center: (f.geometry as GeoJSON.Point).coordinates as [number, number], zoom });
        });
        ready.current = true;
        fit(m, latest.current);
      });
    })();
    return () => { disposed = true; map.current?.remove(); map.current = null; ready.current = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready.current) return;
    (m.getSource("tickets") as GeoJSONSource | undefined)?.setData(toGeoJSON(tickets));
    fit(m, tickets);
  }, [tickets]);

  return (
    <div>
      <div ref={el} className="map" role="region" aria-label={t("map.label")} />
      <div className="legend" aria-label={t("map.legend")}>
        {STATUS_GROUPS.map((g) => (
          <span key={g.key} className="legend-item">
            <span className="badge-dot" style={{ background: g.color }} aria-hidden>{g.icon}</span>
            {f.group(g.key)}
          </span>
        ))}
        <span className="legend-item">
          <span className="badge-dot" style={{ background: "#2a78d6", color: "#fff" }} aria-hidden>n</span>
          {t("map.cluster")}
        </span>
      </div>
    </div>
  );
}

function fit(m: MlMap, tickets: PublicTicket[]) {
  if (tickets.length === 0) return;
  if (tickets.length === 1) {
    m.easeTo({ center: [tickets[0].lon, tickets[0].lat], zoom: 14 });
    return;
  }
  const lons = tickets.map((t) => t.lon);
  const lats = tickets.map((t) => t.lat);
  m.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
              { padding: 48, maxZoom: 15, duration: 0 });
}
