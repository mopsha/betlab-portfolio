/** The app's looks (Oct 12, the second account's first suggestions: "customizable themes, pink/black,
 *  gold/black" and "a better font"). Each is a cookie, so the first paint is already right; the colors
 *  live in globals.css as `:root[data-theme=...]` tokens and the fonts as `html[data-font=...]`. */

export const THEMES = [
  { id: "system", label: "Device", bg: "", accent: "" },
  { id: "light", label: "Light", bg: "#f4f5f7", accent: "#2f4fd8" },
  { id: "dark", label: "Dark", bg: "#0d0f13", accent: "#8ea2ff" },
  { id: "pink", label: "Pink", bg: "#0c0a0c", accent: "#ff5fa8" },
  { id: "gold", label: "Gold", bg: "#0b0a08", accent: "#e2b84a" },
  { id: "purple", label: "Purple", bg: "#0d0b12", accent: "#b18cff" },
  { id: "rose", label: "Rose", bg: "#fbf3f6", accent: "#d6337f" },
  // the iPhone's own (Oct 24, ios/BetLab/Design/Theme.swift)
  { id: "ocean", label: "Ocean", bg: "#06131f", accent: "#38bdf8" },
  { id: "forest", label: "Forest", bg: "#07120b", accent: "#4ade80" },
  { id: "crimson", label: "Crimson", bg: "#120608", accent: "#f43f5e" },
  { id: "sunset", label: "Sunset", bg: "#140a06", accent: "#fb923c" },
  { id: "neon", label: "Neon", bg: "#050505", accent: "#39ff14" },
  { id: "cyber", label: "Cyber", bg: "#0a0614", accent: "#f0abfc" },
  { id: "slate", label: "Slate", bg: "#0f1115", accent: "#94a3b8" },
  { id: "coffee", label: "Coffee", bg: "#120d09", accent: "#d4a373" },
  { id: "mint", label: "Mint", bg: "#eefaf5", accent: "#0f9d78" },
  { id: "sky", label: "Sky", bg: "#eef4ff", accent: "#2563eb" },
  { id: "lavender", label: "Lavender", bg: "#f4f0ff", accent: "#7c3aed" },
  { id: "peach", label: "Peach", bg: "#fff4ec", accent: "#ea580c" },
  { id: "lemon", label: "Lemon", bg: "#fffbe6", accent: "#ca8a04" },
  { id: "paper", label: "Paper", bg: "#f5f3ee", accent: "#111827" },
] as const;
export type ThemeId = (typeof THEMES)[number]["id"];

export const FONTS = [
  { id: "classic", label: "Classic", css: "var(--font-public)" },
  { id: "modern", label: "Modern", css: "var(--font-inter)" },
  { id: "rounded", label: "Rounded", css: "var(--font-nunito)" },
  { id: "sleek", label: "Sleek", css: "var(--font-manrope)" },
] as const;
export type FontId = (typeof FONTS)[number]["id"];

export const themeOf = (v: string | undefined): ThemeId | undefined =>
  THEMES.some((t) => t.id === v && v !== "system") ? (v as ThemeId) : undefined;
export const fontOf = (v: string | undefined): FontId | undefined =>
  FONTS.some((f) => f.id === v && v !== "classic") ? (v as FontId) : undefined;
