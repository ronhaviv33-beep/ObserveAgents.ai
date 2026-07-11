// ui2 design tokens — the new design system's single source of visual truth.
// Semantic names only: components never hardcode hex values. Light is the
// default theme; a future dark theme swaps the values in `light` below
// without touching any component.

const light = {
  // surfaces — light SaaS ramp: soft slate page bg, white cards, and a
  // slightly tinted raised/soft surface for headers and insets.
  bg:            "#F7F8FA",
  surface:       "#FFFFFF",
  surfaceRaised: "#F4F6F9",
  surfaceHover:  "#EFF2F6",
  border:        "#E9EDF2",
  borderStrong:  "#D6DDE6",

  // text — dark, readable tiers on every surface above.
  text:     "#0B1220",
  textDim:  "#4A5568",
  textMute: "#7A889B",

  // brand + semantic
  accent:      "#2563EB",
  accentInk:   "#FFFFFF",   // text on accent fills
  accentSoft:  "#EFF4FF",   // active nav / selected-row wash
  accentDark:  "#1D4ED8",   // text on accentSoft
  indigo:      "#4F46E5",   // secondary accent
  indigoSoft:  "#EEF0FF",
  riskCritical:"#DC2626",
  riskHigh:    "#EA580C",
  riskMedium:  "#C2740A",
  riskLow:     "#0E7490",
  riskInfo:    "#7A889B",
  purple:      "#4F46E5",
  teal:        "#0D9488",
  ok:          "#15925A",
};

export const C = light;

export const FONT = {
  ui:   "'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif",
  mono: "'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif",
  code: "'JetBrains Mono','IBM Plex Mono',ui-monospace,monospace",
};

export const RADIUS = { sm: 8, md: 12, lg: 16, xl: 20 };

// Layered, low-opacity shadows for premium card depth (Stripe/Linear feel).
export const SHADOW = {
  sm:    "0 1px 2px rgba(11,18,32,0.04), 0 1px 3px rgba(11,18,32,0.03)",
  md:    "0 2px 8px rgba(11,18,32,0.05), 0 1px 3px rgba(11,18,32,0.04)",
  hover: "0 6px 20px rgba(11,18,32,0.08), 0 2px 8px rgba(11,18,32,0.05)",
  focus: "0 0 0 3px rgba(37,99,235,0.15)",
};

/** Risk level → color. The only place severity maps to color in ui2. */
export const riskColor = (level) => ({
  critical: C.riskCritical,
  high:     C.riskHigh,
  medium:   C.riskMedium,
  low:      C.riskLow,
  info:     C.riskInfo,
}[level] || C.riskInfo);

/** Small-caps label style used for section/card headers. */
export const microLabel = {
  fontSize: 11,
  fontFamily: FONT.ui,
  fontWeight: 600,
  color: C.textMute,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
};
