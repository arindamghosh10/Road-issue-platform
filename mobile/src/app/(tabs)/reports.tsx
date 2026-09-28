import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { FlatList, Pressable, RefreshControl, View } from "react-native";
import { Body, Button, Card, Empty, ErrorText, Screen, Small, StatusPill } from "@/components/ui";
import { api, type MyReport } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { CATEGORIES, formatDate, reportStatusView } from "@/lib/logic";
import { space } from "@/lib/theme";

const label = (code: string) => CATEGORIES.find((c) => c.code === code)?.label ?? code;

export default function MyReports() {
  const router = useRouter();
  const { signOut } = useAuth();
  const [rows, setRows] = useState<MyReport[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try { setRows(await api.myReports()); setError(null); } catch (e) { setError((e as Error).message); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  return (
    <Screen>
      <FlatList
        data={rows ?? []}
        keyExtractor={(r) => r.id}
        contentContainerStyle={{ padding: space(4), gap: space(3) }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
        ListHeaderComponent={error ? <ErrorText>{error}</ErrorText> : null}
        ListEmptyComponent={rows ? <Empty title="No reports yet" hint="Use the Report tab to photograph a damaged road or bridge." /> : null}
        renderItem={({ item }) => (
          <Pressable onPress={() => router.push(`/report/${item.id}`)} accessibilityRole="button"
                     accessibilityLabel={`${label(item.category)}, ${reportStatusView(item.status).label}`}>
            <Card>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <Body>{label(item.category)}</Body>
                <StatusPill view={reportStatusView(item.status)} />
              </View>
              <Small>
                Sent {formatDate(item.submitted_on)}
                {item.ticket_ref ? ` · issue ${item.ticket_ref}` : ""}
              </Small>
              {item.status === "rejected" && item.rejection_reason ? <Small>{item.rejection_reason}</Small> : null}
            </Card>
          </Pressable>
        )}
        ListFooterComponent={<View style={{ marginTop: space(6) }}><Button title="Sign out" kind="secondary" onPress={signOut} /></View>}
      />
    </Screen>
  );
}
