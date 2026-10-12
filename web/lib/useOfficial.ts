"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, getToken, govGet, setToken } from "./api";
import type { Me } from "./types";

/** The signed-in official, or a redirect to the sign-in page. */
export function useOfficial() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  useEffect(() => {
    if (!getToken()) {
      router.replace("/gov/login");
      return;
    }
    govGet<Me>("/me")
      .then(setMe)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) router.replace("/gov/login");
      });
  }, [router]);
  const logout = () => {
    setToken(null);
    router.replace("/gov/login");
  };
  return { me, logout };
}
