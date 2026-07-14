import { C, FONT, riskColor } from "./tokens.js";

/**
 * ui2 viz — lightweight SVG visualization primitives shared by every page.
 *
 * These are deliberately dependency-free (recharts stays for full time-series
 * panels): a sparkline for metric tiles, a severity segment bar, a donut with
 * a center stat, a radial gauge, an activity heat strip, and the animated
 * evidence-flow ribbon that is the product's signature element.
 *
 * All ambient animation is gated behind prefers-reduced-motion via the
 * `.oa-flow` / `.oa-pulse` classes defined in index.css.
 */

/* ── Sparkline ─────────────────────────────────────────────────────────────
   Tiny gradient area chart for metric tiles. `data` is an array of numbers. */
export function Sparkline({ data = [], color = C.accent, width = 120, height = 34, strokeWidth = 1.6, id }) {
  const uid = id || `sp-${color.replace("#", "")}-${data.length}-${Math.round((data[0] ?? 0) * 100)}`;
  if (!data || data.length < 2) {
    return (
      <svg width={width} height={height} aria-hidden="true">
        <line x1="0" y1={height - 6} x2={width} y2={height - 6} stroke={C.border} strokeDasharray="3 4" />
      </svg>
    );
  }
  const min = Math.min(...data), max = Math.max(...data);
  const span = max - min || 1;
  const px = (i) => (i / (data.length - 1)) * (width - 2) + 1;
  const py = (v) => height - 4 - ((v - min) / span) * (height - 10);
  const line = data.map((v, i) => `${i ? "L" : "M"}${px(i).toFixed(1)},${py(v).toFixed(1)}`).join(" ");
  const area = `${line} L${px(data.length - 1).toFixed(1)},${height} L1,${height} Z`;
  return (
    <svg width={width} height={height} aria-hidden="true" style={{ display: "block", overflow: "visible" }}>
      <defs>
        <linearGradient id={uid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.34" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${uid})`} />
      <path d={line} fill="none" stroke={color} strokeWidth={strokeWidth} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={px(data.length - 1)} cy={py(data[data.length - 1])} r="2.4" fill={color} />
    </svg>
  );
}

/* ── SegBar ────────────────────────────────────────────────────────────────
   Stacked horizontal segments, e.g. findings by severity.
   `segments`: [{ value, color, label }] */
export function SegBar({ segments = [], height = 8, radius = 4, gap = 2 }) {
  const total = segments.reduce((s, x) => s + (x.value || 0), 0);
  if (!total) return <div style={{ height, borderRadius: radius, background: C.surfaceRaised }} />;
  return (
    <div style={{ display: "flex", gap, height, borderRadius: radius, overflow: "hidden" }}>
      {segments.filter((s) => s.value > 0).map((s, i) => (
        <div key={i} title={s.label ? `${s.label}: ${s.value}` : String(s.value)}
          style={{ width: `${(s.value / total) * 100}%`, background: s.color, minWidth: 3 }} />
      ))}
    </div>
  );
}

/* ── Donut ─────────────────────────────────────────────────────────────────
   SVG donut with a center stat. `segments`: [{ value, color }]. */
export function Donut({ segments = [], size = 132, thickness = 13, centerValue, centerLabel, trackColor = C.surfaceRaised }) {
  const r = (size - thickness) / 2;
  const cx = size / 2, cy = size / 2;
  const circ = 2 * Math.PI * r;
  const total = segments.reduce((s, x) => s + (x.value || 0), 0);
  let acc = 0;
  return (
    <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }} aria-hidden="true">
        <circle cx={cx} cy={cy} r={r} fill="none" stroke={trackColor} strokeWidth={thickness} />
        {total > 0 && segments.filter((s) => s.value > 0).map((s, i) => {
          const frac = s.value / total;
          const dash = Math.max(frac * circ - 2.5, 0.5);
          const el = (
            <circle key={i} cx={cx} cy={cy} r={r} fill="none"
              stroke={s.color} strokeWidth={thickness} strokeLinecap="round"
              strokeDasharray={`${dash} ${circ - dash}`}
              strokeDashoffset={-acc * circ} />
          );
          acc += frac;
          return el;
        })}
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
        <span style={{ fontSize: size / 5.4, fontWeight: 700, color: C.text, fontFamily: FONT.display, letterSpacing: "-0.02em", lineHeight: 1 }}>{centerValue}</span>
        {centerLabel && <span style={{ fontSize: 8.5, fontFamily: FONT.mono, color: C.textMute, letterSpacing: "0.14em", textTransform: "uppercase", marginTop: 4 }}>{centerLabel}</span>}
      </div>
    </div>
  );
}

/* ── Gauge ─────────────────────────────────────────────────────────────────
   270° radial gauge for scores/percentages. `value` in [0, max]. */
export function Gauge({ value = 0, max = 100, size = 130, thickness = 11, color = C.accent, label, format = (v) => `${Math.round(v)}%` }) {
  const r = (size - thickness) / 2;
  const cx = size / 2, cy = size / 2;
  const circ = 2 * Math.PI * r;
  const arc = circ * 0.75; // 270°
  const frac = Math.min(Math.max(value / max, 0), 1);
  return (
    <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: "rotate(135deg)" }} aria-hidden="true">
        <circle cx={cx} cy={cy} r={r} fill="none" stroke={C.surfaceRaised} strokeWidth={thickness}
          strokeDasharray={`${arc} ${circ}`} strokeLinecap="round" />
        <circle cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth={thickness}
          strokeDasharray={`${Math.max(frac * arc, 0.5)} ${circ}`} strokeLinecap="round"
          style={{ transition: "stroke-dasharray 0.6s cubic-bezier(0.2,0.7,0.2,1)" }} />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
        <span style={{ fontSize: size / 5, fontWeight: 700, color: C.text, fontFamily: FONT.display, letterSpacing: "-0.02em", lineHeight: 1 }}>{format(value)}</span>
        {label && <span style={{ fontSize: 8.5, fontFamily: FONT.mono, color: C.textMute, letterSpacing: "0.14em", textTransform: "uppercase", marginTop: 4 }}>{label}</span>}
      </div>
    </div>
  );
}

/* ── HeatStrip ─────────────────────────────────────────────────────────────
   One-row activity heatmap (e.g. events per hour). `data`: number[]. */
export function HeatStrip({ data = [], color = C.accent, cell = 14, gap = 3, radius = 3, labels }) {
  const max = Math.max(...data, 1);
  return (
    <div>
      <div style={{ display: "flex", gap }}>
        {data.map((v, i) => (
          <div key={i} title={labels?.[i] != null ? `${labels[i]}: ${v}` : String(v)}
            style={{
              width: cell, height: cell, borderRadius: radius,
              background: v > 0 ? color : C.surfaceRaised,
              opacity: v > 0 ? 0.25 + 0.75 * (v / max) : 1,
              border: `1px solid ${v > 0 ? "transparent" : C.border}`,
            }} />
        ))}
      </div>
    </div>
  );
}

/* ── PulseDot ──────────────────────────────────────────────────────────────
   Live indicator. Pulses unless reduced motion. */
export function PulseDot({ color = C.ok, size = 7 }) {
  return (
    <span className="oa-pulse" aria-hidden="true"
      style={{ display: "inline-block", width: size, height: size, borderRadius: "50%", background: color, flexShrink: 0 }} />
  );
}

/* ── FlowRibbon ────────────────────────────────────────────────────────────
   The signature element: the evidence chain as a living pipeline. Nodes are
   product stages; edges carry a slow animated dash — evidence flowing left
   to right. Clickable nodes navigate; the active/planned states mirror the
   old FlowStrip's semantics.

   `steps`: [{ label, sub, page, planned, tone }] — tone colors the node dot.
   `onNavigate(page)`, `allows(page)` gate clicks. */
export function FlowRibbon({ steps = [], onNavigate, allows = () => true, compact = false }) {
  const n = steps.length;
  if (!n) return null;
  const H = compact ? 62 : 84;
  const nodeW = 100 / n;
  return (
    <div style={{ position: "relative", width: "100%" }}>
      {/* edge layer */}
      <svg width="100%" height={12} viewBox="0 0 1000 12" preserveAspectRatio="none"
        style={{ position: "absolute", top: compact ? 3 : 5, left: 0, pointerEvents: "none" }} aria-hidden="true">
        <defs>
          <linearGradient id="oa-flow-grad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#3BC7F0" />
            <stop offset="55%" stopColor="#7B8CFF" />
            <stop offset="100%" stopColor="#B07BFF" />
          </linearGradient>
        </defs>
        <line x1={1000 / n / 2} y1="6" x2={1000 - 1000 / n / 2} y2="6"
          stroke={C.borderStrong} strokeWidth="1.5" />
        <line className="oa-flow" x1={1000 / n / 2} y1="6" x2={1000 - 1000 / n / 2} y2="6"
          stroke="url(#oa-flow-grad)" strokeWidth="2.5" strokeDasharray="10 16" strokeLinecap="round" opacity="0.95" />
      </svg>
      {/* node layer */}
      <div style={{ display: "flex", position: "relative", minHeight: H }}>
        {steps.map((s) => {
          const clickable = s.page && allows(s.page) && onNavigate;
          const tone = s.tone || (s.planned ? C.textMute : C.accent);
          return (
            <button key={s.label} onClick={clickable ? () => onNavigate(s.page) : undefined}
              disabled={!clickable}
              style={{
                width: `${nodeW}%`, background: "transparent", border: "none", padding: 0,
                display: "flex", flexDirection: "column", alignItems: "center", gap: compact ? 6 : 8,
                cursor: clickable ? "pointer" : "default", opacity: s.planned ? 0.55 : 1,
              }}>
              <span style={{
                width: compact ? 18 : 22, height: compact ? 18 : 22, borderRadius: "50%",
                background: C.surface, border: `2px solid ${tone}`,
                boxShadow: `0 0 0 4px ${tone}1A, 0 0 14px ${tone}40`,
                display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1,
              }}>
                <span style={{ width: compact ? 6 : 8, height: compact ? 6 : 8, borderRadius: "50%", background: tone }} />
              </span>
              <span style={{ fontFamily: FONT.mono, fontSize: compact ? 9.5 : 10.5, color: s.planned ? C.textMute : C.textDim, letterSpacing: "0.04em", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: "94%" }}>
                {s.label}{s.planned ? " · planned" : ""}
              </span>
              {!compact && s.sub && (
                <span style={{ fontFamily: FONT.mono, fontSize: 9, color: C.textMute, marginTop: -4 }}>{s.sub}</span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ── BarRow ────────────────────────────────────────────────────────────────
   Labeled horizontal bar (per-agent activity, top-N lists). */
export function BarRow({ label, value, max, color = C.accent, errorValue = 0, errorColor = C.riskCritical, right, onClick, title }) {
  const frac = Math.min((value || 0) / Math.max(max || 1, 1), 1);
  const errFrac = Math.min((errorValue || 0) / Math.max(max || 1, 1), frac);
  return (
    <div onClick={onClick} title={title}
      style={{ display: "flex", alignItems: "center", gap: 10, cursor: onClick ? "pointer" : "default" }}>
      <span style={{ fontSize: 11, fontFamily: FONT.mono, color: C.text, width: 170, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flexShrink: 0 }}>
        {label}
      </span>
      <div style={{ flex: 1, height: 12, background: C.surfaceRaised, borderRadius: 6, overflow: "hidden", display: "flex" }}>
        <div style={{ width: `${(frac - errFrac) * 100}%`, background: `linear-gradient(90deg, ${color}, ${color}99)` }} />
        {errFrac > 0 && <div style={{ width: `${errFrac * 100}%`, background: errorColor }} />}
      </div>
      {right != null && (
        <span style={{ fontSize: 10, fontFamily: FONT.mono, color: C.textMute, width: 112, textAlign: "right", flexShrink: 0 }}>{right}</span>
      )}
    </div>
  );
}

/* ── severitySegments ──────────────────────────────────────────────────────
   Helper: counts by severity → SegBar/Donut segments, worst first. */
export function severitySegments(counts) {
  return ["critical", "high", "medium", "low", "info"]
    .map((level) => ({ label: level, value: counts[level] || 0, color: riskColor(level) }))
    .filter((s) => s.value > 0);
}
