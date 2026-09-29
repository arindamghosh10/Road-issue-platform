import { Redirect, Tabs } from "expo-router";
import { ActivityIndicator, type ColorValue, Text, View } from "react-native";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/locale";
import { useTheme } from "@/lib/theme";

function TabIcon({ glyph, color }: { glyph: string; color: ColorValue }) {
  return <Text style={{ fontSize: 20, color }} accessibilityElementsHidden>{glyph}</Text>;
}

export default function TabsLayout() {
  const { ready, signedIn } = useAuth();
  const t = useTheme();
  const { t: tr } = useI18n();
  if (!ready) {
    return <View style={{ flex: 1, justifyContent: "center", backgroundColor: t.page }}><ActivityIndicator /></View>;
  }
  if (!signedIn) return <Redirect href="/login" />;

  return (
    <Tabs screenOptions={{
      tabBarActiveTintColor: t.accent,
      tabBarInactiveTintColor: t.muted,
      tabBarStyle: { backgroundColor: t.surface, borderTopColor: t.border },
      headerStyle: { backgroundColor: t.surface },
      headerTintColor: t.ink,
      sceneStyle: { backgroundColor: t.page },
    }}>
      <Tabs.Screen name="index" options={{ title: tr("tab.report"), tabBarIcon: ({ color }) => <TabIcon glyph="◎" color={color} /> }} />
      <Tabs.Screen name="reports" options={{ title: tr("tab.reports"), tabBarIcon: ({ color }) => <TabIcon glyph="☰" color={color} /> }} />
      <Tabs.Screen name="nearby" options={{ title: tr("tab.nearby"), tabBarIcon: ({ color }) => <TabIcon glyph="⌖" color={color} /> }} />
      <Tabs.Screen name="inbox" options={{ title: tr("tab.inbox"), tabBarIcon: ({ color }) => <TabIcon glyph="✉" color={color} /> }} />
    </Tabs>
  );
}
