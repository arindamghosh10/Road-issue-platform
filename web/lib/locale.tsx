"use client";

// The visitor's language, shared with every component. The server reads the cookie
// (or Accept-Language) and passes `initial`, so the first paint is already in the
// right language; changing it rewrites the cookie and re-renders in place.

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { makeFormat, type Format } from "./format";
import { DEFAULT_LOCALE, LOCALE_COOKIE, translator, type Locale, type T } from "./i18n";

type I18n = { locale: Locale; t: T; f: Format; setLocale: (l: Locale) => void };

const defaultT = translator(DEFAULT_LOCALE);
const I18nContext = createContext<I18n>({
  locale: DEFAULT_LOCALE, t: defaultT, f: makeFormat(DEFAULT_LOCALE, defaultT), setLocale: () => {},
});

export function I18nProvider({ initial, children }: { initial: Locale; children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(initial);
  const setLocale = useCallback((l: Locale) => {
    document.cookie = `${LOCALE_COOKIE}=${l}; path=/; max-age=31536000; samesite=lax`;
    document.documentElement.lang = l;
    setLocaleState(l);
  }, []);
  const value = useMemo(() => {
    const t = translator(locale);
    return { locale, t, f: makeFormat(locale, t), setLocale };
  }, [locale, setLocale]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export const useI18n = () => useContext(I18nContext);
