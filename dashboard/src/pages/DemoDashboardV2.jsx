// DemoDashboardV2 — the demo-mode landing, rebuilt on ui2.
// Pure frontend, curated synthetic data only. No API calls, no real
// infrastructure or hostnames. Production renders ExecutiveDashboard instead.
import { Fragment } from "react";
import { C, FONT, RADIUS, microLabel } from "../ui2/tokens.js";
import Section from "../ui2/Section.jsx";
import MetricCard from "../ui2/MetricCard.jsx";
import StatusPill from "../ui2/StatusPill.jsx";
import { BRAND } from "../config.js";
import { surfaceAllowsPage } from "../productSurface.js";
import { useBreakpoint } from "../hooks/useBreakpoint.js";

const FLOW = ["OTel / OTLP", "Runtime", "Asset Intelligence", "Security Intelligence", "Detection Rules", "Gateway Control Center"];

const KPIS = [
  { label: "Agents discovered",   value: "47",      sub: "across 6 teams",                       tone: C.accent },
  { label: "Connected providers", value: "4",       sub: "OpenAI · Anthropic · Google · Local",  tone: C.riskLow },
  { label: "MCP servers",         value: "9",       sub: "tools + resources",                    tone: C.purple },
  { label: "Runtime cost",        value: "$12,480", sub: "last 30 days",                         tone: C.riskMedium },
  { label: "Requests",            value: "1.2M",    sub: "513K this week",                       tone: C.teal },
  { label: "Ownership coverage",  value: "92%",     sub: "43 of 47 assigned",                    tone: C.accent },
  { label: "Open findings",       value: "23",      sub: "5 high severity",                      tone: C.riskHigh },
  { label: "Control candidates",  value: "3",       sub: "recommended for review",               tone: C.riskMedium },
];

const ACTIVITY = [
  { agent: "finance-analyst-agent",   action: "used",     target: "GPT-4o",              kind: "model",    ts: "just now" },
  { agent: "sales-assistant",         action: "accessed", target: "Hubspot",             kind: "crm",      ts: "1m ago" },
  { agent: "research-agent",          action: "queried",  target: "postgres-finance-db", kind: "database", ts: "3m ago" },
  { agent: "customer-support-agent",  action: "invoked",  target: "MCP tool",            kind: "mcp",      ts: "6m ago" },
  { agent: "soc-investigation-agent", action: "used",     target: "Claude Sonnet",       kind: "model",    ts: "11m ago" },
  { agent: "release-assistant-agent", action: "accessed", target: "GitHub API",          kind: "tool",     ts: "18m ago" },
];
const KIND_TONE = { model: C.riskLow, crm: C.riskMedium, database: C.teal, mcp: C.purple, tool: C.accent };

const CAPABILITIES = [
  { name: "Agent Discovery",      desc: "Automatically inventory every AI agent the moment it sends a trace.", icon: "◎" },
  { name: "Runtime Evidence",     desc: "Sessions, execution waterfalls, and per-step timing from OpenTelemetry.", icon: "▶" },
  { name: "Security Intelligence", desc: "Agent-specific runtime security findings — MCP, databases, providers, ownership.", icon: "⚑" },
  { name: "Dependency Mapping",   desc: "See how agents connect to providers, models, tools and databases.", icon: "⤳" },
  { name: "Ownership",            desc: "Assign owners and teams so no agent is left unaccounted for.", icon: "◈" },
  { name: "Cost Intelligence",    desc: "Attribute runtime spend to teams, agents and models in real time.", icon: "$" },
  { name: "Gateway Control",      desc: "Evidence-backed control recommendations — observe-only until explicitly configured.", icon: "⇥" },
];

const EXPLORE = [
  { label: "Explore Runtime",                  page: "runtime",                tone: C.accent },
  { label: "Explore Asset Intelligence",       page: "intelligence",           tone: C.purple },
  { label: "Explore Security Intelligence",    page: "security_intel",         tone: C.riskHigh },
  { label: "Explore Gateway Control Center",   page: "gateway_control_center", tone: C.riskMedium },
  { label: "Gateway vs OTEL — how data gets in", page: "surfaces_demo",        tone: C.teal },
];

export default function DemoDashboardV2({ onNavigate }) {
  const bp = useBreakpoint();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 30, fontFamily: FONT.ui, maxWidth: 1160 }}>

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <div style={{ padding: bp.isMobile ? "28px 22px" : "42px 46px", background: C.surface,
        border: `1px solid ${C.border}`, borderRadius: RADIUS.lg, position: "relative", overflow: "hidden" }}>
        <div style={{ position: "absolute", top: -80, right: -80, width: 320, height: 320, borderRadius: "50%", background: `${C.accent}06`, pointerEvents: "none" }} />
        <div style={{ ...microLabel, color: C.accent, marginBottom: 14 }}>Interactive demo · synthetic data only</div>
        <div style={{ fontSize: bp.isMobile ? 30 : 44, fontWeight: 700, letterSpacing: "-0.04em", lineHeight: 1.05, color: C.text }}>
          {BRAND.name}
        </div>
        <div style={{ fontSize: 14.5, fontFamily: FONT.mono, color: C.textDim, letterSpacing: "0.03em", marginTop: 10 }}>
          {BRAND.subtitle}
        </div>
        <div style={{ fontSize: 14, color: C.textDim, lineHeight: 1.7, maxWidth: 620, marginTop: 18 }}>
          Every AI agent leaves evidence when it runs. ObserveAgents turns that evidence into an AI
          inventory, security findings, and Gateway control recommendations.{" "}
          <span style={{ color: C.accent }}>Observe first. Control only what matters.</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginTop: 22 }}>
          {FLOW.map((step, i) => (
            <Fragment key={step}>
              <span style={{ fontSize: 11, fontFamily: FONT.mono, color: C.text, background: C.surfaceRaised,
                border: `1px solid ${C.border}`, borderRadius: RADIUS.sm, padding: "5px 11px", whiteSpace: "nowrap" }}>{step}</span>
              {i < FLOW.length - 1 && <span style={{ color: C.textMute, fontSize: 11 }}>→</span>}
            </Fragment>
          ))}
        </div>
      </div>

      {/* ── Platform at a glance ─────────────────────────────────────────── */}
      <Section label="Platform at a glance"
        right={<span style={{ fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute }}>synthetic demo data</span>}>
        <div style={{ display: "grid", gridTemplateColumns: `repeat(auto-fill, minmax(${bp.isMobile ? 150 : 210}px, 1fr))`, gap: 12 }}>
          {KPIS.map((k) => <MetricCard key={k.label} label={k.label} value={k.value} sub={k.sub} tone={k.tone} />)}
        </div>
      </Section>

      <div style={{ display: "grid", gridTemplateColumns: bp.isMobile ? "1fr" : "3fr 2fr", gap: 16 }}>
        {/* ── Recent activity ────────────────────────────────────────────── */}
        <Section label="Recent activity"
          right={<span style={{ fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute }}>live runtime</span>}>
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: RADIUS.md, padding: "6px 18px" }}>
            {ACTIVITY.map((a, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 0",
                borderBottom: i < ACTIVITY.length - 1 ? `1px solid ${C.border}` : "none" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ fontSize: 12.5, color: C.text, fontFamily: FONT.mono }}>{a.agent}</span>
                  <span style={{ fontSize: 12, color: C.textDim }}> {a.action} </span>
                  <span style={{ fontSize: 12.5, color: C.text }}>{a.target}</span>
                </div>
                <StatusPill tone={KIND_TONE[a.kind] || C.textDim}>{a.kind}</StatusPill>
                <span style={{ fontSize: 10, fontFamily: FONT.mono, color: C.textMute, whiteSpace: "nowrap" }}>{a.ts}</span>
              </div>
            ))}
          </div>
        </Section>

        {/* ── Observe-to-Control moment ──────────────────────────────────── */}
        <Section label="From evidence to control">
          <div style={{ background: C.surface, border: `1px solid ${C.riskMedium}33`, borderLeft: `3px solid ${C.riskMedium}`,
            borderRadius: RADIUS.md, padding: "16px 18px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: C.text, fontFamily: FONT.mono }}>finance-analyst-agent</span>
              <StatusPill tone={C.riskHigh}>high risk</StatusPill>
              <StatusPill tone={C.textDim}>production</StatusPill>
            </div>
            <div style={{ fontSize: 12, color: C.textDim, lineHeight: 1.65, marginBottom: 10 }}>
              MCP tools in production, direct database access, and no assigned owner —
              runtime evidence recommends reviewing this agent for Gateway control.
              Nothing is applied automatically.
            </div>
            <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginBottom: 12 }}>
              <StatusPill tone={C.purple}>route through gateway</StatusPill>
              <StatusPill tone={C.accent}>owner assignment</StatusPill>
              <StatusPill tone={C.riskHigh}>mcp/tool usage policy</StatusPill>
            </div>
            {surfaceAllowsPage("gateway_control_center") && (
              <button onClick={() => onNavigate?.("gateway_control_center")}
                style={{ background: "transparent", color: C.riskMedium, border: `1px solid ${C.riskMedium}44`,
                  borderRadius: RADIUS.sm, padding: "6px 14px", fontSize: 11, fontFamily: FONT.mono, cursor: "pointer" }}>
                Open Gateway Control Center →
              </button>
            )}
          </div>
        </Section>
      </div>

      {/* ── Platform capabilities ────────────────────────────────────────── */}
      <Section label="Platform capabilities">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(250px, 1fr))", gap: 12 }}>
          {CAPABILITIES.map((c) => (
            <div key={c.name} style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: RADIUS.md, padding: "18px 20px" }}>
              <div style={{ fontSize: 17, color: C.accent, marginBottom: 9 }}>{c.icon}</div>
              <div style={{ fontSize: 13, fontWeight: 600, color: C.text, marginBottom: 5 }}>{c.name}</div>
              <div style={{ fontSize: 11.5, color: C.textDim, lineHeight: 1.6 }}>{c.desc}</div>
            </div>
          ))}
        </div>
      </Section>

      {/* ── Explore the platform ─────────────────────────────────────────── */}
      <Section label="Explore the platform">
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          {EXPLORE.filter((cta) => surfaceAllowsPage(cta.page)).map((cta) => (
            <button key={cta.page} onClick={() => onNavigate?.(cta.page)}
              style={{ background: "transparent", color: cta.tone, border: `1px solid ${cta.tone}44`,
                borderRadius: RADIUS.sm, padding: "10px 18px", fontSize: 12.5, fontWeight: 600,
                fontFamily: FONT.ui, cursor: "pointer", transition: "border-color .15s" }}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = cta.tone; }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = cta.tone + "44"; }}>
              {cta.label} →
            </button>
          ))}
        </div>
      </Section>
    </div>
  );
}
