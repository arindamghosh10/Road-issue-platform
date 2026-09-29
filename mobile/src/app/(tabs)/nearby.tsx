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
import { errorText, type MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/locale";
import { formatDistance, ticketStatusView } from "@/lib/logic";
import { space } from "@/lib/theme";

type Fix = { lat: number; lon: number; accuracy: number };

export default function Nearby() {
  const router = useRouter();
  const { t: tr } = useI18n();
  const catName = (x: NearbyTicket) => tr(`cat.${x.category}` as MessageKey);
  const [fix, setFix] = useState<Fix | null>(null);
  const [rows, setRows] = useState<NearbyTicket[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyRef, setBusyRef] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const perm = await Location.requestForegroundPermissionsAsync();
      if (!perm.granted) { setError(tr("near.allowLoc")); return; }
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      const f = { lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy: pos.coords.accuracy ?? 999 };
      setFix(f);
      setRows(await api.nearby(f.lat, f.lon));
    } catch (e) { setError(errorText(tr, e)); }
  }, [tr]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  async function seeToo(t: NearbyTicket) {
    if (!fix) return;
    setBusyRef(t.ref); setError(null);
    try {
      const r = await api.iSeeThisToo(t.ref, fix.lat, fix.lon, fix.accuracy);
      setRows((prev) => prev?.map((x) => x.ref === t.ref ? { ...x, i_saw: true, also_seen: r.also_seen } : x) ?? null);
    } catch (e) { setError(errorText(tr, e)); } finally { setBusyRef(null); }
  }

  const points = (rows ?? []).map((t) => ({
    ref: t.ref, lat: t.lat, lon: t.lon, color: ticketStatusView(t.status).color,
    label: `${catName(t)}, ${tr(ticketStatusView(t.status).key)}`,
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
            {fix && <MiniMap points={points} me={fix} onPick={(ref) => router.push(`/ticket/${ref}`)}
                             label={tr("map.label")} offlineText={tr("map.offline")} />}
            {error ? <ErrorText>{error}</ErrorText> : null}
            {rows && rows.length > 0 && <Small>{tr("near.count", { n: rows.length })}</Small>}
          </View>
        }
        ListEmptyComponent={rows ? <Empty title={tr("near.emptyTitle")} hint={tr("near.emptyHint")} /> : null}
        renderItem={({ item: t }) => {
          const canSee = !t.i_reported && !t.i_saw && t.status !== "resolved" && t.distance_m <= 150;
          return (
            <Card>
              <Pressable onPress={() => router.push(`/ticket/${t.ref}`)} accessibilityRole="button"
                         accessibilityLabel={`${catName(t)}, ${tr("near.away", { d: formatDistance(t.distance_m) })}`}>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                  <Body>{catName(t)}</Body>
                  <Small>{formatDistance(t.distance_m)}</Small>
                </View>
                <StatusPill view={ticketStatusView(t.status)} />
                <Small>
                  {[tr("near.verified", { n: t.verified_reporters }),
                    t.also_seen ? tr("near.seenBy", { n: t.also_seen }) : null,
                    t.i_reported ? tr("near.youReported") : t.i_saw ? tr("near.youConfirmed") : null,
                  ].filter(Boolean).join(" · ")}
                </Small>
              </Pressable>
              {canSee && (
                <Button title={tr("near.seeToo")} kind="secondary" busy={busyRef === t.ref} onPress={() => seeToo(t)}
                        accessibilityHint={tr("near.seeTooHint")} />
              )}
            </Card>
          );
        }}
      />
    </Screen>
  );
}
