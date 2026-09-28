// Colour tokens, same palette as the web dashboards (validated for colour-blind
// separation and contrast in both modes). Status colours are reserved for status.

import { useColorScheme } from "react-native";

const light = {
  page: "#f9f9f7", surface: "#fcfcfb", surface2: "#f3f2ee", ink: "#0b0b0b", ink2: "#52514e",
  muted: "#898781", border: "rgba(11,11,11,0.10)", grid: "#e1e0d9", accent: "#2a78d6",
  accentInk: "#1c5cab", accentWash: "#cde2fb", onAccent: "#ffffff", danger: "#b3261e", good: "#006300",
};
const dark: typeof light = {
  page: "#0d0d0d", surface: "#1a1a19", surface2: "#232322", ink: "#ffffff", ink2: "#c3c2b7",
  muted: "#898781", border: "rgba(255,255,255,0.10)", grid: "#2c2c2a", accent: "#3987e5",
  accentInk: "#86b6ef", accentWash: "#104281", onAccent: "#ffffff", danger: "#e66767", good: "#0ca30c",
};

export type Theme = typeof light;
export function useTheme(): Theme {
  return useColorScheme() === "dark" ? dark : light;
}

export const radius = 12;
export const space = (n: number) => n * 4;
