// ui2 design tokens — the design system's single source of visual truth.
//
// "Night console / aurora signal": a deep indigo-black console where runtime
// evidence reads as light. Two brand hues — signal cyan (telemetry in) and
// aurora violet (control out) — form the gradient that carries the product's
// evidence-chain story. Severity stays on its own disciplined warm ramp and
// never borrows brand color.
//
// Semantic names only: components never hardcode hex values. Every value is a
// 6-digit hex so callers can append alpha (`${C.accent}22`).

const night = {
  // surfaces — layered elevation ramp, all with a cold indigo cast.
  bg:            "#070A14",   // page void
  surface:       "#0D1322",   // cards
  surfaceRaised: "#141C31",   // insets, table headers, chips
  surfaceHover:  "#1A2440",   // hover wash
  border:        "#1D2740",   // hairline on surface
  borderStrong:  "#31406B",   // focus/hover hairline

  // text — cool readable tiers on every surface above.
  text:     "#E9EEF9",
  textDim:  "#9AA9CB",
  textMute: "#5E6D90",

  // brand — signal cyan in, aurora violet out.
  accent:      "#3BC7F0",   // signal cyan (interactive, live telemetry)
  accentInk:   "#04121D",   // text on accent fills
  accentSoft:  "#0E2338",   // active nav / selected-row wash
  accentDark:  "#6FD6F7",   // "accent-as-text" on soft washes (dark theme: brighter)
  violet:      "#8E7BFF",   // aurora violet (control, secondary series)
  purple:      "#A78BFA",   // platform-admin & tertiary accents
  teal:        "#2DD4BF",
  ok:          "#3DDC97",

  // severity — disciplined warm ramp, 400-level so it reads on dark.
  riskCritical:"#FF4D6D",
  riskHigh:    "#FF8A4C",
  riskMedium:  "#F5C544",
  riskLow:     "#6FA8FF",
  riskInfo:    "#8494B7",
};

export const C = night;

// The aurora — the signature gradient. Use sparingly: brand mark, active-nav
// indicator, hero keylines, primary CTA. One memorable thing, kept scarce.
export const AURORA = "linear-gradient(90deg, #3BC7F0 0%, #7B8CFF 55%, #B07BFF 100%)";
export const AURORA_SOFT =
  "linear-gradient(90deg, rgba(59,199,240,0.16) 0%, rgba(123,140,255,0.16) 55%, rgba(176,123,255,0.16) 100%)";

export const FONT = {
  display: "'Space Grotesk','Geist',-apple-system,'Segoe UI',sans-serif", // titles + big numerals
  ui:   "'Inter','Geist',-apple-system,'Segoe UI',sans-serif",
  mono: "'JetBrains Mono','IBM Plex Mono',ui-monospace,monospace",
};

export const RADIUS = { sm: 8, md: 12, lg: 16 };

// Card shell — the one card recipe. Spread into style objects.
export const CARD = {
  background: C.surface,
  border: `1px solid ${C.border}`,
  borderRadius: RADIUS.md,
  boxShadow: "0 1px 0 rgba(255,255,255,0.03) inset, 0 10px 30px rgba(2,4,12,0.45)",
};

// Recharts helpers — dark tooltip + axis tick, shared by every chart.
export const TOOLTIP = {
  background: "#101830",
  border: `1px solid ${C.borderStrong}`,
  borderRadius: 10,
  boxShadow: "0 12px 32px rgba(2,4,12,0.6)",
  fontFamily: FONT.mono,
  fontSize: 11,
  color: C.text,
};
export const TICK = { fill: C.textMute, fontSize: 9.5, fontFamily: FONT.mono };

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
  fontFamily: FONT.mono,
  fontWeight: 500,
  color: C.textMute,
  letterSpacing: "0.08em",
  textTransform: "uppercase",
};
