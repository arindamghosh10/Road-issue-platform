// Inbox: "Is it fixed?" questions first (the platform asks, never the government), then
// notifications. Answers are anonymous: officials see only totals like "3 of 5 said yes".

import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { Image, Pressable, RefreshControl, ScrollView, View } from "react-native";
import { Body, Button, Card, Empty, ErrorText, Screen, Small, Title } from "@/components/ui";
import { api, type Notice, type PendingConfirmation } from "@/lib/api";
import { errorText, noticeText, type MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/locale";
import { radius, space } from "@/lib/theme";

const ANSWERS = [
  { value: "yes", key: "ans.yes" },
  { value: "partly", key: "ans.partly" },
  { value: "no", key: "ans.no" },
] as const;

export default function Inbox() {
  const router = useRouter();
  const { t, date } = useI18n();
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
    } catch (e) { setError(errorText(t, e)); }
  }, [t]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  async function answer(ref: string, value: "yes" | "no" | "partly") {
    setBusy(`${ref}:${value}`); setError(null);
    try {
      const r = await api.confirm(ref, value);
      setThanks(r.ticket_status === "resolved" ? t("inbox.thanksResolved", { ref })
        : r.ticket_status === "reopened" ? t("inbox.thanksReopened", { ref })
        : t("inbox.thanks"));
      await load();
    } catch (e) { setError(errorText(t, e)); } finally { setBusy(null); }
  }

  return (
    <Screen>
      <ScrollView contentContainerStyle={{ padding: space(4), gap: space(4) }}
                  refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}>
        {error ? <ErrorText>{error}</ErrorText> : null}
        {thanks ? <Card><Body>{thanks}</Body></Card> : null}

        {pending && pending.length > 0 && (
          <View style={{ gap: space(3) }}>
            <Title>{t("inbox.fixedQ")}</Title>
            {pending.map((p) => (
              <Card key={p.ticket_ref}>
                <Body>{t(`cat.${p.category}` as MessageKey)} · {p.ticket_ref}</Body>
                <Small>{p.fix_submitted_on ? t("inbox.repairedOn", { date: date(p.fix_submitted_on) }) : t("inbox.repaired")}</Small>
                {p.fix_photos[0] ? (
                  <Image source={{ uri: p.fix_photos[0] }} style={{ width: "100%", aspectRatio: 4 / 3, borderRadius: radius }}
                         accessibilityLabel={t("inbox.repairPhoto")} />
                ) : null}
                {p.my_answer ? <Small>{t("inbox.yourAnswer", { answer: t(ANSWERS.find((a) => a.value === p.my_answer)?.key ?? "ans.yes") })}</Small> : null}
                <View style={{ gap: space(2) }}>
                  {ANSWERS.map((a) => (
                    <Button key={a.value} title={t(a.key)} kind={a.value === "yes" ? "primary" : "secondary"}
                            busy={busy === `${p.ticket_ref}:${a.value}`} disabled={busy !== null}
                            onPress={() => answer(p.ticket_ref, a.value)} />
                  ))}
                </View>
              </Card>
            ))}
          </View>
        )}

        <Title>{t("inbox.notifications")}</Title>
        {notices && notices.length === 0 && <Empty title={t("inbox.emptyTitle")} hint={t("inbox.emptyHint")} />}
        {(notices ?? []).map((n) => ({ n, text: noticeText(t, n) })).map(({ n, text }) => (
          <Pressable key={n.id} disabled={!n.ticket_ref} onPress={() => n.ticket_ref && router.push(`/ticket/${n.ticket_ref}`)}
                     accessibilityRole={n.ticket_ref ? "button" : undefined}>
            <Card>
              <Body>{text.title}</Body>
              <Small>{text.body}</Small>
              <Small>{date(n.created_at)}</Small>
            </Card>
          </Pressable>
        ))}
      </ScrollView>
    </Screen>
  );
}
