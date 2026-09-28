import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { ScrollView, Text, View } from "react-native";
import { Body, Button, Card, ErrorText, Screen, Small, StatusPill, Title } from "@/components/ui";
import { api, type MyReport } from "@/lib/api";
import { CATEGORIES, CHECK_NAMES, formatDate, reportStatusView } from "@/lib/logic";
import { space, useTheme } from "@/lib/theme";

export default function ReportDetail() {
  const t = useTheme();
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [report, setReport] = useState<MyReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | undefined;
    const load = async () => {
      try {
        const r = await api.myReport(id);
        setReport(r);
        if (r.status !== "under_verification" && timer) clearInterval(timer);
      } catch (e) { setError((e as Error).message); }
    };
    load();
    timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [id]);

  if (error) return <Screen style={{ padding: space(4) }}><ErrorText>{error}</ErrorText></Screen>;
  if (!report) return <Screen />;
  const category = CATEGORIES.find((c) => c.code === report.category)?.label ?? report.category;

  return (
    <Screen>
      <ScrollView contentContainerStyle={{ padding: space(4), gap: space(4) }}>
        <Card>
          <Title>{category}</Title>
          <StatusPill view={reportStatusView(report.status)} />
          <Small>Sent {formatDate(report.submitted_on)}</Small>
          {report.rejection_reason ? <Body muted>{report.rejection_reason}</Body> : null}
        </Card>
        {report.checks.length > 0 && (
          <Card>
            <Body>Verification checks</Body>
            {report.checks.map((c) => (
              <View key={c.name} style={{ flexDirection: "row", gap: space(2) }}>
                <Text style={{ color: c.passed ? t.good : t.danger, fontSize: 16 }}>{c.passed ? "✓" : "✕"}</Text>
                <View style={{ flex: 1 }}>
                  <Body>{CHECK_NAMES[c.name] ?? c.name}</Body>
                  <Small>{c.reason}</Small>
                </View>
              </View>
            ))}
          </Card>
        )}
        {report.ticket_ref && <Button title={`Follow issue ${report.ticket_ref}`} onPress={() => router.push(`/ticket/${report.ticket_ref}`)} />}
      </ScrollView>
    </Screen>
  );
}
