import { C, FONT } from "./tokens.js";

/**
 * ui2 Topbar — the desktop page header: page id + title on the left,
 * operational status chips on the right (viewing-org, guard mode, team,
 * range, demo, pricing age). Presentational only; hidden on mobile
 * (AppShell renders the fixed mobile bar instead).
 */
export default function Topbar({ pageId, pageLabel, isTablet, items = [], viewingOrg }) {
  // Desktop: sticky glass header band, full-bleed across <main>'s padding
  // (must mirror AppShell's desktop padding of 28px 36px).
  const band = isTablet
    ? { marginBottom: 18, paddingBottom: 12, borderBottom: `1px solid ${C.border}` }
    : {
        position: "sticky", top: 0, zIndex: 120,
        margin: "-28px -36px 28px", padding: "11px 36px",
        background: "rgba(7,10,20,0.78)", backdropFilter: "blur(14px)", WebkitBackdropFilter: "blur(14px)",
        borderBottom: `1px solid ${C.border}`,
      };
  // One slim row: "workspace ⟩ page" breadcrumb left, operational chips right.
  // The page's own PageHeader carries the big title — never repeated here.
  return (
    <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8, ...band }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span style={{ fontSize: 10, color: C.textMute, fontFamily: FONT.mono, letterSpacing: "0.14em", textTransform: "uppercase" }}>ObserveAgents</span>
        <span style={{ color: C.borderStrong, fontSize: 10 }}>⟩</span>
        <h1 style={{ fontSize: 13, fontWeight: 600, margin: 0, letterSpacing: "-0.01em", color: C.text, fontFamily: FONT.display }}>{pageLabel}</h1>
      </div>
      <div style={{ display: "flex", gap: 10, alignItems: "center", fontFamily: FONT.mono, fontSize: 11, color: C.textDim, flexWrap: "wrap" }}>
        {viewingOrg && (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 5, background: `${C.purple}1A`, border: `1px solid ${C.purple}4d`, color: C.purple, padding: "3px 9px", borderRadius: 999, fontSize: 10 }}>
            ◆ Viewing: {viewingOrg}
          </span>
        )}
        {items.map((it, i) => (
          <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
            {i > 0 && <span style={{ color: C.border }}>|</span>}
            <span title={it.title} style={{ color: it.color || C.textDim, display: "inline-flex", alignItems: "center", gap: 5 }}>
              {it.dot && "● "}{it.label}
            </span>
          </span>
        ))}
      </div>
    </header>
  );
}
