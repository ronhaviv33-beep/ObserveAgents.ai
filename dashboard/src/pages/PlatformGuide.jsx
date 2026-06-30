import React from "react";
import { T, FONT_UI, FONT_MONO } from "../theme.js";

export default function CustomerWelcomePage({ onNavigate }) {
  const discoveredItems = [
    { icon: "◈", color: T.accent,  label: "AI systems",         detail: "Every AI system making model calls — named, fingerprinted, attributed to a team" },
    { icon: "🔗", color: T.teal,   label: "Runtime dependencies", detail: "MCP servers, tools, APIs, databases, and CRMs each AI system touches at runtime" },
    { icon: "⊞", color: T.info,   label: "Models in use",     detail: "Every model variant across OpenAI, Anthropic, and other providers" },
    { icon: "⚡", color: T.yellow, label: "Workflows",         detail: "n8n, Zapier, LangGraph, and orchestration chains discovered automatically" },
    { icon: "⊙", color: T.purple,  label: "Unmanaged AI",      detail: "AI that appeared outside official channels — surfaced before it becomes a risk" },
    { icon: "$",  color: T.accent,  label: "Cost attribution",  detail: "Spend by team, AI system, and model — no manual tagging needed" },
  ];

  const features = [
    { icon: "◈", color: T.accent,  title: "AI Inventory",             page: "agent_inventory",  desc: "Every AI system that has touched your traffic — automatically catalogued, attributed to a team, and tracked over time." },
    { icon: "🔗", color: T.teal,   title: "Runtime Dependency Map",   page: "relationship_map",  desc: "Automatically maps what every AI system touches at runtime — MCP servers, tools, workflows, APIs, and CRMs." },
    { icon: "⊙", color: T.yellow,  title: "Discovery Center",         page: "discovery",         desc: "Surface AI systems and automations created outside official channels — before they become a risk." },
    { icon: "⊛", color: T.info,    title: "Governance Center",        page: "governance",        desc: "Review newly discovered AI systems, assign owners, and enforce policies — without slowing teams down." },
    { icon: "$", color: T.accent,  title: "Cost Intelligence",        page: "cost",              desc: "See how much each team and AI system spends on AI APIs. No manual tagging required." },
    { icon: "⚑", color: T.crit,   title: "Security Intelligence",    page: "security_intel",    desc: "Alerts on unusual activity, prompt-injection attempts, and policy violations — detected automatically." },
  ];

  const steps = [
    {
      n: "1", color: T.accent,
      title: "Runtime Discovery — observe live AI activity",
      desc: "Route AI traffic through the gateway using your existing stack — replace base_url and api_key, no code rewrite. The platform observes active AI systems, the models they use, and the tools, APIs, and databases they touch at runtime.",
      note: "Works with OpenAI SDK, LangChain, CrewAI, LiteLLM, OpenAI Agents SDK, MCP Clients, and any OpenAI-compatible client. SDK metadata is optional and improves identity quality.",
      cta: "Start Runtime Discovery →", page: "integrations",
    },
    {
      n: "2", color: T.purple,
      title: "Ecosystem Discovery — find AI outside runtime traffic",
      desc: "Connect enterprise tools — GitHub, Slack, Jira, ServiceNow, n8n, MCP servers, Copilot Studio, cloud functions — to surface AI activity, workflows, and automations that never touch the gateway.",
      note: "Findings are surfaced as potential AI systems and sent for review — no manual registration required.",
      cta: "Connect Ecosystem Sources →", page: "ecosystem",
    },
    {
      n: "3", color: T.info,
      title: "Review, assign ownership, and govern",
      desc: "Discovered AI systems appear for review. Assign owners, add context, and promote them to managed — or dismiss signals that aren't real AI systems. Unmanaged AI and ownership gaps are surfaced so nothing runs without an owner.",
      note: "Historical telemetry is never modified — review only writes ownership and governance metadata.",
      cta: "Open Governance →", page: "governance",
    },
    {
      n: "4", color: T.teal,
      title: "Invite your team",
      desc: "Add engineering, security, and FinOps colleagues as Viewers or Analysts. Each sees the AI systems their team owns and the spend they're responsible for.",
      note: null, cta: "Manage Users →", page: "users",
    },
  ];

  return (
    <div style={{ maxWidth:900, margin:"0 auto", padding:"32px 24px", fontFamily:FONT_UI }}>

      {/* Hero */}
      <div style={{ marginBottom:32, padding:"40px 44px", background:T.panel,
        border:`1px solid ${T.border}`, borderRadius:12, position:"relative", overflow:"hidden" }}>
        <div style={{ position:"absolute", top:-60, right:-60, width:280, height:280, borderRadius:"50%",
          background:`${T.accent}06`, pointerEvents:"none" }} />
        <div style={{ position:"absolute", bottom:-40, left:-40, width:180, height:180, borderRadius:"50%",
          background:`${T.teal}05`, pointerEvents:"none" }} />

        <div style={{ fontSize:11, fontFamily:FONT_MONO, color:T.accent, letterSpacing:"0.15em",
          textTransform:"uppercase", marginBottom:12 }}>ObserveAgents · Enterprise AI Intelligence Platform</div>

        <div style={{ fontSize:32, fontWeight:700, color:T.text, marginBottom:14, lineHeight:1.15 }}>
          Know every AI system in your organization.<br/>
          <span style={{ color:T.accent }}>Two discovery engines build the inventory for you.</span>
        </div>

        <div style={{ fontSize:15, color:T.textDim, lineHeight:1.75, maxWidth:600, marginBottom:10 }}>
          <strong style={{ color:T.text }}>Runtime Discovery</strong> observes live AI activity through the gateway.
          <strong style={{ color:T.text }}> Ecosystem Discovery</strong> finds AI signals across your enterprise tools.
          Together they answer: what AI exists, what it's doing, what it can access, who owns it, and what risk it creates.
        </div>
        <div style={{ fontSize:13, color:T.textMute, lineHeight:1.6, maxWidth:560, marginBottom:28 }}>
          Built for engineering, security, and operations teams managing AI at scale — from the systems your teams
          built intentionally to the unmanaged AI that appeared without anyone knowing. No manual registration, no tagging spreadsheets.
        </div>

        <div style={{ display:"flex", gap:10, flexWrap:"wrap" }}>
          <button onClick={() => onNavigate("integrations")}
            style={{ background:T.accent, color:"#000", border:"none", borderRadius:6,
              padding:"11px 24px", fontSize:13, fontWeight:700, fontFamily:FONT_UI, cursor:"pointer" }}>
            Start Runtime Discovery →
          </button>
          <button onClick={() => onNavigate("agent_inventory")}
            style={{ background:"transparent", color:T.text, border:`1px solid ${T.border}`,
              borderRadius:6, padding:"11px 24px", fontSize:13, fontWeight:600, fontFamily:FONT_UI, cursor:"pointer" }}>
            View AI Inventory
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
          textTransform:"uppercase", marginBottom:16 }}>◆ Discovered automatically — no manual work required</div>
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
        textTransform:"uppercase", marginBottom:14 }}>How it works · two discovery engines</div>
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
            <div style={{ flex:1, padding:"18px 22px 18px 22px" }}>
              <div style={{ fontSize:14, fontWeight:600, color:T.text, marginBottom:6 }}>{s.title}</div>
              <div style={{ fontSize:12, color:T.textDim, lineHeight:1.65, marginBottom: s.note ? 8 : 0 }}>{s.desc}</div>
              {s.note && (
                <div style={{ fontSize:11, color:T.textMute, lineHeight:1.55,
                  borderLeft:`2px solid ${s.color}33`, paddingLeft:10 }}>{s.note}</div>
              )}
            </div>
            {s.cta && (
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
