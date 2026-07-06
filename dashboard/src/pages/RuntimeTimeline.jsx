import React, { useState, useEffect, useMemo, useCallback } from "react";
import { fetchRuntimeTraces, fetchRuntimeTrace } from "../api.js";
import { T, FONT_UI, FONT_MONO } from "../theme.js";
import { Card, Stat, Pill, SortableTh, SearchBox, useSortable, useSearch } from "../components/ui.jsx";

// Runtime Step type → color + label for the trace waterfall
const STEP_META = {
  agent:        { color: T.accent, label: "Agent" },
  workflow:     { color: T.accent, label: "Workflow" },
  plan:         { color: T.purple, label: "Plan" },
  llm:          { color: T.purple, label: "LLM" },
  retrieval:    { color: T.teal,   label: "Retrieval" },
  embedding:    { color: T.purple, label: "Embedding" },
  tool:         { color: T.teal,   label: "Tool" },
  mcp_tool:     { color: T.warn,   label: "MCP Tool" },
  memory:       { color: T.info,   label: "Memory" },
  database:     { color: T.info,   label: "Database" },
  external_api: { color: T.warn,   label: "API" },
  step:         { color: T.textDim, label: "Step" },
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

// Compute nesting depth for each span from its parent chain.
function withDepth(spans) {
  const byId = Object.fromEntries(spans.map((s) => [s.span_id, s]));
  const depthOf = (s, seen = new Set()) => {
    let d = 0, cur = s;
    while (cur.parent_span_id && byId[cur.parent_span_id] && !seen.has(cur.parent_span_id)) {
      seen.add(cur.parent_span_id);
      cur = byId[cur.parent_span_id];
      d += 1;
      if (d > 32) break; // defensive: malformed cycles
    }
    return d;
  };
  return spans.map((s) => ({ ...s, depth: depthOf(s) }));
}

function StepPill({ type }) {
  const meta = STEP_META[type] || STEP_META.step;
  return <Pill color={meta.color}>{meta.label}</Pill>;
}

// ── Trace waterfall (detail view) ─────────────────────────────────────────────

function TraceWaterfall({ trace, onBack }) {
  const spans = useMemo(() => withDepth(trace.spans || []), [trace]);
  const total = Math.max(trace.duration_ms || 0, 1);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14, flexWrap: "wrap" }}>
        <button onClick={onBack}
          style={{ background: "transparent", color: T.textDim, border: `1px solid ${T.border}`, padding: "6px 14px", borderRadius: 4, fontSize: 12, fontFamily: FONT_MONO, cursor: "pointer" }}>
          ← All traces
        </button>
        <div style={{ fontFamily: FONT_MONO, fontSize: 12, color: T.textMute }}>
          trace <span style={{ color: T.text }}>{trace.trace_id.slice(0, 16)}…</span>
          {trace.session_id && <> · session <span style={{ color: T.text }}>{trace.session_id.slice(0, 8)}</span></>}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 14, marginBottom: 14 }}>
        <Stat label="Request"     value={trace.root_span_name || "—"} />
        <Stat label="Service"     value={trace.service_name || "—"} />
        <Stat label="Total time"  value={fmtMs(trace.duration_ms)} />
        <Stat label="Steps"       value={trace.span_count} />
        <Stat label="Errors"      value={trace.error_count} accent={trace.error_count > 0 ? T.crit : T.text} />
      </div>

      <Card title="Execution Timeline" subtitle="Each Runtime Step positioned by start offset and sized by duration — where this request spent its time">
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {spans.map((s) => {
            const meta = STEP_META[s.step_type] || STEP_META.step;
            const barColor = s.error ? T.crit : meta.color;
            const left = Math.min(((s.offset_ms ?? 0) / total) * 100, 100);
            const width = Math.max(Math.min(((s.duration_ms ?? 0) / total) * 100, 100 - left), 0.5);
            return (
              <div key={s.span_id}
                style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 8px", borderRadius: 4, background: s.error ? `${T.crit}0D` : "transparent" }}>
                <div style={{ width: 280, minWidth: 180, display: "flex", alignItems: "center", gap: 8, paddingLeft: s.depth * 16, flexShrink: 0, overflow: "hidden" }}>
                  {s.depth > 0 && <span style={{ color: T.textMute, fontFamily: FONT_MONO, fontSize: 10, flexShrink: 0 }}>└</span>}
                  <span title={s.name} style={{ fontSize: 12, color: s.error ? T.crit : T.text, fontFamily: FONT_MONO, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.name}</span>
                </div>
                <div style={{ width: 76, flexShrink: 0 }}><StepPill type={s.step_type} /></div>
                <div style={{ flex: 1, position: "relative", height: 18, background: T.panelHi, borderRadius: 3, overflow: "hidden", minWidth: 120 }}>
                  <div title={`${s.name}: ${fmtMs(s.duration_ms)} @ +${fmtMs(s.offset_ms)}`}
                    style={{ position: "absolute", left: `${left}%`, width: `${width}%`, top: 3, bottom: 3, background: barColor, borderRadius: 2, opacity: 0.85 }} />
                </div>
                <div style={{ width: 70, textAlign: "right", fontFamily: FONT_MONO, fontSize: 11, color: s.error ? T.crit : T.textDim, flexShrink: 0 }}>
                  {fmtMs(s.duration_ms)}
                </div>
              </div>
            );
          })}
        </div>
        {spans.some((s) => s.error) && (
          <div style={{ marginTop: 14, padding: "10px 14px", background: `${T.crit}0D`, border: `1px solid ${T.crit}33`, borderRadius: 4, fontSize: 12, color: T.textDim }}>
            {spans.filter((s) => s.error).map((s) => (
              <div key={s.span_id} style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                <span style={{ color: T.crit, fontFamily: FONT_MONO, flexShrink: 0 }}>✗ {s.name}</span>
                <span>{s.status_message || "span reported error status"}</span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function RuntimeTimeline() {
  const [traces, setTraces]     = useState([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);
  const [selected, setSelected] = useState(null);     // trace detail object
  const [detailLoading, setDetailLoading] = useState(false);
  const [serviceFilter, setServiceFilter] = useState("all");
  // Sessions collapsed by default — one aggregate row each; click to expand.
  const [openSessions, setOpenSessions] = useState(() => new Set());
  const toggleSession = (key) => setOpenSessions((prev) => {
    const next = new Set(prev);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchRuntimeTraces({ limit: 100 })
      .then((rows) => setTraces(rows || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const openTrace = (traceId) => {
    setDetailLoading(true);
    fetchRuntimeTrace(traceId)
      .then(setSelected)
      .catch((e) => setError(e.message))
      .finally(() => setDetailLoading(false));
  };

  const services = useMemo(
    () => [...new Set(traces.map((t) => t.service_name).filter(Boolean))].sort(),
    [traces]
  );
  const byService = serviceFilter === "all" ? traces : traces.filter((t) => t.service_name === serviceFilter);

  const { query, setQuery, filtered } = useSearch(byService, (t) =>
    `${t.trace_id} ${t.root_span_name || ""} ${t.service_name || ""} ${t.session_id || ""}`);
  const { sortKey, sortDir, toggle, sort } = useSortable("start_time");
  const rows = sort(filtered, (t, key) => t[key]);

  // Arrange traces by session: consecutive interactions from the same agent
  // session (session.id / gen_ai.conversation.id) render under one header.
  // Groups keep the position of their first trace in the current sort order.
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

  // Stat tiles follow the current selection (service filter + search), not
  // the whole database — pick an agent and the numbers are that agent's.
  const stats = useMemo(() => {
    const durations = filtered.map((t) => t.duration_ms).filter((d) => d != null);
    return {
      traces: filtered.length,
      spans: filtered.reduce((s, t) => s + (t.span_count || 0), 0),
      avgMs: durations.length ? Math.round(durations.reduce((a, b) => a + b, 0) / durations.length) : null,
      errored: filtered.filter((t) => (t.error_count || 0) > 0).length,
    };
  }, [filtered]);

  if (selected) {
    return <TraceWaterfall trace={selected} onBack={() => setSelected(null)} />;
  }

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 14, marginBottom: 14 }}>
        <Stat label="Traces"        value={stats.traces} />
        <Stat label="Runtime steps" value={stats.spans} />
        <Stat label="Avg duration"  value={fmtMs(stats.avgMs)} />
        <Stat label="With errors"   value={stats.errored} accent={stats.errored > 0 ? T.crit : T.text} />
      </div>

      <Card
        title="Execution Traces"
        subtitle="Recent AI system executions observed via OpenTelemetry — click a trace to see where it spent time"
        right={
          <button onClick={load}
            style={{ background: "transparent", color: T.textDim, border: `1px solid ${T.border}`, padding: "5px 12px", borderRadius: 3, fontSize: 10, fontFamily: FONT_MONO, cursor: "pointer", letterSpacing: "0.08em", textTransform: "uppercase" }}>
            ↻ Refresh
          </button>
        }>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <SearchBox query={query} onChange={setQuery} placeholder="Search traces…" count={filtered.length} total={byService.length} />
          {services.length > 0 && (
            <select value={serviceFilter} onChange={(e) => setServiceFilter(e.target.value)}
              style={{ background: T.panelHi, color: T.text, border: `1px solid ${T.border}`, padding: "6px 8px", borderRadius: 4, fontSize: 12, fontFamily: FONT_MONO, cursor: "pointer", marginBottom: 10 }}>
              <option value="all">All services</option>
              {services.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          )}
        </div>

        {error && (
          <div style={{ padding: "12px 14px", background: `${T.crit}0D`, border: `1px solid ${T.crit}33`, borderRadius: 4, color: T.crit, fontFamily: FONT_MONO, fontSize: 12, marginBottom: 10 }}>
            {error}
          </div>
        )}

        {loading ? (
          <div style={{ padding: "40px 0", textAlign: "center", color: T.textMute, fontFamily: FONT_MONO, fontSize: 13 }}>Loading traces…</div>
        ) : rows.length === 0 ? (
          <div style={{ padding: "40px 20px", textAlign: "center" }}>
            <div style={{ color: T.textDim, fontSize: 14, marginBottom: 6 }}>No execution traces yet</div>
            <div style={{ color: T.textMute, fontSize: 12, fontFamily: FONT_MONO }}>
              Point an OpenTelemetry exporter at POST /otel/v1/traces and executions will appear here.
            </div>
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: FONT_UI }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                  <SortableTh label="Request"  sortKey="root_span_name" active={sortKey === "root_span_name"} dir={sortDir} onToggle={toggle} />
                  <SortableTh label="Service"  sortKey="service_name"   active={sortKey === "service_name"}   dir={sortDir} onToggle={toggle} />
                  <SortableTh label="Started"  sortKey="start_time"     active={sortKey === "start_time"}     dir={sortDir} onToggle={toggle} />
                  <SortableTh label="Duration" sortKey="duration_ms"    active={sortKey === "duration_ms"}    dir={sortDir} onToggle={toggle} />
                  <SortableTh label="Steps"    sortKey="span_count"     active={sortKey === "span_count"}     dir={sortDir} onToggle={toggle} />
                  <SortableTh label="Errors"   sortKey="error_count"    active={sortKey === "error_count"}    dir={sortDir} onToggle={toggle} />
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
                  // Most common root span name represents the session in one row.
                  const nameCounts = {};
                  g.traces.forEach((t) => { const n = t.root_span_name || "trace"; nameCounts[n] = (nameCounts[n] || 0) + 1; });
                  const topName = Object.entries(nameCounts).sort((a, b) => b[1] - a[1])[0]?.[0];
                  return (
                    <React.Fragment key={g.key}>
                      {grouped && (
                        // One row per session: aggregate of all its interactions.
                        <tr onClick={() => toggleSession(g.key)}
                          style={{ borderBottom: `1px solid ${T.border}`, cursor: "pointer", background: isOpen ? T.panelHi : "transparent" }}
                          onMouseEnter={(e) => { e.currentTarget.style.background = T.panelHi; }}
                          onMouseLeave={(e) => { e.currentTarget.style.background = isOpen ? T.panelHi : "transparent"; }}>
                          <td style={{ padding: "10px 8px", fontSize: 13, color: T.text }}>
                            <span style={{ color: T.textMute, fontFamily: FONT_MONO, fontSize: 10, marginRight: 8 }}>{isOpen ? "▾" : "▸"}</span>
                            {topName}
                            <span style={{ marginLeft: 8, fontFamily: FONT_MONO, fontSize: 10, color: T.textDim, border: `1px solid ${T.border}`, borderRadius: 10, padding: "1px 7px", whiteSpace: "nowrap" }}>
                              ×{g.traces.length}
                            </span>
                            <div style={{ fontFamily: FONT_MONO, fontSize: 10, color: T.textMute, marginTop: 3, marginLeft: 18 }}>
                              ⛓ session {g.session_id.slice(0, 8)} · {fmtWhen(starts[0])} → {fmtWhen(starts[starts.length - 1])}
                            </div>
                          </td>
                          <td style={{ padding: "10px 8px", fontSize: 12, color: T.textDim, fontFamily: FONT_MONO }}>{g.traces[0].service_name || "—"}</td>
                          <td style={{ padding: "10px 8px", fontSize: 12, color: T.textDim, fontFamily: FONT_MONO, whiteSpace: "nowrap" }}>{fmtWhen(starts[starts.length - 1])}</td>
                          <td style={{ padding: "10px 8px", fontSize: 12, color: T.text, fontFamily: FONT_MONO }}>{fmtMs(totalMs)}</td>
                          <td style={{ padding: "10px 8px", fontSize: 12, color: T.textDim, fontFamily: FONT_MONO }}>{totalSteps}</td>
                          <td style={{ padding: "10px 8px" }}>
                            {totalErrors > 0
                              ? <Pill color={T.crit}>{totalErrors} error{totalErrors > 1 ? "s" : ""}</Pill>
                              : <span style={{ color: T.textMute, fontFamily: FONT_MONO, fontSize: 11 }}>—</span>}
                          </td>
                        </tr>
                      )}
                      {(!grouped || isOpen) && g.traces.map((t) => (
                        <tr key={t.trace_id} onClick={() => openTrace(t.trace_id)}
                          style={{ borderBottom: `1px solid ${T.border}`, cursor: "pointer" }}
                          onMouseEnter={(e) => { e.currentTarget.style.background = T.panelHi; }}
                          onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}>
                          <td style={{ padding: "10px 8px", paddingLeft: grouped ? 34 : 8, fontSize: 13, color: T.text }}>
                            {t.root_span_name || <span style={{ color: T.textMute, fontFamily: FONT_MONO }}>{t.trace_id.slice(0, 12)}…</span>}
                          </td>
                          <td style={{ padding: "10px 8px", fontSize: 12, color: T.textDim, fontFamily: FONT_MONO }}>{t.service_name || "—"}</td>
                          <td style={{ padding: "10px 8px", fontSize: 12, color: T.textDim, fontFamily: FONT_MONO, whiteSpace: "nowrap" }}>{fmtWhen(t.start_time)}</td>
                          <td style={{ padding: "10px 8px", fontSize: 12, color: T.text, fontFamily: FONT_MONO }}>{fmtMs(t.duration_ms)}</td>
                          <td style={{ padding: "10px 8px", fontSize: 12, color: T.textDim, fontFamily: FONT_MONO }}>{t.span_count}</td>
                          <td style={{ padding: "10px 8px" }}>
                            {t.error_count > 0
                              ? <Pill color={T.crit}>{t.error_count} error{t.error_count > 1 ? "s" : ""}</Pill>
                              : <span style={{ color: T.textMute, fontFamily: FONT_MONO, fontSize: 11 }}>—</span>}
                          </td>
                        </tr>
                      ))}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {detailLoading && (
          <div style={{ padding: "10px 0", textAlign: "center", color: T.textMute, fontFamily: FONT_MONO, fontSize: 12 }}>Loading trace…</div>
        )}
      </Card>
    </div>
  );
}
