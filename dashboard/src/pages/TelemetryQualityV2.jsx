import { useState, useEffect, useMemo, useCallback } from "react";
import { C, FONT, RADIUS, microLabel } from "../ui2/tokens.js";
import PageHeader from "../ui2/PageHeader.jsx";
import Section from "../ui2/Section.jsx";
import MetricCard from "../ui2/MetricCard.jsx";
import StatusPill from "../ui2/StatusPill.jsx";
import EmptyState from "../ui2/EmptyState.jsx";
import { useBreakpoint } from "../hooks/useBreakpoint.js";
import { fetchTelemetryQuality, reclassifyTelemetry } from "../api.js";

/**
 * TelemetryQualityV2 — how well each service's telemetry classifies.
 *
 * OTel is the pipe, semantic conventions are the language, ObserveAgents is
 * the intelligence layer. This page shows where the language is incomplete:
 * per-service classification status, the exact signals that are missing,
 * custom attribute keys that may deserve an org mapping, and unidentified
 * (fallback-identity) sources pending review. Master/detail like Asset
 * Intelligence; read for everyone, Reclassify for admins.
 */

const STATUS_META = {
  fully_classified:     { label: "Fully classified",     tone: () => C.riskLow },
  partially_classified: { label: "Partially classified", tone: () => C.riskMedium },
  unclassified:         { label: "Unclassified",         tone: () => C.riskHigh },
  unscored:             { label: "Unscored",             tone: () => C.textMute },
};
const statusMeta = (s) => STATUS_META[s] || { label: s || "unscored", tone: () => C.textMute };

const MISSING_LABEL = {
  identity: "Service identity (service.name / gen_ai.agent.*)",
  environment: "Deployment environment",
  genai_model: "GenAI model name",
  genai_provider: "GenAI provider",
  tool_name: "Tool name",
  mcp_server: "MCP server name",
};

const ISSUE_LABEL = {
  missing_identity: "Spans arrive without a service identity",
  missing_environment: "Spans arrive without a deployment environment",
  genai_missing_model: "LLM calls without a model name",
  genai_missing_provider: "LLM calls without a provider",
  tool_missing_name: "Tool calls without a tool name",
  mcp_missing_server: "MCP activity without a server name",
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

/** Stacked classification bar for one service's span counts. */
function SpanBar({ counts }) {
  const total = counts?.total || 0;
  if (!total) return null;
  const seg = (n, color) =>
    n > 0 ? <div style={{ width: `${(n / total) * 100}%`, background: color, minWidth: 2 }} /> : null;
  return (
    <div style={{ display: "flex", height: 6, borderRadius: 3, overflow: "hidden", background: C.border, marginTop: 8 }}>
      {seg(counts.fully_classified, C.riskLow)}
      {seg(counts.partially_classified, C.riskMedium)}
      {seg(counts.unclassified, C.riskHigh)}
      {seg(counts.unscored, C.textMute)}
    </div>
  );
}

function ServiceRow({ s, selected, onSelect }) {
  const meta = statusMeta(s.classification_status);
  const issueCount = Object.values(s.missing || {}).reduce((a, b) => a + b, 0);
  return (
    <div onClick={onSelect}
      style={{
        background: selected ? C.surfaceRaised : C.surface,
        border: `1px solid ${selected ? C.borderStrong : C.border}`,
        borderLeft: `3px solid ${meta.tone()}`,
        borderRadius: RADIUS.md, padding: "12px 14px", cursor: "pointer",
      }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: C.text, fontFamily: FONT.mono, overflowWrap: "anywhere" }}>
          {s.service_name}
        </span>
        <StatusPill tone={meta.tone()}>{meta.label}</StatusPill>
        {s.environment && <StatusPill tone={C.textDim}>{s.environment}</StatusPill>}
      </div>
      <div style={{ fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute, marginTop: 6 }}>
        score {s.confidence_score != null ? `${s.confidence_score}` : "—"} ·{" "}
        {s.span_counts?.total || 0} spans · {issueCount} missing signals
        {s.candidate_attribute_keys?.length ? ` · ${s.candidate_attribute_keys.length} custom keys` : ""}
      </div>
      <SpanBar counts={s.span_counts} />
    </div>
  );
}

const WINDOWS = [7, 30, 90];

export default function TelemetryQualityV2({ isAdmin, onNavigate }) {
  const bp = useBreakpoint();
  const [report, setReport] = useState(null);
  const [days, setDays] = useState(30);
  const [selectedName, setSelectedName] = useState(null);
  const [reclassifying, setReclassifying] = useState(false);
  const [reclassResult, setReclassResult] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async (windowDays) => {
    try {
      const data = await fetchTelemetryQuality(windowDays);
      setReport(data);
      setError(null);
    } catch (e) {
      setError(e.message);
      setReport({ services: [], unidentified_assets: [], attribute_mapping_configured: false });
    }
  }, []);
  useEffect(() => { (async () => { await load(days); })(); }, [load, days]);

  const handleReclassify = () => {
    setReclassifying(true); setReclassResult(null); setError(null);
    reclassifyTelemetry()
      .then((res) => {
        setReclassResult(`${res.spans_reclassified} spans reclassified · ${res.spans_rescored} re-extracted`);
        return load(days);
      })
      .catch((e) => setError(e.message))
      .finally(() => setReclassifying(false));
  };

  const services = useMemo(() => {
    const rank = { unclassified: 0, partially_classified: 1, unscored: 2, fully_classified: 3 };
    return [...(report?.services || [])].sort((a, b) =>
      (rank[a.classification_status] ?? 2) - (rank[b.classification_status] ?? 2)
      || (b.span_counts?.total || 0) - (a.span_counts?.total || 0));
  }, [report]);

  const selected = useMemo(
    () => services.find((s) => s.service_name === selectedName) || services[0] || null,
    [services, selectedName]);

  const totals = useMemo(() => {
    const sum = { total: 0, full: 0 };
    for (const s of services) {
      sum.total += s.span_counts?.total || 0;
      sum.full += s.span_counts?.fully_classified || 0;
    }
    return sum;
  }, [services]);

  const mapKey = (key) => {
    try { sessionStorage.setItem("otel_mapping_prefill", key); } catch { /* ignore */ }
    onNavigate?.("settings");
  };

  if (report === null) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 280, color: C.textMute, fontFamily: FONT.mono, fontSize: 13 }}>
      Loading telemetry quality…
    </div>
  );

  const needsAttention = services.filter((s) =>
    s.classification_status && s.classification_status !== "fully_classified").length;
  const unidentified = report.unidentified_assets || [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24, fontFamily: FONT.ui, maxWidth: 1240 }}>

      <div>
        <PageHeader
          title="Telemetry Quality"
          purpose="How well each service's telemetry classifies — which signals are missing, which custom attributes may need mapping, and which sources are unidentified.">
          <div style={{ display: "flex", gap: 4 }}>
            {WINDOWS.map((w) => (
              <button key={w} onClick={() => setDays(w)}
                style={{
                  background: days === w ? C.surfaceRaised : "transparent",
                  color: days === w ? C.text : C.textDim,
                  border: `1px solid ${days === w ? C.borderStrong : C.border}`,
                  borderRadius: 999, padding: "5px 12px", fontSize: 10.5, fontFamily: FONT.mono, cursor: "pointer",
                }}>
                {w}d
              </button>
            ))}
          </div>
          {isAdmin && (
            <button onClick={handleReclassify} disabled={reclassifying}
              title="Re-run classification and extraction over stored spans with the current attribute mapping"
              style={{ background: C.accent, color: C.accentInk, border: "none", borderRadius: RADIUS.sm,
                padding: "8px 16px", fontSize: 12, fontWeight: 700, fontFamily: FONT.ui,
                cursor: reclassifying ? "wait" : "pointer", opacity: reclassifying ? 0.6 : 1 }}>
              {reclassifying ? "Reclassifying…" : "Reclassify"}
            </button>
          )}
        </PageHeader>
        <div style={{ fontSize: 11.5, color: C.textMute, marginTop: 6 }}>
          OpenTelemetry is the pipeline, GenAI semantic conventions are the meaning — this page shows where the meaning is incomplete.
        </div>
        {reclassResult && <div style={{ fontSize: 11, fontFamily: FONT.mono, color: C.accent, marginTop: 8 }}>Reclassify complete — {reclassResult}</div>}
        {error && <div style={{ fontSize: 11, fontFamily: FONT.mono, color: C.riskHigh, marginTop: 8 }}>{error}</div>}
      </div>

      {!report.attribute_mapping_configured && services.some((s) => s.candidate_attribute_keys?.length) && (
        <div style={{ background: C.surface, border: `1px solid ${C.riskMedium}55`, borderLeft: `3px solid ${C.riskMedium}`, borderRadius: RADIUS.md, padding: "12px 16px", fontSize: 12, color: C.textDim }}>
          Custom attribute keys were detected but no attribute mapping is configured yet —{" "}
          <span onClick={() => onNavigate?.("settings")} style={{ color: C.accent, cursor: "pointer", fontWeight: 600 }}>
            map them in Settings
          </span>{" "}
          so the intelligence layer can read them.
        </div>
      )}

      <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
        <MetricCard label="Services reporting" value={services.length} sub={`last ${report.window_days || days} days`} />
        <MetricCard label="Fully classified spans"
          value={totals.total ? `${Math.round((totals.full / totals.total) * 100)}%` : "—"}
          sub={`${totals.full.toLocaleString()} of ${totals.total.toLocaleString()} spans`}
          tone={totals.total && totals.full === totals.total ? C.riskLow : C.text} />
        <MetricCard label="Needs attention" value={needsAttention}
          sub="services with missing signals"
          tone={needsAttention > 0 ? C.riskMedium : C.text} />
        <MetricCard label="Unidentified sources" value={unidentified.length}
          sub="no service.name — needs review"
          tone={unidentified.length > 0 ? C.riskHigh : C.text} />
      </div>

      {services.length === 0 ? (
        <EmptyState icon="◍"
          text={<span><strong style={{ color: C.text }}>No telemetry in this window.</strong>{" "}
            Send OpenTelemetry traces to see per-service classification quality.</span>} />
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: bp.isMobile ? "1fr" : "minmax(300px, 5fr) 7fr", gap: 16, alignItems: "start" }}>

          {/* ── Service list ────────────────────────────────────────────── */}
          <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: bp.isMobile ? "none" : 620, overflowY: "auto", paddingRight: 4 }}>
            {services.map((s) => (
              <ServiceRow key={s.service_name} s={s}
                selected={selected?.service_name === s.service_name}
                onSelect={() => setSelectedName(s.service_name)} />
            ))}
          </div>

          {/* ── Selected service detail ─────────────────────────────────── */}
          {selected && (
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: RADIUS.md, padding: "20px 22px", display: "flex", flexDirection: "column", gap: 20 }}>

              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 17, fontWeight: 700, color: C.text, fontFamily: FONT.mono, overflowWrap: "anywhere" }}>
                    {selected.service_name}
                  </span>
                  <StatusPill tone={statusMeta(selected.classification_status).tone()}>
                    {statusMeta(selected.classification_status).label}
                  </StatusPill>
                  {selected.environment && <StatusPill tone={C.textDim}>{selected.environment}</StatusPill>}
                </div>
                <div style={{ fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute, marginTop: 8 }}>
                  telemetry quality score {selected.confidence_score != null ? `${selected.confidence_score} / 100` : "—"}
                </div>
              </div>

              <Section label="Span classification">
                <div style={{ fontSize: 12, fontFamily: FONT.mono, color: C.textDim, lineHeight: 1.9 }}>
                  {["fully_classified", "partially_classified", "unclassified", "unscored"].map((k) => (
                    <div key={k} style={{ display: "flex", justifyContent: "space-between", maxWidth: 360 }}>
                      <span>
                        <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: 2, background: statusMeta(k).tone(), marginRight: 8 }} />
                        {statusMeta(k).label}
                      </span>
                      <span style={{ color: C.text }}>{selected.span_counts?.[k] ?? 0}</span>
                    </div>
                  ))}
                </div>
              </Section>

              {Object.keys(selected.missing || {}).length > 0 && (
                <Section label="Missing signals">
                  <div style={{ fontSize: 12, fontFamily: FONT.mono, color: C.textDim, lineHeight: 1.9 }}>
                    {Object.entries(selected.missing).sort((a, b) => b[1] - a[1]).map(([code, n]) => (
                      <div key={code} style={{ display: "flex", justifyContent: "space-between", maxWidth: 460 }}>
                        <span>{MISSING_LABEL[code] || code}</span>
                        <span style={{ color: C.riskMedium }}>{n} spans</span>
                      </div>
                    ))}
                  </div>
                </Section>
              )}

              {selected.candidate_attribute_keys?.length > 0 && (
                <Section label="Custom attribute keys detected">
                  <div style={{ fontSize: 11.5, color: C.textMute, marginBottom: 8 }}>
                    These keys look like signals the intelligence layer could use — map them to canonical attributes, no code change needed.
                  </div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {selected.candidate_attribute_keys.map((k) => (
                      <button key={k} onClick={() => mapKey(k)}
                        title="Map this key in Settings"
                        style={{ background: C.surfaceRaised, border: `1px solid ${C.border}`, borderRadius: 999,
                          padding: "4px 12px", fontSize: 11, fontFamily: FONT.mono, color: C.accent, cursor: "pointer" }}>
                        {k} →
                      </button>
                    ))}
                  </div>
                </Section>
              )}

              {selected.remediation?.length > 0 && (
                <Section label="How to fix">
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {selected.remediation.map((r) => (
                      <div key={r.issue} style={{ background: C.surfaceRaised, border: `1px solid ${C.border}`, borderRadius: RADIUS.sm, padding: "10px 14px" }}>
                        <div style={{ fontSize: 12, fontWeight: 600, color: C.text }}>{ISSUE_LABEL[r.issue] || r.issue}</div>
                        <div style={{ fontSize: 11.5, fontFamily: FONT.mono, color: C.textDim, marginTop: 4 }}>
                          → add {r.add_attributes?.join(" or ")}
                          {r.or_map_via && <span style={{ color: C.textMute }}> · or map a custom key in Settings</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                </Section>
              )}
            </div>
          )}
        </div>
      )}

      {unidentified.length > 0 && (
        <Section label="Unidentified sources — needs review">
          <div style={{ fontSize: 11.5, color: C.textMute, marginBottom: 10 }}>
            Telemetry arrived without any service identity. Each row below is a stable grouping of that traffic — add{" "}
            <span style={{ fontFamily: FONT.mono }}>service.name</span> at the source to claim it.
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 520 }}>
              <thead>
                <tr>
                  {["Source", "First seen", "Last seen"].map((h) => (
                    <th key={h} style={{ ...microLabel, textAlign: "left", padding: "8px 12px", borderBottom: `1px solid ${C.border}` }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {unidentified.map((u) => (
                  <tr key={u.asset_key}>
                    <td style={{ padding: "9px 12px", fontSize: 12, fontFamily: FONT.mono, color: C.text, borderBottom: `1px solid ${C.border}` }}>
                      {u.agent_id_raw}
                    </td>
                    <td style={{ padding: "9px 12px", fontSize: 11.5, fontFamily: FONT.mono, color: C.textDim, borderBottom: `1px solid ${C.border}` }}>
                      {relTime(u.first_seen)}
                    </td>
                    <td style={{ padding: "9px 12px", fontSize: 11.5, fontFamily: FONT.mono, color: C.textDim, borderBottom: `1px solid ${C.border}` }}>
                      {relTime(u.last_seen)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}
    </div>
  );
}
