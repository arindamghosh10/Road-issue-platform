// Sign in with a phone number + one-time code. The phone number goes only to the
// identity vault; the app receives a token that carries an anonymous id.

import { useRouter } from "expo-router";
import { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Body, Button, Card, ErrorText, Small, Title } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { normalizePhone } from "@/lib/logic";
import { space, useTheme } from "@/lib/theme";

export default function Login() {
  const t = useTheme();
  const router = useRouter();
  const { signIn } = useAuth();
  const [phone, setPhone] = useState("");
  const [challenge, setChallenge] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const input = [styles.input, { color: t.ink, borderColor: t.border, backgroundColor: t.surface }];

  async function sendCode() {
    const e164 = normalizePhone(phone);
    if (!e164) { setError("Enter a 10-digit Indian mobile number."); return; }
    setBusy(true); setError(null);
    try {
      setChallenge((await api.requestOtp(e164)).challenge_id);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  async function verify() {
    if (!challenge) return;
    setBusy(true); setError(null);
    try {
      const { access_token } = await api.verifyOtp(challenge, code.trim());
      await signIn(access_token);
      router.replace("/");
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.page }}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={styles.wrap} keyboardShouldPersistTaps="handled">
          <View style={{ gap: space(2) }}>
            <Title>RoadWatch</Title>
            <Body muted>Report damaged roads and bridges. We verify every report and track it until it is fixed.</Body>
          </View>

          <Card>
            {!challenge ? (
              <>
                <Body>Your mobile number</Body>
                <TextInput style={input} value={phone} onChangeText={setPhone} keyboardType="phone-pad"
                           autoComplete="tel" placeholder="98300 12345" placeholderTextColor={t.muted}
                           accessibilityLabel="Mobile number" maxLength={16} />
                <Button title="Send code" onPress={sendCode} busy={busy} disabled={!phone.trim()} />
              </>
            ) : (
              <>
                <Body>Enter the 6-digit code we sent</Body>
                <TextInput style={input} value={code} onChangeText={setCode} keyboardType="number-pad"
                           autoComplete="one-time-code" placeholder="123456" placeholderTextColor={t.muted}
                           accessibilityLabel="One-time code" maxLength={6} />
                <Button title="Sign in" onPress={verify} busy={busy} disabled={code.trim().length < 4} />
                <Button title="Use a different number" kind="secondary" onPress={() => { setChallenge(null); setCode(""); }} />
              </>
            )}
            {error ? <ErrorText>{error}</ErrorText> : null}
          </Card>

          <Card>
            <Body>🔒 Your identity stays private</Body>
            <Small>
              Your number is stored encrypted, separately from reports, and is never shared with the
              government. Officials only see “a verified citizen reported this”.
            </Small>
          </Card>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: space(5), gap: space(5), flexGrow: 1, justifyContent: "center" },
  input: { minHeight: 48, borderWidth: 1, borderRadius: 10, paddingHorizontal: space(3), fontSize: 18, letterSpacing: 1 },
});
