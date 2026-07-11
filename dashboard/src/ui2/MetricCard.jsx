import { C, FONT, RADIUS, SHADOW } from "./tokens.js";

/** Stat tile: micro label, big number, optional sub-line and click-through. */
export default function MetricCard({ label, value, sub, tone = C.text, onClick }) {
  return (
    <div onClick={onClick}
      style={{
        flex: 1, minWidth: 170, background: C.surface, border: `1px solid ${C.border}`,
        borderRadius: RADIUS.lg, padding: "20px 22px", cursor: onClick ? "pointer" : "default",
        boxShadow: SHADOW.sm,
        transition: "box-shadow .18s ease, border-color .18s ease, transform .18s ease",
      }}
      onMouseEnter={(e) => { if (onClick) { e.currentTarget.style.borderColor = C.borderStrong; e.currentTarget.style.boxShadow = SHADOW.hover; e.currentTarget.style.transform = "translateY(-1px)"; } }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = C.border; e.currentTarget.style.boxShadow = SHADOW.sm; e.currentTarget.style.transform = "none"; }}>
      <div style={{ fontSize: 12.5, fontFamily: FONT.ui, fontWeight: 500, color: C.textDim, marginBottom: 12 }}>{label}</div>
      <div style={{ fontSize: 32, fontWeight: 650, color: tone, letterSpacing: "-0.03em", lineHeight: 1, fontFamily: FONT.ui, fontVariantNumeric: "tabular-nums" }}>{value ?? "—"}</div>
      {sub && <div style={{ fontSize: 12.5, color: C.textMute, fontFamily: FONT.ui, marginTop: 10, lineHeight: 1.5 }}>{sub}</div>}
    </div>
  );
}
