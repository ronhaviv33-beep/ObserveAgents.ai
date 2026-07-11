// Design tokens — shared across all components
// Light-first SaaS theme: soft slate page bg, white cards, slate borders,
// dark readable text; brand blue accent. Semantic colors are 600-level so
// they stay readable as text on white surfaces.
export const T = {
  bg: "#F7F8FA", panel: "#FFFFFF", panelHi: "#F4F6F9",
  border: "#E9EDF2", borderHi: "#D6DDE6",
  text: "#0B1220", textDim: "#4A5568", textMute: "#7A889B",
  textDisabled: "#A6B1C0",
  accent: "#2563EB", accentDim: "#1D4ED8",
  ok: "#15925A",
  warn: "#C2740A", crit: "#DC2626", info: "#0E7490", purple: "#4F46E5",
  teal: "#0D9488", yellow: "#B45309",
  // Layered soft shadows for premium card depth.
  shadow: "0 1px 2px rgba(11,18,32,0.04), 0 1px 3px rgba(11,18,32,0.03)",
  shadowHover: "0 4px 14px rgba(11,18,32,0.08), 0 2px 6px rgba(11,18,32,0.04)",
};
// Single clean sans across the whole product (executive SaaS feel). The
// "mono" slot intentionally maps to the same family so legacy monospace
// usages read as premium sans; genuine code blocks opt into FONT_CODE.
export const FONT_UI   = "'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif";
export const FONT_MONO = "'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif";
export const FONT_CODE = "'JetBrains Mono','IBM Plex Mono',ui-monospace,SFMono-Regular,monospace";
