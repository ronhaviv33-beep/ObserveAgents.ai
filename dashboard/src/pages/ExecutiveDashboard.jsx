import { useState, useEffect } from "react";
import {
  fetchAgentsSummary, fetchAgents,
  fetchCostIntelligence, fetchSecurityAlerts,
} from "../api.js";
import { useBreakpoint } from "../hooks/useBreakpoint.js";
import { isObservability, isGateway } from "../productSurface.js";
import CollapsiblePanel, { PanelGroupControls } from "../components/CollapsiblePanel.jsx";

const T = {
  bg: "#0A0B0F", panel: "#0F1117", panelHi: "#141823",
  border: "#1E2230", borderHi: "#2A3142",
  text: "#E8ECF4", textDim: "#7A8499", textMute: "#4B5468",
  accent: "#7CFFB2", warn: "#FFB547", crit: "#FF5C7A",
  info: "#6FA8FF", yellow: "#FFD700", purple: "#B47AFF", teal: "#5BD9C5",
};
const FONT = "'Geist','Söhne',-apple-system,sans-serif";
const MONO = "'JetBrains Mono','IBM Plex Mono',monospace";

const fmtUSD = (v) =>
  "$" + (+(v || 0)).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function KpiCard({ label, value, sub, color, onClick }) {
  const [hover, setHover] = useState(false);
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        background: T.panel,
        border: `1px solid ${hover && onClick ? T.borderHi : T.border}`,
        borderRadius: 8, padding: "20px 22px", flex: 1, minWidth: 155,
        cursor: onClick ? "pointer" : "default", transition: "border-color 0.15s",
      }}
    >
      <div style={{ fontSize: 9, fontFamily: MONO, color: T.textMute, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: 10 }}>
        {label}
      </div>
      <div style={{ fontSize: 32, fontWeight: 700, color: color || T.text, letterSpacing: "-0.03em", lineHeight: 1 }}>
        {value ?? "—"}
      </div>
      {sub && <div style={{ fontSize: 11, color: T.textMute, fontFamily: MONO, marginTop: 8 }}>{sub}</div>}
    </div>
  );
}

// Small header action button reused inside CollapsiblePanel headers on the dashboard.
const DASH_ACTION_BTN = { background: "transparent", border: `1px solid ${T.border}`, color: T.textDim, padding: "4px 12px", borderRadius: 4, fontSize: 11, fontFamily: MONO, cursor: "pointer", letterSpacing: "0.04em" };

function SectionTitle({ title, sub, action, onAction }) {
  return (
    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 16 }}>
      <div>
        <div style={{ fontSize: 14, fontWeight: 600, color: T.text }}>{title}</div>
        {sub && <div style={{ fontSize: 11, color: T.textMute, fontFamily: MONO, marginTop: 3 }}>{sub}</div>}
      </div>
      {action && (
        <button onClick={onAction} style={{ background: "transparent", border: `1px solid ${T.border}`, color: T.textDim, padding: "4px 12px", borderRadius: 4, fontSize: 11, fontFamily: MONO, cursor: "pointer", letterSpacing: "0.04em" }}>
          {action}
        </button>
      )}
    </div>
  );
}

function Panel({ children, style }) {
  return (
    <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: "20px 24px", ...style }}>
      {children}
    </div>
  );
}

export default function ExecutiveDashboard({ onNavigate }) {
  const [summary, setSummary]         = useState(null);
  const [agents, setAgents]           = useState([]);
  const [costData, setCostData]       = useState(null);
  const [alerts, setAlerts]           = useState([]);
  const [loading, setLoading]         = useState(true);
  const bp = useBreakpoint();

  useEffect(() => {
    (async () => {
      try {
        const [s, a, c, al] = await Promise.allSettled([
          fetchAgentsSummary(30),
          fetchAgents({ limit: 500 }),
          fetchCostIntelligence({ breakdown_by: "agent", days: 30 }),
          fetchSecurityAlerts(),
        ]);
        if (s.status  === "fulfilled" && s.value)  setSummary(s.value);
        if (a.status  === "fulfilled" && a.value) {
          const raw = a.value;
          setAgents(Array.isArray(raw) ? raw : raw?.agents || raw?.items || []);
        }
        if (c.status  === "fulfilled" && c.value)  setCostData(c.value);
        if (al.status === "fulfilled" && al.value)  setAlerts(Array.isArray(al.value) ? al.value : []);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 280, color: T.textMute, fontFamily: MONO, fontSize: 13 }}>
      Loading executive overview…
    </div>
  );

  // ── Derived metrics ──────────────────────────────────────────────────────────
  const total            = (summary?.verified_agents?.total ?? 0) + (summary?.potential_agents?.total ?? 0) || agents.length;
  const managed          = summary?.managed_agents ?? summary?.verified_agents?.managed ?? 0;
  // verified agents with no owner + potential agents (all need owner assignment)
  const unassigned       = (summary?.verified_agents?.unassigned ?? 0) + (summary?.potential_agents?.total ?? 0);
  const needsValidation  = summary?.potential_agents?.needs_validation ?? summary?.potential_agents?.total ?? 0;
  // runtime_cost is at the top level of the cost intelligence response, not nested under "overview"
  const monthlyCost      = costData?.runtime_cost?.total_usd ?? 0;

  // Top cost drivers
  const breakdown = (costData?.breakdown?.items || costData?.breakdown || []).sort((a, b) => (b.cost_usd || 0) - (a.cost_usd || 0));
  const topCosts  = breakdown.slice(0, 10);
  const otherCost = Math.max(0, monthlyCost - topCosts.reduce((s, x) => s + (x.cost_usd || 0), 0));

  // Risk signals from security alerts
  const critAlerts = alerts.filter(a => a.sev === "critical");
  const warnAlerts = alerts.filter(a => a.sev === "warning");
  const highRiskCount = new Set(critAlerts.map(a => a.entity)).size;

  const agentByKey = {};
  agents.forEach(a => {
    if (a.agent_id)   agentByKey[a.agent_id]   = a;
    if (a.agent_name) agentByKey[a.agent_name] = a;
  });

  const riskList = [];
  const seen = new Set();
  [...critAlerts, ...warnAlerts].forEach(alert => {
    if (seen.has(alert.entity)) return;
    seen.add(alert.entity);
    const ag = agentByKey[alert.entity] || null;
    riskList.push({
      entity: alert.entity,
      name:   ag?.agent_name || alert.entity,
      level:  alert.sev === "critical" ? "High" : "Medium",
      risk:   alert.msg,
      owner:  ag?.owner || "Unassigned",
      team:   ag?.team  || "Unknown",
    });
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 32, fontFamily: FONT }}>

      {/* ── Brand ──────────────────────────────────────────────────────────────── */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: bp.isMobile ? 20 : 24, fontWeight: 700, color: T.text, letterSpacing: "-0.025em" }}>
            ObserveAgents
          </h2>
          <div style={{ fontSize: 12, color: T.textMute, fontFamily: MONO, marginTop: 5 }}>
            Understand what AI exists · what is running · how it is connected · how it evolves
          </div>
        </div>
        <div style={{ fontSize: 11, color: T.textMute, fontFamily: MONO, textAlign: "right" }}>
          <div style={{ marginBottom: 3 }}>Executive Overview</div>
          <div>{new Date().toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</div>
          <PanelGroupControls group="dashboard" style={{ marginTop: 8, justifyContent: "flex-end" }} />
        </div>
      </div>

      {/* ── Product intro: what this surface is + where to look ────────────────── */}
      <div style={{ marginBottom: 4 }}>
        <div style={{ fontSize: 16, fontWeight: 600, color: T.text, letterSpacing: "-0.01em" }}>
          {isObservability ? "See what AI is actually running."
            : isGateway ? "Control AI traffic without instrumenting every app."
            : "See your real AI footprint"}
        </div>
        <div style={{ fontSize: 12, color: T.textDim, marginTop: 4, lineHeight: 1.6 }}>
          {isObservability
            ? "ObserveAgents Observability uses OpenTelemetry to show which AI systems are running, what they connect to, and where they need attention."
            : isGateway
            ? "ObserveAgents Gateway lets teams route AI requests through a controlled endpoint, manage providers, track usage, set budgets, and optionally enforce policies."
            : "Observe shows which AI systems exist, which ones are actually running, what they connect to, and where they need attention."}
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: bp.isMobile ? "1fr" : bp.isTablet ? "repeat(3, 1fr)" : "repeat(6, 1fr)", gap: 8 }}>
        {(isObservability ? [
          { page: "runtime",        title: "Runtime",             desc: "See live AI traces and execution timelines" },
          { page: "intelligence",   title: "Asset Intelligence",  desc: "Every AI system — models, tools, capabilities, findings" },
          { page: "security_intel", title: "Security",            desc: "Find risky runtime behavior before it's a problem" },
          { page: "runtime",        title: "Cost Signals",        desc: "Token usage and slow steps, visible per trace in Runtime" },
          { page: "guardrails",     title: "Guardrails",          desc: "Observe-only: detect, explain, recommend — no blocking" },
          { page: "integrations",   title: "OTel Setup",          desc: "Send OpenTelemetry traces and watch systems appear" },
        ] : isGateway ? [
          { page: "agent_inventory", title: "Traffic",            desc: "AI systems observed sending requests through the gateway" },
          { page: "providers",       title: "Providers",          desc: "Connect the AI providers your traffic routes to" },
          { page: "integrations",    title: "SDK Setup",          desc: "Existing provider SDKs with the Gateway base_url" },
          { page: "budgets",         title: "Budgets",            desc: "Set spend limits per team or agent" },
          { page: "cost",            title: "Cost",                desc: "Token and cost accounting from gateway traffic" },
          { page: "settings",        title: "Guard Modes",         desc: "Observe → alert → enforce, one team at a time" },
        ] : [
          { page: "runtime",        title: "Runtime",             desc: "See live AI traces and execution timelines" },
          { page: "intelligence",   title: "Asset Intelligence",  desc: "Every AI system — models, tools, capabilities, findings" },
          { page: "security_intel", title: "Security",            desc: "Find risky runtime behavior before it's a problem" },
          { page: "cost",           title: "Cost",                desc: "Spot heavy, slow, or potentially expensive workflows" },
          { page: "guardrails",     title: "Guardrails",          desc: "Observe-only: detect, explain, recommend — no blocking" },
          { page: "integrations",   title: "Integrations",        desc: "Connect telemetry and discovery sources" },
        ]).map((c) => (
          <button key={c.page} onClick={() => onNavigate?.(c.page)}
            style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: "10px 12px", textAlign: "left", cursor: "pointer", fontFamily: FONT }}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = T.borderHi; }}
            onMouseLeave={(e) => { e.currentTarget.style.borderColor = T.border; }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: T.text, marginBottom: 3 }}>{c.title} →</div>
            <div style={{ fontSize: 10, color: T.textMute, lineHeight: 1.5 }}>{c.desc}</div>
          </button>
        ))}
      </div>

      {/* ── Empty state — no agents discovered yet ──────────────────────────────── */}
      {total === 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "22px 26px", background: `${T.accent}0D`, border: `1px solid ${T.accent}33`, borderRadius: 10 }}>
          <div style={{ fontSize: 28 }}>🛰</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: T.text, marginBottom: 4 }}>No AI systems yet.</div>
            <div style={{ fontSize: 12, color: T.textDim, lineHeight: 1.6 }}>
              Connect OpenTelemetry traces from one AI service to see AI systems appear here. No manual registration required.
            </div>
          </div>
          <button onClick={() => onNavigate?.("integrations")}
            style={{ background: T.accent, color: "#001b10", border: "none", borderRadius: 6, padding: "9px 20px", fontSize: 12, fontWeight: 600, fontFamily: FONT, cursor: "pointer", whiteSpace: "nowrap" }}>
            Start Setup →
          </button>
        </div>
      )}

      {/* ── KPI Row — Agent Inventory ────────────────────────────────────────────── */}
      <div>
        <div style={{ fontSize: 9, fontFamily: MONO, color: T.textMute, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: 10 }}>
          Agent Inventory
        </div>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <KpiCard label="Total AI Agents"   value={total}               sub="Across all teams"                                                                   onClick={() => onNavigate?.("agent_inventory")} />
          <KpiCard label="Managed Agents"    value={managed}             sub={total ? `${Math.round(managed / total * 100)}% of total` : "—"}  color={T.accent}  onClick={() => onNavigate?.("agent_inventory")} />
          <KpiCard label="Needs Owner"       value={unassigned}          sub="Awaiting ownership review"            color={unassigned  > 0 ? T.yellow : T.accent} onClick={() => onNavigate?.("governance")} />
          <KpiCard label="Needs Review"      value={needsValidation}     sub="Awaiting validation"                  color={needsValidation > 0 ? T.warn : T.accent} onClick={() => onNavigate?.("discovery")} />
          <KpiCard label="Monthly AI Spend"  value={fmtUSD(monthlyCost)} sub="Runtime estimate (30d)"               color={T.info}                               onClick={() => onNavigate?.("cost")} />
          <KpiCard label="High Risk Agents"  value={highRiskCount}       sub={highRiskCount > 0 ? "Immediate review" : "No critical risks"} color={highRiskCount > 0 ? T.crit : T.accent} onClick={() => onNavigate?.("security_intel")} />
        </div>
      </div>

      {/* ── Top Cost Drivers — gateway cost accounting; hidden on the
           Observability surface (its cost story is OTel usage signals) ─────── */}
      {!isObservability && <CollapsiblePanel group="dashboard" storageKey="oa-panel-dash-cost-drivers"
        title="Top Cost Drivers" subtitle="Last 30 days · runtime estimate"
        actions={<button onClick={() => onNavigate?.("cost")} style={DASH_ACTION_BTN}>View Cost Intelligence →</button>}>
        {topCosts.length > 0 ? (
          <div>
            {topCosts.map((item, i) => {
              const name = item.name || item.agent_name || item.label || item.agent_id || "—";
              const pct  = monthlyCost > 0 ? (item.cost_usd || 0) / monthlyCost : 0;
              return (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", borderBottom: i < topCosts.length - 1 ? `1px solid ${T.border}` : "none" }}>
                  <div style={{ width: 22, fontSize: 11, fontFamily: MONO, color: T.textMute, textAlign: "right", flexShrink: 0 }}>{i + 1}.</div>
                  <div title={name} style={{ flex: 1, minWidth: 0, fontSize: 13, color: T.text, fontFamily: MONO, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</div>
                  {!bp.isMobile && <div style={{ fontSize: 11, color: T.textDim, width: 80, textAlign: "center" }}>{item.team || "—"}</div>}
                  {!bp.isMobile && (
                    <div style={{ width: 100, display: "flex", alignItems: "center", gap: 6 }}>
                      <div style={{ flex: 1, background: T.panelHi, borderRadius: 2, height: 4 }}>
                        <div style={{ width: `${Math.min(100, pct * 100)}%`, background: T.info, height: 4, borderRadius: 2 }} />
                      </div>
                      <span style={{ fontSize: 10, fontFamily: MONO, color: T.textMute, width: 32, textAlign: "right" }}>{Math.round(pct * 100)}%</span>
                    </div>
                  )}
                  <div style={{ flexShrink: 0, textAlign: "right", fontFamily: MONO, fontSize: 13, color: T.text }}>{fmtUSD(item.cost_usd)}</div>
                </div>
              );
            })}
            {otherCost > 1 && (
              <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", borderTop: `1px solid ${T.border}` }}>
                <div style={{ width: 22, fontSize: 11, fontFamily: MONO, color: T.textMute, textAlign: "right" }}>…</div>
                <div style={{ flex: 1, minWidth: 0, fontSize: 12, color: T.textMute, fontFamily: MONO }}>Others ({Math.max(0, total - topCosts.length)} agents)</div>
                {!bp.isMobile && <div style={{ width: 80 }} />}
                {!bp.isMobile && <div style={{ width: 100 }} />}
                <div style={{ flexShrink: 0, textAlign: "right", fontFamily: MONO, fontSize: 12, color: T.textMute }}>{fmtUSD(otherCost)}</div>
              </div>
            )}
            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12, paddingTop: 12, borderTop: `1px solid ${T.border}` }}>
              <span style={{ fontFamily: MONO, fontSize: 13, color: T.textDim }}>
                Total Monthly (Est):&nbsp;
                <strong style={{ color: T.text, fontSize: 15 }}>{fmtUSD(monthlyCost)}</strong>
              </span>
            </div>
          </div>
        ) : (
          <div style={{ color: T.textMute, fontFamily: MONO, fontSize: 12 }}>No cost data for the last 30 days</div>
        )}
      </CollapsiblePanel>}

      {/* ── High Risk + Action Items ───────────────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: bp.isMobile ? "1fr" : "3fr 2fr", gap: 16 }}>

        {/* High Risk Agents */}
        <Panel>
          <SectionTitle title="High Risk Agents" sub="Requires immediate action" action="View Security →" onAction={() => onNavigate?.("security_intel")} />
          {riskList.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {riskList.slice(0, 5).map((a, i) => (
                <div key={i} style={{
                  padding: "12px 14px", background: T.panelHi, borderRadius: 6,
                  border: `1px solid ${a.level === "High" ? T.crit + "44" : T.warn + "44"}`,
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                    <span style={{ fontSize: 10, color: a.level === "High" ? T.crit : T.warn }}>●</span>
                    <span style={{ fontSize: 13, fontWeight: 500, color: T.text, fontFamily: MONO }}>{a.name}</span>
                    <span style={{
                      fontSize: 10, padding: "2px 7px", borderRadius: 10, fontFamily: MONO,
                      color: a.level === "High" ? T.crit : T.warn,
                      background: a.level === "High" ? T.crit + "1A" : T.warn + "1A",
                    }}>{a.level} Risk</span>
                  </div>
                  <div style={{ fontSize: 12, color: T.textMute, marginBottom: 6, marginLeft: 16 }}>{a.risk}</div>
                  <div style={{ fontSize: 11, color: T.textDim, fontFamily: MONO, marginLeft: 16, marginBottom: 8 }}>
                    Owner: {a.owner} · Team: {a.team}
                  </div>
                  <div style={{ display: "flex", gap: 8, marginLeft: 16 }}>
                    <button onClick={() => onNavigate?.("security_intel")} style={{ background: "transparent", border: `1px solid ${T.border}`, color: T.textDim, padding: "3px 10px", borderRadius: 4, fontSize: 11, fontFamily: MONO, cursor: "pointer" }}>
                      Review Risk
                    </button>
                    {a.owner === "Unassigned" && (
                      <button onClick={() => onNavigate?.("governance")} style={{ background: "transparent", border: `1px solid ${T.border}`, color: T.textDim, padding: "3px 10px", borderRadius: 4, fontSize: 11, fontFamily: MONO, cursor: "pointer" }}>
                        Assign Owner
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ display: "flex", alignItems: "center", gap: 10, color: T.accent, fontFamily: MONO, fontSize: 13, padding: "16px 0" }}>
              <span style={{ fontSize: 18 }}>✓</span> No high risk agents detected
            </div>
          )}
        </Panel>

        {/* Action Items */}
        <Panel>
          <SectionTitle title="Action Items" />
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {[
              { count: critAlerts.length,     label: "need review",     color: T.crit,   prefix: "Critical", nav: "security_intel", btn: "Resolve" },
              { count: warnAlerts.length,     label: "need attention",  color: T.warn,   prefix: "Warning",  nav: "security_intel", btn: "View" },
              { count: needsValidation,       label: "need validation", color: T.yellow, prefix: "Info",     nav: "discovery",      btn: "Review" },
              { count: unassigned,            label: "unassigned",      color: T.yellow, prefix: "Info",     nav: "governance",     btn: "Assign" },
            ].filter(x => x.count > 0).map(({ count, label, color, prefix, nav, btn }, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 13px", background: color + "0D", border: `1px solid ${color}33`, borderRadius: 6 }}>
                <span style={{ fontSize: 10, color, flexShrink: 0 }}>● {prefix}</span>
                <span style={{ flex: 1, fontSize: 12, color: T.text }}>{count} agent{count !== 1 ? "s" : ""} {label}</span>
                <button onClick={() => onNavigate?.(nav)} style={{ background: "transparent", border: `1px solid ${color}55`, color, padding: "3px 10px", borderRadius: 4, fontSize: 11, fontFamily: MONO, cursor: "pointer", flexShrink: 0 }}>
                  {btn}
                </button>
              </div>
            ))}
            {critAlerts.length === 0 && warnAlerts.length === 0 && needsValidation === 0 && unassigned === 0 && (
              <div style={{ display: "flex", alignItems: "center", gap: 10, color: T.accent, fontFamily: MONO, fontSize: 13, padding: "16px 0" }}>
                <span style={{ fontSize: 18 }}>✓</span> No action items
              </div>
            )}
          </div>

          {/* Governance coverage */}
          <div style={{ marginTop: 20, paddingTop: 16, borderTop: `1px solid ${T.border}` }}>
            <div style={{ fontSize: 9, color: T.textMute, fontFamily: MONO, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: 12 }}>Review Queue</div>
            {[
              { label: "Ownership review", value: managed,                  color: T.accent },
              { label: "Validation review", value: total - needsValidation, color: T.info },
            ].map(({ label, value, color }) => {
              const remaining = Math.max(0, total - value);
              const fill = total > 0 ? (value / total) * 100 : 0;
              return (
                <div key={label} style={{ marginBottom: 10 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: T.textDim, marginBottom: 5 }}>
                    <span>{label}</span>
                    <span style={{ fontFamily: MONO, color: remaining > 0 ? T.warn : T.accent }}>
                      {remaining > 0 ? `${remaining} awaiting review` : "✓ all reviewed"}
                    </span>
                  </div>
                  <div style={{ background: T.panelHi, borderRadius: 2, height: 5 }}>
                    <div style={{ width: `${fill}%`, background: color, height: 5, borderRadius: 2, transition: "width 0.5s" }} />
                  </div>
                </div>
              );
            })}
          </div>
        </Panel>
      </div>
    </div>
  );
}
