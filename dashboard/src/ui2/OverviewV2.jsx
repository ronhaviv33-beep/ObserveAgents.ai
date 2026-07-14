import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import {
  ResponsiveContainer, AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, Tooltip, CartesianGrid, Cell,
} from "recharts";
import { C, FONT, RADIUS, CARD, TOOLTIP, TICK, microLabel, riskColor } from "./tokens.js";
import PageHeader from "./PageHeader.jsx";
import Section from "./Section.jsx";
import MetricCard from "./MetricCard.jsx";
import RiskBadge from "./RiskBadge.jsx";
import StatusPill from "./StatusPill.jsx";
import EmptyState from "./EmptyState.jsx";
import { FlowRibbon, Donut, BarRow, PulseDot, severitySegments } from "./viz.jsx";
import { surfaceAllowsPage } from "../productSurface.js";
import { useBreakpoint } from "../hooks/useBreakpoint.js";
import {
  getAssetSummary, getOpenFindings, getRecentTraces, getControlCandidates, getAttention,
} from "../overviewApi.js";

/**
 * OverviewV2 — the ui2 landing page (docs/ui_redesign_plan.md).
 *
 * Layout: hero line · evidence-flow ribbon (the signature element) · four
 * primary metrics with live sparklines · analytics column · Zone of Attention
 * (evidence-backed, conditional) · Gateway Control preview. Everything shown
 * traces back to runtime evidence; the page teaches the Observe-to-Control
 * product model in one glance.
 */

const FLOW = [
  { label: "OTel / OTLP",     page: "integrations" },
  { label: "Runtime",         page: "runtime" },
  { label: "Assets",          page: "intelligence" },
  { label: "Security",        page: "security_intel" },
  { label: "Rules",           page: "rules_alerts" },
  { label: "Gateway Control", page: "gateway_control_center", tone: "#B07BFF" },
];

const SLOW_MS = 5000;

const fmtMs = (ms) => {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
};

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
        getAttention(), getAssetSummary(), getOpenFindings(), getRecentTraces(100), getControlCandidates(),
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
  // One row per agent: all its recent events correlated into a single line,
  // not a feed of every individual trace.
  const agentActivity = useMemo(() => {
    const byAgent = new Map();
    traceRows.forEach((t) => {
      const key = t.service_name || "unknown";
      let a = byAgent.get(key);
      if (!a) { a = { agent: key, events: 0, errors: 0, slow: 0, totalMs: 0, withMs: 0, last: null }; byAgent.set(key, a); }
      a.events += 1;
      a.errors += t.error_count || 0;
      if ((t.duration_ms || 0) >= SLOW_MS) a.slow += 1;
      if (t.duration_ms != null) { a.totalMs += t.duration_ms; a.withMs += 1; }
      if (!a.last || (t.start_time || "") > a.last) a.last = t.start_time;
    });
    return [...byAgent.values()].sort((x, y) => (y.last || "").localeCompare(x.last || ""));
  }, [traceRows]);

  // ── Chart series (all derived from already-fetched evidence) ─────────────
  // Activity over time: recent traces bucketed into a fixed-width series.
  const activitySeries = useMemo(() => {
    const times = traceRows.map((t) => new Date(t.start_time || 0).getTime()).filter((n) => n > 0);
    if (!times.length) return [];
    const min = Math.min(...times), max = Math.max(...times);
    const N = 12, step = Math.max((max - min) / N, 1);
    const wide = (max - min) > 36 * 3600000;
    const buckets = Array.from({ length: N }, (_, i) => ({ t: min + i * step, events: 0, errors: 0 }));
    traceRows.forEach((t) => {
      const ts = new Date(t.start_time || 0).getTime();
      if (!ts) return;
      const i = Math.min(Math.floor((ts - min) / step), N - 1);
      buckets[i].events += 1;
      if ((t.error_count || 0) > 0) buckets[i].errors += 1;
    });
    return buckets.map((b) => ({
      ...b,
      label: new Date(b.t).toLocaleString("en-US", wide
        ? { month: "short", day: "numeric" }
        : { hour: "2-digit", minute: "2-digit" }),
    }));
  }, [traceRows]);

  const eventTrend = useMemo(() => activitySeries.map((b) => b.events), [activitySeries]);
  const errorTrend = useMemo(() => activitySeries.map((b) => b.errors), [activitySeries]);

  const sevCounts = useMemo(() => {
    const m = {};
    openFindings.forEach((f) => { m[f.severity] = (m[f.severity] || 0) + 1; });
    return m;
  }, [openFindings]);
  const sevSegments = useMemo(() => severitySegments(sevCounts), [sevCounts]);

  const latencyBuckets = useMemo(() => {
    const b = [
      { label: "<1s", n: 0, color: C.accent }, { label: "1–5s", n: 0, color: C.violet },
      { label: "5–15s", n: 0, color: C.riskMedium }, { label: "15s+", n: 0, color: C.riskHigh },
    ];
    traceRows.forEach((t) => {
      const d = t.duration_ms || 0;
      if (d < 1000) b[0].n += 1; else if (d < 5000) b[1].n += 1; else if (d < 15000) b[2].n += 1; else b[3].n += 1;
    });
    return b;
  }, [traceRows]);

  const att = attention || {};
  const nav = (page, opts) => { if (surfaceAllowsPage(page)) onNavigate?.(page, opts); };

  const chartCard = { ...CARD, padding: "16px 18px" };

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 280, color: C.textMute, fontFamily: FONT.mono, fontSize: 13 }}>
      Loading overview…
    </div>
  );

  const anySample = assets?.demo || findings?.demo || traces?.demo || att.demo;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 26, fontFamily: FONT.ui, maxWidth: 1160 }}>

      {/* ── Hero + evidence-flow ribbon ──────────────────────────────────── */}
      <div className="oa-rise">
        <PageHeader
          eyebrow="Mission Control"
          title="Overview"
          purpose={<span>Runtime evidence from your AI systems, turned into inventory, findings, and control recommendations. <span style={{ color: C.accentDark }}>Observe first. Control only what matters.</span></span>}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 7, fontSize: 10, fontFamily: FONT.mono, color: C.textMute }}>
            <PulseDot /> live · next refresh <span style={{ color: C.textDim, fontVariantNumeric: "tabular-nums", display: "inline-block", minWidth: 24 }}>{nextIn}s</span>
          </span>
          {anySample && <StatusPill tone={C.textMute}>sample data</StatusPill>}
        </PageHeader>
        <div style={{ ...CARD, marginTop: 18, padding: "18px 22px 10px", borderRadius: RADIUS.lg, position: "relative", overflow: "hidden" }}>
          <div aria-hidden="true" style={{ position: "absolute", inset: 0, pointerEvents: "none", background: "radial-gradient(600px 120px at 50% 0%, rgba(123,140,255,0.07), transparent 70%)" }} />
          <div style={{ ...microLabel, fontSize: 9, marginBottom: 14 }}>The evidence chain — telemetry in, control out</div>
          <FlowRibbon steps={FLOW} onNavigate={(p) => nav(p)} allows={surfaceAllowsPage} />
        </div>
      </div>

      {/* ── Primary metrics ──────────────────────────────────────────────── */}
      <div className="oa-rise oa-rise-1" style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <MetricCard label="AI assets discovered" value={assetList.length}
          sub={`${att.systemsManaged ?? 0} managed`} tone={C.text}
          trend={eventTrend} trendColor={C.accent}
          onClick={surfaceAllowsPage("intelligence") ? () => nav("intelligence") : undefined} />
        <MetricCard label="Open findings" value={openFindings.length}
          sub={`across ${agentsWithFindings} agent${agentsWithFindings !== 1 ? "s" : ""}`}
          tone={openFindings.length > 0 ? C.riskMedium : C.ok}
          onClick={surfaceAllowsPage("security_intel") ? () => nav("security_intel") : undefined} />
        <MetricCard label="Error traces" value={errorTraces}
          sub={`${slowTraces} slow trace${slowTraces !== 1 ? "s" : ""}`}
          tone={errorTraces > 0 ? C.riskHigh : C.ok}
          trend={errorTrend.some((n) => n > 0) ? errorTrend : undefined} trendColor={C.riskHigh}
          onClick={surfaceAllowsPage("runtime") ? () => nav("runtime") : undefined} />
        <MetricCard label="Gateway control candidates" value={openCandidates.length}
          sub="recommended for review — nothing applied automatically"
          tone={openCandidates.length > 0 ? C.violet : C.ok}
          onClick={surfaceAllowsPage("gateway_control_center") ? () => nav("gateway_control_center") : undefined} />
      </div>

      {/* ── Charts + attention sidebar ───────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: bp.isMobile ? "1fr" : "2fr 1fr", gap: 16, alignItems: "start" }}>

        {/* Left: analytics */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16, minWidth: 0 }}>

          <div className="oa-rise oa-rise-2" style={chartCard}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12 }}>
              <span style={microLabel}>Runtime activity</span>
              <span style={{ fontSize: 10, fontFamily: FONT.mono, color: C.textMute }}>
                <span style={{ color: errorTraces > 0 ? C.riskHigh : C.textMute }}>{errorTraces} error</span> · {slowTraces} slow
              </span>
            </div>
            {activitySeries.length > 0 ? (
              <ResponsiveContainer width="100%" height={170}>
                <AreaChart data={activitySeries} margin={{ top: 4, right: 4, left: -22, bottom: 0 }}>
                  <defs>
                    <linearGradient id="ovAct" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={C.accent} stopOpacity={0.32} />
                      <stop offset="100%" stopColor={C.accent} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke={C.border} strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="label" tick={TICK} axisLine={{ stroke: C.border }} tickLine={false} />
                  <YAxis tick={TICK} axisLine={false} tickLine={false} allowDecimals={false} />
                  <Tooltip contentStyle={TOOLTIP} labelStyle={{ color: C.textDim }} />
                  <Area type="monotone" dataKey="events" stroke={C.accent} strokeWidth={2} fill="url(#ovAct)" name="events" />
                  <Area type="monotone" dataKey="errors" stroke={C.riskHigh} strokeWidth={1.5} fill={`${C.riskHigh}22`} name="error traces" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState icon="⟶" text="No runtime traces yet. Point an OTLP exporter at ObserveAgents and executions appear here."
                actionLabel={surfaceAllowsPage("integrations") ? "Open Setup" : undefined}
                onAction={() => nav("integrations")} />
            )}
          </div>

          <div className="oa-rise oa-rise-3" style={{ display: "grid", gridTemplateColumns: bp.isMobile ? "1fr" : "1fr 1fr", gap: 16 }}>
            <div style={chartCard}>
              <div style={{ ...microLabel, marginBottom: 12 }}>Findings by severity</div>
              {sevSegments.length > 0 ? (
                <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                  <Donut segments={sevSegments} size={124} thickness={12}
                    centerValue={openFindings.length} centerLabel="open" />
                  <div style={{ fontFamily: FONT.mono, fontSize: 10.5, lineHeight: 2.1, minWidth: 0 }}>
                    {sevSegments.map((d) => (
                      <div key={d.label} style={{ color: C.textDim }}>
                        <span style={{ color: d.color }}>●</span> {d.value} {d.label}
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div style={{ fontSize: 11.5, fontFamily: FONT.mono, color: C.textMute, padding: "24px 0" }}>No open findings.</div>
              )}
            </div>

            <div style={chartCard}>
              <div style={{ ...microLabel, marginBottom: 12 }}>Latency distribution</div>
              {traceRows.length > 0 ? (
                <ResponsiveContainer width="100%" height={130}>
                  <BarChart data={latencyBuckets} margin={{ top: 4, right: 4, left: -26, bottom: 0 }}>
                    <XAxis dataKey="label" tick={TICK} axisLine={{ stroke: C.border }} tickLine={false} />
                    <YAxis tick={TICK} axisLine={false} tickLine={false} allowDecimals={false} />
                    <Tooltip contentStyle={TOOLTIP} labelStyle={{ color: C.textDim }} formatter={(v) => [v, "traces"]} cursor={{ fill: `${C.accent}0D` }} />
                    <Bar dataKey="n" radius={[5, 5, 0, 0]}>
                      {latencyBuckets.map((b) => <Cell key={b.label} fill={b.color} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ fontSize: 11.5, fontFamily: FONT.mono, color: C.textMute, padding: "24px 0" }}>No traces yet.</div>
              )}
            </div>
          </div>

          <div className="oa-rise oa-rise-4" style={chartCard}>
            <div style={{ ...microLabel, marginBottom: 14 }}>Events per agent</div>
            {agentActivity.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {agentActivity.slice(0, 8).map((a) => {
                  const maxEv = Math.max(...agentActivity.map((x) => x.events), 1);
                  return (
                    <BarRow key={a.agent} label={a.agent} title={a.agent}
                      value={a.events} max={maxEv} errorValue={Math.min(a.errors, a.events)}
                      right={<>{a.events} ev{a.errors > 0 && <> · <span style={{ color: C.riskHigh }}>{a.errors} err</span></>} · {fmtMs(a.withMs ? Math.round(a.totalMs / a.withMs) : null)}</>}
                      onClick={surfaceAllowsPage("runtime") ? () => onNavigate?.("runtime", { runtimeAgent: a.agent }) : undefined} />
                  );
                })}
              </div>
            ) : (
              <div style={{ fontSize: 11.5, fontFamily: FONT.mono, color: C.textMute }}>No agent activity yet.</div>
            )}
          </div>
        </div>

        {/* Right: attention + gateway preview */}
        <div className="oa-rise oa-rise-3" style={{ display: "flex", flexDirection: "column", gap: 16, minWidth: 0 }}>

          <Section label="Attention · worst first">
            {(() => {
              const rows = [];
              if (att.worstOffender) rows.push({
                key: "worst", color: riskColor("critical"), title: att.worstOffender.asset_name,
                sub: `${att.worstOffender.highFindings} high finding${att.worstOffender.highFindings !== 1 ? "s" : ""} · ${att.worstOffender.errorTraces} error trace${att.worstOffender.errorTraces !== 1 ? "s" : ""}`,
                page: "intelligence",
              });
              if (mcpProd.length > 0) rows.push({
                key: "mcp", color: riskColor("high"), title: "MCP tools in production",
                sub: `${mcpProd.reduce((n, f) => n + (f.occurrence_count || 1), 0)} occurrences · ${distinctAssets(mcpProd)} agent${distinctAssets(mcpProd) !== 1 ? "s" : ""}`,
                page: "security_intel",
              });
              if (unknownProvider.length > 0) rows.push({
                key: "provider", color: riskColor("high"), title: "Unknown provider in production",
                sub: `${distinctAssets(unknownProvider)} agent${distinctAssets(unknownProvider) !== 1 ? "s" : ""} outside the catalog`,
                page: "security_intel",
              });
              if (humanReview.length > 0) rows.push({
                key: "review", color: riskColor("medium"), title: "Human review recommended",
                sub: `${distinctAssets(humanReview)} agent${distinctAssets(humanReview) !== 1 ? "s" : ""} with a high-risk combination`,
                page: "security_intel",
              });
              return rows.length > 0 ? (
                <div style={{ ...CARD, overflow: "hidden" }}>
                  {rows.map((r, i) => (
                    <div key={r.key} onClick={() => nav(r.page)}
                      style={{ display: "flex", alignItems: "center", gap: 10, padding: "12px 16px",
                        borderBottom: i < rows.length - 1 ? `1px solid ${C.border}` : "none",
                        cursor: surfaceAllowsPage(r.page) ? "pointer" : "default" }}
                      onMouseEnter={(e) => { e.currentTarget.style.background = C.surfaceHover; }}
                      onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}>
                      <span style={{ width: 8, height: 8, borderRadius: "50%", background: r.color, boxShadow: `0 0 8px ${r.color}66`, flexShrink: 0 }} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 12.5, fontWeight: 600, color: C.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.title}</div>
                        <div style={{ fontSize: 10, fontFamily: FONT.mono, color: C.textMute, marginTop: 2 }}>{r.sub}</div>
                      </div>
                      <span style={{ fontSize: 11, fontFamily: FONT.mono, color: C.accentDark, flexShrink: 0 }}>→</span>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState icon="✓" text="Nothing needs attention right now. New signals appear here as runtime evidence arrives." />
              );
            })()}
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
                  <div key={cand.id} style={{ ...CARD, padding: "14px 16px" }}>
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
                        style={{ background: `${C.violet}14`, color: C.violet, border: `1px solid ${C.violet}44`,
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
    </div>
  );
}
