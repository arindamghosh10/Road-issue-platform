// Issues near me: map + list (nearest first). "I see this too" confirms an issue while
// standing near it (the server checks you're within 150 m). To add a new photo instead,
// use the Report tab — it merges into the same issue automatically.

import * as Location from "expo-location";
import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { FlatList, Pressable, RefreshControl, View } from "react-native";
import { MiniMap } from "@/components/MiniMap";
import { Body, Button, Card, Empty, ErrorText, Screen, Small, StatusPill } from "@/components/ui";
import { api, type NearbyTicket } from "@/lib/api";
import { formatDistance, ticketStatusView } from "@/lib/logic";
import { space } from "@/lib/theme";

type Fix = { lat: number; lon: number; accuracy: number };

export default function Nearby() {
  const router = useRouter();
  const [fix, setFix] = useState<Fix | null>(null);
  const [rows, setRows] = useState<NearbyTicket[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyRef, setBusyRef] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const perm = await Location.requestForegroundPermissionsAsync();
      if (!perm.granted) { setError("Allow location to see issues near you."); return; }
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      const f = { lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy: pos.coords.accuracy ?? 999 };
      setFix(f);
      setRows(await api.nearby(f.lat, f.lon));
    } catch (e) { setError((e as Error).message); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  async function seeToo(t: NearbyTicket) {
    if (!fix) return;
    setBusyRef(t.ref); setError(null);
    try {
      const r = await api.iSeeThisToo(t.ref, fix.lat, fix.lon, fix.accuracy);
      setRows((prev) => prev?.map((x) => x.ref === t.ref ? { ...x, i_saw: true, also_seen: r.also_seen } : x) ?? null);
    } catch (e) { setError((e as Error).message); } finally { setBusyRef(null); }
  }

  const points = (rows ?? []).map((t) => ({
    ref: t.ref, lat: t.lat, lon: t.lon, color: ticketStatusView(t.status).color,
    label: `${t.category_name}, ${ticketStatusView(t.status).label}`,
  }));

  return (
    <Screen>
      <FlatList
        data={rows ?? []}
        keyExtractor={(t) => t.ref}
        contentContainerStyle={{ padding: space(4), gap: space(3) }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
        ListHeaderComponent={
          <View style={{ gap: space(3) }}>
            {fix && <MiniMap points={points} me={fix} onPick={(ref) => router.push(`/ticket/${ref}`)} />}
            {error ? <ErrorText>{error}</ErrorText> : null}
            {rows && rows.length > 0 && <Small>{rows.length} issue(s) within 1.5 km, nearest first</Small>}
          </View>
        }
        ListEmptyComponent={rows ? <Empty title="No reported issues nearby" hint="Spotted one? Report it from the Report tab." /> : null}
        renderItem={({ item: t }) => {
          const canSee = !t.i_reported && !t.i_saw && t.status !== "resolved" && t.distance_m <= 150;
          return (
            <Card>
              <Pressable onPress={() => router.push(`/ticket/${t.ref}`)} accessibilityRole="button"
                         accessibilityLabel={`${t.category_name}, ${formatDistance(t.distance_m)} away`}>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                  <Body>{t.category_name}</Body>
                  <Small>{formatDistance(t.distance_m)}</Small>
                </View>
                <StatusPill view={ticketStatusView(t.status)} />
                <Small>
                  {t.verified_reporters} verified report(s){t.also_seen ? ` · seen by ${t.also_seen} more` : ""}
                  {t.i_reported ? " · you reported this" : t.i_saw ? " · you confirmed this" : ""}
                </Small>
              </Pressable>
              {canSee && (
                <Button title="I see this too" kind="secondary" busy={busyRef === t.ref} onPress={() => seeToo(t)}
                        accessibilityHint="Confirms this issue is still there. You must be standing near it." />
              )}
            </Card>
          );
        }}
      />
    </Screen>
  );
}
