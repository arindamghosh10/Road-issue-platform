// Thin fetch wrapper around the RoadWatch API.
// The official's login token lives in localStorage (per-browser convenience). Every
// access is wrapped in try/catch because storage can be unavailable (private windows).

import type { Filters } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "roadwatch.gov.token";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function getToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: the session just won't persist */
  }
}

async function request<T>(path: string, init: RequestInit = {}, auth = false): Promise<T> {
  const headers = new Headers(init.headers);
  if (auth) {
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    if (res.status === 401 && auth) setToken(null);
    throw new ApiError(res.status, message);
  }
  const type = res.headers.get("content-type") ?? "";
  return (type.includes("application/json") ? res.json() : res.text()) as Promise<T>;
}

export const publicGet = <T>(path: string) => request<T>(`/api/v1/public${path}`);
export const govGet = <T>(path: string) => request<T>(`/api/v1/gov${path}`, {}, true);
export const govPost = <T>(path: string, body: unknown) =>
  request<T>(`/api/v1/gov${path}`, {
    method: "POST",
    body: body instanceof FormData ? body : JSON.stringify(body),
  }, true);

/** Query string for the dashboard filter row. */
export function filterQuery(f: Filters, extra: Record<string, string | number | null | undefined> = {}) {
  const params = new URLSearchParams();
  if (f.jurisdictionId != null) params.set("jurisdiction_id", String(f.jurisdictionId));
  if (f.category) params.set("category", f.category);
  if (f.days) params.set("days", String(f.days));
  for (const [k, v] of Object.entries(extra)) if (v != null && v !== "") params.set(k, String(v));
  const s = params.toString();
  return s ? `?${s}` : "";
}

/** Download the CSV export with the auth header (a plain link can't send it). */
export async function downloadCsv(f: Filters) {
  const res = await fetch(`${API_URL}/api/v1/gov/tickets/export.csv${filterQuery({ ...f, days: null })}`, {
    headers: { Authorization: `Bearer ${getToken() ?? ""}` },
  });
  if (!res.ok) throw new ApiError(res.status, "Export failed");
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = "roadwatch-tickets.csv";
  a.click();
  URL.revokeObjectURL(url);
}
