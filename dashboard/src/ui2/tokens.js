// ui2 design tokens — the new design system's single source of visual truth.
// Semantic names only: components never hardcode hex values. Light is the
// default theme; a future dark theme swaps the values in `light` below
// without touching any component.

const light = {
  // surfaces — light SaaS ramp: soft slate page bg, white cards, and a
  // slightly tinted raised/soft surface for headers and insets.
  bg:            "#F8FAFC",
  surface:       "#FFFFFF",
  surfaceRaised: "#F1F5F9",
  surfaceHover:  "#EEF2F7",
  border:        "#E2E8F0",
  borderStrong:  "#CBD5E1",

  // text — dark, readable tiers on every surface above.
  text:     "#0F172A",
  textDim:  "#475569",
  textMute: "#64748B",

  // brand + semantic
  accent:      "#2563EB",
  accentInk:   "#FFFFFF",   // text on accent fills
  accentSoft:  "#EFF6FF",   // active nav / selected-row wash
  accentDark:  "#1D4ED8",   // text on accentSoft
  riskCritical:"#DC2626",
  riskHigh:    "#EA580C",
  riskMedium:  "#D97706",
  riskLow:     "#0891B2",
  riskInfo:    "#64748B",
  purple:      "#7C3AED",
  teal:        "#0D9488",
};

export const C = light;

export const FONT = {
  ui:   "'Geist','Söhne',-apple-system,'Segoe UI',sans-serif",
  mono: "'JetBrains Mono','IBM Plex Mono',monospace",
};

export const RADIUS = { sm: 8, md: 12, lg: 16 };

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
