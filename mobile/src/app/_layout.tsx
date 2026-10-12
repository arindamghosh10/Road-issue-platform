import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { AuthProvider } from "@/lib/auth";
import { I18nProvider, useI18n } from "@/lib/locale";
import { useTheme } from "@/lib/theme";

function RootStack() {
  const t = useTheme();
  const { t: tr } = useI18n();
  return (
    <Stack screenOptions={{
      headerStyle: { backgroundColor: t.surface },
      headerTintColor: t.ink,
      contentStyle: { backgroundColor: t.page },
    }}>
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      <Stack.Screen name="login" options={{ title: tr("screen.signIn"), headerShown: false }} />
      <Stack.Screen name="report/[id]" options={{ title: tr("screen.report") }} />
      <Stack.Screen name="ticket/[ref]" options={{ title: tr("screen.issue") }} />
    </Stack>
  );
}

export default function RootLayout() {
  return (
    <I18nProvider>
      <AuthProvider>
        <StatusBar style="auto" />
        <RootStack />
      </AuthProvider>
    </I18nProvider>
  );
}
