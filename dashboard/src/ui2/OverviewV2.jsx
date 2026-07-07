import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { C, FONT, RADIUS, microLabel } from "./tokens.js";
import PageHeader from "./PageHeader.jsx";
import Section from "./Section.jsx";
import MetricCard from "./MetricCard.jsx";
import RiskBadge from "./RiskBadge.jsx";
import StatusPill from "./StatusPill.jsx";
import EvidenceCard from "./EvidenceCard.jsx";
import EmptyState from "./EmptyState.jsx";
import { surfaceAllowsPage } from "../productSurface.js";
import { useBreakpoint } from "../hooks/useBreakpoint.js";
import {
  getAssetSummary, getOpenFindings, getRecentTraces, getControlCandidates, getAttention,
} from "../overviewApi.js";

/**
 * OverviewV2 — the first ui2 page (redesign step 1, docs/ui_redesign_plan.md).
 *
 * Layout: hero line · flow strip · four primary metrics · Zone of Attention
 * (evidence-backed, conditional) · Runtime Activity (30s countdown) · Gateway
 * Control Preview. Everything shown traces back to runtime evidence; the page
 * teaches the Observe-to-Control product model in one glance.
 */

const FLOW = [
  { label: "OTel / OTLP",   page: "integrations" },
  { label: "Runtime",       page: "runtime" },
  { label: "Assets",        page: "intelligence" },
  { label: "Security",      page: "security_intel" },
  { label: "Rules",         page: null, planned: true },
  { label: "Gateway Control", page: "gateway_control_center" },
];

const SLOW_MS = 5000;

const fmtMs = (ms) => {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
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

function FlowStrip({ onNavigate }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
      {FLOW.map((step, i) => {
        const clickable = step.page && surfaceAllowsPage(step.page);
        return (
          <span key={step.label} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
            <button onClick={clickable ? () => onNavigate?.(step.page) : undefined}
              style={{
                background: C.surfaceRaised, color: step.planned ? C.textMute : C.text,
                border: `1px solid ${C.border}`, borderRadius: RADIUS.sm, padding: "6px 12px",
                fontSize: 11, fontFamily: FONT.mono, whiteSpace: "nowrap",
                cursor: clickable ? "pointer" : "default", opacity: step.planned ? 0.65 : 1,
              }}>
              {step.label}{step.planned && <span style={{ marginLeft: 6, fontSize: 9, color: C.textMute }}>planned</span>}
            </button>
            {i < FLOW.length - 1 && <span style={{ color: C.textMute, fontSize: 11 }}>→</span>}
          </span>
        );
      })}
    </div>
  );
}

export default function OverviewV2({ onNavigate }) {
  const bp = useBreakpoint();
  const [attention, setAttention]  = useState(null);
  const [assets, setAssets]        = useState(null);
  const [findings, setFindings]    = useState(null);
  const [traces, setTraces]        = useState(null);
  const [candidates, setCandidates] = useState(null);
  const [loading, setLoading]      = useState(true);

  const refreshAttention = useCallback(() => {
    getAttention().then(setAttention).catch(() => {});
  }, []);

  useEffect(() => {
    (async () => {
      const [att, a, f, t, c] = await Promise.all([
        getAttention(), getAssetSummary(), getOpenFindings(), getRecentTraces(20), getControlCandidates(),
      ]);
      setAttention(att); setAssets(a); setFindings(f); setTraces(t); setCandidates(c);
      setLoading(false);
    })();
  }, []);

  // 30-second refresh cadence, shown as a countdown — never as a sentence.
  const nextRef = useRef(30);
  const [nextIn, setNextIn] = useState(30);
  useEffect(() => {
    const id = setInterval(() => {
      nextRef.current -= 1;
      if (nextRef.current <= 0) {
        nextRef.current = 30;
        refreshAttention();
      }
      setNextIn(nextRef.current);
    }, 1000);
    return () => clearInterval(id);
  }, [refreshAttention]);

  // ── Derived, evidence-backed numbers ──────────────────────────────────────
  const assetList = useMemo(() => assets?.data.assets || [], [assets]);
  const openFindings = useMemo(() => (findings?.data || []).filter((f) => f.status === "open" || !f.status), [findings]);
  const agentsWithFindings = useMemo(
    () => assetList.filter((a) => (a.open_findings_count || 0) > 0).length, [assetList]);
  const openCandidates = useMemo(
    () => (candidates?.data || []).filter((c) => c.status === "open"), [candidates]);
  const nameByKey = useMemo(() => {
    const m = {};
    assetList.forEach((a) => { m[a.asset_key] = a.asset_name || a.service_name; });
    return m;
  }, [assetList]);

  const byType = useCallback((type) => openFindings.filter((f) => f.finding_type === type), [openFindings]);
  const distinctAssets = (rows) => new Set(rows.map((f) => f.asset_key)).size;

  const unknownProvider = useMemo(() => byType("agent_uses_unknown_model_provider"), [byType]);
  const mcpProd         = useMemo(() => byType("agent_uses_mcp_tool_in_production"), [byType]);
  const humanReview     = useMemo(() => byType("human_review_recommended"), [byType]);

  const traceRows   = useMemo(() => traces?.data || [], [traces]);
  const errorTraces = traceRows.filter((t) => (t.error_count || 0) > 0).length;
  const slowTraces  = traceRows.filter((t) => (t.duration_ms || 0) >= SLOW_MS).length;
  const lastSeenAgents = useMemo(() => {
    const seen = new Map();
    traceRows.forEach((t) => { if (t.service_name && !seen.has(t.service_name)) seen.set(t.service_name, t.start_time); });
    return [...seen.entries()].slice(0, 5);
  }, [traceRows]);

  const att = attention || {};
  const nav = (page, opts) => { if (surfaceAllowsPage(page)) onNavigate?.(page, opts); };

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 280, color: C.textMute, fontFamily: FONT.mono, fontSize: 13 }}>
      Loading overview…
    </div>
  );

  const anySample = assets?.demo || findings?.demo || traces?.demo || att.demo;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28, fontFamily: FONT.ui, maxWidth: 1160 }}>

      {/* ── Hero + flow strip ────────────────────────────────────────────── */}
      <div>
        <PageHeader
          title="Overview"
          purpose={<span>Runtime evidence from your AI systems, turned into inventory, findings, and control recommendations. <span style={{ color: C.accent }}>Observe first. Control only what matters.</span></span>}>
          <span style={{ fontSize: 10, fontFamily: FONT.mono, color: C.textMute }}>
            next refresh · <span style={{ color: C.textDim }}>{nextIn}s</span>
          </span>
          {anySample && <StatusPill tone={C.textMute}>sample data</StatusPill>}
        </PageHeader>
        <div style={{ marginTop: 16 }}>
          <FlowStrip onNavigate={onNavigate} />
        </div>
      </div>

      {/* ── Primary metrics ──────────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <MetricCard label="AI assets discovered" value={assetList.length}
          sub={`${att.systemsManaged ?? 0} managed`} tone={C.text}
          onClick={surfaceAllowsPage("intelligence") ? () => nav("intelligence") : undefined} />
        <MetricCard label="Agents with findings" value={agentsWithFindings}
          sub={`${openFindings.length} open findings`}
          tone={agentsWithFindings > 0 ? C.riskMedium : C.accent}
          onClick={surfaceAllowsPage("intelligence") ? () => nav("intelligence") : undefined} />
        <MetricCard label="Agents needing owner" value={att.agentsNeedingOwner ?? 0}
          sub="assign ownership before production expansion"
          tone={(att.agentsNeedingOwner ?? 0) > 0 ? C.riskMedium : C.accent}
          onClick={surfaceAllowsPage("governance") ? () => nav("governance") : undefined} />
        <MetricCard label="Gateway control candidates" value={openCandidates.length}
          sub="recommended for review — nothing applied automatically"
          tone={openCandidates.length > 0 ? C.riskHigh : C.accent}
          onClick={surfaceAllowsPage("gateway_control_center") ? () => nav("gateway_control_center") : undefined} />
      </div>

      {/* ── Zone of Attention (conditional, evidence-backed) ─────────────── */}
      <Section label="Zone of attention">
        {(() => {
          const cards = [];
          if (att.worstOffender) cards.push(
            <EvidenceCard key="worst" level="high" title={att.worstOffender.asset_name}
              reason={`${att.worstOffender.highFindings} high-severity open finding${att.worstOffender.highFindings !== 1 ? "s" : ""} · ${att.worstOffender.errorTraces} error trace${att.worstOffender.errorTraces !== 1 ? "s" : ""} — the agent that most needs attention today.`}
              actionLabel="Investigate →" onAction={() => nav("intelligence")} />);
          if ((att.agentsNeedingOwner ?? 0) > 0) cards.push(
            <EvidenceCard key="owner" level="medium" title="Agent needs owner"
              reason={`${att.agentsNeedingOwner} observed AI asset${att.agentsNeedingOwner !== 1 ? "s" : ""} without assigned ownership should be reviewed before production expansion.`}
              pills={["agent_missing_owner"]}
              actionLabel="Assign owner →" onAction={() => nav("governance")} />);
          if (unknownProvider.length > 0) cards.push(
            <EvidenceCard key="provider" level="high" title="Unknown provider in production"
              reason={`${distinctAssets(unknownProvider)} agent${distinctAssets(unknownProvider) !== 1 ? "s" : ""} using a model provider outside the known catalog.`}
              pills={["agent_uses_unknown_model_provider"]}
              actionLabel="Review →" onAction={() => nav("security_intel")} />);
          if (mcpProd.length > 0) cards.push(
            <EvidenceCard key="mcp" level="high" title="MCP tools in production"
              reason={`${distinctAssets(mcpProd)} agent${distinctAssets(mcpProd) !== 1 ? "s" : ""} invoking MCP tools in a production environment (${mcpProd.reduce((n, f) => n + (f.occurrence_count || 1), 0)} occurrences).`}
              pills={["agent_uses_mcp_tool_in_production"]}
              actionLabel="Review →" onAction={() => nav("security_intel")} />);
          if (humanReview.length > 0) cards.push(
            <EvidenceCard key="review" level="medium" title="Human review recommended"
              reason={`${distinctAssets(humanReview)} agent${distinctAssets(humanReview) !== 1 ? "s" : ""} with a high-risk runtime combination that warrants a person's judgement.`}
              pills={humanReview.slice(0, 1).flatMap((f) => (f.evidence?.reasons || []).slice(0, 2))}
              actionLabel="Review →" onAction={() => nav("security_intel")} />);
          return cards.length > 0
            ? <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>{cards}</div>
            : <EmptyState icon="✓" text="Nothing needs attention right now. New signals appear here as runtime evidence arrives." />;
        })()}
      </Section>

      {/* ── Runtime activity + Gateway Control preview ───────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: bp.isMobile ? "1fr" : "3fr 2fr", gap: 16 }}>

        <Section label="Runtime activity"
          right={<span style={{ fontSize: 10, fontFamily: FONT.mono, color: C.textMute }}>{errorTraces} error · {slowTraces} slow</span>}>
          <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: RADIUS.md, padding: "6px 18px" }}>
            {traceRows.length > 0 ? traceRows.slice(0, 8).map((t, i) => (
              <div key={t.trace_id}
                onClick={surfaceAllowsPage("runtime") ? () => nav("runtime") : undefined}
                style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0",
                  borderBottom: i < Math.min(traceRows.length, 8) - 1 ? `1px solid ${C.border}` : "none",
                  cursor: surfaceAllowsPage("runtime") ? "pointer" : "default" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12.5, color: C.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {t.root_span_name || t.trace_id.slice(0, 12)}
                  </div>
                  <div style={{ fontSize: 10, fontFamily: FONT.mono, color: C.textMute, marginTop: 2 }}>
                    {t.service_name || "—"} · {relTime(t.start_time)}
                  </div>
                </div>
                <span style={{ fontFamily: FONT.mono, fontSize: 11.5, color: (t.duration_ms || 0) >= SLOW_MS ? C.riskMedium : C.text }}>{fmtMs(t.duration_ms)}</span>
                {t.error_count > 0
                  ? <StatusPill tone={C.riskHigh}>{t.error_count} error{t.error_count > 1 ? "s" : ""}</StatusPill>
                  : <span style={{ fontFamily: FONT.mono, fontSize: 11, color: C.textMute }}>ok</span>}
              </div>
            )) : (
              <div style={{ padding: "14px 0" }}>
                <EmptyState icon="⟶" text="No runtime traces yet. Point an OTLP exporter at ObserveAgents and executions appear here."
                  actionLabel={surfaceAllowsPage("integrations") ? "Open Setup" : undefined}
                  onAction={() => nav("integrations")} />
              </div>
            )}
          </div>
          {lastSeenAgents.length > 0 && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
              {lastSeenAgents.map(([name, ts]) => (
                <StatusPill key={name} tone={C.textDim}>{name} · {relTime(ts)}</StatusPill>
              ))}
            </div>
          )}
        </Section>

        <Section label="Gateway control preview"
          right={surfaceAllowsPage("gateway_control_center") && openCandidates.length > 0 && (
            <button onClick={() => nav("gateway_control_center")}
              style={{ background: "transparent", border: `1px solid ${C.border}`, color: C.textDim,
                padding: "4px 12px", borderRadius: RADIUS.sm, fontSize: 10.5, fontFamily: FONT.mono, cursor: "pointer" }}>
              Control Center →
            </button>
          )}>
          {openCandidates.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {openCandidates.slice(0, 3).map((cand) => {
                const controls = cand.evidence?.recommended_controls || [];
                const top = controls[0];
                return (
                  <div key={cand.id} style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: RADIUS.md, padding: "14px 16px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8, flexWrap: "wrap" }}>
                      <span style={{ fontSize: 13, fontWeight: 600, color: C.text, fontFamily: FONT.mono }}>
                        {nameByKey[cand.asset_key] || cand.asset_key.slice(0, 12) + "…"}
                      </span>
                      <RiskBadge level={cand.severity} />
                      <StatusPill tone={C.textDim}>{cand.evidence?.environment || "unknown"}</StatusPill>
                    </div>
                    <div style={{ fontSize: 11.5, color: C.textDim, lineHeight: 1.55, marginBottom: 10 }}>
                      {cand.evidence?.trigger_count || 0} trigger finding{(cand.evidence?.trigger_count || 0) !== 1 ? "s" : ""}
                      {top ? <> · suggested: <span style={{ color: C.text }}>{top.control}</span>{top.kind === "hard" && <span style={{ color: C.riskHigh }}> (requires Gateway routing)</span>}</> : null}
                    </div>
                    {surfaceAllowsPage("gateway_control_center") && (
                      <button onClick={() => onNavigate?.("gateway_control_center", { gccFocus: cand.asset_key })}
                        style={{ background: "transparent", color: C.riskMedium, border: `1px solid ${C.riskMedium}44`,
                          borderRadius: RADIUS.sm, padding: "5px 13px", fontSize: 10.5, fontFamily: FONT.mono, cursor: "pointer" }}>
                        Review in Control Center →
                      </button>
                    )}
                  </div>
                );
              })}
              <div style={{ ...microLabel, letterSpacing: "0.04em", textTransform: "none", lineHeight: 1.5 }}>
                Recommendations only — no control is applied automatically.
              </div>
            </div>
          ) : (
            <EmptyState icon="⊘" text="No agents are recommended for Gateway control. Candidates appear when runtime evidence shows high-risk behavior." />
          )}
        </Section>
      </div>
    </div>
  );
}
