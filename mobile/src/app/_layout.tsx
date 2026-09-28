import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { AuthProvider } from "@/lib/auth";
import { useTheme } from "@/lib/theme";

export default function RootLayout() {
  const t = useTheme();
  return (
    <AuthProvider>
      <StatusBar style="auto" />
      <Stack screenOptions={{
        headerStyle: { backgroundColor: t.surface },
        headerTintColor: t.ink,
        contentStyle: { backgroundColor: t.page },
      }}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="login" options={{ title: "Sign in", headerShown: false }} />
        <Stack.Screen name="report/[id]" options={{ title: "Your report" }} />
        <Stack.Screen name="ticket/[ref]" options={{ title: "Issue" }} />
      </Stack>
    </AuthProvider>
  );
}
