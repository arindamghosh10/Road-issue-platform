import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { ScrollView, Text, View } from "react-native";
import { Body, Button, Card, ErrorText, Screen, Small, StatusPill, Title } from "@/components/ui";
import { api, type MyReport } from "@/lib/api";
import { checkLines, codeText, errorText, type MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/locale";
import { reportStatusView } from "@/lib/logic";
import { space, useTheme } from "@/lib/theme";

export default function ReportDetail() {
  const t = useTheme();
  const { t: tr, date } = useI18n();
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
      } catch (e) { setError(errorText(tr, e)); }
    };
    load();
    timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [id, tr]);

  if (error) return <Screen style={{ padding: space(4) }}><ErrorText>{error}</ErrorText></Screen>;
  if (!report) return <Screen />;
  const category = tr(`cat.${report.category}` as MessageKey);

  return (
    <Screen>
      <ScrollView contentContainerStyle={{ padding: space(4), gap: space(4) }}>
        <Card>
          <Title>{category}</Title>
          <StatusPill view={reportStatusView(report.status)} />
          <Small>{tr("reports.sent", { date: date(report.submitted_on) })}</Small>
          {report.rejection_reason
            ? <Body muted>{codeText(tr, report.rejection_code, report.rejection_params, report.rejection_reason)}</Body> : null}
        </Card>
        {report.checks.length > 0 && (
          <Card>
            <Body>{tr("detail.checks")}</Body>
            {report.checks.map((c) => {
              const line = checkLines(tr, c);
              return (
                <View key={c.name} style={{ flexDirection: "row", gap: space(2) }}>
                  <Text style={{ color: c.passed ? t.good : t.danger, fontSize: 16 }}>{c.passed ? "✓" : "✕"}</Text>
                  <View style={{ flex: 1 }}>
                    <Body>{line.title}</Body>
                    <Small>{line.detail}</Small>
                  </View>
                </View>
              );
            })}
          </Card>
        )}
        {report.ticket_ref && <Button title={tr("detail.follow", { ref: report.ticket_ref })} onPress={() => router.push(`/ticket/${report.ticket_ref}`)} />}
      </ScrollView>
    </Screen>
  );
}
