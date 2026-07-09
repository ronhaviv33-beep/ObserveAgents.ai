import { C, FONT } from "./tokens.js";

/**
 * ui2 Topbar — the desktop page header: page id + title on the left,
 * operational status chips on the right (viewing-org, guard mode, team,
 * range, demo, pricing age). Presentational only; hidden on mobile
 * (AppShell renders the fixed mobile bar instead).
 */
export default function Topbar({ pageId, pageLabel, isTablet, items = [], viewingOrg }) {
  // Desktop: sticky translucent header band, full-bleed across <main>'s
  // padding (must mirror AppShell's desktop padding of 28px 36px).
  const band = isTablet
    ? { marginBottom: 18, paddingBottom: 12, borderBottom: `1px solid ${C.border}` }
    : {
        position: "sticky", top: 0, zIndex: 120,
        margin: "-28px -36px 28px", padding: "14px 36px",
        background: "rgba(255,255,255,0.86)", backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)",
        borderBottom: `1px solid ${C.border}`,
      };
  return (
    <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8, ...band }}>
      <div>
        <div style={{ fontSize: 10.5, color: C.textMute, fontFamily: FONT.ui, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase" }}>{pageId}</div>
        <h1 style={{ fontSize: isTablet ? 18 : 21, fontWeight: 600, margin: "3px 0 0", letterSpacing: "-0.02em", color: C.text }}>{pageLabel}</h1>
      </div>
      <div style={{ display: "flex", gap: 10, alignItems: "center", fontFamily: FONT.mono, fontSize: 11, color: C.textDim, flexWrap: "wrap" }}>
        {viewingOrg && (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 5, background: `${C.purple}1f`, border: `1px solid ${C.purple}4d`, color: C.purple, padding: "3px 9px", borderRadius: 4, fontSize: 10 }}>
            ◆ Viewing: {viewingOrg}
          </span>
        )}
        {items.map((it, i) => (
          <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
            {i > 0 && <span style={{ color: C.textMute }}>|</span>}
            <span title={it.title} style={{ color: it.color || C.textDim, display: "inline-flex", alignItems: "center", gap: 5 }}>
              {it.dot && "● "}{it.label}
            </span>
          </span>
        ))}
      </div>
    </header>
  );
}
