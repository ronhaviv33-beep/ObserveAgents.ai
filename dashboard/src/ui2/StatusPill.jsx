import { C, FONT } from "./tokens.js";

/** Neutral pill for environment / status / control-kind labels. */
export default function StatusPill({ children, tone = C.textDim }) {
  return (
    <span style={{
      display: "inline-block", background: `${tone}24`, color: tone, border: `1px solid ${tone}59`,
      fontSize: 10, fontFamily: FONT.mono, padding: "2px 9px", borderRadius: 999, whiteSpace: "nowrap",
    }}>{children}</span>
  );
}
