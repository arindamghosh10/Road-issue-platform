import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { setUnauthorizedHandler, tokenStore } from "./api";
import { useI18n } from "./locale";
import { registerForPush, unregisterPush, usePushHandlers } from "./push";

type AuthState = { ready: boolean; signedIn: boolean; signIn: (token: string) => Promise<void>; signOut: () => Promise<void> };

const AuthContext = createContext<AuthState>({
  ready: false, signedIn: false, signIn: async () => {}, signOut: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    tokenStore.get().then((t) => { setSignedIn(!!t); setReady(true); });
    setUnauthorizedHandler(() => setSignedIn(false));
  }, []);

  // Signed in (fresh or on launch), or language changed → (re-)register this phone for
  // "you have an update" pushes, in the app's language.
  const { locale } = useI18n();
  useEffect(() => { if (signedIn) registerForPush(); }, [signedIn, locale]);
  usePushHandlers(signedIn);

  const signIn = useCallback(async (token: string) => {
    await tokenStore.set(token);
    setSignedIn(true);
  }, []);
  const signOut = useCallback(async () => {
    await unregisterPush(); // needs the login token, so before clearing it
    await tokenStore.set(null);
    setSignedIn(false);
  }, []);

  return <AuthContext.Provider value={{ ready, signedIn, signIn, signOut }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
