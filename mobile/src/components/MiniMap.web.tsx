// Web build (demo/testing only): same map in an iframe instead of a native WebView.
import { useEffect } from "react";
import { useColorScheme, View } from "react-native";
import { mapHtml, type MapPoint } from "./mapHtml";

export function MiniMap({ points, me, onPick, height = 260, label, offlineText }: {
  points: MapPoint[]; me: { lat: number; lon: number } | null; onPick: (ref: string) => void; height?: number;
  label: string; offlineText: string;
}) {
  const dark = useColorScheme() === "dark";
  useEffect(() => {
    const handler = (e: MessageEvent) => {
      try { const ref = JSON.parse(String(e.data)).ref; if (ref) onPick(ref); } catch { /* ignore */ }
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, [onPick]);
  return (
    <View style={{ height, borderRadius: 12, overflow: "hidden" }}>
      <iframe title={label} srcDoc={mapHtml(points, me, dark, offlineText)}
              style={{ border: 0, width: "100%", height: "100%" }} sandbox="allow-scripts" />
    </View>
  );
}
