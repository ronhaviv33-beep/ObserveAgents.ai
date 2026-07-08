// ui2 design tokens — the new design system's single source of visual truth.
// Semantic names only: components never hardcode hex values. Dark is the
// default theme; a future light theme swaps the values in `dark` below
// without touching any component.

const dark = {
  // surfaces — dark navy ramp: page bg → card → raised → hover, each one
  // step lighter so panels and rows separate without heavy borders.
  bg:            "#0B1020",
  surface:       "#111827",
  surfaceRaised: "#1E293B",
  surfaceHover:  "#253349",
  border:        "#334155",
  borderStrong:  "#475569",

  // text — every tier stays readable on all surfaces above.
  text:     "#F8FAFC",
  textDim:  "#CBD5E1",
  textMute: "#94A3B8",

  // brand + semantic
  accent:      "#38BDF8",
  accentInk:   "#06121F",   // text on accent fills
  riskCritical:"#F87171",
  riskHigh:    "#FB923C",
  riskMedium:  "#FBBF24",
  riskLow:     "#60A5FA",
  riskInfo:    "#94A3B8",
  purple:      "#A78BFA",
  teal:        "#2DD4BF",
};

export const C = dark;

export const FONT = {
  ui:   "'Geist','Söhne',-apple-system,'Segoe UI',sans-serif",
  mono: "'JetBrains Mono','IBM Plex Mono',monospace",
};

export const RADIUS = { sm: 6, md: 10, lg: 14 };

/** Risk level → color. The only place severity maps to color in ui2. */
export const riskColor = (level) => ({
  critical: C.riskCritical,
  high:     C.riskHigh,
  medium:   C.riskMedium,
  low:      C.riskLow,
  info:     C.riskInfo,
}[level] || C.riskInfo);

/** Uppercase mono micro-label style used for section/card headers. */
export const microLabel = {
  fontSize: 9.5,
  fontFamily: FONT.mono,
  color: C.textMute,
  letterSpacing: "0.14em",
  textTransform: "uppercase",
};
