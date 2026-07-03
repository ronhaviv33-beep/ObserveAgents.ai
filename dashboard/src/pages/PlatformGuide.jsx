import React from "react";
import { T, FONT_UI, FONT_MONO } from "../theme.js";
import { useBreakpoint } from "../hooks/useBreakpoint.js";

export default function CustomerWelcomePage({ onNavigate }) {
  const bp = useBreakpoint();
  const discoveredItems = [
    { icon: "◈", color: T.accent,  label: "AI Agents",         detail: "Every agent making LLM calls — named, fingerprinted, attributed to a team" },
    { icon: "🔗", color: T.teal,   label: "Dependencies",      detail: "MCP servers, tools, APIs, databases, and CRMs each agent touches at runtime" },
    { icon: "⊞", color: T.info,   label: "Models in use",     detail: "Every model variant across OpenAI, Anthropic, and other providers" },
    { icon: "⚡", color: T.yellow, label: "Workflows",         detail: "n8n, Zapier, LangGraph, and orchestration chains discovered automatically" },
    { icon: "⊙", color: T.purple,  label: "Shadow AI",         detail: "Agents that appeared outside official channels — surfaced before they become a risk" },
    { icon: "$",  color: T.accent,  label: "Cost signals",      detail: "Runtime usage and cost signals by team, agent, and model — no manual tagging needed" },
  ];

  const features = [
    { icon: "▶", color: T.accent,  title: "Runtime",                  page: "runtime",           desc: "See live AI traces and execution timelines — where every request actually spends its time." },
    { icon: "◈", color: T.purple,  title: "Asset Intelligence",       page: "intelligence",      desc: "Understand every AI system: its models, tools, dependencies, capabilities, and findings — grouped in one place." },
    { icon: "⚑", color: T.crit,   title: "Security Intelligence",    page: "security_intel",    desc: "Find risky runtime behavior like database access, MCP usage, external APIs, and broad tool access." },
    { icon: "$", color: T.accent,  title: "Cost Intelligence",        page: "cost",              desc: "Spot heavy, slow, or potentially expensive AI workflows. Usage signals, not exact billing." },
    { icon: "⊛", color: T.info,    title: "Guardrails",               page: "guardrails",        desc: "Start in observe-only mode: detect, explain, and recommend — without blocking production AI." },
    { icon: "🔗", color: T.teal,   title: "Dependency Map",           page: "relationship_map",  desc: "See what every AI system connects to — MCP servers, tools, workflows, APIs, and databases." },
  ];

  const steps = [
    {
      n: "1", color: T.accent,
      title: "How data gets in",
      desc: "Send OpenTelemetry traces to the OTLP endpoint, or route AI traffic through the gateway. Both work with your existing stack — no proprietary SDK required. Ecosystem sources like GitHub, Jira, Slack, n8n, and MCP are coming later.",
      note: null,
      sdks: ["OpenTelemetry", "OpenAI SDK", "LangChain", "CrewAI", "LiteLLM", "MCP Clients", "Vercel AI SDK", "any OpenAI-compatible client"],
      cta: "Open Setup →", page: "integrations",
    },
    {
      n: "2", color: T.teal,
      title: "What you can see",
      desc: "Runtime traces and execution timelines. An inventory of every AI system. Capabilities, dependencies, and findings per system. Security signals, cost signals, and guardrail observations — all derived from observed behavior.",
      note: "Everything appears automatically once data flows. No manual registration, no tagging.",
      cta: "Open Runtime →", page: "runtime",
    },
    {
      n: "3", color: T.info,
      title: "What to do next",
      desc: "Send OpenTelemetry traces from one AI service. Then open Runtime to see traces, Asset Intelligence to see discovered AI systems, and Guardrails to see advisory observations. Check Security and Cost Intelligence for risky or heavy systems.",
      note: "Optional: review and assign owners to discovered systems in Governance Readiness when you're ready.",
      cta: "Open Asset Intelligence →", page: "intelligence",
    },
    {
      n: "4", color: T.purple,
      title: "Invite your team",
      desc: "Add engineers, security, and FinOps colleagues as Viewers or Analysts. Everyone sees the same clear picture of what AI is running and where it needs attention.",
      note: null, cta: "Manage Users →", page: "users",
    },
  ];

  return (
    <div style={{ maxWidth:900, margin:"0 auto", padding: bp.isMobile ? "16px" : "32px 24px", fontFamily:FONT_UI }}>

      {/* Hero */}
      <div style={{ marginBottom:32, padding: bp.isMobile ? "24px 20px" : "40px 44px", background:T.panel,
        border:`1px solid ${T.border}`, borderRadius:12, position:"relative", overflow:"hidden" }}>
        <div style={{ position:"absolute", top:-60, right:-60, width:280, height:280, borderRadius:"50%",
          background:`${T.accent}06`, pointerEvents:"none" }} />
        <div style={{ position:"absolute", bottom:-40, left:-40, width:180, height:180, borderRadius:"50%",
          background:`${T.teal}05`, pointerEvents:"none" }} />

        <div style={{ fontSize:11, fontFamily:FONT_MONO, color:T.accent, letterSpacing:"0.15em",
          textTransform:"uppercase", marginBottom:12 }}>ObserveAgents · Enterprise AI Intelligence Platform</div>

        <div style={{ fontSize: bp.isMobile ? 22 : 32, fontWeight:700, color:T.text, marginBottom:14, lineHeight:1.15 }}>
          See your real AI footprint.<br/>
          <span style={{ color:T.accent }}>No manual registration needed.</span>
        </div>

        <div style={{ fontSize:15, color:T.textDim, lineHeight:1.75, maxWidth:580, marginBottom:10 }}>
          Observe connects signals from your AI systems and turns them into a clear view of what is
          running, what it uses, and what needs attention. It helps teams see what AI exists, what is
          actually running, what it connects to, and where it needs attention.
        </div>
        <div style={{ fontSize:13, color:T.textMute, lineHeight:1.6, maxWidth:560, marginBottom:28 }}>
          Built for engineering and security teams managing AI at scale — from the systems your teams
          built intentionally to the shadow AI nobody knew about.
        </div>

        <div style={{ display:"flex", gap:10, flexWrap:"wrap" }}>
          <button onClick={() => onNavigate("integrations")}
            style={{ background:T.accent, color:"#000", border:"none", borderRadius:6,
              padding:"11px 24px", fontSize:13, fontWeight:700, fontFamily:FONT_UI, cursor:"pointer" }}>
            Get Data Flowing →
          </button>
          <button onClick={() => onNavigate("intelligence")}
            style={{ background:"transparent", color:T.text, border:`1px solid ${T.border}`,
              borderRadius:6, padding:"11px 24px", fontSize:13, fontWeight:600, fontFamily:FONT_UI, cursor:"pointer" }}>
            Open Asset Intelligence
          </button>
          <button onClick={() => onNavigate("discovery")}
            style={{ background:"transparent", color:T.teal, border:`1px solid ${T.teal}44`,
              borderRadius:6, padding:"11px 24px", fontSize:13, fontWeight:600, fontFamily:FONT_UI, cursor:"pointer" }}>
            Discovery Center
          </button>
        </div>
      </div>

      {/* What's discovered automatically */}
      <div style={{ marginBottom:32, padding:"24px 28px", background:`${T.teal}08`,
        border:`1px solid ${T.teal}22`, borderRadius:10 }}>
        <div style={{ fontSize:11, fontFamily:FONT_MONO, color:T.teal, letterSpacing:"0.14em",
          textTransform:"uppercase", marginBottom:16 }}>◆ Automatic Discovery — no manual work required</div>
        <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(260px,1fr))", gap:12 }}>
          {discoveredItems.map(item => (
            <div key={item.label} style={{ display:"flex", gap:12, alignItems:"flex-start" }}>
              <div style={{ fontSize:16, color:item.color, flexShrink:0, marginTop:1 }}>{item.icon}</div>
              <div>
                <div style={{ fontSize:13, fontWeight:600, color:T.text, marginBottom:2 }}>{item.label}</div>
                <div style={{ fontSize:11, color:T.textDim, lineHeight:1.55 }}>{item.detail}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Getting started */}
      <div style={{ fontSize:11, fontFamily:FONT_MONO, color:T.textMute, letterSpacing:"0.12em",
        textTransform:"uppercase", marginBottom:14 }}>How it works</div>
      <div style={{ display:"flex", flexDirection:"column", gap:0, marginBottom:32,
        background:T.panel, border:`1px solid ${T.border}`, borderRadius:10, overflow:"hidden" }}>
        {steps.map((s, i) => (
          <div key={s.n} style={{ display:"flex", gap:0,
            borderBottom: i < steps.length - 1 ? `1px solid ${T.border}` : "none" }}>
            <div style={{ width:56, display:"flex", flexDirection:"column", alignItems:"center",
              justifyContent:"flex-start", paddingTop:20, paddingBottom:20, flexShrink:0,
              borderRight:`1px solid ${T.border}` }}>
              <div style={{ width:30, height:30, borderRadius:"50%",
                background:`${s.color}15`, border:`1px solid ${s.color}40`,
                display:"flex", alignItems:"center", justifyContent:"center",
                fontSize:13, fontWeight:700, color:s.color, fontFamily:FONT_MONO }}>
                {s.n}
              </div>
            </div>
            <div style={{ flex:1, minWidth:0, padding: bp.isMobile ? "14px 14px" : "18px 22px" }}>
              <div style={{ fontSize:14, fontWeight:600, color:T.text, marginBottom:6 }}>{s.title}</div>
              <div style={{ fontSize:12, color:T.textDim, lineHeight:1.65, marginBottom: (s.sdks || s.note) ? 8 : 0 }}>{s.desc}</div>
              {s.sdks && (
                <div style={{ display:"flex", flexWrap:"wrap", gap:4, marginBottom:4 }}>
                  {s.sdks.map(sdk => (
                    <span key={sdk} style={{ fontSize:10, fontFamily:FONT_MONO, color:s.color,
                      background:`${s.color}12`, border:`1px solid ${s.color}33`,
                      borderRadius:4, padding:"2px 7px" }}>✓ {sdk}</span>
                  ))}
                </div>
              )}
              {s.note && (
                <div style={{ fontSize:11, color:T.textMute, lineHeight:1.55,
                  borderLeft:`2px solid ${s.color}33`, paddingLeft:10 }}>{s.note}</div>
              )}
              {s.cta && bp.isMobile && (
                <div style={{ marginTop:12 }}>
                  <button onClick={() => onNavigate(s.page)}
                    style={{ background:"transparent", border:`1px solid ${T.border}`, color:s.color,
                      borderRadius:5, padding:"9px 14px", fontSize:11, fontFamily:FONT_MONO,
                      cursor:"pointer", minHeight:44 }}>
                    {s.cta}
                  </button>
                </div>
              )}
            </div>
            {s.cta && !bp.isMobile && (
              <div style={{ display:"flex", alignItems:"center", paddingRight:20, flexShrink:0 }}>
                <button onClick={() => onNavigate(s.page)}
                  style={{ background:"transparent", border:`1px solid ${T.border}`, color:s.color,
                    borderRadius:5, padding:"7px 14px", fontSize:11, fontFamily:FONT_MONO,
                    cursor:"pointer", whiteSpace:"nowrap" }}>
                  {s.cta}
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Features */}
      <div style={{ fontSize:11, fontFamily:FONT_MONO, color:T.textMute, letterSpacing:"0.12em",
        textTransform:"uppercase", marginBottom:14 }}>What you get</div>
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(260px,1fr))", gap:12 }}>
        {features.map(f => (
          <button key={f.page} onClick={() => onNavigate(f.page)}
            style={{ background:T.panel, border:`1px solid ${T.border}`, borderRadius:10,
              padding:"20px", textAlign:"left", cursor:"pointer", transition:"border-color 0.15s" }}
            onMouseEnter={e => e.currentTarget.style.borderColor = f.color+"55"}
            onMouseLeave={e => e.currentTarget.style.borderColor = T.border}>
            <div style={{ fontSize:18, marginBottom:10, color:f.color }}>{f.icon}</div>
            <div style={{ fontSize:13, fontWeight:600, color:T.text, marginBottom:6 }}>{f.title}</div>
            <div style={{ fontSize:11, color:T.textDim, lineHeight:1.6 }}>{f.desc}</div>
          </button>
        ))}
      </div>

    </div>
  );
}
