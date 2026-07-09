import { useState, useEffect } from "react";
import {
  ResponsiveContainer, AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
} from "recharts";
import { T, FONT_UI as FONT, FONT_MONO as MONO } from "../theme.js";
import { Card, Pill } from "../components/ui.jsx";
import { useBreakpoint } from "../hooks/useBreakpoint.js";
import { surfaceAllowsPage } from "../productSurface.js";
import {
  GATEWAY_FLOW, OTEL_FLOW, COMPARISON, SURFACE_STATS,
  SPEND_SERIES, FINDINGS_BARS, verdictLabel,
} from "./surfacesDemoData.js";

const LANE_KEY = "oa-surfaces-lane";
const LANE_META = {
  gateway: { label: "Gateway", mode: "ENFORCE", color: T.accent,
    desc: "Sits in the request path. Traffic routes through it — so it can allow, flag, or block." },
  otel:    { label: "OTEL", mode: "OBSERVE", color: T.purple,
    desc: "Sits beside the path. Reads telemetry — so it sees everything and stops nothing." },
};
const VERDICT_COLOR = { BLOCKED: T.crit, FLAGGED: T.warn, ALLOWED: T.accent, LOGGED: T.purple };

/**
 * Browser-chrome frame around a product-surface mockup. The mockup JSX is the
 * default child — swap in a real <img> later without touching layout.
 */
function SurfaceScreenshot({ surface, children }) {
  const meta = surface === "gateway" ? LANE_META.gateway : LANE_META.otel;
  return (
    <div style={{ border: `1px solid ${T.borderHi}`, borderRadius: 10, overflow: "hidden", background: T.panel }}>
      <div style={{ display: "flex", alignItems: "center", gap: 7, padding: "9px 12px", background: T.panelHi, borderBottom: `1px solid ${T.border}` }}>
        {[T.crit, T.warn, T.accent].map((c, i) => (
          <span key={i} style={{ width: 10, height: 10, borderRadius: "50%", background: `${c}66`, flexShrink: 0 }} />
        ))}
        <span style={{ marginLeft: 8, background: T.bg, borderRadius: 5, padding: "3px 12px", fontFamily: MONO, fontSize: 10, color: T.textMute, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          app.observeagents.ai · VITE_PRODUCT_SURFACE={surface === "gateway" ? "gateway" : "observability"}
        </span>
        <span style={{ marginLeft: "auto", fontFamily: MONO, fontSize: 9, letterSpacing: "0.12em", color: meta.color, border: `1px solid ${meta.color}44`, borderRadius: 999, padding: "2px 10px", whiteSpace: "nowrap" }}>
          {meta.mode}
        </span>
      </div>
      <div style={{ padding: 16 }}>{children}</div>
    </div>
  );
}

function MiniStat({ label, value, color }) {
  return (
    <div style={{ background: T.panelHi, border: `1px solid ${T.border}`, borderRadius: 6, padding: "10px 12px", flex: 1, minWidth: 90 }}>
      <div style={{ fontSize: 8, fontFamily: MONO, color: T.textMute, letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 700, color: color || T.text, letterSpacing: "-0.02em" }}>{value}</div>
    </div>
  );
}

function VerdictTag({ label }) {
  const color = VERDICT_COLOR[label] || T.textDim;
  return (
    <span style={{ fontFamily: MONO, fontSize: 9, fontWeight: 600, letterSpacing: "0.1em", color, background: `${color}1A`, border: `1px solid ${color}33`, borderRadius: 3, padding: "2px 8px", whiteSpace: "nowrap" }}>
      {label}
    </span>
  );
}

/**
 * Animated flow rows revealing one by one. Mounted with key={lane}, so a lane
 * change remounts it and the counter resets naturally; the interval is cleared
 * on unmount and stops once every row is shown.
 */
function FlowStrip({ lane, flow, isMobile }) {
  const [revealCount, setRevealCount] = useState(0);
  useEffect(() => {
    const id = setInterval(() => {
      setRevealCount((n) => {
        if (n >= flow.length) { clearInterval(id); return n; }
        return n + 1;
      });
    }, 550);
    return () => clearInterval(id);
  }, [flow.length]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {flow.map((e, i) => {
        const shown = i < revealCount;
        const label = verdictLabel(lane, e.verdict);
        const risky = label === "BLOCKED" || (lane === "otel" && e.verdict === "flagged");
        return (
          <div key={e.id} style={{
            display: "flex", alignItems: "center", gap: 12, padding: "9px 12px",
            background: shown && label === "BLOCKED" ? `${T.crit}0D` : T.panelHi,
            border: `1px solid ${shown && label === "BLOCKED" ? `${T.crit}33` : T.border}`,
            borderRadius: 6,
            opacity: shown ? 1 : 0, transform: shown ? "none" : "translateY(6px)",
            transition: "opacity 0.4s ease, transform 0.4s ease, background 0.4s, border-color 0.4s",
          }}>
            <span style={{ fontFamily: MONO, fontSize: 12, color: T.text, width: isMobile ? 110 : 150, flexShrink: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {e.agent}
            </span>
            <span style={{ flex: 1, minWidth: 0, fontSize: 12, color: T.textDim, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {e.action}
            </span>
            {shown && <VerdictTag label={label} />}
            {shown && risky && e.reason && !isMobile && (
              <span style={{ fontSize: 10, color: T.textMute, fontStyle: lane === "otel" ? "italic" : "normal", fontFamily: MONO, maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {e.reason}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function SurfacesDemo({ onNavigate }) {
  const bp = useBreakpoint();
  const [lane, setLane] = useState(() =>
    localStorage.getItem(LANE_KEY) === "otel" ? "otel" : "gateway");
  const pickLane = (l) => { setLane(l); localStorage.setItem(LANE_KEY, l); };

  const flow = lane === "gateway" ? GATEWAY_FLOW : OTEL_FLOW;

  const laneMeta = LANE_META[lane];
  const stats = SURFACE_STATS;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24, fontFamily: FONT }}>

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: bp.isMobile ? 20 : 24, fontWeight: 700, color: T.text, letterSpacing: "-0.025em" }}>
          Two ways to connect
        </h2>
        <Pill color={T.info}>Demo</Pill>
        <div style={{ flexBasis: "100%", fontSize: 12, color: T.textMute, fontFamily: MONO }}>
          Same platform, two product surfaces — one can enforce, one only observes.
        </div>
      </div>

      {/* ── Lane picker ─────────────────────────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: bp.isMobile ? "1fr" : "1fr 1fr", gap: 16 }}>
        {Object.entries(LANE_META).map(([key, m]) => (
          <div key={key} onClick={() => pickLane(key)}
            style={{
              background: T.panel, borderRadius: 10, padding: "20px 22px", cursor: "pointer",
              border: `1px solid ${lane === key ? m.color : T.border}`,
              boxShadow: lane === key ? `0 0 0 2px ${m.color}33` : "none",
              transition: "border-color 0.2s, box-shadow 0.2s",
            }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 8 }}>
              <span style={{ fontSize: 16, fontWeight: 650, color: T.text }}>{m.label}</span>
              <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: "0.14em", color: m.color, border: `1px solid ${m.color}44`, borderRadius: 999, padding: "2px 10px" }}>
                {m.mode}
              </span>
            </div>
            <div style={{ fontSize: 13, color: T.textDim, lineHeight: 1.6 }}>{m.desc}</div>
          </div>
        ))}
      </div>

      {/* ── Animated flow strip ─────────────────────────────────────────────── */}
      <Card>
        <div style={{ fontSize: 14, fontWeight: 600, color: T.text, marginBottom: 4 }}>
          The same five agent actions, through the {laneMeta.label} lens
        </div>
        <div style={{ fontSize: 11, color: T.textMute, fontFamily: MONO, marginBottom: 14 }}>
          watch the two risky calls — a prod DB write and a shell exec
        </div>
        <FlowStrip key={lane} lane={lane} flow={flow} isMobile={bp.isMobile} />
        <div style={{ marginTop: 14, fontSize: 12, color: T.textDim, lineHeight: 1.6 }}>
          {lane === "gateway"
            ? <>The Gateway is a control point: the two risky calls <span style={{ color: T.crit, fontWeight: 600 }}>never reached their target</span>.</>
            : <>OTEL observability sees the same two risky calls and turns them into findings — <span style={{ color: T.warn, fontStyle: "italic" }}>seen, not stopped</span>.</>}
        </div>
      </Card>

      {/* ── Surface mockups ─────────────────────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: bp.isMobile ? "1fr" : "1fr 1fr", gap: 16, alignItems: "start" }}>
        <SurfaceScreenshot surface="gateway">
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
            <MiniStat label="Requests" value={stats.gateway.requests} />
            <MiniStat label="Blocked" value={stats.gateway.blocked} color={T.crit} />
            <MiniStat label="Saved" value={stats.gateway.saved} color={T.accent} />
            <MiniStat label="Policies" value={stats.gateway.policies} />
          </div>
          <div style={{ fontSize: 10, fontFamily: MONO, color: T.textMute, letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: 8 }}>
            Live policy decisions
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            {GATEWAY_FLOW.map((e) => (
              <div key={e.id} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <VerdictTag label={verdictLabel("gateway", e.verdict)} />
                <span style={{ fontSize: 11, color: T.textDim, fontFamily: MONO, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {e.agent} · {e.action}
                </span>
              </div>
            ))}
          </div>
        </SurfaceScreenshot>

        <SurfaceScreenshot surface="observability">
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
            <MiniStat label="Spans" value={stats.observability.spans} />
            <MiniStat label="Systems" value={stats.observability.systems} color={T.purple} />
            <MiniStat label="Findings" value={stats.observability.findings} color={T.warn} />
            <MiniStat label="Coverage" value={stats.observability.coverage} color={T.accent} />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "3fr 2fr", gap: 10, marginBottom: 12 }}>
            <div>
              <ResponsiveContainer width="100%" height={90}>
                <AreaChart data={SPEND_SERIES}>
                  <defs>
                    <linearGradient id="sdSpend" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={T.purple} stopOpacity={0.35} />
                      <stop offset="100%" stopColor={T.purple} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke={T.border} vertical={false} />
                  <XAxis dataKey="d" stroke={T.textMute} style={{ fontFamily: MONO, fontSize: 10 }} tickLine={false} />
                  <YAxis hide />
                  <Tooltip contentStyle={{ background: "#FFFFFF", border: `1px solid ${T.border}`, borderRadius: 8, boxShadow: "0 4px 12px rgba(15,23,42,0.08)", fontFamily: MONO, fontSize: 11 }} />
                  <Area type="monotone" dataKey="v" stroke={T.purple} strokeWidth={1.5} fill="url(#sdSpend)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div>
              <ResponsiveContainer width="100%" height={90}>
                <BarChart data={FINDINGS_BARS}>
                  <CartesianGrid stroke={T.border} vertical={false} />
                  <XAxis hide /><YAxis hide />
                  <Tooltip contentStyle={{ background: "#FFFFFF", border: `1px solid ${T.border}`, borderRadius: 8, boxShadow: "0 4px 12px rgba(15,23,42,0.08)", fontFamily: MONO, fontSize: 11 }} cursor={{ fill: `${T.purple}11` }} />
                  <Bar dataKey="v" fill={T.purple} opacity={0.7} radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div style={{ fontSize: 10, fontFamily: MONO, color: T.textMute, letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: 8 }}>
            Open findings (reported, not blocked)
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            {OTEL_FLOW.filter((e) => e.verdict === "flagged").map((e) => (
              <div key={e.id} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <VerdictTag label="FLAGGED" />
                <span style={{ fontSize: 11, color: T.textDim, fontFamily: MONO, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {e.reason}
                </span>
              </div>
            ))}
          </div>
        </SurfaceScreenshot>
      </div>

      {/* ── Comparison table ────────────────────────────────────────────────── */}
      <Card>
        <div style={{ fontSize: 14, fontWeight: 600, color: T.text, marginBottom: 14 }}>Side by side</div>
        <div style={{ display: "grid", gridTemplateColumns: bp.isMobile ? "1fr" : "140px 1fr 1fr", gap: 0 }}>
          {!bp.isMobile && (
            <>
              <div />
              <div style={{ padding: "8px 12px", fontFamily: MONO, fontSize: 10, letterSpacing: "0.12em", textTransform: "uppercase", color: LANE_META.gateway.color, background: `${LANE_META.gateway.color}0D`, borderRadius: "6px 6px 0 0" }}>
                Gateway · Enforce
              </div>
              <div style={{ padding: "8px 12px", fontFamily: MONO, fontSize: 10, letterSpacing: "0.12em", textTransform: "uppercase", color: LANE_META.otel.color, background: `${LANE_META.otel.color}0D`, borderRadius: "6px 6px 0 0" }}>
                OTEL · Observe
              </div>
            </>
          )}
          {COMPARISON.map((row) => (
            bp.isMobile ? (
              <div key={row.dim} style={{ borderBottom: `1px solid ${T.border}`, padding: "10px 0" }}>
                <div style={{ fontSize: 11, fontFamily: MONO, color: T.textMute, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>{row.dim}</div>
                <div style={{ fontSize: 12, color: T.text, marginBottom: 4 }}><span style={{ color: LANE_META.gateway.color, fontFamily: MONO, fontSize: 10 }}>GATEWAY&nbsp;</span>{row.gateway}</div>
                <div style={{ fontSize: 12, color: T.text }}><span style={{ color: LANE_META.otel.color, fontFamily: MONO, fontSize: 10 }}>OTEL&nbsp;</span>{row.otel}</div>
              </div>
            ) : (
              <div key={row.dim} style={{ display: "contents" }}>
                <div style={{ padding: "10px 12px 10px 0", fontSize: 12, fontFamily: MONO, color: T.textMute, borderBottom: `1px solid ${T.border}` }}>{row.dim}</div>
                <div style={{ padding: "10px 12px", fontSize: 13, color: T.text, borderBottom: `1px solid ${T.border}`, background: `${LANE_META.gateway.color}05` }}>{row.gateway}</div>
                <div style={{ padding: "10px 12px", fontSize: 13, color: T.text, borderBottom: `1px solid ${T.border}`, background: `${LANE_META.otel.color}05` }}>{row.otel}</div>
              </div>
            )
          ))}
        </div>
      </Card>

      {/* ── Takeaway ────────────────────────────────────────────────────────── */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "16px 22px", background: T.panel, border: `1px solid ${T.border}`, borderRadius: 10, flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 240, fontSize: 13, color: T.textDim, lineHeight: 1.6 }}>
          <span style={{ color: T.text, fontWeight: 600 }}>The playbook:</span>{" "}
          start with OTEL for instant visibility, route high-stakes agents through the Gateway once you know what to enforce.
        </div>
        {surfaceAllowsPage("integrations") && (
          <button onClick={() => onNavigate?.("integrations")}
            style={{ background: "transparent", border: `1px solid ${T.border}`, color: T.textDim, padding: "7px 16px", borderRadius: 4, fontSize: 11, fontFamily: MONO, cursor: "pointer", letterSpacing: "0.04em", whiteSpace: "nowrap" }}>
            Open Setup →
          </button>
        )}
      </div>
    </div>
  );
}
