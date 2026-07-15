import { useState, useEffect, useCallback, useMemo } from "react";
import { C, FONT, RADIUS, CARD, microLabel } from "../ui2/tokens.js";
import { FlowRibbon } from "../ui2/viz.jsx";
import PageHeader from "../ui2/PageHeader.jsx";
import Section from "../ui2/Section.jsx";
import MetricCard from "../ui2/MetricCard.jsx";
import RiskBadge from "../ui2/RiskBadge.jsx";
import StatusPill from "../ui2/StatusPill.jsx";
import EmptyState from "../ui2/EmptyState.jsx";
import { surfaceAllowsPage } from "../productSurface.js";
import { useBreakpoint } from "../hooks/useBreakpoint.js";
import { dismissFinding, reopenFinding } from "../api.js";
import { getControlCandidates, getAssetSummary } from "../overviewApi.js";

/**
 * GatewayControlCenterV2 — redesign step 2 (docs/ui_redesign_plan.md).
 *
 * The action workspace of the Observe-to-Control story: a review queue of AI
 * agents that runtime evidence recommends for Gateway control. Observe-only —
 * nothing here blocks, reroutes, or configures the Gateway. Everyone can view;
 * only admins act (dismiss/reopen; the server enforces this with a 403).
 *
 * Data: GCR2's gateway_control_recommended findings (category=control), which
 * carry trigger provenance and server-mapped suggested controls in evidence.
 */

const JOURNEY = [
  { label: "Observed via OTel", tone: "#3BC7F0" },
  { label: "Risk detected", tone: "#FF8A4C" },
  { label: "Gateway recommended", tone: "#B07BFF" },
  { label: "Policy draft", planned: true },
  { label: "Explicit enforcement", planned: true },
];

// Suggested controls show only what the Control Center itself will apply:
// remote control of the agent through the Gateway. Soft actions (human
// review, alert-only rules) live on their own pages and are filtered out.
const KIND_META = {
  routing: { label: "routing step",   tone: "purple" },
  hard:    { label: "in development", tone: "violet" },
};

/** The reason's trailing parenthesized finding list duplicates the trigger
 *  pills rendered below it — keep the sentence, drop the parenthetical. */
const trimReason = (text) =>
  (text || "").replace(/\s*\([^()]*\)\s*\.?\s*$/, ".");

// "Why this agent is here", split by the evidence source that produced each
// finding (keys match app/gateway_control.py's trigger_findings_by_source).
const TRIGGER_GROUPS = [
  { key: "detection_rules", label: "Detection Rules" },
  { key: "runtime_security", label: "Security Intelligence" },
  { key: "otel_trace",       label: "Asset Intelligence" },
];

// Fallback only for candidates whose evidence lacks server-mapped controls —
// mirrors app/gateway_control.py's mapping at coarse granularity.
const FALLBACK_CONTROLS = {
  agent_uses_unknown_model_provider: [{ control: "provider allowlist", kind: "hard" }],
  agent_uses_mcp_tool_in_production: [{ control: "mcp/tool usage policy", kind: "hard" }],
  repeated_tool_errors:              [{ control: "alert owner / retry fallback / human review", kind: "soft" }],
  agent_has_database_access:         [{ control: "human review / route through gateway", kind: "routing" }],
  agent_uses_unmanaged_external_api: [{ control: "human review / route through gateway", kind: "routing" }],
  agent_has_broad_tool_surface:      [{ control: "tool-scope policy", kind: "hard" }],
  human_review_recommended:          [{ control: "human review requirement", kind: "soft" }],
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

function JourneyStrip() {
  return (
    <div style={{ ...CARD, borderRadius: RADIUS.lg, padding: "16px 22px 8px", position: "relative", overflow: "hidden" }}>
      <div aria-hidden="true" style={{ position: "absolute", inset: 0, pointerEvents: "none", background: "radial-gradient(600px 120px at 50% 0%, rgba(176,123,255,0.07), transparent 70%)" }} />
      <div style={{ ...microLabel, fontSize: 9, marginBottom: 12 }}>From evidence to explicit control</div>
      <FlowRibbon steps={JOURNEY} compact />
    </div>
  );
}

function suggestedControls(cand) {
  const fromServer = cand.evidence?.recommended_controls;
  const all = (Array.isArray(fromServer) && fromServer.length > 0)
    ? fromServer
    : (() => {
        const out = [];
        const seen = new Set();
        for (const t of cand.evidence?.trigger_finding_types || []) {
          for (const c of FALLBACK_CONTROLS[t] || []) {
            if (!seen.has(c.control)) { seen.add(c.control); out.push(c); }
          }
        }
        return out;
      })();
  // Control Center scope: only controls applied through it (remote control
  // of the agent via the Gateway) — drop soft/observe-side actions.
  return all.filter((c) => c.kind !== "soft");
}

function CandidateCard({ cand, asset, isAdmin, expanded, onToggle, onAction }) {
  const ev = cand.evidence || {};
  const name = asset?.asset_name || asset?.service_name || cand.asset_key.slice(0, 12) + "…";
  const owner = asset?.owner || asset?.team || null;
  const controls = suggestedControls(cand);
  const hasHard = controls.some((c) => c.kind === "hard");
  return (
    <div style={{ background: C.surface, border: `1px solid ${expanded ? C.borderStrong : C.border}`, borderRadius: RADIUS.md, overflow: "hidden" }}>
      <div onClick={onToggle} style={{ display: "flex", alignItems: "center", gap: 12, padding: "14px 18px", cursor: "pointer", flexWrap: "wrap" }}>
        <div style={{ minWidth: 170, flex: "1 1 170px" }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: C.text, fontFamily: FONT.mono }}>{name}</div>
          <div style={{ fontSize: 10, fontFamily: FONT.mono, color: C.textMute, marginTop: 3 }}>
            {cand.asset_key.slice(0, 16)}…{owner ? ` · ${owner}` : ""}
          </div>
        </div>
        <RiskBadge level={cand.severity} />
        <StatusPill tone={C.textDim}>{ev.environment || "unknown"}</StatusPill>
        <StatusPill tone={C.textDim}>{ev.trigger_count || 0} finding{(ev.trigger_count || 0) !== 1 ? "s" : ""}</StatusPill>
        {hasHard && cand.status === "open" && <StatusPill tone={C.purple}>routing required</StatusPill>}
        <StatusPill tone={cand.status === "open" ? C.riskMedium : C.textMute}>
          {cand.status === "open" ? "recommended" : cand.status}
        </StatusPill>
        <span style={{ fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute, marginLeft: "auto" }}>{relTime(cand.last_seen)}</span>
        <span style={{ color: C.textMute, fontSize: 12 }}>{expanded ? "▾" : "▸"}</span>
      </div>

      {expanded && (
        <div style={{ borderTop: `1px solid ${C.border}`, padding: "16px 18px", background: C.surfaceRaised,
          display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 22 }}>
          <div>
            <div style={{ ...microLabel, marginBottom: 8 }}>Why this agent is here</div>
            <div style={{ fontSize: 12, color: C.textDim, lineHeight: 1.65, marginBottom: 12 }}>{trimReason(ev.reason || cand.summary)}</div>
            {(() => {
              const bySource = ev.trigger_findings_by_source;
              // Grouped view (new candidates). Preserve group order; append any
              // unrecognized source so nothing is silently dropped.
              if (bySource && Object.keys(bySource).length) {
                const known = TRIGGER_GROUPS.map((g) => g.key);
                const extra = Object.keys(bySource)
                  .filter((k) => !known.includes(k))
                  .map((k) => ({ key: k, label: "Asset Intelligence" }));
                return (
                  <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    {[...TRIGGER_GROUPS, ...extra].map((g) => {
                      const items = bySource[g.key] || [];
                      if (!items.length) return null;
                      return (
                        <div key={g.key}>
                          <div style={{ fontSize: 10, fontFamily: FONT.mono, letterSpacing: "0.08em", textTransform: "uppercase", color: C.textMute, marginBottom: 6 }}>
                            {g.label}
                          </div>
                          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                            {items.map((t) => <StatusPill key={t} tone={C.riskMedium}>{t}</StatusPill>)}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                );
              }
              // Fallback: flat list for candidates generated before the split.
              return (
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {(ev.trigger_finding_types || []).map((t) => <StatusPill key={t} tone={C.riskMedium}>{t}</StatusPill>)}
                </div>
              );
            })()}
          </div>
          <div>
            <div style={{ ...microLabel, marginBottom: 8 }}>Suggested controls</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
              {controls.length > 0 ? controls.map((c) => {
                const meta = KIND_META[c.kind] || KIND_META.hard;
                const tone = { purple: C.purple, violet: C.violet }[meta.tone] || C.violet;
                return (
                  <div key={c.control} style={{ display: "flex", alignItems: "center", gap: 9, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 12, color: C.text }}>{c.control}</span>
                    <StatusPill tone={tone}>{meta.label}</StatusPill>
                  </div>
                );
              }) : <span style={{ fontSize: 12, color: C.textMute }}>—</span>}
            </div>
            <div style={{ fontSize: 11, color: C.textMute, marginTop: 12, lineHeight: 1.55 }}>
              The goal: remote control of this agent through the Control Center, applied via the
              Gateway after explicit approval. This capability is in development — recommendations
              only, nothing is applied automatically.
            </div>
            {isAdmin && (
              <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
                {cand.status === "open"
                  ? <button onClick={(e) => { e.stopPropagation(); onAction("dismiss", cand.id); }}
                      style={{ background: "transparent", color: C.riskHigh, border: `1px solid ${C.riskHigh}44`, borderRadius: RADIUS.sm, padding: "5px 13px", fontSize: 11, fontFamily: FONT.mono, cursor: "pointer" }}>
                      Dismiss recommendation
                    </button>
                  : <button onClick={(e) => { e.stopPropagation(); onAction("reopen", cand.id); }}
                      style={{ background: "transparent", color: C.textDim, border: `1px solid ${C.border}`, borderRadius: RADIUS.sm, padding: "5px 13px", fontSize: 11, fontFamily: FONT.mono, cursor: "pointer" }}>
                      Reopen
                    </button>}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function GatewayControlCenterV2({ isAdmin = false, focusAssetKey = null, onClearFocus, onNavigate }) {
  const bp = useBreakpoint();
  const [candidates, setCandidates] = useState(null);
  const [assets, setAssets] = useState({});
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(null);

  const load = useCallback(async () => {
    try {
      const [cands, summary] = await Promise.all([getControlCandidates(), getAssetSummary()]);
      const byKey = {};
      for (const a of summary?.data.assets || []) byKey[a.asset_key] = a;
      setCandidates(cands);
      setAssets(byKey);
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { (async () => { await load(); })(); }, [load]);

  const act = useCallback(async (action, id) => {
    try {
      await (action === "dismiss" ? dismissFinding(id) : reopenFinding(id));
      await load();
    } catch (e) {
      setError(e.message);
    }
  }, [load]);

  const all = useMemo(() => candidates?.data || [], [candidates]);
  const focusHasCandidate = focusAssetKey && all.some((c) => c.asset_key === focusAssetKey);
  const visible = useMemo(
    () => (focusHasCandidate ? all.filter((c) => c.asset_key === focusAssetKey) : all),
    [all, focusHasCandidate, focusAssetKey]);

  const open = useMemo(() =>
    visible.filter((c) => c.status === "open")
      .sort((a, b) => (a.severity === b.severity ? 0 : a.severity === "high" ? -1 : 1)),
  [visible]);
  const closed = useMemo(() => visible.filter((c) => c.status !== "open"), [visible]);

  const triggersOf = (c) => c.evidence?.trigger_finding_types || [];
  const openAll = useMemo(() => all.filter((c) => c.status === "open"), [all]);
  const highCount = openAll.filter((c) => c.severity === "high").length;
  const humanReview = openAll.filter((c) => triggersOf(c).includes("human_review_recommended")).length;

  if (error) return <div style={{ color: C.riskHigh, fontFamily: FONT.mono, fontSize: 13, padding: 24 }}>{error}</div>;
  if (candidates === null) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 280, color: C.textMute, fontFamily: FONT.mono, fontSize: 13 }}>
      Loading control candidates…
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 26, fontFamily: FONT.ui, maxWidth: 1100 }}>

      <div className="oa-rise">
        <PageHeader
          eyebrow="Control · Review Queue"
          title="Gateway Control Center"
          purpose="Review AI agents recommended for Gateway control from runtime evidence, findings, and detection signals.">
          {candidates?.demo && <StatusPill tone={C.textMute}>sample data</StatusPill>}
          <StatusPill tone={C.accent}>observe-only</StatusPill>
        </PageHeader>
        <div style={{ fontSize: 11.5, fontFamily: FONT.mono, color: C.textDim, marginTop: 10 }}>
          Observe-only recommendations. Enforcement requires explicit Gateway configuration.
        </div>
        <div style={{ marginTop: 14 }}>
          <JourneyStrip />
        </div>
      </div>

      <div className="oa-rise oa-rise-1" style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <MetricCard label="Control candidates" value={openAll.length}
          sub="recommended for review" tone={openAll.length > 0 ? C.violet : C.ok} />
        <MetricCard label="High risk candidates" value={highCount}
          sub="high-severity evidence" tone={highCount > 0 ? C.riskHigh : C.ok} />
        <MetricCard label="Human review recommended" value={humanReview}
          sub="risk combination needs a person" tone={humanReview > 0 ? C.riskMedium : C.ok} />
      </div>

      {focusAssetKey && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          {focusHasCandidate
            ? <StatusPill tone={C.riskLow}>filtered to one agent</StatusPill>
            : <span style={{ fontSize: 11.5, color: C.textMute, fontFamily: FONT.mono }}>
                The selected agent has no control candidate — showing all candidates.
              </span>}
          <button onClick={onClearFocus}
            style={{ background: "transparent", border: "none", color: C.textDim, fontSize: 11, fontFamily: FONT.mono, cursor: "pointer", textDecoration: "underline" }}>
            show all candidates
          </button>
        </div>
      )}

      <Section label="Recommended for control"
        right={<span style={{ fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute }}>
          Observe can recommend. Gateway can enforce only when explicitly configured.
        </span>}>
        {open.length === 0 ? (
          <EmptyState icon="⊘"
            text={<span><strong style={{ color: C.text }}>No control candidates yet.</strong>{" "}
              When runtime findings or detection rules identify agents that may need Gateway-level control, they will appear here.</span>}
            actionLabel={surfaceAllowsPage("security_intel") ? "Open Security Intelligence" : undefined}
            onAction={() => onNavigate?.("security_intel")} />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {open.map((c) => (
              <CandidateCard key={c.id} cand={c} asset={assets[c.asset_key]} isAdmin={isAdmin}
                expanded={expanded === c.id} onToggle={() => setExpanded(expanded === c.id ? null : c.id)}
                onAction={act} />
            ))}
          </div>
        )}
      </Section>

      {closed.length > 0 && (
        <Section label="Dismissed / resolved">
          <div style={{ display: "flex", flexDirection: "column", gap: 10, opacity: 0.65 }}>
            {closed.map((c) => (
              <CandidateCard key={c.id} cand={c} asset={assets[c.asset_key]} isAdmin={isAdmin}
                expanded={expanded === c.id} onToggle={() => setExpanded(expanded === c.id ? null : c.id)}
                onAction={act} />
            ))}
          </div>
        </Section>
      )}

      {bp.isMobile && <div style={{ height: 8 }} />}
    </div>
  );
}
