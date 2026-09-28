// Small shared UI pieces. Touch targets are ≥ 44pt; status is always icon + words + colour.

import { ActivityIndicator, Pressable, StyleSheet, Text, View, type ViewStyle } from "react-native";
import { radius, space, useTheme } from "@/lib/theme";

export function Screen({ children, style }: { children?: React.ReactNode; style?: ViewStyle }) {
  const t = useTheme();
  return <View style={[{ flex: 1, backgroundColor: t.page }, style]}>{children}</View>;
}

export function Card({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  const t = useTheme();
  return (
    <View style={[styles.card, { backgroundColor: t.surface, borderColor: t.border }, style]}>{children}</View>
  );
}

export function Title({ children }: { children: React.ReactNode }) {
  const t = useTheme();
  return <Text style={[styles.title, { color: t.ink }]} accessibilityRole="header">{children}</Text>;
}

export function Body({ children, muted, style }: { children: React.ReactNode; muted?: boolean; style?: object }) {
  const t = useTheme();
  return <Text style={[styles.body, { color: muted ? t.ink2 : t.ink }, style]}>{children}</Text>;
}

export function Small({ children, style }: { children: React.ReactNode; style?: object }) {
  const t = useTheme();
  return <Text style={[styles.small, { color: t.muted }, style]}>{children}</Text>;
}

export function Button({
  title, onPress, kind = "primary", disabled, busy, accessibilityHint,
}: {
  title: string; onPress: () => void; kind?: "primary" | "secondary" | "danger";
  disabled?: boolean; busy?: boolean; accessibilityHint?: string;
}) {
  const t = useTheme();
  const bg = kind === "primary" ? t.accent : kind === "danger" ? t.danger : t.surface;
  const fg = kind === "secondary" ? t.ink : t.onAccent;
  return (
    <Pressable
      accessibilityRole="button" accessibilityLabel={title} accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: disabled || busy, busy }}
      disabled={disabled || busy} onPress={onPress}
      style={({ pressed }) => [styles.button, {
        backgroundColor: bg, borderColor: kind === "secondary" ? t.border : bg,
        opacity: disabled ? 0.45 : pressed ? 0.8 : 1,
      }]}>
      {busy ? <ActivityIndicator color={fg} /> : <Text style={[styles.buttonText, { color: fg }]}>{title}</Text>}
    </Pressable>
  );
}

export function StatusPill({ view }: { view: { label: string; icon: string; color: string } }) {
  const t = useTheme();
  return (
    <View style={styles.pill} accessible accessibilityLabel={`Status: ${view.label}`}>
      <View style={[styles.pillDot, { backgroundColor: view.color }]}>
        <Text style={styles.pillIcon}>{view.icon}</Text>
      </View>
      <Text style={[styles.small, { color: t.ink2 }]}>{view.label}</Text>
    </View>
  );
}

export function ErrorText({ children }: { children: React.ReactNode }) {
  const t = useTheme();
  return <Text accessibilityRole="alert" style={[styles.body, { color: t.danger }]}>{children}</Text>;
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <View style={{ alignItems: "center", padding: space(8), gap: space(2) }}>
      <Body>{title}</Body>
      {hint ? <Small style={{ textAlign: "center" }}>{hint}</Small> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radius, borderWidth: StyleSheet.hairlineWidth, padding: space(4), gap: space(2) },
  title: { fontSize: 22, fontWeight: "700" },
  body: { fontSize: 16, lineHeight: 22 },
  small: { fontSize: 13, lineHeight: 18 },
  button: { minHeight: 48, borderRadius: 10, borderWidth: 1, paddingHorizontal: space(4), alignItems: "center", justifyContent: "center" },
  buttonText: { fontSize: 16, fontWeight: "600" },
  pill: { flexDirection: "row", alignItems: "center", gap: 6 },
  pillDot: { width: 20, height: 20, borderRadius: 10, alignItems: "center", justifyContent: "center" },
  pillIcon: { fontSize: 11, fontWeight: "700", color: "#0b0b0b" },
});
