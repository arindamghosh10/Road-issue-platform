import { useColorScheme, View } from "react-native";
import { WebView } from "react-native-webview";
import { mapHtml, type MapPoint } from "./mapHtml";

export function MiniMap({ points, me, onPick, height = 260, label, offlineText }: {
  points: MapPoint[]; me: { lat: number; lon: number } | null; onPick: (ref: string) => void; height?: number;
  label: string; offlineText: string;
}) {
  const dark = useColorScheme() === "dark";
  return (
    <View style={{ height, borderRadius: 12, overflow: "hidden" }} accessibilityLabel={label}>
      <WebView
        originWhitelist={["*"]}
        source={{ html: mapHtml(points, me, dark, offlineText) }}
        onMessage={(e) => {
          try { onPick(JSON.parse(e.nativeEvent.data).ref); } catch { /* ignore */ }
        }}
        javaScriptEnabled
        scrollEnabled={false}
      />
    </View>
  );
}
