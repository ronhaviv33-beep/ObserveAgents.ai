import React, { useState, useEffect, useMemo, useCallback } from "react";
import { fetchIntelligenceAssetSummary, fetchGuardModes } from "../api.js";
import { T, FONT_UI, FONT_MONO } from "../theme.js";
import { isObservability } from "../productSurface.js";
import { Card, Stat, Pill } from "../components/ui.jsx";

// Advisory guardrail catalog — evaluated in the browser against already-derived
// intelligence (capabilities + findings). Nothing is persisted, nothing is
// blocked: guardrails detect, explain, and recommend.
const GUARDRAIL_CATALOG = [
  {
    id: "database_access",
    title: "AI system has direct database access",
    severity: "medium",
    test: (a) => a._capTypes.has("database"),
    recommendation: "Scope database credentials to read-only where possible and monitor the queries this system issues.",
  },
  {
    id: "mcp_tools",
    title: "AI system uses MCP tools",
    severity: "medium",
    test: (a) => a._capTypes.has("mcp"),
    recommendation: "Review the connected MCP servers and the tool surface they expose to this system.",
  },
  {
    id: "external_api",
    title: "AI system calls external APIs",
    severity: "low",
    test: (a) => a._capTypes.has("external_api"),
    recommendation: "Confirm the external endpoints are expected and that no sensitive data leaves through them.",
  },
  {
    id: "broad_tool_access",
    title: "AI system has broad tool access",
    severity: "medium",
    test: (a) => a._openTypes.has("broad_tool_access"),
    recommendation: "Trim unused tools — a smaller tool surface reduces blast radius and simplifies review.",
  },
  {
    id: "prod_high_severity",
    title: "Production system with high-severity findings",
    severity: "high",
    test: (a) => ["production", "prod"].includes((a.environment || "").toLowerCase()) && a.high_findings_count > 0,
    recommendation: "Prioritize resolving the high-severity findings on this system — it is live in production.",
  },
  {
    id: "runtime_errors",
    title: "AI system has repeated runtime errors",
    severity: "medium",
    test: (a) => ["runtime_error", "provider_error", "tool_error", "mcp_error"].some((t) => a._openTypes.has(t)),
    recommendation: "Inspect the failing spans in the Runtime timeline to find the failing step.",
  },
  {
    id: "slow_model_path",
    title: "AI system uses a slow or expensive execution path",
    severity: "low",
    test: (a) => ["slow_llm_call", "slow_runtime_step", "slow_tool_call"].some((t) => a._openTypes.has(t)),
    recommendation: "Review the slow steps in the Runtime timeline — long LLM or tool calls are the usual cost hotspots.",
  },
];

const SEV_COLOR = { high: T.crit, medium: T.warn, low: T.info };
const MODE_COLOR = { observe: T.info, alert: T.warn, enforce: T.crit };

export default function Guardrails() {
  const [assets, setAssets]         = useState([]);
  const [guardModes, setGuardModes] = useState(null);   // null = unavailable (viewer) → section hidden
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);
  const [expanded, setExpanded]     = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchIntelligenceAssetSummary()
      .then((summary) => setAssets(summary.assets || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
    // Guard modes are admin/settings-scoped — best effort, hidden if unavailable
    fetchGuardModes().then(setGuardModes).catch(() => setGuardModes(null));
  }, []);

  useEffect(() => { load(); }, [load]);

  // Enrich each asset with cheap lookup sets, evaluate the catalog per render.
  const enriched = useMemo(() => assets.map((a) => ({
    ...a,
    _capTypes: new Set((a.capabilities || []).map((c) => c.capability_type)),
    _openTypes: new Set((a.findings || []).filter((f) => f.status === "open").map((f) => f.finding_type)),
  })), [assets]);

  const evaluated = useMemo(() => GUARDRAIL_CATALOG.map((g) => ({
    ...g,
    affected: enriched.filter((a) => g.test(a)),
  })), [enriched]);

  const triggered = evaluated.filter((g) => g.affected.length > 0);
  const affectedAssets = new Set(triggered.flatMap((g) => g.affected.map((a) => a.asset_key)));

  return (
    <div>
      {/* Observe-only banner — the core promise of advisory guardrails */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, background: `${T.accent}0D`, border: `1px solid ${T.accent}33`, borderRadius: 6, padding: "12px 16px", marginBottom: 14 }}>
        <span style={{ color: T.accent, fontSize: 16 }}>◉</span>
        <div>
          <div style={{ fontFamily: FONT_MONO, fontSize: 11, letterSpacing: "0.1em", textTransform: "uppercase", color: T.accent, fontWeight: 600 }}>
            Observe-only mode
          </div>
          <div style={{ fontSize: 12, color: T.textDim, marginTop: 2 }}>
            {isObservability
              ? "Detect, explain, and recommend — without blocking production AI. Guardrails are derived from observed runtime behavior. Nothing is blocked."
              : "Guardrails detect, explain, and recommend based on observed runtime behavior. Nothing is blocked. Enforcement is optional and can be enabled per team later via guard modes."}
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 14, marginBottom: 14 }}>
        <Stat label="Guardrails triggered" value={triggered.length} suffix={`/ ${GUARDRAIL_CATALOG.length}`} accent={triggered.length > 0 ? T.warn : T.text} />
        <Stat label="AI systems affected"  value={affectedAssets.size} suffix={`/ ${assets.length}`} />
        <Stat label="Enforcement mode"     value="Off" suffix="(observe-only)" />
      </div>

      <Card
        title="Advisory Guardrails"
        subtitle="Which recommended guardrails are being triggered by observed AI behavior? Derived live from capabilities and findings — nothing is persisted or blocked."
        right={
          <button onClick={load}
            style={{ background: "transparent", color: T.textDim, border: `1px solid ${T.border}`, padding: "5px 12px", borderRadius: 3, fontSize: 10, fontFamily: FONT_MONO, cursor: "pointer", letterSpacing: "0.08em", textTransform: "uppercase" }}>
            ↻ Refresh
          </button>
        }>

        {error && (
          <div style={{ padding: "12px 14px", background: `${T.crit}0D`, border: `1px solid ${T.crit}33`, borderRadius: 4, color: T.crit, fontFamily: FONT_MONO, fontSize: 12, marginBottom: 12 }}>
            {error}
          </div>
        )}

        {loading ? (
          <div style={{ padding: "40px 0", textAlign: "center", color: T.textMute, fontFamily: FONT_MONO, fontSize: 13 }}>Loading…</div>
        ) : assets.length === 0 ? (
          <div style={{ padding: "40px 20px", textAlign: "center" }}>
            <div style={{ color: T.textDim, fontSize: 14, marginBottom: 6 }}>No AI systems observed yet.</div>
            <div style={{ color: T.textMute, fontSize: 12, fontFamily: FONT_MONO }}>
              Guardrails evaluate observed runtime behavior — connect OpenTelemetry traces and AI systems appear here automatically.
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {evaluated.map((g) => {
              const isTriggered = g.affected.length > 0;
              const isOpen = expanded === g.id;
              return (
                <div key={g.id}
                  style={{ background: T.panelHi, border: `1px solid ${isTriggered ? (SEV_COLOR[g.severity] + "44") : T.border}`, borderRadius: 6, overflow: "hidden", opacity: isTriggered ? 1 : 0.6 }}>
                  <div onClick={() => setExpanded(isOpen ? null : g.id)}
                    style={{ padding: "12px 16px", cursor: "pointer", display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <span style={{ color: isTriggered ? SEV_COLOR[g.severity] : T.textMute, fontFamily: FONT_MONO, fontSize: 13, flexShrink: 0 }}>
                      {isTriggered ? "▲" : "○"}
                    </span>
                    <span style={{ fontSize: 13, color: T.text }}>{g.title}</span>
                    <Pill color={SEV_COLOR[g.severity]}>{g.severity}</Pill>
                    <Pill color={T.accent}>Observe-only</Pill>
                    <span style={{ marginLeft: "auto", fontFamily: FONT_MONO, fontSize: 11, color: isTriggered ? T.warn : T.textMute }}>
                      {isTriggered ? `${g.affected.length} system${g.affected.length > 1 ? "s" : ""} affected` : "not triggered"}
                    </span>
                  </div>
                  {isOpen && (
                    <div style={{ borderTop: `1px solid ${T.border}`, background: T.panel, padding: "14px 18px" }}>
                      <div style={{ fontFamily: FONT_MONO, fontSize: 9, letterSpacing: "0.14em", textTransform: "uppercase", color: T.textMute, marginBottom: 6 }}>Recommendation</div>
                      <div style={{ fontSize: 13, color: T.text, lineHeight: 1.6, marginBottom: 12 }}>{g.recommendation}</div>
                      <div style={{ fontFamily: FONT_MONO, fontSize: 9, letterSpacing: "0.14em", textTransform: "uppercase", color: T.textMute, marginBottom: 6 }}>Affected AI systems</div>
                      {g.affected.length === 0
                        ? <span style={{ color: T.textMute, fontFamily: FONT_MONO, fontSize: 11 }}>none — this guardrail is clear</span>
                        : <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                            {g.affected.map((a) => (
                              <Pill key={a.asset_key} color={SEV_COLOR[g.severity]}>
                                {a.asset_name}{a.environment ? ` · ${a.environment}` : ""}
                              </Pill>
                            ))}
                          </div>}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* Guard modes — per-team graduation path (admin-scoped API; hidden if
          unavailable). Hidden entirely on the Observability surface: guard
          modes are Gateway enforcement configuration, not observation. */}
      {!isObservability && Array.isArray(guardModes) && guardModes.length > 0 && (
        <Card style={{ marginTop: 14 }}
          title="Guard Modes"
          subtitle="Advisory first — enforcement is optional per team. Teams start in observe (nothing blocked); 'would block' shows what enforce mode would have done.">
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: FONT_UI }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                  {["Team", "Effective mode", "Would block (30d)"].map((h) => (
                    <th key={h} style={{ textAlign: "left", padding: "8px", fontFamily: FONT_MONO, fontSize: 10, letterSpacing: "0.1em", textTransform: "uppercase", color: T.textDim, fontWeight: 500 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {guardModes.map((gm) => (
                  <tr key={gm.team} style={{ borderBottom: `1px solid ${T.border}` }}>
                    <td style={{ padding: "10px 8px", fontSize: 13, color: T.text, fontFamily: FONT_MONO }}>{gm.team}</td>
                    <td style={{ padding: "10px 8px" }}>
                      <Pill color={MODE_COLOR[gm.mode] || T.textDim}>{gm.mode}</Pill>
                      {gm.is_override && <span style={{ marginLeft: 6, fontFamily: FONT_MONO, fontSize: 10, color: T.textMute }}>override</span>}
                    </td>
                    <td style={{ padding: "10px 8px", fontSize: 12, color: (gm.would_block_30d ?? 0) > 0 ? T.warn : T.textDim, fontFamily: FONT_MONO }}>
                      {gm.would_block_30d ?? 0}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ marginTop: 10, fontSize: 11, color: T.textMute, fontFamily: FONT_MONO }}>
            Mode changes are made in Settings → Guard Modes. Observe and alert never block.
          </div>
        </Card>
      )}
    </div>
  );
}
