import { C, FONT } from "./tokens.js";

/**
 * ui2 Topbar — the desktop page header: page id + title on the left,
 * operational status chips on the right (viewing-org, guard mode, team,
 * range, demo, pricing age). Presentational only; hidden on mobile
 * (AppShell renders the fixed mobile bar instead).
 */
export default function Topbar({ pageId, pageLabel, isTablet, items = [], viewingOrg }) {
  return (
    <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18, flexWrap: "wrap", gap: 8 }}>
      <div>
        <div style={{ fontSize: 11, color: C.textMute, fontFamily: FONT.mono, letterSpacing: "0.12em", textTransform: "uppercase" }}>{pageId}</div>
        <h1 style={{ fontSize: isTablet ? 18 : 22, fontWeight: 500, margin: "4px 0 0", letterSpacing: "-0.015em", color: C.text }}>{pageLabel}</h1>
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
