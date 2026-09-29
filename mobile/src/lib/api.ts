// RoadWatch API client for the citizen app.
//
// The login token is kept in the phone's secure storage (Keychain / Android Keystore via
// expo-secure-store). It contains only the opaque reporter id — no phone number.

import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";
import type { ReportStatus, TicketStatus } from "./logic";

// EXPO_PUBLIC_* variables are inlined at build time. On a real phone this must be the
// computer's LAN address (e.g. http://192.168.1.20:8000), not localhost.
export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "roadwatch_citizen_token";

// Secure storage isn't available on web; fall back to localStorage there (dev/demo only).
export const tokenStore = {
  async get(): Promise<string | null> {
    if (Platform.OS === "web") {
      try { return globalThis.localStorage?.getItem(TOKEN_KEY) ?? null; } catch { return null; }
    }
    return SecureStore.getItemAsync(TOKEN_KEY);
  },
  async set(token: string | null): Promise<void> {
    if (Platform.OS === "web") {
      try {
        if (token) globalThis.localStorage?.setItem(TOKEN_KEY, token);
        else globalThis.localStorage?.removeItem(TOKEN_KEY);
      } catch { /* storage unavailable */ }
      return;
    }
    if (token) await SecureStore.setItemAsync(TOKEN_KEY, token);
    else await SecureStore.deleteItemAsync(TOKEN_KEY);
  },
};

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) { onUnauthorized = fn; }

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await tokenStore.get();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Can't reach RoadWatch. Check your internet connection.");
  }
  if (!res.ok) {
    let message = ""; // errorText() in i18n.ts turns this into a translated sentence
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch { /* not JSON */ }
    if (res.status === 401) { await tokenStore.set(null); onUnauthorized?.(); }
    throw new ApiError(res.status, message);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: body instanceof FormData ? body : JSON.stringify(body) });

// --- Types (mirror backend/app/api/citizen.py and views.py) ---------------------------

// `reason` is the server's English; `code` + `params` are translated in i18n.ts.
export interface Check { name: string; passed: boolean; reason: string; code?: string; params?: Record<string, unknown> }
export interface MyReport {
  id: string; status: ReportStatus; category: string; submitted_on: string;
  rejection_reason: string | null; rejection_code?: string | null; rejection_params?: Record<string, unknown>;
  ticket_ref: string | null; checks: Check[];
}
export interface Area { id: number; name: string; level: string }
export interface Ticket {
  ref: string; category: string; category_name: string; status: TicketStatus; severity: number;
  lat: number; lon: number; verified_reporters: number; report_count: number; also_seen: number;
  reported_on: string; sla_due_on: string | null; resolved_on: string | null;
  responsible_area: string | null; authority: string | null; areas: Area[]; photos: string[];
}
export interface NearbyTicket extends Ticket { distance_m: number; i_reported: boolean; i_saw: boolean }
export interface PendingConfirmation {
  ticket_ref: string; category: string; fix_submitted_on: string | null;
  fix_photos: string[]; my_answer: "yes" | "no" | "partly" | null;
}
export interface Notice {
  id: number; kind: string; title: string; body: string; ticket_ref: string | null;
  created_at: string; read: boolean; params?: Record<string, unknown>;
}

// --- Calls --------------------------------------------------------------------------------

export const api = {
  requestOtp: (phone: string) => post<{ challenge_id: string }>("/citizen/auth/otp/request", { phone }),
  verifyOtp: (challenge_id: string, code: string) =>
    post<{ access_token: string }>("/citizen/auth/otp/verify", { challenge_id, code }),

  submitReport: (form: FormData) => post<MyReport>("/citizen/reports", form),
  myReports: () => request<MyReport[]>("/citizen/reports"),
  myReport: (id: string) => request<MyReport>(`/citizen/reports/${encodeURIComponent(id)}`),

  nearby: (lat: number, lon: number, radius = 1500) =>
    request<NearbyTicket[]>(`/citizen/tickets/nearby?lat=${lat}&lon=${lon}&radius_m=${radius}`),
  iSeeThisToo: (ref: string, lat: number, lon: number, gps_accuracy_m: number) =>
    post<{ ticket_ref: string; also_seen: number }>(`/citizen/tickets/${encodeURIComponent(ref)}/seen`,
      { lat, lon, gps_accuracy_m }),
  ticket: (ref: string) => request<Ticket>(`/public/tickets/${encodeURIComponent(ref)}`),

  confirmations: () => request<PendingConfirmation[]>("/citizen/confirmations"),
  confirm: (ref: string, response: "yes" | "no" | "partly") =>
    post<{ ticket_ref: string; ticket_status: TicketStatus }>(
      `/citizen/tickets/${encodeURIComponent(ref)}/confirm`, { response }),
  notifications: () => request<Notice[]>("/citizen/notifications"),

  // Push token → identity vault (encrypted). See src/lib/push.ts.
  registerPushToken: (token: string, platform: "android" | "ios", lang: string) =>
    request<void>("/citizen/push-token", { method: "PUT", body: JSON.stringify({ token, platform, lang }) }),
  removePushToken: (token: string) => post<void>("/citizen/push-token/remove", { token }),
};

/** Attach a photo from the in-app camera to a multipart form. Native: file URI;
 * web (dev only): the camera returns a data URL, which is converted to a Blob. */
export async function appendPhoto(form: FormData, uri: string) {
  if (Platform.OS === "web") {
    const blob = await (await fetch(uri)).blob();
    form.append("photo", blob, "photo.jpg");
  } else {
    // React Native's FormData accepts {uri, name, type} for files.
    form.append("photo", { uri, name: "photo.jpg", type: "image/jpeg" } as unknown as Blob);
  }
}
