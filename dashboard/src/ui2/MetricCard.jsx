import { C, FONT, RADIUS, microLabel } from "./tokens.js";

/** Stat tile: micro label, big number, optional sub-line and click-through. */
export default function MetricCard({ label, value, sub, tone = C.text, onClick }) {
  return (
    <div onClick={onClick}
      style={{
        flex: 1, minWidth: 170, background: C.surface, border: `1px solid ${C.border}`,
        borderRadius: RADIUS.md, padding: "18px 20px", cursor: onClick ? "pointer" : "default",
        transition: "border-color .15s",
      }}
      onMouseEnter={(e) => { if (onClick) e.currentTarget.style.borderColor = C.borderStrong; }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = C.border; }}>
      <div style={{ ...microLabel, marginBottom: 12 }}>{label}</div>
      <div style={{ fontSize: 30, fontWeight: 700, color: tone, letterSpacing: "-0.03em", lineHeight: 1, fontFamily: FONT.ui }}>{value ?? "—"}</div>
      {sub && <div style={{ fontSize: 11, color: C.textMute, fontFamily: FONT.mono, marginTop: 9, lineHeight: 1.5 }}>{sub}</div>}
    </div>
  );
}
