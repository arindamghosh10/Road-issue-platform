"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, getToken, govGet, setToken } from "./api";
import type { Me } from "./types";

const PASSWORD_PAGE = "/gov/password";

/** The signed-in official, or a redirect: to sign-in if there's no session, or to the
 * password page while an admin-issued temporary password is still in use. */
export function useOfficial() {
  const router = useRouter();
  const path = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  useEffect(() => {
    if (!getToken()) {
      router.replace("/gov/login");
      return;
    }
    govGet<Me>("/me")
      .then((m) => {
        if (m.must_change_password && path !== PASSWORD_PAGE) router.replace(PASSWORD_PAGE);
        else setMe(m);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) router.replace("/gov/login");
      });
  }, [router, path]);
  const logout = () => {
    setToken(null);
    router.replace("/gov/login");
  };
  return { me, logout };
}

/** Where an official lands after signing in. */
export function homeFor(me: Me): string {
  if (me.must_change_password) return PASSWORD_PAGE;
  return me.role === "platform_admin" ? "/admin" : "/gov";
}
