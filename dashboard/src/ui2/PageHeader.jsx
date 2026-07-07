import { C, FONT } from "./tokens.js";

/** Page title + one-line purpose + optional right-side actions. */
export default function PageHeader({ title, purpose, children }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
      <div>
        <h2 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: C.text, letterSpacing: "-0.025em", fontFamily: FONT.ui }}>{title}</h2>
        {purpose && <div style={{ fontSize: 13, color: C.textDim, marginTop: 6, maxWidth: 640, lineHeight: 1.6 }}>{purpose}</div>}
      </div>
      {children && <div style={{ display: "flex", alignItems: "center", gap: 10 }}>{children}</div>}
    </div>
  );
}
