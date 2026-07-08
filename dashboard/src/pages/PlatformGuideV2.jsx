import { Fragment } from "react";
import { C, FONT, RADIUS, microLabel } from "../ui2/tokens.js";
import Section from "../ui2/Section.jsx";
import StatusPill from "../ui2/StatusPill.jsx";
import { isObservability, surfaceAllowsPage } from "../productSurface.js";
import { useBreakpoint } from "../hooks/useBreakpoint.js";

/**
 * PlatformGuideV2 — redesign step 5 (docs/ui_redesign_plan.md).
 *
 * Pure content page restyled onto ui2. The copy is carried over from the
 * current guide (operation model, trace-discovered grid, Getting Started
 * steps verbatim, platform cards) with one addition: a Gateway Control
 * Center card, so the guide reflects the shipped Observe-to-Control flow.
 */

const FLOW_STEPS = ["OTel / OTLP", "Runtime", "Asset Intelligence", "Security Intelligence", "Detection Rules", "Gateway Control Center"];

export default function PlatformGuideV2({ onNavigate }) {
  const bp = useBreakpoint();

  const discoveredItems = [
    { icon: "◈", color: C.accent,  label: "AI Agents",     detail: "Every agent making LLM calls — named, fingerprinted, attributed to a team" },
    { icon: "🔗", color: C.teal,   label: "Dependencies",  detail: "MCP servers, tools, APIs, databases, and CRMs each agent touches at runtime" },
    { icon: "⊞", color: C.riskLow, label: "Models in use", detail: "Every model variant across OpenAI, Anthropic, and other providers" },
    { icon: "⚡", color: C.riskMedium, label: "Workflows",  detail: "n8n, Zapier, LangGraph, and orchestration chains discovered automatically" },
    { icon: "⊙", color: C.purple,  label: "Shadow AI",     detail: "Agents that appeared outside official channels — surfaced before they become a risk" },
    { icon: "$",  color: C.accent, label: "Cost signals",  detail: "Runtime usage and cost signals by team, agent, and model — no manual tagging needed" },
  ];

  const features = [
    { icon: "▶", color: C.accent,  title: "Runtime",               page: "runtime",           desc: "See live AI traces and execution timelines — where every request actually spends its time." },
    { icon: "◈", color: C.purple,  title: "Asset Intelligence",    page: "intelligence",      desc: "Understand every AI system: its models, tools, dependencies, capabilities, and findings — grouped in one place." },
    { icon: "⚑", color: C.riskHigh, title: "Security Intelligence", page: "security_intel",   desc: "Find risky runtime behavior like database access, MCP usage, external APIs, and broad tool access." },
    { icon: "⇥", color: C.riskMedium, title: "Gateway Control Center", page: "gateway_control_center", desc: "Review agents recommended for Gateway control — evidence, suggested controls, and explicit approval. Observe-only until configured." },
    ...(isObservability ? [] : [
      { icon: "$", color: C.accent, title: "Cost Intelligence",    page: "cost",              desc: "Spot heavy, slow, or potentially expensive AI workflows. Usage signals, not exact billing." },
    ]),
    { icon: "⊛", color: C.riskLow, title: "Guardrails",            page: "guardrails",        desc: "Start in observe-only mode: detect, explain, and recommend — without blocking production AI." },
    { icon: "🔗", color: C.teal,   title: "Dependency Map",        page: "relationship_map",  desc: "See what every AI system connects to — MCP servers, tools, workflows, APIs, and databases." },
  ].filter((f) => surfaceAllowsPage(f.page));

  // Getting Started — copy carried over verbatim from the current guide.
  const steps = [
    {
      n: "1", color: C.accent,
      title: "How data gets in",
      desc: isObservability
        ? "Send OpenTelemetry traces to the OTLP endpoint — it works with your existing OTel stack and the GenAI semantic conventions. Ecosystem sources like GitHub, Jira, Slack, n8n, and MCP are coming later."
        : "Send OpenTelemetry traces to the OTLP endpoint, or route AI traffic through the gateway. Both work with your existing stack — no proprietary SDK required. Ecosystem sources like GitHub, Jira, Slack, n8n, and MCP are coming later.",
      note: null,
      sdks: isObservability
        ? ["OpenTelemetry", "OTel Collector", "GenAI SemConv", "MCP telemetry", "Claude Code telemetry"]
        : ["OpenTelemetry", "OpenAI SDK", "LangChain", "CrewAI", "LiteLLM", "MCP Clients", "Vercel AI SDK", "any OpenAI-compatible client"],
      cta: "Open Setup →", page: "integrations",
    },
    {
      n: "2", color: C.teal,
      title: "What you can see",
      desc: "Runtime traces and execution timelines. An inventory of every AI system. Capabilities, dependencies, and findings per system. Security signals, cost signals, and guardrail observations — all derived from observed behavior.",
      note: "Everything appears automatically once data flows. No manual registration, no tagging.",
      cta: "Open Runtime →", page: "runtime",
    },
    {
      n: "3", color: C.riskLow,
      title: "What to do next",
      desc: "Send OpenTelemetry traces from one AI service. Then open Runtime to see traces, Asset Intelligence to see discovered AI systems, and Guardrails to see advisory observations. Check Security and Cost Intelligence for risky or heavy systems.",
      note: "Optional: review and assign owners to discovered systems in Governance Readiness when you're ready.",
      cta: "Open Asset Intelligence →", page: "intelligence",
    },
    {
      n: "4", color: C.purple,
      title: "Invite your team",
      desc: "Add engineers, security, and FinOps colleagues as Viewers or Analysts. Each sees the AI systems their team owns and where they need attention.",
      note: null, cta: "Manage Users →", page: "users",
    },
  ];

  return (
    <div style={{ maxWidth: 940, margin: "0 auto", fontFamily: FONT.ui, display: "flex", flexDirection: "column", gap: 30 }}>

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <div style={{ padding: bp.isMobile ? "26px 22px" : "38px 42px", background: C.surface,
        border: `1px solid ${C.border}`, borderRadius: RADIUS.lg, position: "relative", overflow: "hidden" }}>
        <div style={{ position: "absolute", top: -70, right: -70, width: 300, height: 300, borderRadius: "50%",
          background: `${C.accent}06`, pointerEvents: "none" }} />
        <div style={{ ...microLabel, color: C.accent, marginBottom: 14 }}>ObserveAgents · Runtime visibility & control for AI agents</div>
        <div style={{ fontSize: bp.isMobile ? 23 : 31, fontWeight: 700, color: C.text, marginBottom: 14, lineHeight: 1.18, letterSpacing: "-0.02em" }}>
          See your real AI footprint.<br />
          <span style={{ color: C.accent }}>No manual registration needed.</span>
        </div>
        <div style={{ fontSize: 14.5, color: C.textDim, lineHeight: 1.75, maxWidth: 580, marginBottom: 24 }}>
          Observe connects signals from your AI systems and turns them into a clear view of what is
          running, what it uses, and what needs attention — from the systems your teams built
          intentionally to the shadow AI nobody knew about.
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          {surfaceAllowsPage("integrations") && (
            <button onClick={() => onNavigate("integrations")}
              style={{ background: C.accent, color: C.accentInk, border: "none", borderRadius: RADIUS.sm,
                padding: "11px 22px", fontSize: 13, fontWeight: 700, fontFamily: FONT.ui, cursor: "pointer" }}>
              Get Data Flowing →
            </button>
          )}
          {surfaceAllowsPage("intelligence") && (
            <button onClick={() => onNavigate("intelligence")}
              style={{ background: "transparent", color: C.text, border: `1px solid ${C.border}`,
                borderRadius: RADIUS.sm, padding: "11px 22px", fontSize: 13, fontWeight: 600, fontFamily: FONT.ui, cursor: "pointer" }}>
              Open Asset Intelligence
            </button>
          )}
        </div>
      </div>

      {/* ── How ObserveAgents works ─────────────────────────────────────── */}
      <Section label="How ObserveAgents works">
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: RADIUS.md, padding: "22px 26px" }}>
          <div style={{ fontSize: 13, color: C.textDim, lineHeight: 1.75, maxWidth: 720, marginBottom: 16 }}>
            ObserveAgents starts with OpenTelemetry runtime evidence. AI systems send OTLP traces into
            Runtime, where spans and signals reveal what agents actually do. That evidence powers Asset
            Intelligence, Security Intelligence, and Detection Rules. When an agent shows risk, cost,
            reliability, or governance signals, it can be reviewed in the Gateway Control Center with
            recommended controls — observe-only until explicitly configured.
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
            {FLOW_STEPS.map((step, i) => (
              <Fragment key={step}>
                <span style={{ fontSize: 11, fontFamily: FONT.mono, color: C.text,
                  background: C.surfaceRaised, border: `1px solid ${C.border}`, borderRadius: RADIUS.sm,
                  padding: "5px 11px", whiteSpace: "nowrap" }}>{step}</span>
                {i < FLOW_STEPS.length - 1 && <span style={{ color: C.textMute, fontSize: 11 }}>→</span>}
              </Fragment>
            ))}
          </div>
          <div style={{ fontSize: 12, fontFamily: FONT.mono, color: C.accent }}>
            Observe first. Control only what matters.
          </div>
        </div>
      </Section>

      {/* ── Trace discovered ─────────────────────────────────────────────── */}
      <Section label="Trace discovered">
        <div style={{ background: `${C.teal}07`, border: `1px solid ${C.teal}22`, borderRadius: RADIUS.md,
          padding: "22px 26px", display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(260px,1fr))", gap: 14 }}>
          {discoveredItems.map((item) => (
            <div key={item.label} style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
              <div style={{ fontSize: 16, color: item.color, flexShrink: 0, marginTop: 1 }}>{item.icon}</div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: C.text, marginBottom: 3 }}>{item.label}</div>
                <div style={{ fontSize: 11, color: C.textDim, lineHeight: 1.55 }}>{item.detail}</div>
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* ── Getting started (copy unchanged) ─────────────────────────────── */}
      <Section label="Getting started">
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: RADIUS.md, overflow: "hidden" }}>
          {steps.map((s, i) => (
            <div key={s.n} style={{ display: "flex", borderBottom: i < steps.length - 1 ? `1px solid ${C.border}` : "none" }}>
              <div style={{ width: 54, display: "flex", justifyContent: "center", paddingTop: 20, flexShrink: 0, borderRight: `1px solid ${C.border}` }}>
                <div style={{ width: 30, height: 30, borderRadius: "50%", background: `${s.color}15`, border: `1px solid ${s.color}40`,
                  display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 700, color: s.color, fontFamily: FONT.mono }}>
                  {s.n}
                </div>
              </div>
              <div style={{ flex: 1, minWidth: 0, padding: bp.isMobile ? "14px 14px" : "18px 22px" }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: C.text, marginBottom: 6 }}>{s.title}</div>
                <div style={{ fontSize: 12, color: C.textDim, lineHeight: 1.65, marginBottom: (s.sdks || s.note) ? 8 : 0 }}>{s.desc}</div>
                {s.sdks && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 4 }}>
                    {s.sdks.map((sdk) => <StatusPill key={sdk} tone={s.color}>✓ {sdk}</StatusPill>)}
                  </div>
                )}
                {s.note && (
                  <div style={{ fontSize: 11, color: C.textMute, lineHeight: 1.55, borderLeft: `2px solid ${s.color}33`, paddingLeft: 10 }}>{s.note}</div>
                )}
                {s.cta && bp.isMobile && surfaceAllowsPage(s.page) && (
                  <button onClick={() => onNavigate(s.page)}
                    style={{ marginTop: 12, background: "transparent", border: `1px solid ${C.border}`, color: s.color,
                      borderRadius: RADIUS.sm, padding: "9px 14px", fontSize: 11, fontFamily: FONT.mono, cursor: "pointer", minHeight: 44 }}>
                    {s.cta}
                  </button>
                )}
              </div>
              {s.cta && !bp.isMobile && surfaceAllowsPage(s.page) && (
                <div style={{ display: "flex", alignItems: "center", paddingRight: 20, flexShrink: 0 }}>
                  <button onClick={() => onNavigate(s.page)}
                    style={{ background: "transparent", border: `1px solid ${C.border}`, color: s.color,
                      borderRadius: RADIUS.sm, padding: "7px 14px", fontSize: 11, fontFamily: FONT.mono, cursor: "pointer", whiteSpace: "nowrap" }}>
                    {s.cta}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </Section>

      {/* ── Platform ─────────────────────────────────────────────────────── */}
      <Section label="Platform">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(260px,1fr))", gap: 12 }}>
          {features.map((f) => (
            <button key={f.page} onClick={() => onNavigate(f.page)}
              style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: RADIUS.md,
                padding: "20px", textAlign: "left", cursor: "pointer", transition: "border-color 0.15s" }}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = f.color + "55"; }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = C.border; }}>
              <div style={{ fontSize: 18, marginBottom: 10, color: f.color }}>{f.icon}</div>
              <div style={{ fontSize: 13, fontWeight: 600, color: C.text, marginBottom: 6 }}>{f.title}</div>
              <div style={{ fontSize: 11, color: C.textDim, lineHeight: 1.6 }}>{f.desc}</div>
            </button>
          ))}
        </div>
      </Section>
    </div>
  );
}
