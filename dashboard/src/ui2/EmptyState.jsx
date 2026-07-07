import { C, FONT, RADIUS } from "./tokens.js";

/** Empty view: one sentence about what would fill it + the action that will. */
export default function EmptyState({ icon = "◦", text, actionLabel, onAction }) {
  return (
    <div style={{
      border: `1px dashed ${C.border}`, borderRadius: RADIUS.md, padding: "26px 24px",
      display: "flex", alignItems: "center", gap: 14, color: C.textDim, fontSize: 13, lineHeight: 1.6,
    }}>
      <span style={{ fontSize: 18, color: C.textMute }}>{icon}</span>
      <span style={{ flex: 1 }}>{text}</span>
      {actionLabel && onAction && (
        <button onClick={onAction}
          style={{ background: "transparent", color: C.accent, border: `1px solid ${C.accent}44`,
            borderRadius: RADIUS.sm, padding: "7px 14px", fontSize: 11, fontFamily: FONT.mono, cursor: "pointer", whiteSpace: "nowrap" }}>
          {actionLabel}
        </button>
      )}
    </div>
  );
}
