import { FONT, riskColor } from "./tokens.js";

/** The one severity badge. Levels: critical | high | medium | low | info. */
export default function RiskBadge({ level }) {
  const color = riskColor(level);
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5, background: `${color}14`, color, border: `1px solid ${color}2E`,
      fontSize: 11, fontFamily: FONT.ui, fontWeight: 600, padding: "3px 9px", borderRadius: 999,
      letterSpacing: "0.02em", textTransform: "capitalize", whiteSpace: "nowrap",
    }}>
      <span style={{ width: 6, height: 6, borderRadius: 999, background: color, flexShrink: 0 }} />
      {level}
    </span>
  );
}
