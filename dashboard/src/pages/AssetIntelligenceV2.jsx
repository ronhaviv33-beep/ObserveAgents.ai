import { useState, useEffect, useMemo, useCallback } from "react";
import { C, FONT, RADIUS, microLabel } from "../ui2/tokens.js";
import PageHeader from "../ui2/PageHeader.jsx";
import Section from "../ui2/Section.jsx";
import MetricCard from "../ui2/MetricCard.jsx";
import RiskBadge from "../ui2/RiskBadge.jsx";
import StatusPill from "../ui2/StatusPill.jsx";
import EmptyState from "../ui2/EmptyState.jsx";
import Modal from "../ui2/Modal.jsx";
import { surfaceAllowsPage } from "../productSurface.js";
import { useBreakpoint } from "../hooks/useBreakpoint.js";
import { runIntelligence } from "../api.js";
import { getAssetSummary, getControlCandidates } from "../overviewApi.js";

/**
 * AssetIntelligenceV2 — redesign step 4 (docs/ui_redesign_plan.md).
 *
 * The central evidence surface per AI asset: identity, runtime evidence,
 * capabilities, dependencies, grouped findings, and the Gateway Control
 * connection. Master/detail: worst-first asset list on the left, selected
 * asset detail on the right. Trace-discovered inventory, observe-only.
 */

const SEV_RANK = { critical: 5, high: 4, medium: 3, low: 2, info: 1 };
const CATEGORY_ORDER = ["security", "operations", "dependency", "inventory", "performance"];
const CATEGORY_LABEL = {
  security: "Security", operations: "Operations / runtime", dependency: "Dependencies",
  inventory: "Governance / inventory", performance: "Performance", cost: "Cost",
};

const relTime = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  const m = Math.floor((Date.now() - d.getTime()) / 60000);
  if (m < 2) return "just now";
  if (m < 60) return `${m}m ago`;
  if (m < 1440) return `${Math.floor(m / 60)}h ago`;
  return `${Math.floor(m / 1440)}d ago`;
};

const openFinds = (a) => (a.findings || []).filter((f) => f.status === "open");

/** Compact structured-evidence line for a finding — never a raw JSON dump. */
const evidenceLine = (ev) => {
  if (!ev) return null;
  const parts = [];
  if (ev.span_count != null) parts.push(`spans ${ev.span_count}`);
  if (ev.max_total_tokens != null) parts.push(`max ${Number(ev.max_total_tokens).toLocaleString()} tok`);
  if (ev.max_reasoning_tokens != null) parts.push(`max reasoning ${Number(ev.max_reasoning_tokens).toLocaleString()}`);
  if (Array.isArray(ev.details) && ev.details.length) parts.push(ev.details.slice(0, 3).join(" · "));
  return parts.length ? parts.join(" · ") : null;
};
const hasSecurityRisk = (a) => openFinds(a).some((f) => f.category === "security" && SEV_RANK[f.severity] >= 3);
const traceDiscovered = (a) => (a.status || []).includes("runtime_observed");

/**
 * Customer-facing discovery identity (A3/A4). Evidence language only —
 * never confidence scores, percentages, or high/medium/low labels.
 */
const discoveryIdentity = (a) => {
  const method = a.discovery_method
    || (traceDiscovered(a) ? "runtime_telemetry" : "gateway_traffic");
  if (method === "declared_identity") return {
    label: "Explicit Agent", tone: C.accent,
    sub: "Identified from explicit agent metadata.",
  };
  if (method === "runtime_telemetry") return {
    label: "Runtime-discovered AI Workload", tone: C.teal,
    sub: "Discovered from auto-instrumented runtime telemetry.",
  };
  return {
    label: "Gateway-observed", tone: C.textDim,
    sub: "Observed from gateway traffic.",
  };
};

/** Observed runtime signals, derived only from summary data — never raw content. */
const observedSignals = (a) => {
  const caps = a.capabilities || [];
  const hasCap = (t) => caps.some((c) => c.capability_type === t);
  const usage = a.runtime_usage || {};
  const signals = [];
  if ((usage.llm_call_count || 0) > 0) signals.push("LLM calls");
  if ((a.providers || []).length || (a.models || []).length) signals.push("Provider/model");
  if ((usage.input_tokens || 0) + (usage.output_tokens || 0) > 0) signals.push("Token usage");
  if ((a.tools || []).length || hasCap("tool")) signals.push("Tool activity");
  if (hasCap("mcp")) signals.push("MCP activity");
  if (hasCap("database")) signals.push("Database access");
  if (hasCap("external_api") || (a.dependencies || []).length) signals.push("External API activity");
  if ((a.status || []).includes("error_observed")) signals.push("Errors");
  if (["production", "prod"].includes((a.environment || "").toLowerCase())) signals.push("Production environment");
  if ((a.findings || []).some((f) => f.source === "detection_rules" && f.status === "open")) signals.push("Detection rule matches");
  return signals;
};

/** Optional metadata that would make attribution richer — never framed as required. */
const optionalMetadata = (a) => {
  const out = [];
  if (!a.owner) out.push("owner/team");
  if ((a.discovery_method || (traceDiscovered(a) ? "runtime_telemetry" : "gateway_traffic")) !== "declared_identity") out.push("explicit agent name");
  if (!a.environment) out.push("environment");
  if (!a.service_name) out.push("service name");
  return out;
};

const FILTERS = [
  { id: "all",        label: "All",                test: () => true },
  { id: "findings",   label: "With findings",      test: (a) => (a.open_findings_count || 0) > 0 },
  { id: "security",   label: "Security risk",      test: (a) => hasSecurityRisk(a) },
  { id: "candidates", label: "Gateway candidates", test: (a, cand) => cand.has(a.asset_key) },
  { id: "traced",     label: "Trace discovered",   test: (a) => traceDiscovered(a) },
];

function ChipList({ label, items, tone = C.textDim, max = 10 }) {
  if (!items?.length) return null;
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ ...microLabel, marginBottom: 6 }}>{label}</div>
      <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
        {items.slice(0, max).map((x) => <StatusPill key={x} tone={tone}>{x}</StatusPill>)}
        {items.length > max && <StatusPill tone={C.textMute}>+{items.length - max}</StatusPill>}
      </div>
    </div>
  );
}

function AssetRow({ a, isCandidate, onSelect }) {
  const risk = a.high_findings_count > 0 ? "high" : (a.open_findings_count || 0) > 0 ? "medium" : "info";
  return (
    <div onClick={onSelect} className="oa-lift" role="button" tabIndex={0}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(); } }}
      style={{
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderLeft: `3px solid ${risk === "high" ? C.riskHigh : risk === "medium" ? C.riskMedium : C.border}`,
        borderRadius: RADIUS.md, padding: "12px 14px", cursor: "pointer",
      }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 6 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: C.text, fontFamily: FONT.mono }}>{a.asset_name}</span>
        {isCandidate && <StatusPill tone={C.riskMedium}>gateway candidate</StatusPill>}
      </div>
      <div style={{ fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute, lineHeight: 1.6 }}>
        {a.environment || "unknown"} · <span style={{ color: discoveryIdentity(a).tone }}>{discoveryIdentity(a).label}</span> · {relTime(a.last_seen)}
        <br />
        {a.open_findings_count || 0} findings · {a.capabilities_count || 0} capabilities · {(a.dependencies || []).length} dependencies
      </div>
    </div>
  );
}

export default function AssetIntelligenceV2({ onNavigate }) {
  const bp = useBreakpoint();
  const [assets, setAssets] = useState(null);
  const [candidates, setCandidates] = useState(null);
  const [selectedKey, setSelectedKey] = useState(null);
  const [filter, setFilter] = useState("all");
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    const [a, c] = await Promise.all([getAssetSummary(), getControlCandidates()]);
    setAssets(a); setCandidates(c);
  }, []);
  useEffect(() => { (async () => { await load(); })(); }, [load]);

  const handleRun = () => {
    setRunning(true); setRunResult(null); setError(null);
    runIntelligence()
      .then((res) => {
        setRunResult(`${res.capabilities_created + res.capabilities_updated} capabilities · ${res.findings_created + res.findings_updated} findings`);
        return load();
      })
      .catch((e) => setError(e.message))
      .finally(() => setRunning(false));
  };

  const candidateByKey = useMemo(() => {
    const m = new Map();
    (candidates?.data || []).filter((c) => c.status === "open").forEach((c) => m.set(c.asset_key, c));
    return m;
  }, [candidates]);
  const candidateKeys = useMemo(() => new Set(candidateByKey.keys()), [candidateByKey]);

  const list = useMemo(() => {
    const rows = (assets?.data.assets || []).filter((a) =>
      FILTERS.find((f) => f.id === filter)?.test(a, candidateKeys));
    // Worst-first: candidates → high severity → recent activity.
    return rows.sort((a, b) =>
      (candidateKeys.has(b.asset_key) - candidateKeys.has(a.asset_key))
      || ((b.high_findings_count || 0) - (a.high_findings_count || 0))
      || (new Date(b.last_seen || 0) - new Date(a.last_seen || 0)));
  }, [assets, filter, candidateKeys]);

  // Detail opens as a popup only when an asset is clicked — nothing selected by default.
  const selected = useMemo(
    () => list.find((a) => a.asset_key === selectedKey) || null,
    [list, selectedKey]);

  if (assets === null || candidates === null) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 280, color: C.textMute, fontFamily: FONT.mono, fontSize: 13 }}>
      Loading asset intelligence…
    </div>
  );

  const allAssets = assets.data.assets || [];
  const cand = selected ? candidateByKey.get(selected.asset_key) : null;
  const selOpen = selected ? openFinds(selected) : [];
  const grouped = CATEGORY_ORDER
    .map((cat) => [cat, selOpen.filter((f) => f.category === cat)
      .sort((x, y) => (SEV_RANK[y.severity] || 0) - (SEV_RANK[x.severity] || 0))])
    .filter(([, rows]) => rows.length > 0);
  const firstSeen = selected
    ? [...(selected.capabilities || []), ...(selected.findings || [])]
        .map((r) => r.first_seen).filter(Boolean).sort()[0]
    : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24, fontFamily: FONT.ui, maxWidth: 1240 }}>

      <div className="oa-rise">
        <PageHeader
          eyebrow="Observe · Inventory"
          title="Asset Intelligence"
          purpose="AI assets discovered from runtime evidence — ownership, capabilities, dependencies, findings, and control readiness.">
          {(assets.demo || candidates.demo) && <StatusPill tone={C.textMute}>sample data</StatusPill>}
          <button onClick={handleRun} disabled={running}
            style={{ background: C.accent, color: C.accentInk, border: "none", borderRadius: RADIUS.sm,
              padding: "8px 16px", fontSize: 12, fontWeight: 700, fontFamily: FONT.ui, cursor: running ? "wait" : "pointer", opacity: running ? 0.6 : 1 }}>
            {running ? "Running…" : "Run Intelligence"}
          </button>
        </PageHeader>
        <div style={{ fontSize: 11.5, fontFamily: FONT.mono, color: C.textDim, marginTop: 10 }}>
          Trace-discovered inventory. Evidence-backed findings. Observe-only until control is explicitly configured.
        </div>
        <div style={{ fontSize: 11.5, color: C.textMute, marginTop: 6 }}>
          Runtime evidence turns AI activity into assets, capabilities, dependencies, and findings.
        </div>
        {runResult && <div style={{ fontSize: 11, fontFamily: FONT.mono, color: C.accent, marginTop: 8 }}>Intelligence run complete — {runResult}</div>}
        {error && <div style={{ fontSize: 11, fontFamily: FONT.mono, color: C.riskHigh, marginTop: 8 }}>{error}</div>}
      </div>

      {allAssets.length > 0 && (
        <div className="oa-rise oa-rise-1" style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <MetricCard label="AI assets" value={allAssets.length}
            sub={`${allAssets.filter(traceDiscovered).length} trace discovered`} />
          <MetricCard label="With findings" value={allAssets.filter((a) => (a.open_findings_count || 0) > 0).length}
            sub="open findings on the asset"
            tone={allAssets.some((a) => (a.open_findings_count || 0) > 0) ? C.riskMedium : C.ok} />
          <MetricCard label="Security risk" value={allAssets.filter(hasSecurityRisk).length}
            sub="medium+ security findings"
            tone={allAssets.some(hasSecurityRisk) ? C.riskHigh : C.ok} />
          <MetricCard label="Gateway candidates" value={candidateKeys.size}
            sub="recommended for control review"
            tone={candidateKeys.size > 0 ? C.violet : C.ok} />
        </div>
      )}

      {allAssets.length === 0 ? (
        <EmptyState icon="◈"
          text={<span><strong style={{ color: C.text }}>No AI assets discovered yet.</strong>{" "}
            Send OpenTelemetry traces from AI agents to build runtime asset inventory, capabilities, dependencies, and findings.</span>}
          actionLabel={surfaceAllowsPage("integrations") ? "Open Setup" : undefined}
          onAction={() => onNavigate?.("integrations")} />
      ) : (
        <div>

          {/* ── Asset list — click a card to open its detail popup ──────── */}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
            {FILTERS.map((f) => (
              <button key={f.id} onClick={() => setFilter(f.id)}
                style={{
                  background: filter === f.id ? C.surfaceRaised : "transparent",
                  color: filter === f.id ? C.text : C.textDim,
                  border: `1px solid ${filter === f.id ? C.borderStrong : C.border}`,
                  borderRadius: 999, padding: "5px 12px", fontSize: 10.5, fontFamily: FONT.mono, cursor: "pointer",
                }}>
                {f.label}
              </button>
            ))}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: bp.isMobile ? "1fr" : "repeat(auto-fill, minmax(300px, 1fr))", gap: 10 }}>
            {list.length > 0 ? list.map((a) => (
              <AssetRow key={a.asset_key} a={a}
                isCandidate={candidateKeys.has(a.asset_key)}
                onSelect={() => setSelectedKey(a.asset_key)} />
            )) : (
              <div style={{ fontSize: 12, color: C.textMute, fontFamily: FONT.mono, padding: "16px 4px" }}>
                No assets match this filter.
              </div>
            )}
          </div>

          {/* ── Asset detail popup — opens on click, closes on ✕ / outside / Escape ── */}
          <Modal open={!!selected} onClose={() => setSelectedKey(null)}>
          {selected && (
            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", paddingRight: 40 }}>
                  <span style={{ fontSize: 17, fontWeight: 700, color: C.text, fontFamily: FONT.mono }}>{selected.asset_name}</span>
                  <StatusPill tone={discoveryIdentity(selected).tone}>{discoveryIdentity(selected).label}</StatusPill>
                  {selected.environment && <StatusPill tone={["production", "prod"].includes((selected.environment || "").toLowerCase()) ? C.riskMedium : C.riskLow}>{selected.environment}</StatusPill>}
                  {cand && <StatusPill tone={C.riskMedium}>gateway recommended</StatusPill>}
                </div>
                <div style={{ fontSize: 11.5, color: C.textDim, marginTop: 6 }}>
                  {discoveryIdentity(selected).sub}
                </div>
                <div style={{ fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute, marginTop: 8, lineHeight: 1.7 }}>
                  key {selected.asset_key.slice(0, 20)}… · service {selected.service_name || "—"} ·
                  owner {selected.owner || "—"} ·
                  first seen {firstSeen ? relTime(firstSeen) : "—"} · last seen {relTime(selected.last_seen)}
                </div>
              </div>

              {observedSignals(selected).length > 0 && (
                <Section label="Observed signals">
                  <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                    {observedSignals(selected).map((s) => <StatusPill key={s} tone={C.teal}>{s}</StatusPill>)}
                  </div>
                </Section>
              )}

              <Section label="Runtime evidence">
                <div style={{ fontSize: 12, fontFamily: FONT.mono, color: C.textDim, lineHeight: 1.8 }}>
                  {selected.trace_count || 0} trace{(selected.trace_count || 0) !== 1 ? "s" : ""} · {selected.span_count || 0} spans · last activity {relTime(selected.last_seen)}
                  {selected.runtime_usage && (
                    <> · {selected.runtime_usage.llm_call_count || 0} LLM calls · {(selected.runtime_usage.input_tokens || 0).toLocaleString()}→{(selected.runtime_usage.output_tokens || 0).toLocaleString()} tokens</>
                  )}
                </div>
                <div style={{ display: "flex", gap: 20, flexWrap: "wrap", marginTop: 10 }}>
                  <ChipList label="Providers" items={selected.providers} tone={C.riskLow} />
                  <ChipList label="Models" items={selected.models} tone={C.purple} />
                </div>
              </Section>

              <Section label="Capabilities">
                {(selected.capabilities || []).length > 0 ? (
                  <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                    {selected.capabilities.slice(0, 18).map((c) => (
                      <StatusPill key={c.id} tone={c.capability_type === "database" || c.capability_type === "shell" ? C.riskHigh : c.capability_type === "mcp" ? C.riskMedium : C.teal}>
                        {c.capability_type}: {c.capability_name}
                      </StatusPill>
                    ))}
                    {selected.capabilities.length > 18 && <StatusPill tone={C.textMute}>+{selected.capabilities.length - 18}</StatusPill>}
                  </div>
                ) : <span style={{ fontSize: 12, color: C.textMute, fontFamily: FONT.mono }}>No evidence yet — run Intelligence after ingesting traces.</span>}
              </Section>

              <Section label="Dependencies">
                <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
                  <ChipList label="Tools" items={selected.tools} tone={C.teal} />
                  <ChipList label="Reached at runtime" items={selected.dependencies} tone={C.riskLow} />
                </div>
                {!(selected.tools || []).length && !(selected.dependencies || []).length && (
                  <span style={{ fontSize: 12, color: C.textMute, fontFamily: FONT.mono }}>No evidence yet.</span>
                )}
              </Section>

              <Section label={`Findings (${selOpen.length} open)`}>
                {grouped.length > 0 ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                    {grouped.map(([cat, rows]) => (
                      <div key={cat}>
                        <div style={{ ...microLabel, marginBottom: 7 }}>{CATEGORY_LABEL[cat] || cat}</div>
                        <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                          {rows.map((f) => (
                            <div key={f.id} style={{ display: "flex", alignItems: "baseline", gap: 9, flexWrap: "wrap" }}>
                              <RiskBadge level={f.severity} />
                              <span style={{ fontSize: 12.5, color: C.text }}>{f.title}</span>
                              {(f.occurrence_count || 1) > 1 && <span style={{ fontFamily: FONT.mono, fontSize: 10, color: C.textDim }}>×{f.occurrence_count}</span>}
                              <StatusPill tone={C.textMute}>{f.finding_type}</StatusPill>
                              <span style={{ fontSize: 10, fontFamily: FONT.mono, color: C.textMute, marginLeft: "auto" }}>{f.source} · {relTime(f.last_seen)}</span>
                              <div style={{ flexBasis: "100%", fontSize: 11.5, color: C.textDim, lineHeight: 1.55 }}>{f.summary}</div>
                              {evidenceLine(f.evidence) && (
                                <div style={{ flexBasis: "100%", fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute, lineHeight: 1.5 }}>{evidenceLine(f.evidence)}</div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : <span style={{ fontSize: 12, color: C.textMute, fontFamily: FONT.mono }}>No open findings for this asset.</span>}
              </Section>

              <Section label="Gateway control">
                {cand ? (
                  <div>
                    {/* trailing parenthetical duplicates the findings above */}
                    <div style={{ fontSize: 12, color: C.textDim, lineHeight: 1.65, marginBottom: 8 }}>
                      {(cand.evidence?.reason || cand.summary || "").replace(/\s*\([^()]*\)\s*\.?\s*$/, ".")}
                    </div>
                    {(cand.evidence?.recommended_controls || []).filter((cc) => cc.kind !== "soft").length > 0 && (
                      <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginBottom: 12 }}>
                        {cand.evidence.recommended_controls.filter((cc) => cc.kind !== "soft").slice(0, 5).map((cc) => (
                          <StatusPill key={cc.control} tone={cc.kind === "routing" ? C.purple : C.violet}>
                            {cc.control}
                          </StatusPill>
                        ))}
                      </div>
                    )}
                    {surfaceAllowsPage("gateway_control_center") && (
                      <button onClick={() => onNavigate?.("gateway_control_center", { gccFocus: selected.asset_key })}
                        style={{ background: "transparent", color: C.riskMedium, border: `1px solid ${C.riskMedium}44`,
                          borderRadius: RADIUS.sm, padding: "6px 14px", fontSize: 11, fontFamily: FONT.mono, cursor: "pointer" }}>
                        Review in Gateway Control Center →
                      </button>
                    )}
                  </div>
                ) : (
                  <span style={{ fontSize: 12, color: C.textMute, fontFamily: FONT.mono }}>
                    No Gateway control recommendation for this asset yet.
                  </span>
                )}
              </Section>

              {optionalMetadata(selected).length > 0 && (
                <Section label="Optional metadata can improve attribution">
                  <div style={{ fontSize: 11.5, color: C.textMute, lineHeight: 1.6, marginBottom: 8 }}>
                    Visibility starts from runtime telemetry. Optional metadata can make attribution richer.
                  </div>
                  <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                    {optionalMetadata(selected).map((m) => <StatusPill key={m} tone={C.textMute}>{m}</StatusPill>)}
                  </div>
                </Section>
              )}
            </div>
          )}
          </Modal>
        </div>
      )}
    </div>
  );
}
