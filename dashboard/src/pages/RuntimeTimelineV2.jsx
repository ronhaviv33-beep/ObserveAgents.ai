import { Fragment, useState, useEffect, useMemo, useCallback } from "react";
import { Bot, Sparkles, Wrench, Plug, Database, Circle } from "lucide-react";
import { C, FONT, RADIUS } from "../ui2/tokens.js";
import PageHeader from "../ui2/PageHeader.jsx";
import Section from "../ui2/Section.jsx";
import MetricCard from "../ui2/MetricCard.jsx";
import StatusPill from "../ui2/StatusPill.jsx";
import EmptyState from "../ui2/EmptyState.jsx";
import { surfaceAllowsPage } from "../productSurface.js";
import { fetchRuntimeTraces, fetchRuntimeTrace } from "../api.js";

/**
 * RuntimeTimelineV2 — redesign step 6 (docs/ui_redesign_plan.md).
 *
 * What actually executed: session-grouped trace list (one collapsed row per
 * agent session) and a per-trace execution waterfall. Behaviors are ported
 * 1:1 from the previous page — server-side agent refetch, accumulated agent
 * options, selection-scoped stats — restyled onto ui2. Structural metadata
 * only: prompts and responses are never stored.
 */

const STEP_META = {
  agent:        { color: C.accent,     label: "Agent",     icon: Bot },
  workflow:     { color: C.accent,     label: "Workflow",  icon: Bot },
  plan:         { color: C.purple,     label: "Plan",      icon: Sparkles },
  llm:          { color: C.purple,     label: "LLM",       icon: Sparkles },
  retrieval:    { color: C.teal,       label: "Retrieval", icon: Wrench },
  embedding:    { color: C.purple,     label: "Embedding", icon: Sparkles },
  tool:         { color: C.teal,       label: "Tool",      icon: Wrench },
  mcp_tool:     { color: C.riskMedium, label: "MCP Tool",  icon: Plug },
  memory:       { color: C.riskLow,    label: "Memory",    icon: Database },
  database:     { color: C.riskLow,    label: "Database",  icon: Database },
  external_api: { color: C.riskMedium, label: "API",       icon: Plug },
  step:         { color: C.textDim,    label: "Step",      icon: Circle },
};

const fmtMs = (ms) => {
  if (ms == null) return "—";
  if (ms >= 1000) return `${(ms / 1000).toFixed(ms >= 10000 ? 1 : 2)}s`;
  return `${ms}ms`;
};
const fmtWhen = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
};

/** Compact one-line GenAI summary for a span (metadata only, never content). */
const genAiLine = (g) => {
  if (!g) return null;
  const parts = [];
  if (g.provider) parts.push(g.provider);
  const model = g.response_model || g.request_model;
  if (model) parts.push(model);
  if (g.input_tokens != null || g.output_tokens != null) {
    parts.push(`${(g.input_tokens ?? 0).toLocaleString()}→${(g.output_tokens ?? 0).toLocaleString()} tok`);
  }
  if (g.time_to_first_chunk_ms != null) parts.push(`ttfc ${g.time_to_first_chunk_ms}ms`);
  if (g.streaming) parts.push("stream");
  return parts.length ? parts.join(" · ") : null;
};

/** Nesting depth per span from its parent chain (cycle-safe). */
function withDepth(spans) {
  const byId = Object.fromEntries(spans.map((s) => [s.span_id, s]));
  const depthOf = (s, seen = new Set()) => {
    let d = 0, cur = s;
    while (cur.parent_span_id && byId[cur.parent_span_id] && !seen.has(cur.parent_span_id)) {
      seen.add(cur.parent_span_id);
      cur = byId[cur.parent_span_id];
      d += 1;
      if (d > 32) break;
    }
    return d;
  };
  return spans.map((s) => ({ ...s, depth: depthOf(s) }));
}

// Activity-rail feed styles: metadata chip and rail status dots.
const chip = {
  fontSize: 10.5, fontFamily: FONT.mono, color: C.textDim, background: C.surfaceRaised,
  borderRadius: 999, padding: "3px 10px", whiteSpace: "nowrap", flexShrink: 0,
};

const SORT_KEYS = [
  ["start_time", "Started"], ["duration_ms", "Duration"], ["error_count", "Errors"],
  ["root_span_name", "Request"], ["service_name", "Agent"], ["span_count", "Steps"],
];

/** Status dot sitting on the vertical rail; hollow variant for child traces. */
function RailDot({ color, hollow }) {
  return (
    <span style={hollow
      ? { width: 8, height: 8, borderRadius: "50%", background: "#FFFFFF", border: `2px solid ${color}`, boxShadow: "0 0 0 2px #FFFFFF", zIndex: 1 }
      : { width: 10, height: 10, borderRadius: "50%", background: color, boxShadow: "0 0 0 2px #FFFFFF", zIndex: 1 }} />
  );
}

// ── Trace waterfall (detail view) ─────────────────────────────────────────────

function TraceWaterfall({ trace, onBack }) {
  const spans = useMemo(() => withDepth(trace.spans || []), [trace]);
  const total = Math.max(trace.duration_ms || 0, 1);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18, fontFamily: FONT.ui }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <button onClick={onBack}
          style={{ background: "transparent", color: C.textDim, border: `1px solid ${C.border}`,
            padding: "6px 14px", borderRadius: RADIUS.sm, fontSize: 12, fontFamily: FONT.mono, cursor: "pointer" }}>
          ← All traces
        </button>
        <span style={{ fontFamily: FONT.mono, fontSize: 12, color: C.textMute }}>
          trace <span style={{ color: C.text }}>{trace.trace_id.slice(0, 16)}…</span>
          {trace.session_id && <> · session <span style={{ color: C.text }}>{trace.session_id.slice(0, 8)}</span></>}
        </span>
      </div>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <MetricCard label="Request" value={trace.root_span_name || "—"} />
        <MetricCard label="Service" value={trace.service_name || "—"} />
        <MetricCard label="Total time" value={fmtMs(trace.duration_ms)} />
        <MetricCard label="Steps" value={trace.span_count} />
        <MetricCard label="Errors" value={trace.error_count} tone={trace.error_count > 0 ? C.riskHigh : C.text} />
        {trace.usage && (
          <MetricCard label="Tokens in / out"
            value={`${(trace.usage.input_tokens ?? 0).toLocaleString()} / ${(trace.usage.output_tokens ?? 0).toLocaleString()}`} />
        )}
      </div>

      <Section label="Execution timeline"
        right={<span style={{ fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute }}>
          each step positioned by start offset, sized by duration
        </span>}>
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: RADIUS.md, padding: "12px 14px" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {spans.map((s) => {
              const meta = STEP_META[s.step_type] || STEP_META.step;
              const StepIcon = meta.icon;
              const barColor = s.error ? C.riskHigh : meta.color;
              const left = Math.min(((s.offset_ms ?? 0) / total) * 100, 100);
              const width = Math.max(Math.min(((s.duration_ms ?? 0) / total) * 100, 100 - left), 0.5);
              const gLine = genAiLine(s.gen_ai);
              return (
                <div key={s.span_id}
                  style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 8px", borderRadius: RADIUS.sm, background: s.error ? `${C.riskHigh}0D` : "transparent" }}>
                  <div style={{ width: 280, minWidth: 180, display: "flex", alignItems: "center", gap: 8, paddingLeft: s.depth * 16, flexShrink: 0, overflow: "hidden" }}>
                    {s.depth > 0 && <span style={{ color: C.textMute, fontFamily: FONT.mono, fontSize: 10, flexShrink: 0 }}>└</span>}
                    <div style={{ minWidth: 0, display: "flex", flexDirection: "column" }}>
                      <span title={s.name} style={{ fontSize: 12, color: s.error ? C.riskHigh : C.text, fontFamily: FONT.mono, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.name}</span>
                      {gLine && (
                        <span title={gLine} style={{ fontSize: 10, color: C.textMute, fontFamily: FONT.mono, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{gLine}</span>
                      )}
                    </div>
                  </div>
                  <div style={{ width: 116, flexShrink: 0, display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ width: 22, height: 22, borderRadius: 8, background: `${meta.color}14`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                      <StepIcon size={12} color={meta.color} strokeWidth={2.2} />
                    </span>
                    <StatusPill tone={meta.color}>{meta.label}</StatusPill>
                  </div>
                  <div style={{ flex: 1, position: "relative", height: 20, background: C.surfaceRaised, borderRadius: 6, overflow: "hidden", minWidth: 120 }}>
                    <div title={`${s.name}: ${fmtMs(s.duration_ms)} @ +${fmtMs(s.offset_ms)}`}
                      style={{ position: "absolute", left: `${left}%`, width: `${width}%`, top: 3, bottom: 3, background: `linear-gradient(90deg, ${barColor}, ${barColor}CC)`, borderRadius: 4 }} />
                  </div>
                  <div style={{ width: 70, textAlign: "right", fontFamily: FONT.mono, fontSize: 11, color: s.error ? C.riskHigh : C.textDim, flexShrink: 0 }}>
                    {fmtMs(s.duration_ms)}
                  </div>
                </div>
              );
            })}
          </div>
          {spans.some((s) => s.error) && (
            <div style={{ marginTop: 14, padding: "10px 14px", background: `${C.riskHigh}0D`, border: `1px solid ${C.riskHigh}33`, borderRadius: RADIUS.sm, fontSize: 12, color: C.textDim }}>
              {spans.filter((s) => s.error).map((s) => (
                <div key={s.span_id} style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                  <span style={{ color: C.riskHigh, fontFamily: FONT.mono, flexShrink: 0 }}>✗ {s.name}</span>
                  <span>{s.status_message || "span reported error status"}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </Section>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function RuntimeTimelineV2({ onNavigate, focusService = null, onFocusConsumed }) {
  const [traces, setTraces] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  // A deep link (Overview agent row) can open this page pre-filtered.
  const [serviceFilter, setServiceFilter] = useState(focusService || "all");
  const [services, setServices] = useState(() => (focusService ? [focusService] : []));
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState("start_time");
  const [sortDir, setSortDir] = useState("desc");
  const [openSessions, setOpenSessions] = useState(() => new Set());
  // Agents are expanded by default — this set holds the ones the user collapsed.
  const [collapsedAgents, setCollapsedAgents] = useState(() => new Set());

  const toggleSession = (key) => setOpenSessions((prev) => {
    const next = new Set(prev);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });
  const toggleAgent = (key) => setCollapsedAgents((prev) => {
    const next = new Set(prev);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });
  const toggleSort = (k) => {
    if (sortKey === k) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setSortDir("desc"); }
  };

  // Choosing an agent refetches from the server (service_name param); the
  // agent dropdown accumulates options across fetches.
  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchRuntimeTraces({ limit: 100, service_name: serviceFilter === "all" ? undefined : serviceFilter })
      .then((rows) => {
        const list = rows || [];
        setTraces(list);
        setServices((prev) => [...new Set([...prev, ...list.map((t) => t.service_name).filter(Boolean)])].sort());
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [serviceFilter]);
  useEffect(() => { (async () => { await Promise.resolve(); load(); })(); }, [load]);
  useEffect(() => { (async () => { await Promise.resolve(); if (focusService) onFocusConsumed?.(); })(); }, [focusService, onFocusConsumed]);

  const openTrace = (traceId) => {
    setDetailLoading(true);
    fetchRuntimeTrace(traceId)
      .then(setSelected)
      .catch((e) => setError(e.message))
      .finally(() => setDetailLoading(false));
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return traces;
    return traces.filter((t) =>
      `${t.trace_id} ${t.root_span_name || ""} ${t.service_name || ""} ${t.session_id || ""}`.toLowerCase().includes(q));
  }, [traces, query]);

  const rows = useMemo(() => {
    const dir = sortDir === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      const x = a[sortKey], y = b[sortKey];
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return (x > y ? 1 : x < y ? -1 : 0) * dir;
    });
  }, [filtered, sortKey, sortDir]);

  // One group per session (within a set of traces); keeps first-trace order.
  const sessionGroupsOf = (traces) => {
    const out = [];
    const idx = new Map();
    traces.forEach((t) => {
      const key = t.session_id || `solo:${t.trace_id}`;
      if (!idx.has(key)) {
        const g = { key, session_id: t.session_id, traces: [] };
        idx.set(key, g);
        out.push(g);
      }
      idx.get(key).traces.push(t);
    });
    return out;
  };

  // Top tier: one group per agent (service.name), keeping first-trace order.
  const agentGroups = useMemo(() => {
    const out = [];
    const idx = new Map();
    rows.forEach((t) => {
      const key = t.service_name || "—";
      if (!idx.has(key)) {
        const g = { service: key, traces: [] };
        idx.set(key, g);
        out.push(g);
      }
      idx.get(key).traces.push(t);
    });
    return out;
  }, [rows]);

  // Stats follow the current selection (agent filter + search).
  const stats = useMemo(() => {
    const durations = filtered.map((t) => t.duration_ms).filter((d) => d != null);
    return {
      traces: filtered.length,
      agents: new Set(filtered.map((t) => t.service_name).filter(Boolean)).size,
      sessions: new Set(filtered.map((t) => t.session_id).filter(Boolean)).size,
      spans: filtered.reduce((s, t) => s + (t.span_count || 0), 0),
      avgMs: durations.length ? Math.round(durations.reduce((a, b) => a + b, 0) / durations.length) : null,
      errored: filtered.filter((t) => (t.error_count || 0) > 0).length,
    };
  }, [filtered]);

  if (selected) return <TraceWaterfall trace={selected} onBack={() => setSelected(null)} />;

  const inputStyle = {
    background: C.surfaceRaised, color: C.text, border: `1px solid ${C.border}`,
    padding: "7px 10px", borderRadius: RADIUS.sm, fontSize: 12, fontFamily: FONT.mono, outline: "none",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22, fontFamily: FONT.ui, maxWidth: 1160 }}>

      <div>
        <PageHeader
          title="Runtime"
          purpose="What your AI agents actually executed — grouped by agent, then session, each trace expandable into an execution waterfall.">
          <button onClick={load}
            style={{ background: "transparent", color: C.textDim, border: `1px solid ${C.border}`,
              padding: "6px 14px", borderRadius: RADIUS.sm, fontSize: 11, fontFamily: FONT.mono, cursor: "pointer" }}>
            ↻ Refresh
          </button>
        </PageHeader>
        <div style={{ fontSize: 11.5, fontFamily: FONT.mono, color: C.textDim, marginTop: 10 }}>
          Runtime evidence, structural metadata only — prompts and responses are never stored.
        </div>
      </div>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <MetricCard label="Traces" value={stats.traces} />
        <MetricCard label="Agents" value={stats.agents} />
        <MetricCard label="Sessions" value={stats.sessions} />
        <MetricCard label="Runtime steps" value={stats.spans} />
        <MetricCard label="Avg duration" value={fmtMs(stats.avgMs)} />
        <MetricCard label="With errors" value={stats.errored} tone={stats.errored > 0 ? C.riskHigh : C.accent} />
      </div>

      <Section label="Execution traces"
        right={<span style={{ fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute }}>click a trace to see where it spent time</span>}>
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: RADIUS.md, padding: "14px 16px" }}>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search traces…"
              style={{ ...inputStyle, minWidth: 200 }} />
            {services.length > 0 && (
              <select value={serviceFilter} onChange={(e) => setServiceFilter(e.target.value)} style={{ ...inputStyle, cursor: "pointer" }}>
                <option value="all">All agents</option>
                {services.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            )}
            <span style={{ fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute }}>{filtered.length} of {traces.length}</span>
          </div>

          {error && (
            <div style={{ padding: "12px 14px", background: `${C.riskHigh}0D`, border: `1px solid ${C.riskHigh}33`, borderRadius: RADIUS.sm, color: C.riskHigh, fontFamily: FONT.mono, fontSize: 12, marginBottom: 10 }}>
              {error}
            </div>
          )}

          {loading ? (
            <div style={{ padding: "40px 0", textAlign: "center", color: C.textMute, fontFamily: FONT.mono, fontSize: 13 }}>Loading traces…</div>
          ) : rows.length === 0 ? (
            <EmptyState icon="⟶"
              text={<span><strong style={{ color: C.text }}>No execution traces yet.</strong>{" "}
                Point an OpenTelemetry exporter at POST /otel/v1/traces and executions will appear here.</span>}
              actionLabel={surfaceAllowsPage("integrations") ? "Open Setup" : undefined}
              onAction={() => onNavigate?.("integrations")} />
          ) : (
            <>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
                <span style={{ fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute, marginRight: 2 }}>sort</span>
                {SORT_KEYS.map(([k, label]) => {
                  const active = sortKey === k;
                  return (
                    <button key={k} onClick={() => toggleSort(k)}
                      style={{
                        background: active ? C.accentSoft : "transparent",
                        color: active ? C.accentDark : C.textMute,
                        border: `1px solid ${active ? C.accentSoft : C.border}`,
                        borderRadius: 999, padding: "3px 10px", fontSize: 10.5, fontFamily: FONT.mono,
                        fontWeight: active ? 600 : 400, cursor: "pointer",
                      }}>
                      {label}{active ? (sortDir === "asc" ? " ↑" : " ↓") : ""}
                    </button>
                  );
                })}
              </div>
              <div style={{ position: "relative" }}>
                {/* the rail */}
                <div style={{ position: "absolute", left: 14, top: 12, bottom: 12, width: 2, background: C.border, borderRadius: 1 }} />
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {agentGroups.map((ag) => {
                    const agentOpen = !collapsedAgents.has(ag.service);
                    const sessGroups = sessionGroupsOf(ag.traces);
                    const agSteps = ag.traces.reduce((s, t) => s + (t.span_count || 0), 0);
                    const agErrors = ag.traces.reduce((s, t) => s + (t.error_count || 0), 0);
                    const agMs = ag.traces.reduce((s, t) => s + (t.duration_ms || 0), 0);
                    const agStarts = ag.traces.map((t) => t.start_time).filter(Boolean).sort();
                    const agSessions = new Set(ag.traces.map((t) => t.session_id).filter(Boolean)).size;
                    return (
                      <Fragment key={`agent:${ag.service}`}>
                        {/* Agent header — one row per agent (service.name) */}
                        <div style={{ display: "flex", alignItems: "flex-start" }}>
                          <div style={{ width: 30, flexShrink: 0, display: "flex", justifyContent: "center", paddingTop: 15 }}>
                            <RailDot color={agErrors > 0 ? C.riskHigh : C.accent} />
                          </div>
                          <div onClick={() => toggleAgent(ag.service)}
                            style={{ flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
                              padding: "9px 12px", borderRadius: RADIUS.md, cursor: "pointer",
                              background: agentOpen ? C.surfaceRaised : "transparent" }}
                            onMouseEnter={(e) => { e.currentTarget.style.background = C.surfaceHover; }}
                            onMouseLeave={(e) => { e.currentTarget.style.background = agentOpen ? C.surfaceRaised : "transparent"; }}>
                            <div style={{ flex: 1, minWidth: 160 }}>
                              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                                <span style={{ color: C.textMute, fontFamily: FONT.mono, fontSize: 10 }}>{agentOpen ? "▾" : "▸"}</span>
                                <span style={{ fontSize: 13.5, fontWeight: 700, color: C.text }}>{ag.service}</span>
                                <span style={{ fontFamily: FONT.mono, fontSize: 10, color: C.textDim, border: `1px solid ${C.border}`, borderRadius: 999, padding: "1px 7px", whiteSpace: "nowrap" }}>
                                  {ag.traces.length} trace{ag.traces.length > 1 ? "s" : ""}
                                </span>
                              </div>
                              <div style={{ fontFamily: FONT.mono, fontSize: 10, color: C.textMute, marginTop: 3, marginLeft: 18 }}>
                                {agSessions > 0 ? `${agSessions} session${agSessions > 1 ? "s" : ""} · ` : ""}{fmtWhen(agStarts[0])} → {fmtWhen(agStarts[agStarts.length - 1])}
                              </div>
                            </div>
                            <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
                              <span style={chip}>{agSteps} steps</span>
                              {agErrors > 0 && <StatusPill tone={C.riskHigh}>{agErrors} error{agErrors > 1 ? "s" : ""}</StatusPill>}
                              <span style={{ ...chip, fontSize: 11.5, color: C.text, fontWeight: 600 }}>{fmtMs(agMs)}</span>
                            </div>
                          </div>
                        </div>
                        {/* This agent's session groups + traces */}
                        {agentOpen && sessGroups.map((g) => {
                    const grouped = g.session_id && g.traces.length > 1;
                    const isOpen = grouped && openSessions.has(g.key);
                    const totalMs = g.traces.reduce((s, t) => s + (t.duration_ms || 0), 0);
                    const totalSteps = g.traces.reduce((s, t) => s + (t.span_count || 0), 0);
                    const totalErrors = g.traces.reduce((s, t) => s + (t.error_count || 0), 0);
                    const starts = g.traces.map((t) => t.start_time).filter(Boolean).sort();
                    const nameCounts = {};
                    g.traces.forEach((t) => { const n = t.root_span_name || "trace"; nameCounts[n] = (nameCounts[n] || 0) + 1; });
                    const topName = Object.entries(nameCounts).sort((a, b) => b[1] - a[1])[0]?.[0];
                    return (
                      <Fragment key={g.key}>
                        {grouped && (
                          <div style={{ display: "flex", alignItems: "flex-start" }}>
                            <div style={{ width: 30, flexShrink: 0, display: "flex", justifyContent: "center", paddingTop: 15 }}>
                              <RailDot color={totalErrors > 0 ? C.riskHigh : C.accent} />
                            </div>
                            <div onClick={() => toggleSession(g.key)}
                              style={{ flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
                                padding: "9px 12px", borderRadius: RADIUS.md, cursor: "pointer",
                                background: isOpen ? C.surfaceRaised : "transparent" }}
                              onMouseEnter={(e) => { e.currentTarget.style.background = C.surfaceHover; }}
                              onMouseLeave={(e) => { e.currentTarget.style.background = isOpen ? C.surfaceRaised : "transparent"; }}>
                              <div style={{ flex: 1, minWidth: 160 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                                  <span style={{ color: C.textMute, fontFamily: FONT.mono, fontSize: 10 }}>{isOpen ? "▾" : "▸"}</span>
                                  <span style={{ fontSize: 13, fontWeight: 600, color: C.text }}>{topName}</span>
                                  <span style={{ fontFamily: FONT.mono, fontSize: 10, color: C.textDim, border: `1px solid ${C.border}`, borderRadius: 999, padding: "1px 7px", whiteSpace: "nowrap" }}>
                                    ×{g.traces.length}
                                  </span>
                                </div>
                                <div style={{ fontFamily: FONT.mono, fontSize: 10, color: C.textMute, marginTop: 3, marginLeft: 18 }}>
                                  {g.traces[0].service_name || "—"} · ⛓ session {g.session_id.slice(0, 8)} · {fmtWhen(starts[0])} → {fmtWhen(starts[starts.length - 1])}
                                </div>
                              </div>
                              <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
                                <span style={chip}>{totalSteps} steps</span>
                                {totalErrors > 0 && <StatusPill tone={C.riskHigh}>{totalErrors} error{totalErrors > 1 ? "s" : ""}</StatusPill>}
                                <span style={{ ...chip, fontSize: 11.5, color: C.text, fontWeight: 600 }}>{fmtMs(totalMs)}</span>
                              </div>
                            </div>
                          </div>
                        )}
                        {(!grouped || isOpen) && g.traces.map((t) => (
                          <div key={t.trace_id} style={{ display: "flex", alignItems: "flex-start" }}>
                            <div style={{ width: 30, flexShrink: 0, display: "flex", justifyContent: "center", paddingTop: grouped ? 16 : 15 }}>
                              <RailDot color={t.error_count > 0 ? C.riskHigh : C.accent} hollow={grouped} />
                            </div>
                            <div onClick={() => openTrace(t.trace_id)}
                              style={{ flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
                                padding: "9px 12px", borderRadius: RADIUS.md, cursor: "pointer",
                                marginLeft: grouped ? 22 : 0, background: "transparent" }}
                              onMouseEnter={(e) => { e.currentTarget.style.background = C.surfaceHover; }}
                              onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}>
                              <div style={{ flex: 1, minWidth: 160 }}>
                                <div style={{ fontSize: 13, fontWeight: 600, color: C.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                  {t.root_span_name || <span style={{ color: C.textMute, fontFamily: FONT.mono, fontWeight: 400 }}>{t.trace_id.slice(0, 12)}…</span>}
                                </div>
                                <div style={{ fontFamily: FONT.mono, fontSize: 10, color: C.textMute, marginTop: 3 }}>
                                  {t.service_name || "—"} · {fmtWhen(t.start_time)}
                                  {!grouped && t.session_id && <> · ⛓ {t.session_id.slice(0, 8)}</>}
                                </div>
                              </div>
                              <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
                                <span style={chip}>{t.span_count} steps</span>
                                {t.error_count > 0 && <StatusPill tone={C.riskHigh}>{t.error_count} error{t.error_count > 1 ? "s" : ""}</StatusPill>}
                                <span style={{ ...chip, fontSize: 11.5, color: C.text, fontWeight: 600 }}>{fmtMs(t.duration_ms)}</span>
                              </div>
                            </div>
                          </div>
                        ))}
                      </Fragment>
                    );
                  })}
                      </Fragment>
                    );
                  })}
                </div>
              </div>
            </>
          )}
          {detailLoading && (
            <div style={{ padding: "10px 0", textAlign: "center", color: C.textMute, fontFamily: FONT.mono, fontSize: 12 }}>Loading trace…</div>
          )}
        </div>
      </Section>
    </div>
  );
}
