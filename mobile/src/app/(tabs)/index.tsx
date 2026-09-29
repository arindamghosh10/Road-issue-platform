// Report an issue: camera → category → submit → live verification status.
//
// CAMERA ONLY, BY DESIGN. The app contains no gallery / media-library picker at all
// (scripts/check-no-gallery.mjs fails the build if one is added), so every photo is
// taken live, here, with GPS and time captured at the same moment. The API also refuses
// any upload that doesn't declare capture_source=in_app_camera.

import { CameraView, useCameraPermissions } from "expo-camera";
import * as Location from "expo-location";
import { useRouter } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { Image, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { Body, Button, Card, ErrorText, Screen, Small, StatusPill, Title } from "@/components/ui";
import { api, appendPhoto, type MyReport } from "@/lib/api";
import { checkLines, codeText, errorText, type MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/locale";
import { CATEGORIES, gpsQuality, reportStatusView } from "@/lib/logic";
import { radius, space, useTheme } from "@/lib/theme";

type Shot = { uri: string; lat: number; lon: number; accuracy: number | null; takenAt: string };
type Step = "camera" | "details" | "sending" | "done";

export default function ReportScreen() {
  const t = useTheme();
  const { t: tr } = useI18n();
  const router = useRouter();
  const camera = useRef<CameraView>(null);
  const [camPerm, requestCam] = useCameraPermissions();
  const [locPerm, setLocPerm] = useState<boolean | null>(null);
  const [step, setStep] = useState<Step>("camera");
  const [shot, setShot] = useState<Shot | null>(null);
  const [category, setCategory] = useState<string | null>(null);
  const [description, setDescription] = useState("");
  const [result, setResult] = useState<MyReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [capturing, setCapturing] = useState(false);

  useEffect(() => {
    Location.getForegroundPermissionsAsync().then((p) => setLocPerm(p.granted));
  }, []);

  // Poll the report while the server verifies it (usually a few seconds).
  useEffect(() => {
    if (step !== "done" || !result || result.status !== "under_verification") return;
    const timer = setInterval(async () => {
      try { setResult(await api.myReport(result.id)); } catch { /* keep polling */ }
    }, 2000);
    return () => clearInterval(timer);
  }, [step, result]);

  async function askPermissions() {
    await requestCam();
    const loc = await Location.requestForegroundPermissionsAsync();
    setLocPerm(loc.granted);
  }

  async function capture() {
    if (!camera.current) return;
    setCapturing(true); setError(null);
    try {
      // Photo and GPS fix are taken together so they describe the same moment and place.
      const [pic, pos] = await Promise.all([
        camera.current.takePictureAsync({ quality: 0.8 }),
        Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }),
      ]);
      if ((pos as { mocked?: boolean }).mocked) {
        setError(tr("cam.mock"));
        return;
      }
      setShot({ uri: pic.uri, lat: pos.coords.latitude, lon: pos.coords.longitude,
                accuracy: pos.coords.accuracy, takenAt: new Date().toISOString() });
      setStep("details");
    } catch (e) {
      setError(tr("cam.failed", { error: (e as Error).message }));
    } finally { setCapturing(false); }
  }

  async function submit() {
    if (!shot || !category) return;
    setStep("sending"); setError(null);
    try {
      const form = new FormData();
      await appendPhoto(form, shot.uri);
      form.append("category", category);
      form.append("lat", String(shot.lat));
      form.append("lon", String(shot.lon));
      if (shot.accuracy != null) form.append("gps_accuracy_m", String(shot.accuracy));
      form.append("captured_at", shot.takenAt);
      form.append("capture_source", "in_app_camera");
      if (description.trim()) form.append("description", description.trim());
      setResult(await api.submitReport(form));
      setStep("done");
    } catch (e) {
      setError(errorText(tr, e));
      setStep("details");
    }
  }

  function reset() {
    setShot(null); setCategory(null); setDescription(""); setResult(null); setError(null); setStep("camera");
  }

  // --- Permissions -----------------------------------------------------------------------
  if (!camPerm || locPerm === null) return <Screen />;
  if (!camPerm.granted || !locPerm) {
    return (
      <Screen style={styles.pad}>
        <Card>
          <Title>{tr("perm.title")}</Title>
          <Body muted>{tr("perm.body")}</Body>
          <Button title={tr("perm.allow")} onPress={askPermissions} />
          {camPerm.canAskAgain === false && <Small>{tr("perm.denied")}</Small>}
        </Card>
      </Screen>
    );
  }

  // --- Result ------------------------------------------------------------------------------
  if (step === "done" && result) {
    const pending = result.status === "under_verification";
    return (
      <Screen>
        <ScrollView contentContainerStyle={[styles.pad, { gap: space(4) }]}>
          <Card>
            <Title>{pending ? tr("result.checking") : result.status === "verified" ? tr("result.thanks") : tr("result.notVerified")}</Title>
            <StatusPill view={reportStatusView(result.status)} />
            {result.status === "verified" && (
              <Body muted>{tr("result.verifiedBody", { ref: result.ticket_ref ?? "" })}</Body>
            )}
            {result.status === "rejected" && (
              <Body muted>{codeText(tr, result.rejection_code, result.rejection_params, result.rejection_reason ?? "")}</Body>
            )}
            {pending && <Body muted>{tr("result.pending")}</Body>}
          </Card>
          {result.checks.length > 0 && (
            <Card>
              <Body>{tr("result.checked")}</Body>
              {result.checks.map((c) => {
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
          {result.ticket_ref && <Button title={tr("result.view")} kind="secondary" onPress={() => router.push(`/ticket/${result.ticket_ref}`)} />}
          <Button title={tr("result.another")} onPress={reset} />
        </ScrollView>
      </Screen>
    );
  }

  // --- Details -------------------------------------------------------------------------
  if ((step === "details" || step === "sending") && shot) {
    const gps = gpsQuality(shot.accuracy);
    return (
      <Screen>
        <ScrollView contentContainerStyle={[styles.pad, { gap: space(4) }]} keyboardShouldPersistTaps="handled">
          <Image source={{ uri: shot.uri }} style={styles.preview} accessibilityLabel={tr("details.photo")} />
          <Small>
            {tr(gps === "good" ? "gps.good" : gps === "weak" ? "gps.weak" : "gps.poor")}
            {shot.accuracy != null ? ` ${tr("gps.accuracy", { m: Math.round(shot.accuracy) })}` : ""}
          </Small>

          <Body>{tr("details.what")}</Body>
          <View style={styles.chips} accessibilityRole="radiogroup">
            {CATEGORIES.map((c) => {
              const on = category === c.code;
              const label = tr(`cat.${c.code}` as MessageKey);
              return (
                <Pressable key={c.code} onPress={() => setCategory(c.code)} accessibilityRole="radio"
                           accessibilityState={{ checked: on }} accessibilityLabel={label}
                           style={[styles.chip, { borderColor: on ? t.accent : t.border,
                                                  backgroundColor: on ? t.accentWash : t.surface }]}>
                  <Text style={{ color: on ? t.accentInk : t.ink, fontSize: 15 }}>{c.icon}  {label}</Text>
                </Pressable>
              );
            })}
          </View>

          <TextInput value={description} onChangeText={setDescription} placeholder={tr("details.more")}
                     placeholderTextColor={t.muted} multiline maxLength={500} accessibilityLabel={tr("details.descLabel")}
                     style={[styles.textarea, { color: t.ink, borderColor: t.border, backgroundColor: t.surface }]} />
          <Small>{tr("details.anon")}</Small>

          {error ? <ErrorText>{error}</ErrorText> : null}
          <Button title={tr("details.submit")} onPress={submit} busy={step === "sending"}
                  disabled={!category || gps === "too-poor"} />
          <Button title={tr("details.retake")} kind="secondary" onPress={reset} disabled={step === "sending"} />
        </ScrollView>
      </Screen>
    );
  }

  // --- Camera ------------------------------------------------------------------------------
  return (
    <View style={{ flex: 1, backgroundColor: "#000" }}>
      <CameraView ref={camera} style={{ flex: 1 }} facing="back" />
      <View style={styles.cameraBar}>
        <Text style={styles.cameraHint}>{tr("cam.hint")}</Text>
        {error ? <Text style={[styles.cameraHint, { color: "#ffb4ab" }]} accessibilityRole="alert">{error}</Text> : null}
        <Pressable onPress={capture} disabled={capturing} accessibilityRole="button"
                   accessibilityLabel={tr("cam.take")} style={({ pressed }) => [styles.shutter, { opacity: capturing || pressed ? 0.6 : 1 }]}>
          <View style={styles.shutterInner} />
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  pad: { padding: space(4) },
  preview: { width: "100%", aspectRatio: 4 / 3, borderRadius: radius, backgroundColor: "#222" },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: space(2) },
  chip: { minHeight: 44, paddingHorizontal: space(3), borderRadius: 22, borderWidth: 1, justifyContent: "center" },
  textarea: { minHeight: 80, borderWidth: 1, borderRadius: 10, padding: space(3), fontSize: 16, textAlignVertical: "top" },
  cameraBar: { position: "absolute", bottom: 0, left: 0, right: 0, alignItems: "center", paddingBottom: space(8), gap: space(3) },
  cameraHint: { color: "#fff", fontSize: 15, textAlign: "center", paddingHorizontal: space(6),
                textShadowColor: "rgba(0,0,0,0.7)", textShadowRadius: 4 },
  shutter: { width: 76, height: 76, borderRadius: 38, borderWidth: 4, borderColor: "#fff", alignItems: "center", justifyContent: "center" },
  shutterInner: { width: 58, height: 58, borderRadius: 29, backgroundColor: "#fff" },
});
