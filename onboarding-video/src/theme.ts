import { loadFont as loadDisplay } from "@remotion/google-fonts/SpaceGrotesk";
import { loadFont as loadUi } from "@remotion/google-fonts/Inter";
import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";

const { fontFamily: displayFont } = loadDisplay();
const { fontFamily: uiFont } = loadUi();
const { fontFamily: monoFont } = loadMono();

// "Night console / aurora signal" — mirrors dashboard/src/ui2/tokens.js.
// Two brand hues: signal cyan (telemetry in) and aurora violet (control out).
export const theme = {
  bg: "#070A14",
  bgVoid: "#04060D",
  surface: "#0D1322",
  surfaceRaised: "#141C31",
  surfaceHover: "#1A2440",
  border: "#1D2740",
  borderStrong: "#31406B",

  text: "#E9EEF9",
  textDim: "#9AA9CB",
  textMute: "#5E6D90",

  accent: "#3BC7F0",
  accentInk: "#04121D",
  accentSoft: "#0E2338",
  accentDark: "#6FD6F7",
  violet: "#8E7BFF",
  purple: "#A78BFA",
  teal: "#2DD4BF",
  ok: "#3DDC97",

  riskCritical: "#FF4D6D",
  riskHigh: "#FF8A4C",
  riskMedium: "#F5C544",
  riskLow: "#6FA8FF",

  // legacy aliases used across scene files
  orange: "#FF8A4C",
  orangeBright: "#FF8A4C",
  orangeSoft: "rgba(255, 138, 76, 0.16)",
  orangeFaint: "rgba(255, 138, 76, 0.1)",
  blue: "#3BC7F0",
  blueSoft: "rgba(59, 199, 240, 0.16)",
  blueFaint: "rgba(59, 199, 240, 0.1)",
  purpleSoft: "rgba(142, 123, 255, 0.18)",
  tealSoft: "rgba(45, 212, 191, 0.16)",
  slate: "#9AA9CB",
  slateSoft: "#141C31",
  textSoft: "#9AA9CB",
  textFaint: "#5E6D90",

  radiusSm: 8,
  radiusMd: 12,
  radiusLg: 16,

  mono: monoFont,
  sans: uiFont,
  display: displayFont,
};

export const uiEase = [0.16, 1, 0.3, 1] as const;
