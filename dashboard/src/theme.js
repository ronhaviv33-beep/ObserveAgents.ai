// Design tokens — shared across all legacy components.
// Mirrors src/ui2/tokens.js ("night console / aurora signal" dark theme);
// keep the two in sync. Semantic colors are 400-level so they stay readable
// as text on the dark surfaces.
export const T = {
  bg: "#070A14", panel: "#0D1322", panelHi: "#141C31",
  border: "#1D2740", borderHi: "#31406B",
  text: "#E9EEF9", textDim: "#9AA9CB", textMute: "#5E6D90",
  textDisabled: "#46536F",
  accent: "#3BC7F0", accentDim: "#6FD6F7",
  ok: "#3DDC97",
  warn: "#F5C544", crit: "#FF4D6D", info: "#6FA8FF", purple: "#A78BFA",
  teal: "#2DD4BF", yellow: "#F5C544",
};
export const FONT_UI   = "'Inter','Geist',-apple-system,BlinkMacSystemFont,sans-serif";
export const FONT_MONO = "'JetBrains Mono','IBM Plex Mono',ui-monospace,SFMono-Regular,monospace";
