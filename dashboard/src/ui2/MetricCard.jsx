import { C, FONT, RADIUS, CARD, microLabel } from "./tokens.js";
import { Sparkline } from "./viz.jsx";

/**
 * Stat tile: micro label, big display numeral, optional sub-line, optional
 * sparkline (trend), optional delta chip, and click-through. The numeral is
 * set in the display face — the number IS the design.
 */
export default function MetricCard({ label, value, sub, tone = C.text, onClick, trend, trendColor, delta, deltaTone }) {
  // Long text values (service/request names) scale down and wrap instead of
  // overflowing the tile; short numerals keep the full display size.
  const text = value == null ? "—" : String(value);
  const valueSize = text.length > 26 ? 16.5 : text.length > 18 ? 19 : text.length > 12 ? 24 : 32;
  const isLongText = text.length > 12;
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
          <div style={{ fontSize: valueSize, fontWeight: 700, color: tone, letterSpacing: "-0.03em", lineHeight: isLongText ? 1.25 : 1, fontFamily: FONT.display, fontVariantNumeric: "tabular-nums", overflowWrap: "break-word" }}>
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
