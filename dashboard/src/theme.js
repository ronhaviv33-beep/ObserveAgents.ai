// Design tokens — shared across all components
// Dark-navy theme: page bg → card → raised surface step up in lightness so
// panels read against the page; text grays stay ≥ WCAG AA on every surface.
export const T = {
  bg: "#0B1020", panel: "#111827", panelHi: "#1E293B",
  border: "#334155", borderHi: "#475569",
  text: "#F8FAFC", textDim: "#CBD5E1", textMute: "#94A3B8",
  textDisabled: "#64748B",
  accent: "#38BDF8", accentDim: "#0EA5E9",
  ok: "#4ADE80",
  warn: "#FBBF24", crit: "#F87171", info: "#60A5FA", purple: "#A78BFA",
  teal: "#2DD4BF", yellow: "#FACC15",
};
export const FONT_UI   = "'Geist','Söhne',-apple-system,BlinkMacSystemFont,sans-serif";
export const FONT_MONO = "'JetBrains Mono','IBM Plex Mono',ui-monospace,SFMono-Regular,monospace";
