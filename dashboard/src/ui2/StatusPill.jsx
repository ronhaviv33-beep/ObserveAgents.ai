import { C, FONT } from "./tokens.js";

/** Neutral pill for environment / status / control-kind labels. */
export default function StatusPill({ children, tone = C.textDim }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", background: `${tone}14`, color: tone, border: `1px solid ${tone}2E`,
      fontSize: 11.5, fontWeight: 600, fontFamily: FONT.ui, padding: "3px 10px", borderRadius: 999, whiteSpace: "nowrap",
    }}>{children}</span>
  );
}
