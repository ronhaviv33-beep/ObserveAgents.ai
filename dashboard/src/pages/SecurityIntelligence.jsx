import React, { useState, useEffect, useMemo } from "react";
import { fetchSecurityAlerts, fetchAgents, fetchIntelligenceAssetSummary } from "../api.js";
import { useBreakpoint } from "../hooks/useBreakpoint.js";
import CollapsiblePanel, { PanelGroupControls } from "../components/CollapsiblePanel.jsx";

const T = {
  bg: "#0A0B0F", panel: "#0F1117", panelHi: "#141823",
  border: "#1E2230", borderHi: "#2A3242",
  text: "#E8ECF4", textDim: "#7A8499", textMute: "#4B5468",
  accent: "#7CFFB2", warn: "#FFB547", crit: "#FF5C7A",
  info: "#6FA8FF", yellow: "#FFD700", purple: "#B47AFF",
};
const MONO = "'JetBrains Mono','IBM Plex Mono',monospace";
const FONT = "'Geist','Söhne',-apple-system,sans-serif";

function relativeTime(ts) {
  if (!ts) return "—";
  const diff = Date.now() - (typeof ts === "number" ? ts : new Date(ts).getTime());
  const m = Math.floor(diff / 60000), h = Math.floor(diff / 3600000), d = Math.floor(diff / 86400000);
  if (m < 2) return "just now";
  if (m < 60) return `${m}m ago`;
  if (h < 24) return `${h}h ago`;
  return `${d}d ago`;
}

const ALERT_META = {
  agent_cost_spike:          { label: "Cost Spike",           icon: "◆", category: "Cost Anomaly" },
  high_token_prompt:         { label: "Large Prompt",         icon: "◈", category: "Cost Optimization" },
  failed_workflow_spike:     { label: "Workflow Failures",    icon: "◎", category: "Reliability Risk" },
  expensive_model_usage:     { label: "Premium Model Misuse", icon: "◇", category: "Cost Optimization" },
  unusual_after_hours_usage: { label: "After-Hours Activity", icon: "◉", category: "Security Signal" },
  repeated_agent_loop:       { label: "Agent Loop",           icon: "⊙", category: "Reliability Risk" },
  unapproved_model_usage:    { label: "Unapproved Model",     icon: "⊗", category: "Governance Violation" },
  sensitive_data_exposure:   { label: "Sensitive Content",    icon: "⚑", category: "Runtime Signal" },
};

const SEV_CONFIG = {
  critical: { color: T.crit,   bg: T.crit + "1A",  border: T.crit + "44",  label: "Critical" },
  warning:  { color: T.warn,   bg: T.warn + "1A",  border: T.warn + "44",  label: "Warning"  },
  info:     { color: T.info,   bg: T.info + "1A",  border: T.info + "44",  label: "Info"     },
};

function SevBadge({ sev }) {
  const cfg = SEV_CONFIG[sev] || SEV_CONFIG.info;
  return (
    <span style={{ display: "inline-block", background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}`, fontSize: 10, fontFamily: MONO, padding: "2px 8px", borderRadius: 4, letterSpacing: "0.05em" }}>
      {cfg.label}
    </span>
  );
}

function RiskScore({ score }) {
  const color = score >= 70 ? T.crit : score >= 40 ? T.warn : T.accent;
  const label = score >= 70 ? "High" : score >= 40 ? "Medium" : "Low";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
      <div style={{ position: "relative", width: 80, height: 80 }}>
        <svg viewBox="0 0 80 80" style={{ transform: "rotate(-90deg)" }}>
          <circle cx="40" cy="40" r="32" fill="none" stroke={T.panelHi} strokeWidth="8" />
          <circle cx="40" cy="40" r="32" fill="none" stroke={color} strokeWidth="8"
            strokeDasharray={`${(score / 100) * 201} 201`} strokeLinecap="round" />
        </svg>
        <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
          <span style={{ fontSize: 20, fontWeight: 700, color, fontFamily: MONO, lineHeight: 1 }}>{score}</span>
          <span style={{ fontSize: 9, color: T.textMute, fontFamily: MONO }}>/ 100</span>
        </div>
      </div>
      <div>
        <div style={{ fontSize: 18, fontWeight: 600, color }}>{label} Risk</div>
        <div style={{ fontSize: 12, color: T.textMute, fontFamily: MONO, marginTop: 4 }}>Overall posture</div>
      </div>
    </div>
  );
}

const TH = ({ children, style }) => (
  <th style={{ textAlign: "left", padding: "8px 14px", fontSize: 10, fontFamily: MONO, color: T.textMute, letterSpacing: "0.1em", textTransform: "uppercase", fontWeight: 500, borderBottom: `1px solid ${T.border}`, background: T.panelHi, ...style }}>
    {children}
  </th>
);
const TD = ({ children, style }) => (
  <td style={{ padding: "10px 14px", fontSize: 13, color: T.text, borderBottom: `1px solid ${T.border}`, verticalAlign: "middle", ...style }}>
    {children}
  </td>
);

function sortItems(list, key, dir) {
  if (!key) return list;
  const mul = dir === "asc" ? 1 : -1;
  const SEV_RANK = { critical: 3, warning: 2, info: 1 };
  return [...list].sort((a, b) => {
    let va = a[key], vb = b[key];
    if (key === "sev") { va = SEV_RANK[va] ?? 0; vb = SEV_RANK[vb] ?? 0; }
    if (key === "ts") { va = va ? (typeof va === "number" ? va : new Date(va).getTime()) : 0; vb = vb ? (typeof vb === "number" ? vb : new Date(vb).getTime()) : 0; }
    if (typeof va === "number" && typeof vb === "number") return (va - vb) * mul;
    return String(va || "").toLowerCase().localeCompare(String(vb || "").toLowerCase()) * mul;
  });
}

const STH = ({ children, sortKey, sort, onSort, style }) => {
  const active = sort?.key === sortKey;
  const canSort = !!sortKey;
  return (
    <th onClick={canSort ? () => onSort(sortKey) : undefined}
      style={{ textAlign:"left", padding:"8px 14px", fontSize:10, fontFamily:MONO, color: active ? T.accent : T.textMute, letterSpacing:"0.1em", textTransform:"uppercase", fontWeight:500, borderBottom:`1px solid ${T.border}`, background:T.panelHi, cursor: canSort ? "pointer" : "default", userSelect:"none", ...style }}>
      <span style={{ display:"inline-flex", alignItems:"center", gap:4 }}>
        {children}
        {canSort && <span style={{ fontSize:9, opacity: active?1:0.4, color: active?T.accent:T.textMute }}>{active?(sort.dir==="asc"?"▲":"▼"):"⇅"}</span>}
      </span>
    </th>
  );
};

export default function SecurityIntelligence() {
  const [alerts, setAlerts]   = useState([]);
  const [agents, setAgents]   = useState([]);
  const [intelAssets, setIntelAssets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(null);
  const [sevFilter, setSevFilter] = useState("all");
  const [alertSort, setAlertSort] = useState({ key: "ts", dir: "desc" });
  const toggleSort = (key) => setAlertSort(s => s.key===key ? {key, dir: s.dir==="asc"?"desc":"asc"} : {key, dir:"desc"});
  const bp = useBreakpoint();

  useEffect(() => {
    (async () => {
      try {
        const [a, ag, s] = await Promise.allSettled([
          fetchSecurityAlerts(), fetchAgents({ limit: 500 }), fetchIntelligenceAssetSummary(),
        ]);
        if (a.status === "fulfilled")  setAlerts(Array.isArray(a.value)  ? a.value  : []);
        if (ag.status === "fulfilled") setAgents(Array.isArray(ag.value) ? ag.value : ag.value?.agents || []);
        if (s.status === "fulfilled")  setIntelAssets(s.value?.assets || []);
      } finally { setLoading(false); }
    })();
  }, []);

  const agentMap = useMemo(() => {
    const m = {};
    agents.forEach(a => { if (a.agent_id) m[a.agent_id] = a; if (a.agent_name) m[a.agent_name] = a; });
    return m;
  }, [agents]);

  const critical = alerts.filter(a => a.sev === "critical");
  const warning  = alerts.filter(a => a.sev === "warning");
  const info     = alerts.filter(a => a.sev === "info");

  const highRiskEntities   = new Set(critical.map(a => a.entity));
  const medRiskEntities    = new Set(warning.map(a  => a.entity));
  const highRiskCount      = highRiskEntities.size;
  const medRiskCount       = [...medRiskEntities].filter(e => !highRiskEntities.has(e)).length;
  const lowRiskCount       = Math.max(0, agents.length - highRiskCount - medRiskCount);

  const riskScore = Math.min(100, Math.round(
    highRiskCount * 18 +
    medRiskCount  * 8 +
    alerts.filter(a => a.type === "repeated_agent_loop").length * 8 +
    alerts.filter(a => a.type === "unapproved_model_usage").length * 6
  ));

  // Findings breakdown by type
  const findingsByType = {};
  alerts.forEach(a => {
    if (!findingsByType[a.type]) findingsByType[a.type] = { critical: 0, warning: 0, info: 0, entities: new Set() };
    findingsByType[a.type][a.sev] = (findingsByType[a.type][a.sev] || 0) + 1;
    findingsByType[a.type].entities.add(a.entity);
  });

  const filtered = useMemo(() => {
    const base = sevFilter === "all" ? alerts : alerts.filter(a => a.sev === sevFilter);
    return sortItems(base, alertSort.key, alertSort.dir);
  }, [alerts, sevFilter, alertSort]);

  if (loading) return (
    <div style={{ color: T.textMute, fontFamily: MONO, fontSize: 13, padding: "32px 0", textAlign: "center" }}>
      Loading security intelligence…
    </div>
  );

  return (
    <div style={{ fontFamily: FONT, display: "flex", flexDirection: "column", gap: 24 }}>

      {/* ── Page header ────────────────────────────────────────────────────── */}
      <div>
        <div style={{ fontSize: 22, fontWeight: 700, color: T.text, letterSpacing: "-0.02em" }}>AI Agent Runtime Security Intelligence</div>
        <div style={{ fontSize: 13, color: T.textMute, marginTop: 4 }}>
          Security findings derived from AI agent runtime evidence — tools, models, MCP, databases, APIs, ownership, and production activity. Observe-only: detect, explain, recommend.
        </div>
        <PanelGroupControls group="security" style={{ marginTop: 12 }} />
      </div>

      {/* ── Risk Overview ──────────────────────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: bp.isMobile ? "1fr" : "auto 1fr", gap: 20 }}>
        <div style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: "24px 28px", display: "flex", alignItems: "center" }}>
          <RiskScore score={riskScore} />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: bp.isMobile ? "1fr" : "repeat(3, 1fr)", gap: 12 }}>
          {[
            { label: "High Risk Agents",   count: highRiskCount, color: T.crit,   sub: "Immediate review" },
            { label: "Medium Risk Agents", count: medRiskCount,  color: T.warn,   sub: "Monitor closely" },
            { label: "Low Risk Agents",    count: lowRiskCount,  color: T.accent, sub: "Operating normally" },
          ].map(({ label, count, color, sub }) => (
            <div key={label} style={{ background: T.panel, border: `1px solid ${T.border}`, borderRadius: 8, padding: "20px 22px" }}>
              <div style={{ fontSize: 9, fontFamily: MONO, color: T.textMute, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: 10 }}>{label}</div>
              <div style={{ fontSize: 32, fontWeight: 700, color, letterSpacing: "-0.03em", lineHeight: 1 }}>{count}</div>
              <div style={{ fontSize: 11, color: T.textMute, fontFamily: MONO, marginTop: 8 }}>{sub}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Runtime Security Findings (AI-agent-specific, source=runtime_security) ── */}
      {(() => {
        // Every open security finding across assets, tagged with its agent name.
        const secFindings = [];
        intelAssets.forEach(a => {
          (a.findings || []).forEach(f => {
            if (f.status === "open" && f.category === "security") {
              secFindings.push({ ...f, _agent: a.asset_name || a.service_name, _prod: (a.environment || "").toLowerCase().startsWith("prod") });
            }
          });
        });
        if (secFindings.length === 0) return null;

        const agentsFor = (types) => {
          const s = new Set();
          secFindings.forEach(f => { if (types.includes(f.finding_type)) s.add(f._agent); });
          return [...s];
        };
        const prodAgents = [...new Set(secFindings.filter(f => f._prod).map(f => f._agent))];

        const BUCKETS = [
          { key: "prod",    label: "Production agents with findings", color: T.crit,   agents: prodAgents },
          { key: "mcptool", label: "MCP / tool risk",                 color: T.warn,   agents: agentsFor(["agent_uses_mcp_tool_in_production", "agent_has_broad_tool_surface"]) },
          { key: "dbapi",   label: "Database / API access",           color: T.info,   agents: agentsFor(["agent_has_database_access", "agent_uses_unmanaged_external_api"]) },
          { key: "provider",label: "Unknown providers / models",      color: T.purple, agents: agentsFor(["agent_uses_unknown_model_provider"]) },
          { key: "owner",   label: "Missing ownership",               color: T.yellow, agents: agentsFor(["agent_missing_owner"]) },
          { key: "review",  label: "Human review recommended",        color: T.crit,   agents: agentsFor(["human_review_recommended"]) },
        ];

        return (
          <CollapsiblePanel group="security" storageKey="oa-panel-security-runtime" title="Runtime Security Findings"
            subtitle="AI-agent-specific security signals derived from runtime evidence — grouped for triage">
            <div style={{ display: "grid", gridTemplateColumns: bp.isMobile ? "1fr" : "repeat(3, 1fr)", gap: 12 }}>
              {BUCKETS.map(b => (
                <div key={b.key} style={{ background: T.panel, border: `1px solid ${b.agents.length > 0 ? b.color + "44" : T.border}`, borderRadius: 8, padding: "16px 18px" }}>
                  <div style={{ fontSize: 9, fontFamily: MONO, color: T.textMute, letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: 10 }}>{b.label}</div>
                  <div style={{ fontSize: 26, fontWeight: 700, color: b.agents.length > 0 ? b.color : T.textMute, letterSpacing: "-0.03em", lineHeight: 1 }}>{b.agents.length}</div>
                  <div style={{ fontSize: 11, color: T.textDim, fontFamily: MONO, marginTop: 8, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {b.agents.length > 0 ? b.agents.slice(0, 3).join(", ") + (b.agents.length > 3 ? ` +${b.agents.length - 3}` : "") : "None"}
                  </div>
                </div>
              ))}
            </div>
          </CollapsiblePanel>
        );
      })()}

      {/* ── Risky AI Systems (runtime-observed, from asset intelligence) ────── */}
      {(() => {
        const RISKY_TYPES = ["mcp", "database", "shell", "external_api", "crm", "filesystem"];
        const risky = intelAssets
          .map(a => {
            const capTypes = [...new Set((a.capabilities || []).map(c => c.capability_type))].filter(t => RISKY_TYPES.includes(t));
            const secOpen = (a.findings || []).filter(f => f.status === "open" && f.category === "security").length;
            return { ...a, _riskyCaps: capTypes, _secOpen: secOpen };
          })
          .filter(a => a._riskyCaps.length > 0 || a._secOpen > 0)
          .sort((x, y) => (y.high_findings_count - x.high_findings_count) || (y._secOpen - x._secOpen));
        if (risky.length === 0) return null;
        const CAP_RISK_COLOR = { shell: T.crit, database: T.crit, mcp: T.warn, crm: T.warn, filesystem: T.warn, external_api: T.info };
        return (
          <CollapsiblePanel title="Risky AI Systems" group="security"
            storageKey="oa-panel-security-risky-systems" badge={risky.length}>
            <div style={{ fontSize: 12, color: T.textMute, marginBottom: 12 }}>
              Runtime-observed capability surface per AI system — derived from OpenTelemetry evidence and asset intelligence.
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <TH>AI System</TH><TH>Environment</TH><TH>Risky Capabilities</TH>
                    <TH>Open Security Findings</TH><TH>High Severity</TH>
                  </tr>
                </thead>
                <tbody>
                  {risky.map(a => (
                    <tr key={a.asset_key}>
                      <TD style={{ fontFamily: MONO }}>{a.asset_name}</TD>
                      <TD style={{ fontFamily: MONO, fontSize: 12, color: T.textDim }}>{a.environment || "—"}</TD>
                      <TD>
                        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                          {a._riskyCaps.length === 0
                            ? <span style={{ color: T.textMute, fontFamily: MONO, fontSize: 11 }}>—</span>
                            : a._riskyCaps.map(t => (
                                <span key={t} style={{ background: (CAP_RISK_COLOR[t] || T.info) + "1A", color: CAP_RISK_COLOR[t] || T.info, border: `1px solid ${(CAP_RISK_COLOR[t] || T.info)}33`, fontSize: 10, fontFamily: MONO, padding: "2px 8px", borderRadius: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>{t}</span>
                              ))}
                        </div>
                      </TD>
                      <TD style={{ fontFamily: MONO, color: a._secOpen > 0 ? T.warn : T.textDim }}>{a._secOpen}</TD>
                      <TD style={{ fontFamily: MONO, color: a.high_findings_count > 0 ? T.crit : T.textDim }}>{a.high_findings_count}</TD>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CollapsiblePanel>
        );
      })()}

      {/* ── Findings Breakdown ─────────────────────────────────────────────── */}
      <CollapsiblePanel title="Security Findings by Category" group="security"
        storageKey="oa-panel-security-findings" badge={Object.keys(findingsByType).length || null}>
        {Object.keys(findingsByType).length > 0 ? (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 12 }}>
            {Object.entries(findingsByType).map(([type, counts]) => {
              const meta = ALERT_META[type] || { label: type, icon: "●", category: "Other" };
              const sev  = counts.critical > 0 ? "critical" : counts.warning > 0 ? "warning" : "info";
              const cfg  = SEV_CONFIG[sev];
              return (
                <div key={type} style={{ background: T.panelHi, border: `1px solid ${cfg.border}`, borderRadius: 6, padding: "14px 16px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                    <span style={{ color: cfg.color, fontSize: 14 }}>{meta.icon}</span>
                    <span style={{ fontSize: 13, fontWeight: 500, color: T.text }}>{meta.label}</span>
                  </div>
                  <div style={{ fontSize: 11, color: T.textMute, fontFamily: MONO, marginBottom: 8 }}>{meta.category}</div>
                  <div style={{ display: "flex", gap: 12, fontSize: 12, fontFamily: MONO }}>
                    <span style={{ color: T.crit }}>{counts.critical} critical</span>
                    <span style={{ color: T.warn }}>{counts.warning} warning</span>
                    <span style={{ color: T.textDim }}>{counts.entities.size} agents</span>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div style={{ color: T.accent, fontFamily: MONO, fontSize: 13, padding: "12px 0", display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 18 }}>✓</span> No security findings detected
          </div>
        )}
      </CollapsiblePanel>

      {/* ── Alert Feed ─────────────────────────────────────────────────────── */}
      <CollapsiblePanel title="Runtime Security Signals" group="security" storageKey="oa-panel-security-feed"
        badge={alerts.length}
        bodyStyle={{ padding: 0, paddingTop: 0 }}
        actions={
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {[
              { id: "all",      label: `All (${alerts.length})` },
              { id: "critical", label: `Critical (${critical.length})`, color: T.crit },
              { id: "warning",  label: `Warning (${warning.length})`,   color: T.warn },
              { id: "info",     label: `Info (${info.length})`,         color: T.info },
            ].map(({ id, label, color }) => (
              <button key={id} onClick={() => setSevFilter(id)}
                style={{ background: sevFilter === id ? T.panelHi : "transparent", border: sevFilter === id ? `1px solid ${T.border}` : "1px solid transparent", color: sevFilter === id ? (color || T.text) : T.textDim, padding: "4px 12px", borderRadius: 4, fontSize: 11, fontFamily: MONO, cursor: "pointer" }}>
                {label}
              </button>
            ))}
          </div>
        }>
        {filtered.length === 0 ? (
          <div style={{ padding: "32px", textAlign: "center", color: T.textMute, fontFamily: MONO, fontSize: 13 }}>
            {sevFilter === "all" ? "No risk signals detected — security posture is healthy" : `No ${sevFilter} alerts`}
          </div>
        ) : bp.isMobile ? (
          <div>
            {filtered.map((alert, i) => {
              const meta   = ALERT_META[alert.type] || { label: alert.type, icon: "●" };
              const cfg    = SEV_CONFIG[alert.sev]  || SEV_CONFIG.info;
              const isOpen = expanded === i;
              const agInfo = agentMap[alert.entity] || null;
              return (
                <div key={i} onClick={() => setExpanded(isOpen ? null : i)}
                  style={{ padding: "14px 16px", borderBottom: `1px solid ${T.border}`, background: isOpen ? T.panelHi : "transparent", cursor: "pointer" }}>
                  <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8, marginBottom: 6 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ color: cfg.color, fontSize: 12 }}>{meta.icon}</span>
                      <span style={{ fontSize: 13, color: T.text, fontWeight: 500 }}>{meta.label}</span>
                    </div>
                    <SevBadge sev={alert.sev} />
                  </div>
                  <div style={{ fontSize: 12, fontFamily: MONO, color: T.textDim, marginBottom: 4 }}>{alert.entity}</div>
                  {agInfo && <div style={{ fontSize: 11, color: T.textMute, fontFamily: MONO, marginBottom: 4 }}>Team: {agInfo.team}</div>}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 11, color: T.textDim, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{alert.msg}</span>
                    <span style={{ fontSize: 11, fontFamily: MONO, color: T.textMute, flexShrink: 0 }}>{relativeTime(alert.ts)}</span>
                  </div>
                  {isOpen && (
                    <div style={{ marginTop: 12, padding: "12px 14px", background: T.panel, borderRadius: 6, fontSize: 12, display: "flex", flexDirection: "column", gap: 8 }}>
                      <div><span style={{ color: T.textMute, fontFamily: MONO }}>Signal: </span><span style={{ color: T.text }}>{alert.msg}</span></div>
                      {alert.action && <div><span style={{ color: T.textMute, fontFamily: MONO }}>Recommended action: </span><span style={{ color: T.warn }}>{alert.action}</span></div>}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <div style={{ overflowX: "auto", WebkitOverflowScrolling: "touch" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 700 }}>
            <thead>
              <tr>
                <STH sortKey="sev" sort={alertSort} onSort={toggleSort}>Severity</STH>
                <STH sortKey="type" sort={alertSort} onSort={toggleSort}>Finding</STH>
                <STH sortKey="entity" sort={alertSort} onSort={toggleSort}>Agent / Entity</STH>
                <STH sort={alertSort} onSort={toggleSort}>Signal</STH>
                <STH sortKey="ts" sort={alertSort} onSort={toggleSort}>When</STH>
              </tr>
            </thead>
            <tbody>
              {filtered.map((alert, i) => {
                const meta   = ALERT_META[alert.type] || { label: alert.type, icon: "●" };
                const cfg    = SEV_CONFIG[alert.sev]  || SEV_CONFIG.info;
                const isOpen = expanded === i;
                const agInfo = agentMap[alert.entity] || null;
                return (
                  <React.Fragment key={i}>
                    <tr
                      onClick={() => setExpanded(isOpen ? null : i)}
                      style={{ cursor: "pointer", background: isOpen ? T.panelHi : "transparent" }}
                      onMouseEnter={e => { if (!isOpen) e.currentTarget.style.background = T.panelHi + "80"; }}
                      onMouseLeave={e => { if (!isOpen) e.currentTarget.style.background = "transparent"; }}
                    >
                      <TD><SevBadge sev={alert.sev} /></TD>
                      <TD>
                        <span style={{ color: cfg.color, marginRight: 6, fontSize: 12 }}>{meta.icon}</span>
                        {meta.label}
                      </TD>
                      <TD>
                        <div style={{ fontFamily: MONO, fontSize: 12 }}>{alert.entity}</div>
                        {agInfo && <div style={{ fontSize: 11, color: T.textMute, marginTop: 2 }}>Team: {agInfo.team}</div>}
                      </TD>
                      <TD style={{ maxWidth: 280 }}>
                        <span title={alert.msg} style={{ fontSize: 12, color: T.textDim, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", display: "block" }}>{alert.msg}</span>
                      </TD>
                      <TD><span style={{ fontFamily: MONO, fontSize: 12, color: T.textDim }}>{relativeTime(alert.ts)}</span></TD>
                    </tr>
                    {isOpen && (
                      <tr>
                        <td colSpan={5} style={{ background: T.panelHi, padding: "14px 18px", borderBottom: `1px solid ${T.border}` }}>
                          <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 12 }}>
                            <div><span style={{ color: T.textMute, fontFamily: MONO }}>Signal: </span><span style={{ color: T.text }}>{alert.msg}</span></div>
                            {alert.action && <div><span style={{ color: T.textMute, fontFamily: MONO }}>Recommended action: </span><span style={{ color: T.warn }}>{alert.action}</span></div>}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
          </div>
        )}
      </CollapsiblePanel>
    </div>
  );
}
