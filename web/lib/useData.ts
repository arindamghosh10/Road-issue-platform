"use client";

import { useEffect, useState } from "react";

/** Fetch on mount / when `key` changes. Keeps the previous data while reloading, so
 * charts hold their frame instead of flashing (dataviz: refetch keeps the frame). */
export function useData<T>(key: string | null, load: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (key === null) return;
    let cancelled = false;
    setLoading(true);
    load()
      .then((d) => { if (!cancelled) { setData(d); setError(null); } })
      .catch((e: Error) => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return { data, error, loading, setData };
}
