import { C, FONT, AURORA } from "./tokens.js";

/**
 * Page title + one-line purpose + optional right-side actions.
 * `eyebrow` renders a small-caps kicker above the title; the aurora tick to
 * its left is the signature mark carried through every page.
 */
export default function PageHeader({ title, purpose, eyebrow, children }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
      <div>
        {eyebrow && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span aria-hidden="true" style={{ width: 18, height: 3, borderRadius: 2, background: AURORA }} />
            <span style={{ fontSize: 10, fontFamily: FONT.mono, color: C.textMute, letterSpacing: "0.16em", textTransform: "uppercase" }}>{eyebrow}</span>
          </div>
        )}
        <h2 style={{ margin: 0, fontSize: 26, fontWeight: 700, color: C.text, letterSpacing: "-0.025em", fontFamily: FONT.display }}>{title}</h2>
        {purpose && <div style={{ fontSize: 13, color: C.textDim, marginTop: 7, maxWidth: 640, lineHeight: 1.65 }}>{purpose}</div>}
      </div>
      {children && <div style={{ display: "flex", alignItems: "center", gap: 10 }}>{children}</div>}
    </div>
  );
}
