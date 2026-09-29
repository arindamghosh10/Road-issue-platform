// Push notifications ("you have an update") for the citizen app.
//
// Privacy: the push token goes to RoadWatch's identity vault only (encrypted, never
// stored with reports), and pushes never carry details — just "open the app". The
// details are in the Inbox, fetched over our own signed-in API. So Expo / Google /
// Apple, who relay pushes, never learn which issue this phone reported.
//
// Remote push needs a development or store build (not Expo Go) and an EAS project id
// (app.json → extra.eas.projectId). Without them, this quietly does nothing.

import { useEffect } from "react";
import { Platform } from "react-native";
import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import * as SecureStore from "expo-secure-store";
import { router } from "expo-router";
import { api } from "./api";
import { getCurrentLocale } from "./locale";

const PUSH_TOKEN_KEY = "roadwatch_push_token";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true, shouldShowList: true, shouldPlaySound: false, shouldSetBadge: false,
  }),
});

/** Ask for permission and register this phone for pushes. Safe to call on every launch. */
export async function registerForPush(): Promise<void> {
  try {
    if (!Device.isDevice) return; // simulators can't receive remote pushes
    if (Platform.OS === "android") {
      await Notifications.setNotificationChannelAsync("default", {
        name: "Updates on your reports",
        importance: Notifications.AndroidImportance.DEFAULT,
      });
    }
    let { status } = await Notifications.getPermissionsAsync();
    if (status !== "granted") ({ status } = await Notifications.requestPermissionsAsync());
    if (status !== "granted") return; // the Inbox still works without pushes

    const projectId = Constants.easConfig?.projectId ?? Constants.expoConfig?.extra?.eas?.projectId;
    if (!projectId) return;
    const { data: token } = await Notifications.getExpoPushTokenAsync({ projectId });
    // The language only picks the push text ("you have an update") in Hindi/Bengali/English.
    await api.registerPushToken(token, Platform.OS === "ios" ? "ios" : "android", getCurrentLocale());
    await SecureStore.setItemAsync(PUSH_TOKEN_KEY, token);
  } catch {
    // Offline, no Play Services, Expo Go, … — pushes are a convenience, never a blocker.
  }
}

/** Stop pushes to this phone. Call BEFORE the login token is cleared. */
export async function unregisterPush(): Promise<void> {
  try {
    const token = await SecureStore.getItemAsync(PUSH_TOKEN_KEY);
    if (!token) return;
    await SecureStore.deleteItemAsync(PUSH_TOKEN_KEY);
    await api.removePushToken(token);
  } catch {
    // If this fails the server stops using the token once Expo reports it dead.
  }
}

/** Tapping a push opens the Inbox; a new push token (rare) is re-registered. */
export function usePushHandlers(signedIn: boolean) {
  const response = Notifications.useLastNotificationResponse();
  useEffect(() => {
    if (!signedIn || !response) return;
    if (response.notification.request.content.data?.screen === "inbox") router.push("/inbox");
    Notifications.clearLastNotificationResponse();
  }, [signedIn, response]);

  useEffect(() => {
    if (!signedIn) return;
    const sub = Notifications.addPushTokenListener(() => { registerForPush(); });
    return () => sub.remove();
  }, [signedIn]);
}
