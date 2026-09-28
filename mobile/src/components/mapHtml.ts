// HTML for a small MapLibre GL JS map (free OpenFreeMap tiles, no API key), shown in a
// WebView on phones and an iframe on web. Tapping a marker posts the ticket ref back.
// Values are JSON-encoded into the page, never concatenated as HTML.

export type MapPoint = { ref: string; lat: number; lon: number; color: string; label: string };

export function mapHtml(points: MapPoint[], me: { lat: number; lon: number } | null, dark: boolean): string {
  const data = JSON.stringify({ points, me, dark }).replace(/</g, "\\u003c");
  return `<!doctype html><html><head>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<link href="https://cdn.jsdelivr.net/npm/maplibre-gl@5/dist/maplibre-gl.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/maplibre-gl@5/dist/maplibre-gl.js"></script>
<style>html,body,#m{margin:0;height:100%;background:${dark ? "#232322" : "#eeede8"}}
.pin{width:18px;height:18px;border-radius:50%;border:2px solid ${dark ? "#1a1a19" : "#fcfcfb"};box-sizing:border-box;cursor:pointer}
.me{width:14px;height:14px;border-radius:50%;background:#2a78d6;border:3px solid #fff;box-shadow:0 0 0 6px rgba(42,120,214,.25)}
#off{position:absolute;inset:0;display:none;align-items:center;justify-content:center;font:14px system-ui;color:#898781}</style>
</head><body><div id="m"></div><div id="off">Map unavailable offline — see the list below.</div><script>
const D = ${data};
function send(ref){ const msg = JSON.stringify({ref});
  if (window.ReactNativeWebView) window.ReactNativeWebView.postMessage(msg); else window.parent.postMessage(msg, "*"); }
if (!window.maplibregl) { document.getElementById("off").style.display = "flex"; }
else {
  const center = D.me ? [D.me.lon, D.me.lat] : (D.points[0] ? [D.points[0].lon, D.points[0].lat] : [88.3639, 22.5726]);
  const map = new maplibregl.Map({ container: "m", style: "https://tiles.openfreemap.org/styles/" + (D.dark ? "dark" : "positron"),
                                   center, zoom: 14, attributionControl: { compact: true } });
  for (const p of D.points) {
    const el = document.createElement("div"); el.className = "pin"; el.style.background = p.color;
    el.setAttribute("role", "button"); el.setAttribute("aria-label", p.label);
    el.addEventListener("click", () => send(p.ref));
    new maplibregl.Marker({ element: el }).setLngLat([p.lon, p.lat]).addTo(map);
  }
  if (D.me) { const el = document.createElement("div"); el.className = "me"; new maplibregl.Marker({ element: el }).setLngLat([D.me.lon, D.me.lat]).addTo(map); }
}
</script></body></html>`;
}
