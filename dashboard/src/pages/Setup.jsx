import React, { useState, useEffect } from "react";
import { T, FONT_UI, FONT_MONO } from "../theme.js";
import { fetchAgentsSummary, fetchRelationships, fetchProviderCredentials, fetchApiKeys } from "../api.js";
import { gatewayBaseUrl } from "../config.js";
import { useBreakpoint } from "../hooks/useBreakpoint.js";

export default function SimpleIntegrationsPage({ onNavigate, demoMode = false }) {
  const bp = useBreakpoint();
  const gatewayUrl = gatewayBaseUrl(demoMode);
  const [copied, setCopied]   = useState(null);
  const [open,   setOpen]     = useState({ sdk_openai: true, sdk_anthropic: false, sdk_env: false, manual_openai: false, manual_curl: false });
  const [section, setSection] = useState(null);
  const [metrics, setMetrics] = useState({ agents: null, dependencies: null, workflows: null, platforms: null });
  const [progress, setProgress] = useState({ provider: false, key: false, request: false, agent: false });

  const copy   = (id, text) => { navigator.clipboard.writeText(text).catch(() => {}); setCopied(id); setTimeout(() => setCopied(null), 2000); };
  const toggle = (k) => setOpen(o => ({ ...o, [k]: !o[k] }));

  useEffect(() => {
    Promise.allSettled([
      fetchAgentsSummary(), fetchRelationships(),
      fetchProviderCredentials().catch(() => []), fetchApiKeys().catch(() => []),
    ]).then(([agRes, relRes, credRes, keyRes]) => {
      const ag   = agRes.status  === "fulfilled" ? agRes.value  : null;
      const rels = relRes.status === "fulfilled" ? relRes.value : [];
      const creds = credRes.status === "fulfilled" && Array.isArray(credRes.value) ? credRes.value : [];
      const keys  = keyRes.status  === "fulfilled" && Array.isArray(keyRes.value)  ? keyRes.value  : [];
      const wfRels = (rels || []).filter(r => ["triggers_workflow", "uses_workflow"].includes(r.relationship_type));
      const platformCount = ag?.discovery_coverage ? Object.keys(ag.discovery_coverage).length : null;
      const agentCount = ag ? (ag.verified_agents?.total || 0) + (ag.potential_agents?.total || 0) : 0;
      setMetrics({
        agents:       ag ? agentCount : null,
        dependencies: Array.isArray(rels) ? rels.length : null,
        workflows:    new Set(wfRels.map(r => r.target_name)).size,
        platforms:    platformCount,
      });
      setProgress({
        provider: creds.length > 0,
        key:      keys.length > 0,
        request:  agentCount > 0,   // traffic produced at least one discovered agent
        agent:    agentCount > 0,
      });
    });
  }, []);

  const PROGRESS_STEPS = [
    { key: "key",      label: "Create API Key" },
    { key: "request",  label: "Send Traffic" },
    { key: "agent",    label: "Observe AI Systems" },
    { key: "provider", label: "Assign Ownership" },
  ];

  const fmtMetric = (v) => v === null ? "—" : String(v);

  const OPTIONS = [
    {
      id: "gateway", badge: "Recommended", color: T.info,
      title: "Runtime Discovery",
      desc:  "Observe live AI activity across your organization.",
      benefits: ["Discover active AI systems", "Build AI inventory", "Map dependencies", "Discover ownership gaps", "Surface unmanaged systems"],
      cta: "Start Here →",
    },
    {
      id: "platform", badge: "Coming later", color: T.purple,
      title: "Ecosystem Discovery",
      desc:  "Future connectors will scan GitHub, Slack, Jira, ServiceNow, and MCP for AI signals. Not live yet.",
      benefits: ["Discover GitHub, Slack, Jira, ServiceNow, and MCP signals", "Find potential AI assets", "Surface unmanaged dependencies", "Send findings for validation"],
      cta: "Preview →",
    },
  ];

  const GW_FLOW = [
    { label:"Create Organisation API Key",           color:T.accent },
    { label:"Route Traffic Through Gateway",         color:T.warn   },
    { label:"Gateway Derives Identity",              color:T.info   },
    { label:"Verified / Unassigned Agent Created",   color:T.yellow },
    { label:"Admin Reviews Agent",                   color:T.purple },
  ];
  const PLATFORM_FLOW = [
    { label:"Connect Platform",            color:T.info   },
    { label:"Scan for AI Signals",         color:T.warn   },
    { label:"Potential Agent Created",     color:T.yellow },
    { label:"Admin Validates or Rejects",  color:T.purple },
    { label:"Managed Agent",               color:T.accent },
  ];
  const GW_SIGNALS = [
    { label:"API Key Scope",       desc:"Key named after a service — no headers needed" },
    { label:"Framework Hints",     desc:"LangChain, CrewAI, AutoGen, n8n in User-Agent" },
    { label:"Request Origin",      desc:"Meaningful hostname or service label" },
    { label:"Provider Metadata",   desc:"User-Agent and client library name" },
    { label:"Stable Fingerprint",  desc:"Hash of org + key + origin — flags for review" },
  ];
  const PLATFORMS = [
    "GitHub", "n8n", "Slack", "Jira", "ServiceNow",
    "Cloud Functions", "MCP Servers", "Azure DevOps", "Zapier",
    "Copilot Studio", "Bedrock Agents", "OpenAI Agents SDK",
  ];
  const OPT_HEADERS = [
    { name:"X-Agent-Name",        desc:"Override auto-detected agent name",    example:"soc-investigation-agent" },
    { name:"X-Agent-Team",        desc:"Team or department",                   example:"Security" },
    { name:"X-Agent-Owner",       desc:"Owner email or name",                  example:"alice@acme.com" },
    { name:"X-Agent-Environment", desc:"prod / staging / dev",                 example:"prod" },
    { name:"X-Agent-Version",     desc:"Version tag",                          example:"v1.2.0" },
    { name:"X-Agent-Source",      desc:"Origin label for the attribution metadata", example:"manual" },
  ];

  const snippets = {
    sdk_openai:
`# No proprietary SDK required — use the standard OpenAI SDK.
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_GATEWAY_KEY",
    base_url="GATEWAY_URL/v1",
)

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello"}],
)`,

    sdk_anthropic:
`# Use the standard Anthropic SDK — only base_url changes.
from anthropic import Anthropic

client = Anthropic(
    api_key="YOUR_GATEWAY_KEY",
    base_url="GATEWAY_URL",
)

response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Summarise this contract"}],
)`,

    sdk_env:
`# Zero-code setup: point the standard OpenAI SDK at the gateway via env vars.
export OPENAI_API_KEY=YOUR_GATEWAY_KEY
export OPENAI_BASE_URL=GATEWAY_URL/v1

# Optional — enrich identity attribution (any OpenAI-compatible client):
export OPENAI_DEFAULT_HEADERS='{"X-Agent-Name":"customer-support-prod","X-Agent-Team":"Customer Success"}'`,

    manual_openai:
`from openai import OpenAI

client = OpenAI(base_url="GATEWAY_URL/v1", api_key="YOUR_GATEWAY_KEY")

client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello"}],
    extra_headers={
        "X-Agent-Name":        "customer-support-prod",
        "X-Agent-Team":        "Customer Success",
        "X-Agent-Environment": "prod",
    },
)`,

    manual_curl:
`curl GATEWAY_URL/v1/chat/completions \\
  -H "Authorization: Bearer YOUR_GATEWAY_KEY" \\
  -H "X-Agent-Name: customer-support-prod" \\
  -H "Content-Type: application/json" \\
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Hello"}]}'`,
  };

  const resolvedSnippets = Object.fromEntries(
    Object.entries(snippets).map(([k, v]) => [k, v.replace(/GATEWAY_URL/g, gatewayUrl)])
  );

  const FlowColumn = ({ steps }) => (
    <div style={{ display:"flex", flexDirection:"column", alignItems:"flex-start", gap:0 }}>
      {steps.map((s, i) => (
        <div key={i} style={{ display:"flex", flexDirection:"column", alignItems:"flex-start" }}>
          <div style={{ display:"flex", alignItems:"center", gap:10 }}>
            <div style={{ width:8, height:8, borderRadius:"50%", background:s.color, flexShrink:0 }} />
            <span style={{ fontSize:12, color:T.text }}>{s.label}</span>
          </div>
          {i < steps.length - 1 && (
            <div style={{ width:1, height:16, background:T.border, marginLeft:3 }} />
          )}
        </div>
      ))}
    </div>
  );

  const CodeBlock = ({ id, label, snippet, accentColor }) => (
    <div style={{ border:`1px solid ${open[id] ? (accentColor || T.accent)+"44" : T.border}`, borderRadius:8, overflow:"hidden" }}>
      <button onClick={() => toggle(id)}
        style={{ width:"100%", background:open[id] ? T.panelHi : T.panel, border:"none",
          padding:"11px 16px", display:"flex", alignItems:"center", gap:12, cursor:"pointer", textAlign:"left" }}>
        <span style={{ width:7, height:7, borderRadius:"50%", background:accentColor || T.accent, flexShrink:0 }} />
        <span style={{ fontSize:12, fontFamily:FONT_MONO, color:open[id] ? T.text : T.textDim, flex:1 }}>{label}</span>
        <span style={{ fontSize:11, fontFamily:FONT_MONO, color:T.textMute }}>{open[id] ? "▲ close" : "▼ open"}</span>
      </button>
      {open[id] && (
        <div style={{ position:"relative", borderTop:`1px solid ${T.border}` }}>
          <pre style={{ margin:0, padding:"16px", fontSize:12, fontFamily:FONT_MONO, color:T.text, lineHeight:1.7, overflow:"auto", background:T.bg, maxHeight:380 }}>{snippet}</pre>
          <button onClick={() => copy(id, snippet)}
            style={{ position:"absolute", top:8, right:8, background:"transparent", border:`1px solid ${T.border}`,
              color:copied===id?"#34d399":T.textMute, borderRadius:4, padding:"3px 10px", fontSize:10, fontFamily:FONT_MONO, cursor:"pointer" }}>
            {copied===id?"copied":"copy"}
          </button>
        </div>
      )}
    </div>
  );

  return (
    <div style={{ maxWidth:900, margin:"0 auto", padding: bp.isMobile ? "16px" : "32px 24px", fontFamily:FONT_UI }}>

      <div style={{ marginBottom:24 }}>
        <div style={{ fontSize:11, fontFamily:FONT_MONO, color:T.textMute, letterSpacing:"0.12em", textTransform:"uppercase", marginBottom:6 }}>Administration · Setup</div>
        <div style={{ fontSize:24, fontWeight:700, color:T.text, lineHeight:1.2 }}>Setup</div>
        <div style={{ fontSize:13, color:T.textDim, marginTop:6, lineHeight:1.5 }}>
          Get data flowing into Observe. After data starts flowing, open Runtime to see traces and Asset Intelligence to see discovered AI systems.
        </div>
      </div>

      {/* Setup progress */}
      <div style={{ marginBottom:28, padding:"16px 24px", background:T.panel, border:`1px solid ${T.border}`, borderRadius:10 }}>
        <div style={{ fontSize:10, fontFamily:FONT_MONO, color:T.textMute, textTransform:"uppercase", letterSpacing:"0.1em", marginBottom:14 }}>Setup progress</div>
        <div style={{ display:"flex", gap:10, flexWrap:"wrap" }}>
          {PROGRESS_STEPS.map((s, i) => {
            const done = progress[s.key];
            return (
              <div key={s.key} style={{ display:"flex", alignItems:"center", gap:8, flex:"1 1 180px" }}>
                <span style={{ width:20, height:20, borderRadius:"50%", flexShrink:0,
                  border:`1px solid ${done ? T.accent : T.border}`, background: done ? `${T.accent}22` : "transparent",
                  color: done ? T.accent : T.textMute, display:"flex", alignItems:"center", justifyContent:"center",
                  fontSize:11, fontFamily:FONT_MONO }}>{done ? "✓" : i + 1}</span>
                <span style={{ fontSize:12, color: done ? T.text : T.textDim }}>{s.label}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Connect your first AI system — the customer path to first data */}
      <div style={{ marginBottom:16, padding:"16px 24px",
        background:`${T.accent}0a`, border:`1px solid ${T.accent}33`, borderRadius:10 }}>
        <div style={{ fontSize:13, fontWeight:600, color:T.text, marginBottom:6 }}>
          Connect your first AI system
        </div>
        <div style={{ fontSize:12, color:T.textDim, lineHeight:1.7, maxWidth:680, marginBottom:12 }}>
          Start by sending OpenTelemetry traces from one AI service. Once traces arrive, Observe discovers
          the AI system, shows its runtime timeline, and generates Asset Intelligence.
        </div>
        <ol style={{ margin:"0 0 14px", paddingLeft:20, fontSize:12, color:T.textDim, lineHeight:1.9 }}>
          <li>Create or copy an API key.</li>
          <li>Configure your OpenTelemetry exporter to send traces to <code style={{ fontFamily:FONT_MONO, fontSize:11, color:T.accent }}>POST /otel/v1/traces</code>.</li>
          <li>Open Runtime to confirm traces are arriving.</li>
          <li>Open Asset Intelligence to review discovered systems, capabilities, and findings.</li>
          <li>Add more teams, services, and integrations over time.</li>
        </ol>
        <button
          onClick={() => setSection(s => s === "gateway" ? null : "gateway")}
          style={{ background:T.accent, color:"#000", border:"none", borderRadius:6,
            padding:"9px 20px", fontSize:12, fontWeight:600, fontFamily:FONT_UI, cursor:"pointer" }}>
          Start Runtime Discovery →
        </button>
      </div>

      <div style={{ background:T.panel, border:`1px solid ${T.border}`, borderRadius:10, padding:"16px 24px", marginBottom:28 }}>
        <div style={{ fontSize:10, fontFamily:FONT_MONO, color:T.textMute, textTransform:"uppercase", letterSpacing:"0.1em", marginBottom:12 }}>Currently discovered</div>
        <div style={{ display:"grid", gridTemplateColumns: bp.isMobile ? "repeat(2,1fr)" : "repeat(4,1fr)", gap: bp.isMobile ? 16 : 0 }}>
          {[
            { label:"AI Assets",        value:fmtMetric(metrics.agents),       color:T.accent },
            { label:"Dependencies",      value:fmtMetric(metrics.dependencies), color:"#5BD9C5" },
            { label:"Workflows",         value:fmtMetric(metrics.workflows),    color:T.warn },
            { label:"Discovery Sources", value:fmtMetric(metrics.platforms),    color:T.info },
          ].map((m, i) => (
            <div key={m.label} style={{ padding: bp.isMobile ? 0 : "0 20px 0 0", borderRight: !bp.isMobile && i < 3 ? `1px solid ${T.border}` : "none", marginRight: !bp.isMobile && i < 3 ? 20 : 0 }}>
              <div style={{ fontSize:26, fontWeight:700, color:m.color, fontFamily:FONT_MONO, letterSpacing:"-0.02em", lineHeight:1 }}>{m.value}</div>
              <div style={{ fontSize:11, color:T.textMute, marginTop:5 }}>{m.label}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ fontSize:10, fontFamily:FONT_MONO, color:T.textMute, letterSpacing:"0.12em", textTransform:"uppercase", marginBottom:14 }}>Setup options</div>
      <div style={{ display:"grid", gridTemplateColumns: bp.isMobile ? "1fr" : "repeat(2,1fr)", gap:14, marginBottom: section ? 20 : 0 }}>
        {OPTIONS.map(opt => (
          <div key={opt.id}
            style={{ background:T.panel,
              border:`1px solid ${section === opt.id ? opt.color+"66" : T.border}`,
              borderRadius:10, padding:"22px 20px", display:"flex", flexDirection:"column", gap:14,
              transition:"border-color 0.15s" }}>
            <div style={{ display:"flex", alignItems:"flex-start", justifyContent:"space-between", gap:8 }}>
              <div style={{ fontSize:14, fontWeight:700, color:T.text, lineHeight:1.3 }}>{opt.title}</div>
              {opt.badge && (
                <span style={{ background:`${opt.color}18`, color:opt.color, border:`1px solid ${opt.color}44`,
                  fontSize:9, fontFamily:FONT_MONO, padding:"2px 8px", borderRadius:3,
                  textTransform:"uppercase", letterSpacing:"0.1em", flexShrink:0 }}>{opt.badge}</span>
              )}
            </div>
            <div style={{ fontSize:12, color:T.textDim, lineHeight:1.65 }}>{opt.desc}</div>
            <ul style={{ margin:0, padding:"0 0 0 14px", display:"flex", flexDirection:"column", gap:5 }}>
              {opt.benefits.map(b => (
                <li key={b} style={{ fontSize:11, color:T.textDim, lineHeight:1.5 }}>{b}</li>
              ))}
            </ul>
            <button
              onClick={() => setSection(s => s === opt.id ? null : opt.id)}
              style={{ marginTop:"auto", background:`${opt.color}14`, border:`1px solid ${opt.color}44`,
                color:opt.color, borderRadius:6, padding:"9px 14px", fontSize:12,
                fontFamily:FONT_MONO, cursor:"pointer", fontWeight:600, textAlign:"center" }}>
              {section === opt.id ? "▲ Collapse" : opt.cta}
            </button>
          </div>
        ))}
      </div>

      {section === "gateway" && (
        <div style={{ border:`1px solid ${T.info}44`, borderRadius:10, padding:"24px 28px", marginBottom:16 }}>
          <div style={{ fontSize:13, fontWeight:600, color:T.text, marginBottom:16 }}>Runtime Discovery — Integration Guide</div>
          <div style={{ fontSize:12, color:T.textDim, lineHeight:1.7, marginBottom:14 }}>
            Integrations are <strong style={{ color:T.text }}>discovery and evidence sources</strong>. Runtime Discovery accepts evidence from{" "}
            <strong style={{ color:T.text }}>OpenTelemetry (OTLP)</strong> and the <strong style={{ color:T.text }}>gateway</strong> —
            Ecosystem Discovery (GitHub, Jira, Slack, n8n, MCP) is next on the roadmap.
          </div>

          {/* OpenTelemetry — evidence source */}
          <div style={{ background:`${T.purple}0d`, border:`1px solid ${T.purple}33`, borderRadius:8, padding:"14px 16px", marginBottom:18 }}>
            <div style={{ fontSize:11, fontFamily:FONT_MONO, color:T.purple, textTransform:"uppercase", letterSpacing:"0.1em", marginBottom:8 }}>OpenTelemetry (OTLP) — no gateway required</div>
            <div style={{ fontSize:12, color:T.textDim, lineHeight:1.7, marginBottom:10 }}>
              Already instrumented with OTel? Point your exporter at{" "}
              <code style={{ fontFamily:FONT_MONO, color:T.accent, fontSize:11 }}>POST {gatewayUrl.replace(/\/v1$/, "")}/otel/v1/traces</code>{" "}
              and AI systems, dependencies, and execution timelines appear automatically. Prompt and response content is never stored.
            </div>
            <pre style={{ margin:0, padding:"10px 12px", background:T.panel, border:`1px solid ${T.border}`, borderRadius:6, fontFamily:FONT_MONO, fontSize:11, color:T.textDim, overflowX:"auto" }}>
{`OTEL_EXPORTER_OTLP_ENDPOINT=${gatewayUrl.replace(/\/v1$/, "")}/otel
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer gk-<your-api-key>
OTEL_SERVICE_NAME=my-agent
OTEL_RESOURCE_ATTRIBUTES=deployment.environment=production`}
            </pre>
          </div>

          <div style={{ fontSize:12, color:T.textDim, lineHeight:1.7, marginBottom:14 }}>
            <strong style={{ color:T.text }}>Gateway path — no proprietary SDK required.</strong> Change your AI client's{" "}
            <code style={{ fontFamily:FONT_MONO, color:T.info, fontSize:11 }}>base_url</code> to{" "}
            <code style={{ fontFamily:FONT_MONO, color:T.accent, fontSize:11 }}>{gatewayUrl}/v1</code>, replace your{" "}
            <code style={{ fontFamily:FONT_MONO, color:T.info, fontSize:11 }}>api_key</code> with a Gateway API Key, and send traffic. No instrumentation, no code rewrite.
          </div>
          <div style={{ display:"flex", flexWrap:"wrap", gap:6, marginBottom:20 }}>
            <span style={{ fontSize:10, fontFamily:FONT_MONO, color:T.textMute, alignSelf:"center", marginRight:4 }}>WORKS WITH</span>
            {["OpenAI SDK","LangChain","CrewAI","LiteLLM","OpenAI Agents SDK","MCP Clients","Vercel AI SDK","Agno","PydanticAI"].map(s => (
              <span key={s} style={{ fontSize:11, fontFamily:FONT_MONO, color:T.accent, background:`${T.accent}12`, border:`1px solid ${T.accent}33`, borderRadius:4, padding:"2px 8px" }}>✓ {s}</span>
            ))}
          </div>
          <div style={{ display:"grid", gridTemplateColumns: bp.isMobile ? "1fr" : "1fr 1fr", gap:24, marginBottom:20 }}>
            <div>
              <div style={{ fontSize:10, fontFamily:FONT_MONO, color:T.textMute, textTransform:"uppercase", letterSpacing:"0.1em", marginBottom:10 }}>Setup flow</div>
              <FlowColumn steps={GW_FLOW} />
            </div>
            <div>
              <div style={{ fontSize:10, fontFamily:FONT_MONO, color:T.textMute, textTransform:"uppercase", letterSpacing:"0.1em", marginBottom:10 }}>Identity signals (priority order)</div>
              {GW_SIGNALS.map((s, i) => (
                <div key={i} style={{ display:"flex", gap:8, padding:"6px 0", borderBottom:`1px solid ${T.border}`, fontSize:12 }}>
                  <span style={{ color:T.textMute, fontFamily:FONT_MONO, fontSize:11, minWidth:16, flexShrink:0 }}>{i+1}.</span>
                  <div>
                    <span style={{ color:T.text, fontWeight:600 }}>{s.label}</span>
                    <span style={{ color:T.textDim, marginLeft:8 }}>{s.desc}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div style={{ background:`${T.info}0d`, border:`1px solid ${T.info}33`, borderRadius:8, padding:"12px 16px" }}>
            <div style={{ fontSize:12, color:T.textDim, lineHeight:1.65 }}>
              <strong style={{ color:T.text }}>Minimum setup:</strong> change <code style={{ fontFamily:FONT_MONO, color:T.info, fontSize:11 }}>base_url</code> to{" "}
              <code style={{ fontFamily:FONT_MONO, color:T.accent, fontSize:11 }}>{gatewayUrl}/v1</code> and use your org API key.
            </div>
          </div>

          {/* Gateway client examples — standard third-party clients, no code rewrite */}
          <div style={{ marginTop:28, borderTop:`1px solid ${T.border}`, paddingTop:24 }}>
            <div style={{ fontSize:10, fontFamily:FONT_MONO, color:T.textMute, textTransform:"uppercase", letterSpacing:"0.1em", marginBottom:10 }}>Client Examples</div>
            <div style={{ fontSize:12, color:T.textDim, lineHeight:1.7, marginBottom:14 }}>
              Point your existing client at the gateway — change <code style={{ fontFamily:FONT_MONO, color:T.info, fontSize:11 }}>base_url</code> and the API key, nothing else.
            </div>
            <div style={{ display:"flex", flexDirection:"column", gap:8, marginBottom:20 }}>
              <CodeBlock id="sdk_openai"    label="Python · OpenAI client"    snippet={resolvedSnippets.sdk_openai}    accentColor={T.info} />
              <CodeBlock id="sdk_anthropic" label="Python · Anthropic client" snippet={resolvedSnippets.sdk_anthropic} accentColor={T.info} />
              <CodeBlock id="sdk_env"       label="Env-var only (no code)"    snippet={resolvedSnippets.sdk_env}       accentColor={T.info} />
            </div>
            <div style={{ background:`${T.warn}08`, border:`1px solid ${T.warn}22`, borderRadius:8, padding:"14px 18px" }}>
              <div style={{ fontSize:11, fontFamily:FONT_MONO, color:T.warn, textTransform:"uppercase", letterSpacing:"0.1em", marginBottom:8 }}>Advanced — Manual Headers</div>
              <div style={{ display:"flex", flexDirection:"column", gap:6, marginBottom:14 }}>
                <CodeBlock id="manual_openai" label="Manual headers · OpenAI" snippet={resolvedSnippets.manual_openai} accentColor={T.warn} />
                <CodeBlock id="manual_curl"   label="Manual headers · cURL"   snippet={resolvedSnippets.manual_curl}   accentColor={T.warn} />
              </div>
              <div style={{ background:T.panel, border:`1px solid ${T.border}`, borderRadius:6, overflowX:"auto", WebkitOverflowScrolling:"touch" }}>
                <table style={{ width:"100%", borderCollapse:"collapse", minWidth:460 }}>
                  <thead>
                    <tr style={{ background:T.panelHi }}>
                      {["Header","Description","Example"].map(h => (
                        <th key={h} style={{ padding:"7px 12px", textAlign:"left", fontSize:10, fontFamily:FONT_MONO, color:T.textMute, letterSpacing:"0.1em", textTransform:"uppercase", borderBottom:`1px solid ${T.border}` }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {OPT_HEADERS.map((row, i) => (
                      <tr key={row.name} style={{ background: i % 2 === 0 ? T.panel : T.bg }}>
                        <td style={{ padding:"7px 12px", borderBottom:`1px solid ${T.border}` }}>
                          <code style={{ fontSize:11, fontFamily:FONT_MONO, color:T.textDim }}>{row.name}</code>
                        </td>
                        <td style={{ padding:"7px 12px", borderBottom:`1px solid ${T.border}`, fontSize:11, color:T.textDim }}>{row.desc}</td>
                        <td style={{ padding:"7px 12px", borderBottom:`1px solid ${T.border}` }}>
                          <code style={{ fontSize:11, fontFamily:FONT_MONO, color:T.textMute }}>{row.example}</code>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}

      {section === "platform" && (
        <div style={{ border:`1px solid ${T.purple}44`, borderRadius:10, padding:"24px 28px", marginBottom:16 }}>
          <div style={{ fontSize:13, fontWeight:600, color:T.text, marginBottom:16 }}>Ecosystem Discovery — Preview</div>
          <div style={{ background:`${T.purple}12`, border:`1px solid ${T.purple}33`, borderRadius:6, padding:"10px 14px", marginBottom:14, fontSize:12, color:T.textDim }}>
            <span style={{ fontFamily:FONT_MONO, fontSize:10, letterSpacing:"0.1em", textTransform:"uppercase", color:T.purple, fontWeight:600, marginRight:8 }}>Coming later</span>
            These connectors are on the roadmap and not live yet. This preview shows how they will work.
          </div>
          <div style={{ fontSize:12, color:T.textDim, lineHeight:1.7, marginBottom:20 }}>
            Ecosystem Discovery will identify AI signals across your tooling — GitHub, Slack, Jira, ServiceNow, and MCP servers — indexed alongside runtime traffic.
          </div>
          <div style={{ display:"grid", gridTemplateColumns: bp.isMobile ? "1fr" : "1fr 1fr", gap:24, marginBottom:20 }}>
            <div>
              <div style={{ fontSize:10, fontFamily:FONT_MONO, color:T.textMute, textTransform:"uppercase", letterSpacing:"0.1em", marginBottom:10 }}>Discovery flow</div>
              <FlowColumn steps={PLATFORM_FLOW} />
            </div>
            <div>
              <div style={{ fontSize:10, fontFamily:FONT_MONO, color:T.textMute, textTransform:"uppercase", letterSpacing:"0.1em", marginBottom:10 }}>Supported platforms</div>
              <div style={{ display:"flex", flexWrap:"wrap", gap:6, marginBottom:14 }}>
                {PLATFORMS.map(p => (
                  <span key={p} style={{ background:T.panelHi, border:`1px solid ${T.border}`, color:T.textDim, fontSize:11, fontFamily:FONT_MONO, padding:"3px 10px", borderRadius:4 }}>{p}</span>
                ))}
              </div>
            </div>
          </div>
          <button onClick={() => onNavigate("ecosystem")}
            style={{ background:`${T.purple}14`, border:`1px solid ${T.purple}44`, color:T.purple,
              borderRadius:6, padding:"9px 18px", fontSize:12, fontFamily:FONT_MONO, cursor:"pointer", fontWeight:600 }}>
            View Connected Platforms →
          </button>
        </div>
      )}

    </div>
  );
}
