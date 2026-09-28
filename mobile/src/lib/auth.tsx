import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { setUnauthorizedHandler, tokenStore } from "./api";

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

  const signIn = useCallback(async (token: string) => {
    await tokenStore.set(token);
    setSignedIn(true);
  }, []);
  const signOut = useCallback(async () => {
    await tokenStore.set(null);
    setSignedIn(false);
  }, []);

  return <AuthContext.Provider value={{ ready, signedIn, signIn, signOut }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
