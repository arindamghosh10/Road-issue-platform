// Inbox: "Is it fixed?" questions first (the platform asks, never the government), then
// notifications. Answers are anonymous: officials see only totals like "3 of 5 said yes".

import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { Image, Pressable, RefreshControl, ScrollView, View } from "react-native";
import { Body, Button, Card, Empty, ErrorText, Screen, Small, Title } from "@/components/ui";
import { api, type Notice, type PendingConfirmation } from "@/lib/api";
import { CATEGORIES, formatDate } from "@/lib/logic";
import { radius, space } from "@/lib/theme";

const ANSWERS = [
  { value: "yes", label: "Yes, fixed" },
  { value: "partly", label: "Partly" },
  { value: "no", label: "No, still broken" },
] as const;

export default function Inbox() {
  const router = useRouter();
  const [pending, setPending] = useState<PendingConfirmation[] | null>(null);
  const [notices, setNotices] = useState<Notice[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [thanks, setThanks] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [p, n] = await Promise.all([api.confirmations(), api.notifications()]);
      setPending(p); setNotices(n); setError(null);
    } catch (e) { setError((e as Error).message); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  async function answer(ref: string, value: "yes" | "no" | "partly") {
    setBusy(`${ref}:${value}`); setError(null);
    try {
      const r = await api.confirm(ref, value);
      setThanks(r.ticket_status === "resolved" ? `Thanks! ${ref} is now marked resolved.`
        : r.ticket_status === "reopened" ? `Thanks. ${ref} was reopened and escalated.`
        : "Thanks — your answer was recorded.");
      await load();
    } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  }

  return (
    <Screen>
      <ScrollView contentContainerStyle={{ padding: space(4), gap: space(4) }}
                  refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}>
        {error ? <ErrorText>{error}</ErrorText> : null}
        {thanks ? <Card><Body>{thanks}</Body></Card> : null}

        {pending && pending.length > 0 && (
          <View style={{ gap: space(3) }}>
            <Title>Is it fixed?</Title>
            {pending.map((p) => (
              <Card key={p.ticket_ref}>
                <Body>{CATEGORIES.find((c) => c.code === p.category)?.label ?? p.category} · {p.ticket_ref}</Body>
                <Small>The authority says this was repaired{p.fix_submitted_on ? ` on ${formatDate(p.fix_submitted_on)}` : ""}. Please check the spot if you can.</Small>
                {p.fix_photos[0] ? (
                  <Image source={{ uri: p.fix_photos[0] }} style={{ width: "100%", aspectRatio: 4 / 3, borderRadius: radius }}
                         accessibilityLabel="Repair photo from the authority" />
                ) : null}
                {p.my_answer ? <Small>Your answer: {ANSWERS.find((a) => a.value === p.my_answer)?.label}. You can change it.</Small> : null}
                <View style={{ gap: space(2) }}>
                  {ANSWERS.map((a) => (
                    <Button key={a.value} title={a.label} kind={a.value === "yes" ? "primary" : "secondary"}
                            busy={busy === `${p.ticket_ref}:${a.value}`} disabled={busy !== null}
                            onPress={() => answer(p.ticket_ref, a.value)} />
                  ))}
                </View>
              </Card>
            ))}
          </View>
        )}

        <Title>Notifications</Title>
        {notices && notices.length === 0 && <Empty title="Nothing yet" hint="Updates about your reports will appear here." />}
        {(notices ?? []).map((n) => (
          <Pressable key={n.id} disabled={!n.ticket_ref} onPress={() => n.ticket_ref && router.push(`/ticket/${n.ticket_ref}`)}
                     accessibilityRole={n.ticket_ref ? "button" : undefined}>
            <Card>
              <Body>{n.title}</Body>
              <Small>{n.body}</Small>
              <Small>{formatDate(n.created_at)}</Small>
            </Card>
          </Pressable>
        ))}
      </ScrollView>
    </Screen>
  );
}
