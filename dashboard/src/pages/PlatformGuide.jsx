import React from "react";
import { T, FONT_UI, FONT_MONO } from "../theme.js";
import { useBreakpoint } from "../hooks/useBreakpoint.js";

export default function CustomerWelcomePage({ onNavigate }) {
  const bp = useBreakpoint();
  const discoveredItems = [
    { icon: "◈", color: T.accent,  label: "AI Agents",         detail: "Every agent making LLM calls — named, attributed to a team." },
    { icon: "🔗", color: T.teal,   label: "Dependencies",      detail: "MCP servers, tools, APIs, and databases per agent." },
    { icon: "⊞", color: T.info,   label: "Models in use",     detail: "Every model variant across all providers." },
    { icon: "⚡", color: T.yellow, label: "Workflows",         detail: "n8n, Zapier, LangGraph — discovered automatically." },
    { icon: "⊙", color: T.purple,  label: "Unmanaged Agents",  detail: "AI systems outside official channels — surfaced and reviewed." },
    { icon: "⊕", color: T.info,    label: "Ecosystem Signals", detail: "GitHub, Jira, Slack, ServiceNow, MCP signals." },
  ];

  const features = [
    { icon: "◈", color: T.accent,  title: "Inventory",          page: "agent_inventory",  desc: "Discover AI assets automatically. Track ownership, teams, models, and environments." },
    { icon: "🔗", color: T.teal,   title: "Relationships",      page: "relationship_map",  desc: "Map dependencies between agents, workflows, tools, providers, and teams." },
    { icon: "⊙", color: T.yellow,  title: "Discovery",          page: "discovery",         desc: "Surface observed AI systems and ecosystem signals. Review and classify in one place." },
    { icon: "⊛", color: T.info,    title: "Governance",         page: "governance",        desc: "Apply policies, budgets, access rules, and organizational controls." },
    { icon: "$", color: T.accent,  title: "Costs",              page: "cost",              desc: "Track spend, token usage, provider usage, budgets, and trends." },
    { icon: "⚑", color: T.crit,   title: "Security",           page: "security_intel",    desc: "Monitor activity, audit usage, and manage access risks." },
  ];

  const steps = [
    {
      n: "1", color: T.accent,
      title: "Connect a provider",
      desc: "Route AI traffic through ObserveAgents. No instrumentation required — use your existing SDK.",
      note: null,
      sdks: ["OpenAI SDK", "LangChain", "CrewAI", "LiteLLM", "OpenAI Agents SDK", "MCP Clients", "Vercel AI SDK", "Agno", "any OpenAI-compatible client"],
      cta: "See Integration Guide →", page: "integrations",
    },
    {
      n: "2", color: T.teal,
      title: "Discovery starts automatically",
      desc: "Agents, models, and dependencies appear as traffic flows. No registration required.",
      note: null,
      cta: "View Discovery Center →", page: "discovery",
    },
    {
      n: "3", color: T.info,
      title: "Review and assign ownership",
      desc: "Agents surface in the Governance Center. Assign owners and promote to managed — or reject what shouldn't be running.",
      note: null,
      cta: "Open Governance →", page: "governance",
    },
    {
      n: "4", color: T.purple,
      title: "Invite your team",
      desc: "Add team members as Viewers or Analysts. Each sees what their team owns.",
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
          textTransform:"uppercase", marginBottom:12 }}>Platform Overview</div>

        <div style={{ fontSize: bp.isMobile ? 22 : 32, fontWeight:700, color:T.text, marginBottom:14, lineHeight:1.15 }}>
          Connect traffic once.<br/>
          <span style={{ color:T.accent }}>Your inventory builds itself.</span>
        </div>

        <div style={{ fontSize:15, color:T.textDim, lineHeight:1.75, maxWidth:580, marginBottom:28 }}>
          Route AI traffic through ObserveAgents and your inventory builds automatically — agents, dependencies, and ownership mapped as activity happens.
        </div>

        <div style={{ display:"flex", gap:10, flexWrap:"wrap" }}>
          <button onClick={() => onNavigate("integrations")}
            style={{ background:T.accent, color:"#000", border:"none", borderRadius:6,
              padding:"11px 24px", fontSize:13, fontWeight:700, fontFamily:FONT_UI, cursor:"pointer" }}>
            Connect Traffic →
          </button>
          <button onClick={() => onNavigate("agent_inventory")}
            style={{ background:"transparent", color:T.text, border:`1px solid ${T.border}`,
              borderRadius:6, padding:"11px 24px", fontSize:13, fontWeight:600, fontFamily:FONT_UI, cursor:"pointer" }}>
            View Agent Inventory
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
          textTransform:"uppercase", marginBottom:16 }}>◆ Discovered automatically</div>
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
        textTransform:"uppercase", marginBottom:14 }}>Getting started</div>
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
        textTransform:"uppercase", marginBottom:14 }}>Platform</div>
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
