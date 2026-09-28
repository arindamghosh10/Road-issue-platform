import { Redirect, Tabs } from "expo-router";
import { ActivityIndicator, type ColorValue, Text, View } from "react-native";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";

function TabIcon({ glyph, color }: { glyph: string; color: ColorValue }) {
  return <Text style={{ fontSize: 20, color }} accessibilityElementsHidden>{glyph}</Text>;
}

export default function TabsLayout() {
  const { ready, signedIn } = useAuth();
  const t = useTheme();
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
      <Tabs.Screen name="index" options={{ title: "Report", tabBarIcon: ({ color }) => <TabIcon glyph="◎" color={color} /> }} />
      <Tabs.Screen name="reports" options={{ title: "My reports", tabBarIcon: ({ color }) => <TabIcon glyph="☰" color={color} /> }} />
      <Tabs.Screen name="nearby" options={{ title: "Nearby", tabBarIcon: ({ color }) => <TabIcon glyph="⌖" color={color} /> }} />
      <Tabs.Screen name="inbox" options={{ title: "Inbox", tabBarIcon: ({ color }) => <TabIcon glyph="✉" color={color} /> }} />
    </Tabs>
  );
}
