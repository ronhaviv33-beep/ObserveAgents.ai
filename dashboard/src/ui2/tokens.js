// ui2 design tokens — the new design system's single source of visual truth.
// Semantic names only: components never hardcode hex values. Dark is the
// default theme; a future light theme swaps the values in `dark` below
// without touching any component.

const dark = {
  // surfaces
  bg:            "#08090D",
  surface:       "#0E1016",
  surfaceRaised: "#141824",
  surfaceHover:  "#181D2B",
  border:        "#1E2331",
  borderStrong:  "#2B3244",

  // text
  text:     "#E9EDF5",
  textDim:  "#8A93A8",
  textMute: "#525B70",

  // brand + semantic
  accent:      "#7CFFB2",
  accentInk:   "#00160B",   // text on accent fills
  riskCritical:"#FF4D6E",
  riskHigh:    "#FF5C7A",
  riskMedium:  "#FFB547",
  riskLow:     "#6FA8FF",
  riskInfo:    "#8A93A8",
  purple:      "#B47AFF",
  teal:        "#5FD4C4",
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
