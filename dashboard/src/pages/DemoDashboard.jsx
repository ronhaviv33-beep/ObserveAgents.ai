// DemoDashboard — premium landing experience shown ONLY in demo mode.
// Pure frontend, synthetic data only. No API calls, no real infrastructure or
// hostnames. Production renders ExecutiveDashboard instead (see App.jsx routing).
import React, { useState, useEffect } from "react";
import { T, FONT_UI, FONT_MONO } from "../theme.js";
import { BRAND } from "../config.js";
import { useBreakpoint } from "../hooks/useBreakpoint.js";

// ── Curated synthetic data ────────────────────────────────────────────────────
const KPIS = [
  { label: "Agents discovered",   value: "47",      sub: "across 6 teams",        color: T.accent },
  { label: "Connected providers", value: "4",       sub: "OpenAI · Anthropic · Google · Local", color: T.info },
  { label: "MCP servers",         value: "9",       sub: "tools + resources",     color: T.purple },
  { label: "Runtime cost",        value: "$12,480", sub: "last 30 days",          color: T.warn },
  { label: "Requests",            value: "1.2M",    sub: "513K this week",        color: T.teal },
  { label: "Teams",               value: "6",       sub: "Sales · Support · …",   color: T.text },
  { label: "Ownership coverage",  value: "92%",     sub: "43 of 47 assigned",     color: T.accent },
  { label: "Governance reviews",  value: "8",       sub: "3 pending approval",    color: T.crit },
];

const ACTIVITY = [
  { agent: "finance-analyst-agent",   action: "used",      target: "GPT-4o",             kind: "model",    ts: "just now" },
  { agent: "sales-assistant",         action: "accessed",  target: "Hubspot",            kind: "crm",      ts: "1m ago" },
  { agent: "research-agent",          action: "queried",   target: "postgres-finance-db", kind: "database", ts: "3m ago" },
  { agent: "customer-support-agent",  action: "invoked",   target: "MCP tool",           kind: "mcp",      ts: "6m ago" },
  { agent: "soc-investigation-agent", action: "used",      target: "Claude Sonnet",      kind: "model",    ts: "11m ago" },
  { agent: "release-assistant-agent", action: "accessed",  target: "GitHub API",         kind: "tool",     ts: "18m ago" },
];

const KIND_COLOR = {
  model: T.info, crm: T.warn, database: T.teal, mcp: T.purple, tool: T.accent,
};

const ECOSYSTEM = [
  { label: "Agent",    desc: "finance-analyst-agent",     color: T.accent },
  { label: "Gateway",  desc: "Runtime interception",      color: T.text },
  { label: "Provider", desc: "OpenAI",                    color: T.info },
  { label: "Model",    desc: "GPT-4o",                    color: T.info },
  { label: "Tool",     desc: "MCP: financial-reports",    color: T.purple },
  { label: "Database", desc: "postgres-finance-db",       color: T.teal },
  { label: "CRM",      desc: "Hubspot",                   color: T.warn },
];

const CAPABILITIES = [
  { name: "Agent Discovery",    desc: "Automatically inventory every AI agent the moment it sends a request.", icon: "◎" },
  { name: "Dependency Mapping", desc: "See how agents connect to providers, models, tools and databases.",   icon: "⤳" },
  { name: "Cost Intelligence",  desc: "Attribute runtime spend to teams, agents and models in real time.",   icon: "$" },
  { name: "Governance",         desc: "Review, approve and enforce policy across every interaction.",          icon: "⚖" },
  { name: "Ownership",          desc: "Assign owners and teams so no agent is left unaccounted for.",          icon: "◈" },
  { name: "MCP Visibility",     desc: "Track Model Context Protocol servers, tools and resource access.",      icon: "⧉" },
  { name: "Runtime Intelligence", desc: "Live telemetry on latency, tokens, errors and PII exposure.",         icon: "✦" },
];

const CTAS = [
  { label: "Explore Discovery",         page: "discovery",        color: T.accent },
  { label: "Explore Dependency Graph",  page: "relationship_map", color: T.purple },
  { label: "Explore Governance",        page: "governance",       color: T.warn },
  { label: "Explore Cost Intelligence", page: "cost",             color: T.teal },
];

// ── Small presentational pieces ────────────────────────────────────────────────
function KpiCard({ k }) {
  const [hover, setHover] = useState(false);
  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        background: T.panel, border: `1px solid ${hover ? T.borderHi : T.border}`,
        borderRadius: 10, padding: "18px 20px", minWidth: 0,
        transition: "border-color 0.15s, transform 0.15s",
        transform: hover ? "translateY(-2px)" : "none",
      }}
    >
      <div style={{ fontSize: 9, fontFamily: FONT_MONO, color: T.textMute, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: 10 }}>
        {k.label}
      </div>
      <div style={{ fontSize: 30, fontWeight: 700, color: k.color, letterSpacing: "-0.03em", lineHeight: 1 }}>
        {k.value}
      </div>
      <div style={{ fontSize: 11, color: T.textDim, marginTop: 8, fontFamily: FONT_UI }}>{k.sub}</div>
    </div>
  );
}

function SectionTitle({ children, hint }) {
  return (
    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 16 }}>
      <h2 style={{ fontSize: 15, fontWeight: 600, color: T.text, margin: 0, letterSpacing: "-0.01em" }}>{children}</h2>
      {hint && <span style={{ fontSize: 10, fontFamily: FONT_MONO, color: T.textMute, letterSpacing: "0.1em", textTransform: "uppercase" }}>{hint}</span>}
    </div>
  );
}

// ── Main ────────────────────────────────────────────────────────────────────────
export default function DemoDashboard({ onNavigate }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => { const id = requestAnimationFrame(() => setMounted(true)); return () => cancelAnimationFrame(id); }, []);
  const bp = useBreakpoint();

  const fadeUp = (delay = 0) => ({
    opacity: mounted ? 1 : 0,
    transform: mounted ? "translateY(0)" : "translateY(12px)",
    transition: `opacity 0.5s ${delay}s ease, transform 0.5s ${delay}s ease`,
  });

  return (
    <div style={{ fontFamily: FONT_UI, color: T.text, maxWidth: 1180, margin: "0 auto", paddingBottom: 48 }}>
      {/* ── Hero ───────────────────────────────────────────────────────────── */}
      <section
        style={{
          position: "relative", overflow: "hidden", borderRadius: 16,
          border: `1px solid ${T.borderHi}`,
          background: `radial-gradient(1200px 400px at 15% -20%, rgba(124,255,178,0.16), transparent 60%), radial-gradient(900px 360px at 95% 0%, rgba(180,122,255,0.14), transparent 55%), linear-gradient(180deg, ${T.panelHi}, ${T.panel})`,
          padding: bp.isMobile ? "24px 16px" : "52px 44px", marginBottom: 28, ...fadeUp(0),
        }}
      >
        <div style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "5px 12px", borderRadius: 999, border: `1px solid ${T.border}`, background: "rgba(124,255,178,0.06)", marginBottom: 22 }}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: T.accent, boxShadow: `0 0 10px ${T.accent}` }} />
          <span style={{ fontSize: 11, fontFamily: FONT_MONO, color: T.accent, letterSpacing: "0.12em", textTransform: "uppercase" }}>Live Demo</span>
        </div>
        <div style={{ fontSize: 46, fontWeight: 700, letterSpacing: "-0.04em", lineHeight: 1.02 }}>{BRAND.name}</div>
        <div style={{ fontSize: 15, fontFamily: FONT_MONO, color: T.textDim, letterSpacing: "0.04em", marginTop: 10 }}>{BRAND.subtitle}</div>
        <div style={{ marginTop: 26, display: "flex", flexDirection: "column", gap: 4 }}>
          {(BRAND.taglineLines || []).map((line, i) => (
            <div key={i} style={{ fontSize: 26, fontWeight: 600, letterSpacing: "-0.02em",
              background: `linear-gradient(90deg, ${T.text}, ${T.textDim})`, WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent",
              ...fadeUp(0.1 + i * 0.08) }}>
              {line}
            </div>
          ))}
        </div>
      </section>

      {/* ── KPI cards ──────────────────────────────────────────────────────── */}
      <section style={{ marginBottom: 36, ...fadeUp(0.15) }}>
        <SectionTitle hint="Synthetic demo data">Platform at a glance</SectionTitle>
        <div style={{ display: "grid", gridTemplateColumns: bp.isMobile ? "repeat(2, 1fr)" : "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 }}>
          {KPIS.map((k) => <KpiCard key={k.label} k={k} />)}
        </div>
      </section>

      <div style={{ display: "grid", gridTemplateColumns: bp.isMobile ? "1fr" : "1.1fr 0.9fr", gap: 24, marginBottom: 36 }}>
        {/* ── Recent activity ──────────────────────────────────────────────── */}
        <section style={{ ...fadeUp(0.2) }}>
          <SectionTitle hint="Live runtime">Recent activity</SectionTitle>
          <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 10, overflow: "hidden" }}>
            {ACTIVITY.map((a, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "13px 16px", borderTop: i ? `1px solid ${T.border}` : "none" }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", flexShrink: 0, background: KIND_COLOR[a.kind] || T.accent, boxShadow: `0 0 8px ${KIND_COLOR[a.kind] || T.accent}` }} />
                <div style={{ flex: 1, minWidth: 0, fontSize: 13 }}>
                  <span style={{ fontFamily: FONT_MONO, color: T.text }}>{a.agent}</span>
                  <span style={{ color: T.textDim }}> {a.action} </span>
                  <span style={{ color: KIND_COLOR[a.kind] || T.accent, fontWeight: 600 }}>{a.target}</span>
                </div>
                <span style={{ fontSize: 11, fontFamily: FONT_MONO, color: T.textMute, flexShrink: 0 }}>{a.ts}</span>
              </div>
            ))}
          </div>
        </section>

        {/* ── Ecosystem visualization ──────────────────────────────────────── */}
        <section style={{ ...fadeUp(0.25) }}>
          <SectionTitle hint="One request, traced">Ecosystem</SectionTitle>
          <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 10, padding: "18px 16px" }}>
            {ECOSYSTEM.map((node, i) => (
              <React.Fragment key={node.label}>
                <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 10px", borderRadius: 8, border: `1px solid ${T.border}`, background: T.panelHi }}>
                  <span style={{ width: 9, height: 9, borderRadius: 2, background: node.color, flexShrink: 0, boxShadow: `0 0 8px ${node.color}` }} />
                  <span style={{ fontSize: 12, fontFamily: FONT_MONO, color: T.textMute, width: 64, flexShrink: 0, textTransform: "uppercase", letterSpacing: "0.08em" }}>{node.label}</span>
                  <span style={{ fontSize: 13, color: T.text }}>{node.desc}</span>
                </div>
                {i < ECOSYSTEM.length - 1 && (
                  <div style={{ textAlign: "center", color: T.textMute, fontSize: 13, lineHeight: "14px", padding: "2px 0" }}>↓</div>
                )}
              </React.Fragment>
            ))}
          </div>
        </section>
      </div>

      {/* ── Platform capabilities ──────────────────────────────────────────── */}
      <section style={{ marginBottom: 36, ...fadeUp(0.3) }}>
        <SectionTitle>Platform capabilities</SectionTitle>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(250px, 1fr))", gap: 12 }}>
          {CAPABILITIES.map((c) => (
            <div key={c.name} style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 10, padding: "16px 18px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                <span style={{ width: 26, height: 26, borderRadius: 7, display: "grid", placeItems: "center", background: "rgba(124,255,178,0.08)", color: T.accent, fontSize: 14 }}>{c.icon}</span>
                <span style={{ fontSize: 14, fontWeight: 600 }}>{c.name}</span>
              </div>
              <div style={{ fontSize: 12.5, color: T.textDim, lineHeight: 1.5 }}>{c.desc}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── CTAs ───────────────────────────────────────────────────────────── */}
      <section style={{ ...fadeUp(0.35) }}>
        <SectionTitle>Explore the platform</SectionTitle>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
          {CTAS.map((cta) => (
            <button
              key={cta.page}
              onClick={() => onNavigate && onNavigate(cta.page)}
              style={{
                flex: "1 1 240px", minWidth: 0, textAlign: "left", cursor: "pointer",
                background: T.panel, border: `1px solid ${T.border}`, borderRadius: 10,
                padding: "16px 18px", color: T.text, fontFamily: FONT_UI,
                display: "flex", alignItems: "center", justifyContent: "space-between",
                transition: "border-color 0.15s, background 0.15s",
              }}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = cta.color; e.currentTarget.style.background = T.panelHi; }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = T.border; e.currentTarget.style.background = T.panel; }}
            >
              <span style={{ fontSize: 14, fontWeight: 600 }}>{cta.label}</span>
              <span style={{ color: cta.color, fontSize: 16 }}>→</span>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
