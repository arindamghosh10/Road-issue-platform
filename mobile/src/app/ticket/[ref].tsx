import { useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { Image, ScrollView, View } from "react-native";
import { Body, Card, ErrorText, Screen, Small, StatusPill, Title } from "@/components/ui";
import { api, type Ticket } from "@/lib/api";
import { formatDate, ticketStatusView } from "@/lib/logic";
import { radius, space } from "@/lib/theme";

export default function TicketScreen() {
  const { ref } = useLocalSearchParams<{ ref: string }>();
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { api.ticket(ref).then(setTicket).catch((e) => setError(e.message)); }, [ref]);
  if (error) return <Screen style={{ padding: space(4) }}><ErrorText>{error}</ErrorText></Screen>;
  if (!ticket) return <Screen />;

  return (
    <Screen>
      <ScrollView contentContainerStyle={{ padding: space(4), gap: space(4) }}>
        <Card>
          <Title>{ticket.category_name}</Title>
          <Small>{ticket.ref}</Small>
          <StatusPill view={ticketStatusView(ticket.status)} />
          <Body muted>{ticket.areas.map((a) => a.name).join(" › ")}</Body>
        </Card>
        <Card>
          <Body>{ticket.verified_reporters} verified citizen(s) reported this
            {ticket.also_seen ? `, ${ticket.also_seen} more saw it` : ""}.</Body>
          <Small>Road owner: {ticket.authority ?? "—"}</Small>
          <Small>Currently answerable: {ticket.responsible_area ?? "—"}</Small>
          {ticket.status !== "resolved" && ticket.sla_due_on && <Small>Deadline: {formatDate(ticket.sla_due_on)}</Small>}
          {ticket.resolved_on && <Small>Resolved on {formatDate(ticket.resolved_on)}</Small>}
        </Card>
        {ticket.photos.length > 0 && (
          <View style={{ gap: space(2) }}>
            <Small>Photos (faces and number plates blurred)</Small>
            <ScrollView horizontal contentContainerStyle={{ gap: space(2) }}>
              {ticket.photos.map((u) => (
                <Image key={u} source={{ uri: u }} style={{ width: 200, height: 150, borderRadius: radius }}
                       accessibilityLabel="Citizen photo" />
              ))}
            </ScrollView>
          </View>
        )}
      </ScrollView>
    </Screen>
  );
}
