import { microLabel } from "./tokens.js";

/** Labeled content band with consistent spacing and an optional right slot. */
export default function Section({ label, right, children, style }) {
  return (
    <div style={style}>
      {(label || right) && (
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 10, marginBottom: 12 }}>
          <span style={microLabel}>{label}</span>
          {right}
        </div>
      )}
      {children}
    </div>
  );
}
