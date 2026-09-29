"use client";

import { useEffect, useState } from "react";

const VARS = ["--series-1", "--series-2", "--surface", "--ink", "--ink-2", "--muted", "--grid", "--axis"] as const;
export type ThemeColors = Record<(typeof VARS)[number], string>;

const LIGHT: ThemeColors = {
  "--series-1": "#2a78d6", "--series-2": "#eb6834", "--surface": "#fcfcfb", "--ink": "#0b0b0b",
  "--ink-2": "#52514e", "--muted": "#898781", "--grid": "#e1e0d9", "--axis": "#c3c2b7",
};

/** Resolve CSS colour tokens for SVG chart attributes (which can't read var()),
 * re-reading when the OS light/dark setting flips. */
export function useThemeColors(): ThemeColors {
  const [colors, setColors] = useState<ThemeColors>(LIGHT);
  useEffect(() => {
    const read = () => {
      const cs = getComputedStyle(document.documentElement);
      setColors(Object.fromEntries(VARS.map((v) => [v, cs.getPropertyValue(v).trim() || LIGHT[v]])) as ThemeColors);
    };
    read();
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", read);
    return () => mq.removeEventListener("change", read);
  }, []);
  return colors;
}
