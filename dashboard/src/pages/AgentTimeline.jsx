import { Fragment, useState, useEffect, useMemo, useCallback } from "react";
import { Bot, Sparkles, Wrench, Plug, Database, Circle, AlertTriangle } from "lucide-react";
import { C, FONT, RADIUS, microLabel } from "../ui2/tokens.js";
import PageHeader from "../ui2/PageHeader.jsx";
import Section from "../ui2/Section.jsx";
import MetricCard from "../ui2/MetricCard.jsx";
import StatusPill from "../ui2/StatusPill.jsx";
import RiskBadge from "../ui2/RiskBadge.jsx";
import EmptyState from "../ui2/EmptyState.jsx";
import { fetchAgents, fetchAgentTimeline } from "../api.js";

/**
 * AgentTimeline — per-agent operational evidence feed (telemetry ingestion MVP).
 *
 * Answers: what did this agent do, when, with which model/tool, at what cost
 * and latency, and was any of it risky or against policy. Reads normalized
 * telemetry_events via GET /agents/{id}/timeline; the summary row comes from
 * the precomputed agent_metrics_daily rollup, not raw scans.
 */

const EVENT_META = {
  llm_call:   { color: C.purple,     label: "LLM",       icon: Sparkles },
  tool_call:  { color: C.teal,       label: "Tool",      icon: Wrench },
  agent_step: { color: C.accent,     label: "Agent",     icon: Bot },
  retrieval:  { color: C.teal,       label: "Retrieval", icon: Database },
  external_api: { color: C.riskMedium, label: "API",     icon: Plug },
  error:      { color: C.riskHigh,   label: "Error",     icon: AlertTriangle },
  custom:     { color: C.textDim,    label: "Event",     icon: Circle },
};

const RANGES = [
  { days: 1, label: "24h" },
  { days: 7, label: "7d" },
  { days: 30, label: "30d" },
];

const fmtMs = (ms) => {
  if (ms == null) return null;
  if (ms >= 1000) return `${(ms / 1000).toFixed(ms >= 10000 ? 1 : 2)}s`;
  return `${Math.round(ms)}ms`;
};
const fmtCost = (v) => {
  if (v == null) return null;
  if (v >= 1) return `$${v.toFixed(2)}`;
  return `$${v.toFixed(4)}`;
};
const fmtTime = (iso) => {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
};
const fmtDay = (iso) => {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
};
const dayKey = (iso) => (iso ? new Date(iso).toDateString() : "unknown");

// risk_level from the API: none|low|medium|high → RiskBadge levels (info shown only ≥ low)
const badgeLevel = (level) => (level === "none" ? null : level);

const chip = {
  fontSize: 10.5, fontFamily: FONT.mono, color: C.textDim, background: C.surfaceRaised,
  borderRadius: 999, padding: "3px 10px", whiteSpace: "nowrap", flexShrink: 0,
};

const statusTone = (e) => {
  if (e.status === "error") return C.riskHigh;
  if (e.status === "blocked" || e.policy_action === "block") return C.riskCritical;
  if (e.risk_level === "high") return C.riskHigh;
  if (e.risk_level === "medium") return C.riskMedium;
  return C.ok || C.accent;
};

/** One-line title: the most meaningful thing the event did. */
const eventTitle = (e) => {
  if (e.event_type === "tool_call" && e.tool_name) return `tool: ${e.tool_name}`;
  if (e.action_name) return e.action_name;
  if (e.model) return e.provider ? `${e.model} via ${e.provider}` : e.model;
  if (e.tool_name) return `tool: ${e.tool_name}`;
  return (EVENT_META[e.event_type] || EVENT_META.custom).label;
};

/** Muted one-line explanation: error first, then the top risk reason. */
const eventNote = (e) => {
  if (e.error_message) return e.error_message;
  if (e.risk_reasons && e.risk_reasons.length) return e.risk_reasons[0];
  return null;
};

function TimelineRow({ e }) {
  const meta = EVENT_META[e.event_type] || EVENT_META.custom;
  const Icon = meta.icon;
  const note = eventNote(e);
  const level = badgeLevel(e.risk_level);
  return (
    <div style={{ display: "flex", gap: 14, alignItems: "flex-start", padding: "10px 0", position: "relative" }}>
      <span style={{
        width: 10, height: 10, borderRadius: "50%", background: statusTone(e),
        boxShadow: `0 0 0 3px ${C.surface}, 0 0 10px ${statusTone(e)}55`,
        marginTop: 5, zIndex: 1, flexShrink: 0,
      }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span style={{ fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute, flexShrink: 0 }}>{fmtTime(e.timestamp)}</span>
          <Icon size={13} color={meta.color} style={{ flexShrink: 0 }} />
          <span style={{ fontSize: 13, color: C.text, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {eventTitle(e)}
          </span>
          <StatusPill tone={meta.color}>{meta.label}</StatusPill>
          {e.status !== "ok" && <StatusPill tone={statusTone(e)}>{e.status}</StatusPill>}
          {e.policy_action !== "allow" && <StatusPill tone={e.policy_action === "block" ? C.riskCritical : C.riskMedium}>policy: {e.policy_action}</StatusPill>}
          {level && <RiskBadge level={level} />}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 7, flexWrap: "wrap" }}>
          {e.total_tokens != null && <span style={chip}>{e.total_tokens.toLocaleString()} tok</span>}
          {fmtMs(e.latency_ms) && <span style={chip}>{fmtMs(e.latency_ms)}</span>}
          {fmtCost(e.cost_usd) && <span style={chip}>{fmtCost(e.cost_usd)}{e.cost_estimated ? " est" : ""}</span>}
          {note && (
            <span style={{ fontSize: 11.5, color: e.error_message ? C.riskHigh : C.textDim, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 }}>
              {note}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export default function AgentTimeline({ focusAgentId = null, onFocusConsumed, embedded = false }) {
  const [agents, setAgents] = useState([]);
  const [agentId, setAgentId] = useState(focusAgentId || "");
  const [days, setDays] = useState(7);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);

  // Populate the agent selector from the existing inventory endpoint.
  useEffect(() => {
    let cancelled = false;
    fetchAgents({ days: 90 }).then((rows) => {
      if (cancelled) return;
      const list = Array.isArray(rows) ? rows : [];
      setAgents(list);
      setAgentId((cur) => cur || (list[0]?.id ?? ""));
    }).catch(() => { if (!cancelled) setAgents([]); });
    return () => { cancelled = true; };
  }, []);

  // Consume a one-shot focus target from Agent Inventory click-through.
  useEffect(() => {
    if (focusAgentId) {
      setAgentId(focusAgentId);
      onFocusConsumed?.();
    }
  }, [focusAgentId, onFocusConsumed]);

  const load = useCallback(() => {
    if (!agentId) { setData(null); return; }
    setLoading(true);
    setError(null);
    fetchAgentTimeline(agentId, { days, limit: 50 })
      .then(setData)
      .catch((e) => { setData(null); setError(e.message || "Failed to load timeline"); })
      .finally(() => setLoading(false));
  }, [agentId, days]);

  useEffect(() => { load(); }, [load]);

  const loadMore = useCallback(() => {
    if (!data?.next_cursor) return;
    setLoadingMore(true);
    fetchAgentTimeline(agentId, { days, limit: 50, cursor: data.next_cursor })
      .then((more) => setData((cur) => ({
        ...more,
        events: [...(cur?.events || []), ...more.events],
      })))
      .catch(() => {})
      .finally(() => setLoadingMore(false));
  }, [agentId, days, data]);

  const byDay = useMemo(() => {
    const groups = [];
    let current = null;
    for (const e of data?.events || []) {
      const key = dayKey(e.timestamp);
      if (!current || current.key !== key) {
        current = { key, label: fmtDay(e.timestamp), events: [] };
        groups.push(current);
      }
      current.events.push(e);
    }
    return groups;
  }, [data]);

  const s = data?.summary;
  const selectStyle = {
    background: C.surfaceRaised, color: C.text, border: `1px solid ${C.border}`,
    borderRadius: RADIUS.sm, padding: "7px 12px", fontSize: 12.5, fontFamily: FONT.ui, maxWidth: 280,
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22, fontFamily: FONT.ui }}>
      {(() => {
        const controls = (
          <>
            <select value={agentId} onChange={(e) => setAgentId(e.target.value)} style={selectStyle} aria-label="Agent">
              {!agents.length && <option value="">No agents yet</option>}
              {agents.map((a) => (
                <option key={a.id} value={a.id}>{a.name || a.agent_name || a.id}</option>
              ))}
            </select>
            <div style={{ display: "flex", gap: 4 }}>
              {RANGES.map((r) => (
                <button key={r.days} onClick={() => setDays(r.days)}
                  style={{
                    background: days === r.days ? `${C.accent}1F` : "transparent",
                    color: days === r.days ? C.accentDark || C.accent : C.textDim,
                    border: `1px solid ${days === r.days ? `${C.accent}55` : C.border}`,
                    borderRadius: RADIUS.sm, padding: "7px 13px", fontSize: 11.5,
                    fontFamily: FONT.mono, cursor: "pointer",
                  }}>{r.label}</button>
              ))}
            </div>
          </>
        );
        return embedded ? (
          <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            {controls}
          </div>
        ) : (
          <PageHeader
            eyebrow="Operational evidence"
            title="Agent Timeline"
            purpose="Everything one agent did — model calls, tools, cost, latency, errors, and risk — as a single reviewable feed."
          >
            {controls}
          </PageHeader>
        );
      })()}

      {data?.agent && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: C.text }}>{data.agent.name}</span>
          {data.agent.environment && <StatusPill>{data.agent.environment}</StatusPill>}
          {data.agent.team && <StatusPill tone={C.teal}>{data.agent.team}</StatusPill>}
          <span style={{ fontSize: 11.5, color: C.textMute, fontFamily: FONT.mono }}>
            owner: {data.agent.owner || "unassigned"}
          </span>
          {s?.last_seen && (
            <span style={{ fontSize: 11.5, color: C.textMute, fontFamily: FONT.mono }}>
              last seen {fmtDay(s.last_seen)} {fmtTime(s.last_seen)}
            </span>
          )}
        </div>
      )}

      {s && (
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
          <MetricCard label="Events" value={s.events.toLocaleString()} sub={`last ${days}d`} />
          <MetricCard label="Cost" value={s.total_cost_usd >= 1 ? `$${s.total_cost_usd.toFixed(2)}` : `$${s.total_cost_usd.toFixed(4)}`}
            sub={`${s.total_tokens.toLocaleString()} tokens`} />
          <MetricCard label="Errors" value={s.errors} tone={s.errors ? C.riskHigh : C.text}
            sub={s.blocked ? `${s.blocked} blocked` : "0 blocked"} />
          <MetricCard label="Avg latency" value={fmtMs(s.avg_latency_ms) ?? "—"} />
          <MetricCard label="High risk" value={s.high_risk_events} tone={s.high_risk_events ? C.riskHigh : C.text}
            sub={`${s.policy_violations} policy violation${s.policy_violations === 1 ? "" : "s"}`} />
        </div>
      )}

      {s?.models?.length > 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={{ ...microLabel, fontSize: 10 }}>Models</span>
          {s.models.map((m) => (
            <span key={m.model} style={chip}>
              {m.model} · {m.events.toLocaleString()} ev · {fmtCost(m.cost_usd) ?? "$0"}
            </span>
          ))}
        </div>
      )}

      <Section label="Activity">
        {loading && <div style={{ color: C.textDim, fontSize: 13, padding: "18px 4px" }}>Loading timeline…</div>}
        {!loading && error && (
          <EmptyState icon="!" text={error} actionLabel="Retry" onAction={load} />
        )}
        {!loading && !error && !byDay.length && (
          <EmptyState
            icon="◦"
            text={agentId
              ? "No telemetry events for this agent in the selected range. Send events to POST /api/v1/telemetry/batch to populate the timeline."
              : "No agents discovered yet. Ingest telemetry via POST /api/v1/telemetry/batch or the OTel endpoint to see agent activity here."}
          />
        )}
        {!loading && !error && byDay.length > 0 && (
          <div style={{ position: "relative", paddingLeft: 4 }}>
            {/* the vertical rail */}
            <div aria-hidden="true" style={{ position: "absolute", left: 8, top: 8, bottom: 8, width: 2, background: `${C.border}88`, borderRadius: 2 }} />
            {byDay.map((g) => (
              <Fragment key={g.key}>
                <div style={{ ...microLabel, fontSize: 10, padding: "14px 0 4px 26px", position: "sticky", top: 0, background: C.bg, zIndex: 2 }}>
                  {g.label}
                </div>
                {g.events.map((e) => <TimelineRow key={e.id} e={e} />)}
              </Fragment>
            ))}
            {data?.next_cursor && (
              <div style={{ paddingLeft: 26, paddingTop: 10 }}>
                <button onClick={loadMore} disabled={loadingMore}
                  style={{ background: "transparent", color: C.textDim, border: `1px solid ${C.border}`,
                    padding: "7px 16px", borderRadius: RADIUS.sm, fontSize: 12, fontFamily: FONT.mono,
                    cursor: loadingMore ? "wait" : "pointer" }}>
                  {loadingMore ? "Loading…" : "Load more"}
                </button>
              </div>
            )}
          </div>
        )}
      </Section>
    </div>
  );
}
