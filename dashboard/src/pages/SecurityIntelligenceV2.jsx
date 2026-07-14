import { useState, useEffect, useMemo } from "react";
import { ShieldAlert, AlertTriangle, Info } from "lucide-react";
import { C, FONT, RADIUS, CARD, microLabel, riskColor } from "../ui2/tokens.js";
import PageHeader from "../ui2/PageHeader.jsx";
import Section from "../ui2/Section.jsx";
import RiskBadge from "../ui2/RiskBadge.jsx";
import StatusPill from "../ui2/StatusPill.jsx";
import EmptyState from "../ui2/EmptyState.jsx";
import { Donut, SegBar, BarRow, severitySegments } from "../ui2/viz.jsx";
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

function FindingRow({ f, assetName, isCandidate, onNavigate, hideAsset }) {
  const sevColor = riskColor(f.severity);
  const SevIcon = SEV_ICON[f.severity] || Info;
  return (
    <div style={{ display: "flex", gap: 12, alignItems: "flex-start",
      background: `linear-gradient(90deg, ${sevColor}0A 0%, ${C.surface} 30%)`,
      border: `1px solid ${C.border}`, borderLeft: `3px solid ${sevColor}`,
      borderRadius: RADIUS.md, padding: "13px 16px", boxShadow: CARD.boxShadow }}>
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
          {f.source && <StatusPill tone={C.textMute}>{f.source}</StatusPill>}
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
      <div style={{ marginTop: 8 }}>
        <SegBar segments={severitySegments(a.counts)} height={5} />
      </div>
    </div>
  );
}

export default function SecurityIntelligenceV2({ onNavigate }) {
  const bp = useBreakpoint();
  const [assets, setAssets] = useState(null);
  const [findings, setFindings] = useState(null);
  const [candidates, setCandidates] = useState(null);
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

  const candidateKeys = useMemo(
    () => new Set((candidates?.data || []).filter((c) => c.status === "open").map((c) => c.asset_key)),
    [candidates]);

  const listRows = useMemo(() => [...securityFindings].sort((a, b) =>
    (SEV_RANK[b.severity] || 0) - (SEV_RANK[a.severity] || 0)
    || new Date(b.last_seen || 0) - new Date(a.last_seen || 0)), [securityFindings]);

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

  const loading = assets === null || findings === null || candidates === null;
  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 280, color: C.textMute, fontFamily: FONT.mono, fontSize: 13 }}>
      Loading security intelligence…
    </div>
  );

  const anySample = assets?.demo || findings?.demo || candidates?.demo;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 26, fontFamily: FONT.ui, maxWidth: 1160 }}>

      <div className="oa-rise">
        <PageHeader
          eyebrow="Observe · Risk Investigation"
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

      {/* Posture band: severity donut + worst agents at a glance */}
      {securityFindings.length > 0 && (
        <div className="oa-rise oa-rise-1" style={{ ...CARD, borderRadius: RADIUS.lg, padding: "18px 22px", display: "flex", gap: 28, alignItems: "center", flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <Donut size={110} thickness={11}
              segments={severitySegments(securityFindings.reduce((m, f) => { m[f.severity] = (m[f.severity] || 0) + 1; return m; }, {}))}
              centerValue={securityFindings.length} centerLabel="findings" />
            <div style={{ fontFamily: FONT.mono, fontSize: 10.5, lineHeight: 2, minWidth: 0 }}>
              {severitySegments(securityFindings.reduce((m, f) => { m[f.severity] = (m[f.severity] || 0) + 1; return m; }, {})).map((d) => (
                <div key={d.label} style={{ color: C.textDim }}>
                  <span style={{ color: d.color }}>●</span> {d.value} {d.label}
                </div>
              ))}
            </div>
          </div>
          <div style={{ flex: 1, minWidth: 260 }}>
            <div style={{ ...microLabel, marginBottom: 12 }}>Most findings · worst first</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {agents.slice(0, 4).map((a) => (
                <BarRow key={a.key} label={a.name} value={a.findings.length}
                  max={Math.max(...agents.map((x) => x.findings.length), 1)}
                  color={riskColor(a.worst)}
                  right={`${a.findings.length} finding${a.findings.length !== 1 ? "s" : ""}`}
                  onClick={() => setSelectedKey(a.key)} />
              ))}
            </div>
          </div>
        </div>
      )}

      <Section
        label={`Agents with findings (${agents.length})`}
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
              <div style={{ ...CARD, padding: "20px 22px",
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
