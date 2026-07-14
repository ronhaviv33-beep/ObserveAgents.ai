import { C, FONT, RADIUS, CARD, microLabel } from "./tokens.js";
import { Sparkline } from "./viz.jsx";

/**
 * Stat tile: micro label, big display numeral, optional sub-line, optional
 * sparkline (trend), optional delta chip, and click-through. The numeral is
 * set in the display face — the number IS the design.
 */
export default function MetricCard({ label, value, sub, tone = C.text, onClick, trend, trendColor, delta, deltaTone }) {
  return (
    <div onClick={onClick} className={onClick ? "oa-lift" : undefined}
      style={{
        ...CARD,
        flex: 1, minWidth: 172, borderRadius: RADIUS.lg, padding: "18px 20px 16px",
        cursor: onClick ? "pointer" : "default", position: "relative", overflow: "hidden",
      }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 12 }}>
        <div style={{ ...microLabel, fontSize: 10 }}>{label}</div>
        {delta != null && (
          <span style={{ fontSize: 10, fontFamily: FONT.mono, color: deltaTone || C.textMute, background: `${deltaTone || C.textMute}1A`, padding: "1px 7px", borderRadius: 999 }}>
            {delta}
          </span>
        )}
      </div>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 10 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 32, fontWeight: 700, color: tone, letterSpacing: "-0.03em", lineHeight: 1, fontFamily: FONT.display, fontVariantNumeric: "tabular-nums" }}>
            {value ?? "—"}
          </div>
          {sub && <div style={{ fontSize: 10.5, color: C.textMute, fontFamily: FONT.mono, marginTop: 9, lineHeight: 1.5 }}>{sub}</div>}
        </div>
        {trend && trend.length > 1 && (
          <div style={{ flexShrink: 0, marginBottom: sub ? 0 : 2 }}>
            <Sparkline data={trend} color={trendColor || (tone === C.text ? C.accent : tone)} width={92} height={30} />
          </div>
        )}
      </div>
    </div>
  );
}
