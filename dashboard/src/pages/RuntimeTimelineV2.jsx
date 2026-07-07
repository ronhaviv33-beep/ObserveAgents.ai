import { Fragment, useState, useEffect, useMemo, useCallback } from "react";
import { C, FONT, RADIUS, microLabel } from "../ui2/tokens.js";
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
  agent:        { color: C.accent,     label: "Agent" },
  workflow:     { color: C.accent,     label: "Workflow" },
  plan:         { color: C.purple,     label: "Plan" },
  llm:          { color: C.purple,     label: "LLM" },
  retrieval:    { color: C.teal,       label: "Retrieval" },
  embedding:    { color: C.purple,     label: "Embedding" },
  tool:         { color: C.teal,       label: "Tool" },
  mcp_tool:     { color: C.riskMedium, label: "MCP Tool" },
  memory:       { color: C.riskLow,    label: "Memory" },
  database:     { color: C.riskLow,    label: "Database" },
  external_api: { color: C.riskMedium, label: "API" },
  step:         { color: C.textDim,    label: "Step" },
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

const td = { padding: "10px 8px", fontSize: 12, color: C.textDim, fontFamily: FONT.mono };

function Th({ label, k, sortKey, sortDir, onToggle }) {
  const active = sortKey === k;
  return (
    <th onClick={() => onToggle(k)}
      style={{ ...microLabel, textAlign: "left", padding: "8px", cursor: "pointer",
        color: active ? C.text : C.textMute, userSelect: "none", whiteSpace: "nowrap" }}>
      {label}{active ? (sortDir === "asc" ? " ↑" : " ↓") : ""}
    </th>
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
      </div>

      <Section label="Execution timeline"
        right={<span style={{ fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute }}>
          each step positioned by start offset, sized by duration
        </span>}>
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: RADIUS.md, padding: "12px 14px" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {spans.map((s) => {
              const meta = STEP_META[s.step_type] || STEP_META.step;
              const barColor = s.error ? C.riskHigh : meta.color;
              const left = Math.min(((s.offset_ms ?? 0) / total) * 100, 100);
              const width = Math.max(Math.min(((s.duration_ms ?? 0) / total) * 100, 100 - left), 0.5);
              return (
                <div key={s.span_id}
                  style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 8px", borderRadius: RADIUS.sm, background: s.error ? `${C.riskHigh}0D` : "transparent" }}>
                  <div style={{ width: 280, minWidth: 180, display: "flex", alignItems: "center", gap: 8, paddingLeft: s.depth * 16, flexShrink: 0, overflow: "hidden" }}>
                    {s.depth > 0 && <span style={{ color: C.textMute, fontFamily: FONT.mono, fontSize: 10, flexShrink: 0 }}>└</span>}
                    <span title={s.name} style={{ fontSize: 12, color: s.error ? C.riskHigh : C.text, fontFamily: FONT.mono, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.name}</span>
                  </div>
                  <div style={{ width: 82, flexShrink: 0 }}><StatusPill tone={meta.color}>{meta.label}</StatusPill></div>
                  <div style={{ flex: 1, position: "relative", height: 18, background: C.surfaceRaised, borderRadius: 3, overflow: "hidden", minWidth: 120 }}>
                    <div title={`${s.name}: ${fmtMs(s.duration_ms)} @ +${fmtMs(s.offset_ms)}`}
                      style={{ position: "absolute", left: `${left}%`, width: `${width}%`, top: 3, bottom: 3, background: barColor, borderRadius: 2, opacity: 0.85 }} />
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

  const toggleSession = (key) => setOpenSessions((prev) => {
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

  // One group per session; groups keep the position of their first trace.
  const groups = useMemo(() => {
    const out = [];
    const idx = new Map();
    rows.forEach((t) => {
      const key = t.session_id || `solo:${t.trace_id}`;
      if (!idx.has(key)) {
        const g = { key, session_id: t.session_id, traces: [] };
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
          purpose="What your AI agents actually executed — traces grouped by session, each expandable into an execution waterfall.">
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
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: FONT.ui }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${C.border}` }}>
                    <Th label="Request" k="root_span_name" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} />
                    <Th label="Agent" k="service_name" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} />
                    <Th label="Started" k="start_time" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} />
                    <Th label="Duration" k="duration_ms" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} />
                    <Th label="Steps" k="span_count" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} />
                    <Th label="Errors" k="error_count" sortKey={sortKey} sortDir={sortDir} onToggle={toggleSort} />
                  </tr>
                </thead>
                <tbody>
                  {groups.map((g) => {
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
                          <tr onClick={() => toggleSession(g.key)}
                            style={{ borderBottom: `1px solid ${C.border}`, cursor: "pointer", background: isOpen ? C.surfaceRaised : "transparent" }}
                            onMouseEnter={(e) => { e.currentTarget.style.background = C.surfaceRaised; }}
                            onMouseLeave={(e) => { e.currentTarget.style.background = isOpen ? C.surfaceRaised : "transparent"; }}>
                            <td style={{ ...td, fontSize: 13, color: C.text }}>
                              <span style={{ color: C.textMute, fontFamily: FONT.mono, fontSize: 10, marginRight: 8 }}>{isOpen ? "▾" : "▸"}</span>
                              {topName}
                              <span style={{ marginLeft: 8, fontFamily: FONT.mono, fontSize: 10, color: C.textDim, border: `1px solid ${C.border}`, borderRadius: 10, padding: "1px 7px", whiteSpace: "nowrap" }}>
                                ×{g.traces.length}
                              </span>
                              <div style={{ fontFamily: FONT.mono, fontSize: 10, color: C.textMute, marginTop: 3, marginLeft: 18 }}>
                                ⛓ session {g.session_id.slice(0, 8)} · {fmtWhen(starts[0])} → {fmtWhen(starts[starts.length - 1])}
                              </div>
                            </td>
                            <td style={td}>{g.traces[0].service_name || "—"}</td>
                            <td style={{ ...td, whiteSpace: "nowrap" }}>{fmtWhen(starts[starts.length - 1])}</td>
                            <td style={{ ...td, color: C.text }}>{fmtMs(totalMs)}</td>
                            <td style={td}>{totalSteps}</td>
                            <td style={{ padding: "10px 8px" }}>
                              {totalErrors > 0
                                ? <StatusPill tone={C.riskHigh}>{totalErrors} error{totalErrors > 1 ? "s" : ""}</StatusPill>
                                : <span style={{ color: C.textMute, fontFamily: FONT.mono, fontSize: 11 }}>—</span>}
                            </td>
                          </tr>
                        )}
                        {(!grouped || isOpen) && g.traces.map((t) => (
                          <tr key={t.trace_id} onClick={() => openTrace(t.trace_id)}
                            style={{ borderBottom: `1px solid ${C.border}`, cursor: "pointer" }}
                            onMouseEnter={(e) => { e.currentTarget.style.background = C.surfaceRaised; }}
                            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}>
                            <td style={{ ...td, paddingLeft: grouped ? 34 : 8, fontSize: 13, color: C.text, fontFamily: FONT.ui }}>
                              {t.root_span_name || <span style={{ color: C.textMute, fontFamily: FONT.mono }}>{t.trace_id.slice(0, 12)}…</span>}
                            </td>
                            <td style={td}>{t.service_name || "—"}</td>
                            <td style={{ ...td, whiteSpace: "nowrap" }}>{fmtWhen(t.start_time)}</td>
                            <td style={{ ...td, color: C.text }}>{fmtMs(t.duration_ms)}</td>
                            <td style={td}>{t.span_count}</td>
                            <td style={{ padding: "10px 8px" }}>
                              {t.error_count > 0
                                ? <StatusPill tone={C.riskHigh}>{t.error_count} error{t.error_count > 1 ? "s" : ""}</StatusPill>
                                : <span style={{ color: C.textMute, fontFamily: FONT.mono, fontSize: 11 }}>—</span>}
                            </td>
                          </tr>
                        ))}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {detailLoading && (
            <div style={{ padding: "10px 0", textAlign: "center", color: C.textMute, fontFamily: FONT.mono, fontSize: 12 }}>Loading trace…</div>
          )}
        </div>
      </Section>
    </div>
  );
}
