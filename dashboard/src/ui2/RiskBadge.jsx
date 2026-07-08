import { FONT, riskColor } from "./tokens.js";

/** The one severity badge. Levels: critical | high | medium | low | info. */
export default function RiskBadge({ level }) {
  const color = riskColor(level);
  return (
    <span style={{
      display: "inline-block", background: `${color}24`, color, border: `1px solid ${color}59`,
      fontSize: 10, fontFamily: FONT.mono, padding: "2px 9px", borderRadius: 4,
      letterSpacing: "0.06em", textTransform: "uppercase", whiteSpace: "nowrap",
    }}>{level}</span>
  );
}
