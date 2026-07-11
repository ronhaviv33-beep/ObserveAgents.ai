import { C, FONT, RADIUS } from "./tokens.js";

/** Empty view: one sentence about what would fill it + the action that will. */
export default function EmptyState({ icon = "◦", text, actionLabel, onAction }) {
  return (
    <div style={{
      border: `1px dashed ${C.borderStrong}`, borderRadius: RADIUS.lg, padding: "28px 26px",
      display: "flex", alignItems: "center", gap: 16, color: C.textDim, fontSize: 14, lineHeight: 1.6,
      background: C.surfaceRaised,
    }}>
      <span style={{
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        width: 40, height: 40, borderRadius: 999, background: C.surface,
        border: `1px solid ${C.border}`, fontSize: 18, color: C.textMute, flexShrink: 0,
      }}>{icon}</span>
      <span style={{ flex: 1 }}>{text}</span>
      {actionLabel && onAction && (
        <button onClick={onAction}
          style={{ background: C.accent, color: C.accentInk, border: `1px solid ${C.accent}`,
            borderRadius: RADIUS.sm, padding: "9px 16px", fontSize: 13, fontWeight: 600, fontFamily: FONT.ui, cursor: "pointer", whiteSpace: "nowrap" }}>
          {actionLabel}
        </button>
      )}
    </div>
  );
}
