import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { FlatList, Pressable, RefreshControl, View } from "react-native";
import { Body, Button, Card, Empty, ErrorText, LanguagePicker, Screen, Small, StatusPill } from "@/components/ui";
import { api, type MyReport } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { codeText, errorText, type MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/locale";
import { reportStatusView } from "@/lib/logic";
import { space } from "@/lib/theme";

export default function MyReports() {
  const router = useRouter();
  const { signOut } = useAuth();
  const { t, date } = useI18n();
  const label = (code: string) => t(`cat.${code}` as MessageKey);
  const [rows, setRows] = useState<MyReport[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try { setRows(await api.myReports()); setError(null); } catch (e) { setError(errorText(t, e)); }
  }, [t]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  return (
    <Screen>
      <FlatList
        data={rows ?? []}
        keyExtractor={(r) => r.id}
        contentContainerStyle={{ padding: space(4), gap: space(3) }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
        ListHeaderComponent={error ? <ErrorText>{error}</ErrorText> : null}
        ListEmptyComponent={rows ? <Empty title={t("reports.emptyTitle")} hint={t("reports.emptyHint")} /> : null}
        renderItem={({ item }) => (
          <Pressable onPress={() => router.push(`/report/${item.id}`)} accessibilityRole="button"
                     accessibilityLabel={`${label(item.category)}, ${t(reportStatusView(item.status).key)}`}>
            <Card>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <Body>{label(item.category)}</Body>
                <StatusPill view={reportStatusView(item.status)} />
              </View>
              <Small>
                {t("reports.sent", { date: date(item.submitted_on) })}
                {item.ticket_ref ? ` · ${t("reports.issue", { ref: item.ticket_ref })}` : ""}
              </Small>
              {item.status === "rejected" && item.rejection_reason
                ? <Small>{codeText(t, item.rejection_code, item.rejection_params, item.rejection_reason)}</Small> : null}
            </Card>
          </Pressable>
        )}
        ListFooterComponent={
          <View style={{ marginTop: space(6), gap: space(4) }}>
            <LanguagePicker />
            <Button title={t("reports.signOut")} kind="secondary" onPress={signOut} />
          </View>
        }
      />
    </Screen>
  );
}
