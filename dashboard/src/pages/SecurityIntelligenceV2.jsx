import { useState, useEffect, useMemo } from "react";
import { ShieldAlert, AlertTriangle, Info, Wrench, Database, HelpCircle, UserX, RefreshCcw, Eye, SlidersHorizontal } from "lucide-react";
import { C, FONT, RADIUS, microLabel, riskColor } from "../ui2/tokens.js";
import PageHeader from "../ui2/PageHeader.jsx";
import Section from "../ui2/Section.jsx";
import MetricCard from "../ui2/MetricCard.jsx";
import RiskBadge from "../ui2/RiskBadge.jsx";
import StatusPill from "../ui2/StatusPill.jsx";
import EmptyState from "../ui2/EmptyState.jsx";
import { surfaceAllowsPage } from "../productSurface.js";
import { useBreakpoint } from "../hooks/useBreakpoint.js";
import { getAssetSummary, getOpenFindings, getControlCandidates } from "../overviewApi.js";

/**
 * SecurityIntelligenceV2 — redesign step 3 (docs/ui_redesign_plan.md).
 *
 * The investigation workspace: explains WHY agents are risky from runtime
 * evidence, and connects the risky ones to the Gateway Control Center where
 * the control path is recommended. Observe-only findings — this page never
 * enforces, and it is deliberately AI-agent-shaped, not generic security.
 *
 *   Security Intelligence explains the risk.
 *   Gateway Control Center recommends the control path.
 */

const SEV_RANK = { critical: 5, high: 4, medium: 3, low: 2, info: 1 };

// Investigation buckets — finding_type groups over open findings (any category:
// tool errors live under operations, ownership under operations/security).
// A bucket matches by `types` list, or by a `match(finding)` predicate.
const BUCKETS = [
  { id: "mcp",      label: "MCP / tool risk", icon: Wrench,
    types: ["agent_uses_mcp_tool_in_production", "mcp_tool_access", "mcp_enabled",
            "agent_has_broad_tool_surface", "broad_tool_access", "shell_enabled"] },
  { id: "data",     label: "Database & API access", icon: Database,
    types: ["agent_has_database_access", "database_access", "agent_uses_unmanaged_external_api",
            "external_api_access", "sensitive_system_access", "filesystem_enabled"] },
  { id: "provider", label: "Unknown providers / models", icon: HelpCircle,
    types: ["agent_uses_unknown_model_provider", "unknown_model"] },
  { id: "owner",    label: "Missing ownership", icon: UserX,
    types: ["agent_missing_owner", "unmanaged_runtime"] },
  { id: "errors",   label: "Repeated tool errors", icon: RefreshCcw,
    types: ["repeated_tool_errors", "tool_error", "mcp_error"] },
  { id: "review",   label: "Human review recommended", icon: Eye,
    types: ["human_review_recommended"] },
  // R3 (docs/ai_agent_detection_rules_alerts_design.md): detection-rule matches
  // grouped by provenance, not type — new built-in rules join automatically.
  { id: "rules",    label: "Detection rule matches", icon: SlidersHorizontal,
    match: (f) => f.source === "detection_rules" },
];

/** Severity → alert icon for the finding cards. */
const SEV_ICON = { critical: ShieldAlert, high: ShieldAlert, medium: AlertTriangle, low: Info, info: Info };

const relTime = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  const m = Math.floor((Date.now() - d.getTime()) / 60000);
  if (m < 2) return "just now";
  if (m < 60) return `${m}m ago`;
  if (m < 1440) return `${Math.floor(m / 60)}h ago`;
  return `${Math.floor(m / 1440)}d ago`;
};

function BucketCard({ bucket, rows, active, onSelect }) {
  const agents = new Set(rows.map((f) => f.asset_key)).size;
  const high = rows.filter((f) => SEV_RANK[f.severity] >= 4).length;
  const med  = rows.filter((f) => f.severity === "medium").length;
  const topTypes = [...new Set(rows.map((f) => f.finding_type))].slice(0, 2);
  const urgency = rows.length ? (high > 0 ? C.riskHigh : C.riskMedium) : C.textMute;
  const BucketIcon = bucket.icon;
  return (
    <div onClick={rows.length ? onSelect : undefined}
      style={{
        flex: "1 1 240px", minWidth: 220,
        background: active ? C.accentSoft : C.surface,
        border: `1px solid ${active ? C.accent : C.border}`,
        borderRadius: RADIUS.md, padding: "14px 16px",
        boxShadow: "0 1px 2px rgba(15,23,42,0.04)",
        cursor: rows.length ? "pointer" : "default", opacity: rows.length ? 1 : 0.55,
      }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 8 }}>
        <span style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          <span style={{ width: 26, height: 26, borderRadius: 8, background: `${urgency}14`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <BucketIcon size={14} color={urgency} strokeWidth={2} />
          </span>
          <span style={{ fontSize: 12.5, fontWeight: 600, color: C.text }}>{bucket.label}</span>
        </span>
        <span style={{ fontSize: 18, fontWeight: 700, fontFamily: FONT.mono, color: rows.length ? C.text : C.textMute }}>{rows.length}</span>
      </div>
      <div style={{ fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute, lineHeight: 1.6 }}>
        {rows.length > 0 ? (
          <>
            {agents} agent{agents !== 1 ? "s" : ""} · {high} high · {med} medium
            <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginTop: 7 }}>
              {topTypes.map((t) => <StatusPill key={t} tone={C.textDim}>{t}</StatusPill>)}
            </div>
          </>
        ) : "no open findings"}
      </div>
      {rows.length > 0 && (
        <div style={{ fontSize: 10, fontFamily: FONT.mono, color: active ? C.accent : C.textDim, marginTop: 9 }}>
          {active ? "showing below ↓" : "view findings ↓"}
        </div>
      )}
    </div>
  );
}

function FindingRow({ f, assetName, isCandidate, onNavigate, hideAsset }) {
  const sevColor = riskColor(f.severity);
  const SevIcon = SEV_ICON[f.severity] || Info;
  return (
    <div style={{ display: "flex", gap: 12, alignItems: "flex-start", background: C.surface,
      border: `1px solid ${C.border}`, borderLeft: `3px solid ${sevColor}`,
      borderRadius: RADIUS.md, padding: "13px 16px", boxShadow: "0 1px 2px rgba(15,23,42,0.04)" }}>
      <span style={{ width: 30, height: 30, borderRadius: 8, background: `${sevColor}14`,
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 1 }}>
        <SevIcon size={15} color={sevColor} strokeWidth={2} />
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 6 }}>
          <span style={{ fontSize: 13.5, fontWeight: 600, color: C.text }}>{f.title}</span>
          <RiskBadge level={f.severity} />
          {(f.occurrence_count || 1) > 1 && (
            <span style={{ fontFamily: FONT.mono, fontSize: 10, color: C.textDim }}>×{f.occurrence_count}</span>
          )}
          <span style={{ marginLeft: "auto", fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute }}>{relTime(f.last_seen)}</span>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
          {assetName && !hideAsset && (
            <button onClick={() => onNavigate?.("intelligence")}
              style={{ background: "transparent", border: `1px solid ${C.border}`, color: C.text,
                fontSize: 10, fontFamily: FONT.mono, padding: "2px 9px", borderRadius: 999, cursor: "pointer" }}>
              {assetName}
            </button>
          )}
          <StatusPill tone={C.textDim}>{f.finding_type}</StatusPill>
          <StatusPill tone={C.textMute}>{f.source}</StatusPill>
        </div>
        <div style={{ fontSize: 12, color: C.textDim, lineHeight: 1.6 }}>{f.summary}</div>
        {isCandidate && surfaceAllowsPage("gateway_control_center") && (
          <button onClick={() => onNavigate?.("gateway_control_center", { gccFocus: f.asset_key })}
            style={{ marginTop: 10, background: "transparent", color: C.riskMedium, border: `1px solid ${C.riskMedium}44`,
              borderRadius: RADIUS.sm, padding: "5px 13px", fontSize: 10.5, fontFamily: FONT.mono, cursor: "pointer" }}>
            Review in Gateway Control Center →
          </button>
        )}
      </div>
    </div>
  );
}

/** Compact selectable agent card for the master list (mirrors AssetIntelligence's AssetRow). */
function AgentSecurityRow({ a, selected, onSelect }) {
  return (
    <div onClick={onSelect}
      style={{
        background: selected ? C.surfaceRaised : C.surface,
        border: `1px solid ${selected ? C.borderStrong : C.border}`,
        borderLeft: `3px solid ${riskColor(a.worst)}`,
        borderRadius: RADIUS.md, padding: "12px 14px", cursor: "pointer",
      }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 6 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: C.text, fontFamily: FONT.mono }}>{a.name}</span>
        <RiskBadge level={a.worst} />
        {a.isCandidate && <StatusPill tone={C.riskMedium}>gateway candidate</StatusPill>}
      </div>
      <div style={{ fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute, lineHeight: 1.6 }}>
        {a.findings.length} finding{a.findings.length !== 1 ? "s" : ""}
        {a.counts.critical > 0 && <> · {a.counts.critical} critical</>}
        {a.counts.high > 0 && <> · {a.counts.high} high</>}
        {a.counts.medium > 0 && <> · {a.counts.medium} medium</>}
        {" · "}{relTime(a.lastSeen)}
      </div>
    </div>
  );
}

export default function SecurityIntelligenceV2({ onNavigate }) {
  const bp = useBreakpoint();
  const [assets, setAssets] = useState(null);
  const [findings, setFindings] = useState(null);
  const [candidates, setCandidates] = useState(null);
  const [bucketFilter, setBucketFilter] = useState(null);
  const [selectedKey, setSelectedKey] = useState(null);

  useEffect(() => {
    (async () => {
      const [a, f, c] = await Promise.all([getAssetSummary(), getOpenFindings(), getControlCandidates()]);
      setAssets(a); setFindings(f); setCandidates(c);
    })();
  }, []);

  const nameByKey = useMemo(() => {
    const m = {};
    (assets?.data.assets || []).forEach((a) => { m[a.asset_key] = a.asset_name || a.service_name; });
    return m;
  }, [assets]);

  const openFindings = useMemo(() => (findings?.data || []).filter((f) => f.status === "open" || !f.status), [findings]);
  const securityFindings = useMemo(() => openFindings.filter((f) => f.category === "security"), [openFindings]);

  const bucketRows = useMemo(() => {
    const m = {};
    for (const b of BUCKETS) m[b.id] = openFindings.filter(
      (f) => (b.match ? b.match(f) : b.types.includes(f.finding_type)));
    return m;
  }, [openFindings]);

  const candidateKeys = useMemo(
    () => new Set((candidates?.data || []).filter((c) => c.status === "open").map((c) => c.asset_key)),
    [candidates]);

  const listRows = useMemo(() => {
    const base = bucketFilter
      ? bucketRows[bucketFilter] || []
      : securityFindings;
    return [...base].sort((a, b) =>
      (SEV_RANK[b.severity] || 0) - (SEV_RANK[a.severity] || 0)
      || new Date(b.last_seen || 0) - new Date(a.last_seen || 0));
  }, [bucketFilter, bucketRows, securityFindings]);

  // One card per agent: listRows is already worst-first, so grouping by
  // first appearance keeps both the agent order and each agent's findings
  // sorted worst-first.
  const agents = useMemo(() => {
    const byKey = new Map();
    for (const f of listRows) {
      const key = f.asset_key || "unknown";
      if (!byKey.has(key)) {
        byKey.set(key, {
          key, name: nameByKey[key] || key, findings: [],
          worst: f.severity, counts: { critical: 0, high: 0, medium: 0, low: 0, info: 0 },
          lastSeen: f.last_seen, isCandidate: candidateKeys.has(key),
        });
      }
      const a = byKey.get(key);
      a.findings.push(f);
      if (f.severity in a.counts) a.counts[f.severity] += 1;
      if (new Date(f.last_seen || 0) > new Date(a.lastSeen || 0)) a.lastSeen = f.last_seen;
    }
    return [...byKey.values()];
  }, [listRows, nameByKey, candidateKeys]);

  const selectedAgent = agents.find((a) => a.key === selectedKey) ?? agents[0];

  const agentsWithSecurity = new Set(securityFindings.map((f) => f.asset_key)).size;
  const highRisk = securityFindings.filter((f) => SEV_RANK[f.severity] >= 4).length;
  const humanReview = (bucketRows.review || []).length;
  const openCandidates = candidateKeys.size;

  const loading = assets === null || findings === null || candidates === null;
  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 280, color: C.textMute, fontFamily: FONT.mono, fontSize: 13 }}>
      Loading security intelligence…
    </div>
  );

  const anySample = assets?.demo || findings?.demo || candidates?.demo;
  const activeBucket = bucketFilter ? BUCKETS.find((b) => b.id === bucketFilter) : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 26, fontFamily: FONT.ui, maxWidth: 1160 }}>

      <div>
        <PageHeader
          title="AI Agent Runtime Security Intelligence"
          purpose="Investigate AI-agent security findings derived from runtime evidence — tools, MCP, providers, databases, APIs, ownership, and human-review signals.">
          {anySample && <StatusPill tone={C.textMute}>sample data</StatusPill>}
          <StatusPill tone={C.accent}>observe-only</StatusPill>
        </PageHeader>
        <div style={{ fontSize: 11.5, fontFamily: FONT.mono, color: C.textDim, marginTop: 10 }}>
          Observe-only findings. Control recommendations are reviewed in Gateway Control Center.
        </div>
        <div style={{ fontSize: 11.5, color: C.textMute, marginTop: 6 }}>
          Security Intelligence explains the risk. Gateway Control Center recommends the control path.
        </div>
      </div>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <MetricCard label="Agents with security findings" value={agentsWithSecurity}
          sub={`${securityFindings.length} open security findings`}
          tone={agentsWithSecurity > 0 ? C.riskMedium : C.accent} />
        <MetricCard label="High-risk findings" value={highRisk}
          sub="high or critical severity" tone={highRisk > 0 ? C.riskHigh : C.accent} />
        <MetricCard label="Human review recommended" value={humanReview}
          sub="risk combinations that need a person" tone={humanReview > 0 ? C.riskMedium : C.accent} />
        <MetricCard label="Gateway control candidates" value={openCandidates}
          sub="recommended for control review"
          tone={openCandidates > 0 ? C.riskHigh : C.accent}
          onClick={surfaceAllowsPage("gateway_control_center") ? () => onNavigate?.("gateway_control_center") : undefined} />
      </div>

      <Section label="Investigation buckets"
        right={bucketFilter && (
          <button onClick={() => setBucketFilter(null)}
            style={{ background: "transparent", border: "none", color: C.textDim, fontSize: 11, fontFamily: FONT.mono, cursor: "pointer", textDecoration: "underline" }}>
            clear filter
          </button>
        )}>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          {BUCKETS.map((b) => (
            <BucketCard key={b.id} bucket={b} rows={bucketRows[b.id] || []}
              active={bucketFilter === b.id}
              onSelect={() => setBucketFilter(bucketFilter === b.id ? null : b.id)} />
          ))}
        </div>
      </Section>

      <Section
        label={activeBucket ? `Agents — ${activeBucket.label} (${agents.length})` : `Agents with findings (${agents.length})`}
        right={<span style={{ fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute }}>
          Only agents with sufficient runtime risk signals are recommended for Gateway Control.
        </span>}>
        {agents.length === 0 ? (
          <EmptyState icon="⛨"
            text={<span><strong style={{ color: C.text }}>No runtime security findings yet.</strong>{" "}
              When AI-agent runtime evidence shows risky tool usage, unknown providers, sensitive dependencies,
              missing ownership, or human-review signals, findings will appear here.</span>}
            actionLabel={surfaceAllowsPage("runtime") ? "Open Runtime" : undefined}
            onAction={() => onNavigate?.("runtime")} />
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: bp.isMobile ? "1fr" : "minmax(300px, 5fr) 7fr", gap: 16, alignItems: "start" }}>

            {/* Master: one card per agent, worst first */}
            <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 620, overflowY: "auto" }}>
              {agents.map((a) => (
                <AgentSecurityRow key={a.key} a={a}
                  selected={selectedAgent?.key === a.key}
                  onSelect={() => setSelectedKey(a.key)} />
              ))}
            </div>

            {/* Detail: the selected agent's security posture + findings */}
            {selectedAgent && (
              <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: RADIUS.md,
                boxShadow: "0 1px 2px rgba(15,23,42,0.04)", padding: "20px 22px",
                display: "flex", flexDirection: "column", gap: 18 }}>

                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 17, fontWeight: 700, color: C.text, fontFamily: FONT.mono }}>{selectedAgent.name}</span>
                    <RiskBadge level={selectedAgent.worst} />
                    {selectedAgent.isCandidate && <StatusPill tone={C.riskMedium}>gateway candidate</StatusPill>}
                    <button onClick={() => onNavigate?.("intelligence")}
                      style={{ marginLeft: "auto", background: "transparent", border: "none", color: C.accentDark,
                        fontSize: 10.5, fontFamily: FONT.mono, cursor: "pointer", padding: 0, whiteSpace: "nowrap" }}>
                      Open in Asset Intelligence →
                    </button>
                  </div>
                  <div style={{ fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute, marginTop: 8, lineHeight: 1.7 }}>
                    key {String(selectedAgent.key).slice(0, 20)}… · {selectedAgent.findings.length} open finding{selectedAgent.findings.length !== 1 ? "s" : ""} · last seen {relTime(selectedAgent.lastSeen)}
                  </div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 10 }}>
                    {["critical", "high", "medium", "low", "info"].filter((s) => selectedAgent.counts[s] > 0).map((s) => (
                      <StatusPill key={s} tone={riskColor(s)}>{selectedAgent.counts[s]} {s}</StatusPill>
                    ))}
                  </div>
                </div>

                <Section label="Findings (worst first)">
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {selectedAgent.findings.map((f) => (
                      <FindingRow key={f.id} f={f} hideAsset isCandidate={false} onNavigate={onNavigate} />
                    ))}
                  </div>
                </Section>

                {selectedAgent.isCandidate && surfaceAllowsPage("gateway_control_center") && (
                  <button onClick={() => onNavigate?.("gateway_control_center", { gccFocus: selectedAgent.key })}
                    style={{ alignSelf: "flex-start", background: "transparent", color: C.riskMedium,
                      border: `1px solid ${C.riskMedium}44`, borderRadius: RADIUS.sm, padding: "6px 14px",
                      fontSize: 11, fontFamily: FONT.mono, cursor: "pointer" }}>
                    Review in Gateway Control Center →
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </Section>

      {bp.isMobile && <div style={{ height: 8 }} />}
      <div style={{ ...microLabel, textTransform: "none", letterSpacing: "0.04em", lineHeight: 1.6 }}>
        Observe first. Control only what matters. Findings are derived from privacy-scrubbed runtime
        evidence — identifiers and counts only, never prompts or responses.
      </div>
    </div>
  );
}
