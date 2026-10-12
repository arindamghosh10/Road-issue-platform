// The citizen's language. Defaults to the phone's language when it's Hindi or Bengali,
// and can be changed on the sign-in screen or under My reports. The choice is kept on
// the phone only (it isn't personal data, and the server doesn't need it for the inbox).

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { Platform } from "react-native";
import { getLocales } from "expo-localization";
import * as SecureStore from "expo-secure-store";
import { DEFAULT_LOCALE, formatDate, isLocale, pickLocale, translator, type Locale, type T } from "./i18n";

const KEY = "roadwatch_language";

const store = {
  async get(): Promise<string | null> {
    if (Platform.OS === "web") {
      try { return globalThis.localStorage?.getItem(KEY) ?? null; } catch { return null; }
    }
    return SecureStore.getItemAsync(KEY);
  },
  async set(value: Locale): Promise<void> {
    if (Platform.OS === "web") {
      try { globalThis.localStorage?.setItem(KEY, value); } catch { /* storage unavailable */ }
      return;
    }
    await SecureStore.setItemAsync(KEY, value);
  },
};

function deviceLocale(): Locale {
  try { return pickLocale(getLocales().map((l) => l.languageCode)); } catch { return DEFAULT_LOCALE; }
}

type I18n = { locale: Locale; t: T; date: (iso: string) => string; setLocale: (l: Locale) => void };

const initialT = translator(DEFAULT_LOCALE);
const I18nContext = createContext<I18n>({
  locale: DEFAULT_LOCALE, t: initialT, date: (iso) => formatDate(DEFAULT_LOCALE, iso), setLocale: () => {},
});

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(deviceLocale);
  useEffect(() => {
    store.get().then((saved) => { if (isLocale(saved)) setLocaleState(saved); }).catch(() => {});
  }, []);
  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    store.set(l).catch(() => {});
  }, []);
  // Set during render (not in an effect): children's effects, like the push-token
  // registration in AuthProvider, run before this component's effects would.
  currentLocale = locale;
  const value = useMemo(() => {
    const t = translator(locale);
    return { locale, t, date: (iso: string) => formatDate(locale, iso), setLocale };
  }, [locale, setLocale]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export const useI18n = () => useContext(I18nContext);

// For code outside React (the push-token registration sends the language with it).
let currentLocale: Locale = DEFAULT_LOCALE;
export const getCurrentLocale = () => currentLocale;
