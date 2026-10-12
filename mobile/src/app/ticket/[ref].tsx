import { useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { Image, ScrollView, View } from "react-native";
import { Body, Card, ErrorText, Screen, Small, StatusPill, Title } from "@/components/ui";
import { api, type Ticket } from "@/lib/api";
import { errorText, type MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/locale";
import { ticketStatusView } from "@/lib/logic";
import { radius, space } from "@/lib/theme";

export default function TicketScreen() {
  const { ref } = useLocalSearchParams<{ ref: string }>();
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { t, date } = useI18n();

  useEffect(() => { api.ticket(ref).then(setTicket).catch((e) => setError(errorText(t, e))); }, [ref, t]);
  if (error) return <Screen style={{ padding: space(4) }}><ErrorText>{error}</ErrorText></Screen>;
  if (!ticket) return <Screen />;

  return (
    <Screen>
      <ScrollView contentContainerStyle={{ padding: space(4), gap: space(4) }}>
        <Card>
          <Title>{t(`cat.${ticket.category}` as MessageKey)}</Title>
          <Small>{ticket.ref}</Small>
          <StatusPill view={ticketStatusView(ticket.status)} />
          <Body muted>{ticket.areas.map((a) => a.name).join(" › ")}</Body>
        </Card>
        <Card>
          <Body>{ticket.also_seen
            ? t("tk.reportersSeen", { n: ticket.verified_reporters, m: ticket.also_seen })
            : t("tk.reporters", { n: ticket.verified_reporters })}</Body>
          <Small>{t("tk.owner", { name: ticket.authority ?? "—" })}</Small>
          <Small>{t("tk.answerable", { name: ticket.responsible_area ?? "—" })}</Small>
          {ticket.status !== "resolved" && ticket.sla_due_on && <Small>{t("tk.deadline", { date: date(ticket.sla_due_on) })}</Small>}
          {ticket.resolved_on && <Small>{t("tk.resolvedOn", { date: date(ticket.resolved_on) })}</Small>}
        </Card>
        {ticket.photos.length > 0 && (
          <View style={{ gap: space(2) }}>
            <Small>{t("tk.photos")}</Small>
            <ScrollView horizontal contentContainerStyle={{ gap: space(2) }}>
              {ticket.photos.map((u) => (
                <Image key={u} source={{ uri: u }} style={{ width: 200, height: 150, borderRadius: radius }}
                       accessibilityLabel={t("tk.photoAlt")} />
              ))}
            </ScrollView>
          </View>
        )}
      </ScrollView>
    </Screen>
  );
}
