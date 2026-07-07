import { C, FONT, RADIUS, riskColor } from "./tokens.js";
import RiskBadge from "./RiskBadge.jsx";
import StatusPill from "./StatusPill.jsx";

/**
 * "Why you're seeing this" card — the evidence-first primitive.
 *
 * Renders a titled attention/insight card with the runtime evidence that
 * supports it: a reason line, optional evidence pills (finding types, tool
 * names…), and exactly one action. Nothing in ui2 asserts risk without
 * rendering its evidence — this is the component that enforces that.
 */
export default function EvidenceCard({ level = "info", title, reason, pills = [], actionLabel, onAction, right }) {
  const color = riskColor(level);
  return (
    <div style={{
      background: C.surface, border: `1px solid ${color}33`, borderLeft: `3px solid ${color}`,
      borderRadius: RADIUS.md, padding: "14px 18px", display: "flex", gap: 14, alignItems: "flex-start",
    }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6, flexWrap: "wrap" }}>
          <span style={{ fontSize: 13.5, fontWeight: 600, color: C.text, fontFamily: FONT.ui }}>{title}</span>
          <RiskBadge level={level} />
          {right}
        </div>
        {reason && <div style={{ fontSize: 12, color: C.textDim, lineHeight: 1.6, marginBottom: pills.length ? 8 : 0 }}>{reason}</div>}
        {pills.length > 0 && (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {pills.map((p) => <StatusPill key={p} tone={C.textDim}>{p}</StatusPill>)}
          </div>
        )}
      </div>
      {actionLabel && onAction && (
        <button onClick={onAction}
          style={{ background: "transparent", color, border: `1px solid ${color}44`, borderRadius: RADIUS.sm,
            padding: "6px 13px", fontSize: 11, fontFamily: FONT.mono, cursor: "pointer", whiteSpace: "nowrap", flexShrink: 0 }}>
          {actionLabel}
        </button>
      )}
    </div>
  );
}
