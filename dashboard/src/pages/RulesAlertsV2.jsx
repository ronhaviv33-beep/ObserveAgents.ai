import { useState, useEffect, useMemo, useCallback } from "react";
import { Shield, Wrench, UserCheck, CircleDollarSign } from "lucide-react";
import { C, FONT, RADIUS, microLabel, riskColor } from "../ui2/tokens.js";
import PageHeader from "../ui2/PageHeader.jsx";
import Section from "../ui2/Section.jsx";
import MetricCard from "../ui2/MetricCard.jsx";
import RiskBadge from "../ui2/RiskBadge.jsx";
import StatusPill from "../ui2/StatusPill.jsx";
import EmptyState from "../ui2/EmptyState.jsx";
import { surfaceAllowsPage } from "../productSurface.js";
import { runIntelligence, fetchRiskFindings, fetchRiskFindingsSummary,
  fetchDetectionRules, fetchDetectionRuleTemplates, createDetectionRule,
  updateDetectionRule, deleteDetectionRule } from "../api.js";
import { getAssetSummary, getControlCandidates, getRuleMatches } from "../overviewApi.js";

/**
 * RulesAlertsV2 — R6 of docs/ai_agent_detection_rules_alerts_design.md.
 *
 * Read-only MVP: the built-in rule template catalog plus recent rule matches
 * (findings with source=detection_rules). Rules evaluate during the
 * intelligence run — never at ingestion — and never enforce anything.
 * Configurable rules (R7) and notification channels (R5) come later.
 *
 *   Rules observe and alert. Gateway can optionally enforce later.
 */

const SEV_RANK = { critical: 5, high: 4, medium: 3, low: 2, info: 1 };

// Built-in catalog — mirrors app/detection_rules.py (implemented) and the
// design doc's MVP templates (planned). Read-only: defaults are hardcoded
// until the R7 rule builder.
const RULE_TEMPLATES = [
  { type: "mcp_tool_access_threshold", title: "MCP tool access threshold",
    category: "security", severity: "medium → high in production", implemented: true,
    trigger: "Agent calls MCP tools more than 5 times in the evidence window.",
    action: "Review whether this agent should have this MCP/tool access level.",
    gateway: "candidate if production or high count" },
  { type: "repeated_tool_errors", title: "Repeated tool errors",
    category: "operations", severity: "medium → high in production", implemented: true,
    trigger: "Same agent records 3 or more tool/MCP errors in the evidence window.",
    action: "Check dependency health, add fallback behavior, or route to human review.",
    gateway: "candidate if repeated in production" },
  { type: "unknown_provider_in_production", title: "Unknown provider in production",
    category: "security", severity: "high", implemented: true,
    trigger: "Production agent uses a provider/model outside the known catalog.",
    action: "Confirm provider approval and ownership.",
    gateway: "candidate" },
  { type: "database_access_in_production", title: "Database access in production",
    category: "security", severity: "medium", implemented: false,
    trigger: "Agent accesses a database in production.",
    action: "Review whether this agent should access this database.",
    gateway: "candidate depending on severity" },
  { type: "db_to_external_api_same_trace", title: "DB + external API in same trace",
    category: "security", severity: "high", implemented: false,
    trigger: "One trace shows database access and an external API call.",
    action: "Review whether sensitive data could leave internal systems.",
    gateway: "candidate" },
  { type: "broad_tool_surface", title: "Broad tool surface",
    category: "security", severity: "medium → high", implemented: false,
    trigger: "Agent uses 5 or more distinct tools.",
    action: "Reduce tool scope or add a tool-routing policy.",
    gateway: "candidate if production and high count" },
  { type: "missing_owner_in_production", title: "Missing owner in production",
    category: "governance", severity: "high in production", implemented: false,
    trigger: "Production agent has no owner/team metadata.",
    action: "Assign owner/team before expanding use.",
    gateway: "strengthens other candidates" },
  { type: "high_token_usage_threshold", title: "High token usage threshold",
    category: "cost", severity: "medium", implemented: false,
    trigger: "Agent exceeds a token threshold in a time window (cost signal, not billing).",
    action: "Review workflow efficiency, model choice, and retry behavior.",
    gateway: "budget/rate-limit recommendation if routed" },
  { type: "flagged_dependency_touched", title: "Flagged dependency touched",
    category: "security", severity: "high", implemented: false,
    trigger: "Agent touches a domain, repo, MCP server, package, or tool on a configured watchlist.",
    action: "Review dependency trust before allowing production use.",
    gateway: "candidate if severity high" },
];

const STATUS_TONE = { open: C.riskMedium, acknowledged: C.teal, resolved: C.accent, dismissed: C.textMute };

// Rule category → icon + color for the template list.
const CATEGORY_META = {
  security:   { icon: Shield,           color: C.accent },
  operations: { icon: Wrench,           color: C.teal },
  governance: { icon: UserCheck,        color: C.purple },
  cost:       { icon: CircleDollarSign, color: C.riskMedium },
};

/** Compact "medium → high" style chip text from the catalog's severity phrase. */
const sevShort = (severity) => severity.replace(" in production", "").replace(" if production or high count", "");

const relTime = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
  const m = Math.floor((Date.now() - d.getTime()) / 60000);
  if (m < 2) return "just now";
  if (m < 60) return `${m}m ago`;
  if (m < 1440) return `${Math.floor(m / 60)}h ago`;
  return `${Math.floor(m / 1440)}d ago`;
};

function RuleListRow({ t, open, onToggle, last }) {
  const cat = CATEGORY_META[t.category] || CATEGORY_META.security;
  const CatIcon = cat.icon;
  return (
    <div style={{ borderBottom: last ? "none" : `1px solid ${C.border}` }}>
      <div onClick={onToggle} role="button" aria-expanded={open}
        style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 16px",
          cursor: "pointer", background: open ? C.surfaceRaised : "transparent",
          opacity: t.implemented ? 1 : 0.65 }}
        onMouseEnter={(e) => { e.currentTarget.style.background = C.surfaceHover; }}
        onMouseLeave={(e) => { e.currentTarget.style.background = open ? C.surfaceRaised : "transparent"; }}>
        <span style={{ color: C.textMute, fontFamily: FONT.mono, fontSize: 10, width: 10, flexShrink: 0 }}>{open ? "▾" : "▸"}</span>
        <span style={{ width: 24, height: 24, borderRadius: 8, background: `${cat.color}14`,
          display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <CatIcon size={13} color={cat.color} strokeWidth={2} />
        </span>
        <span style={{ fontSize: 13, fontWeight: 600, color: C.text }}>{t.title}</span>
        <StatusPill tone={t.implemented ? C.accent : C.textMute}>
          {t.implemented ? "built-in" : "planned"}
        </StatusPill>
        <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          <span style={{ fontSize: 10, fontFamily: FONT.mono, color: C.textMute, textTransform: "uppercase", letterSpacing: "0.06em" }}>{t.category}</span>
          <span style={{ fontSize: 10, fontFamily: FONT.mono, color: C.textDim, background: C.surfaceRaised, borderRadius: 999, padding: "2px 9px", whiteSpace: "nowrap" }}>
            {sevShort(t.severity)}
          </span>
        </span>
      </div>
      {open && (
        <div style={{ padding: "2px 16px 14px 60px", background: C.surfaceRaised }}>
          <div style={{ display: "grid", gridTemplateColumns: "110px 1fr", rowGap: 6, columnGap: 12, maxWidth: 720 }}>
            <span style={{ fontSize: 9.5, fontFamily: FONT.mono, color: C.textMute, textTransform: "uppercase", letterSpacing: "0.08em", paddingTop: 2 }}>Trigger</span>
            <span style={{ fontSize: 12, color: C.textDim, lineHeight: 1.6 }}>{t.trigger}</span>
            <span style={{ fontSize: 9.5, fontFamily: FONT.mono, color: C.textMute, textTransform: "uppercase", letterSpacing: "0.08em", paddingTop: 2 }}>Severity</span>
            <span style={{ fontSize: 12, color: C.textDim, lineHeight: 1.6 }}>{t.severity}</span>
            <span style={{ fontSize: 9.5, fontFamily: FONT.mono, color: C.textMute, textTransform: "uppercase", letterSpacing: "0.08em", paddingTop: 2 }}>Gateway</span>
            <span style={{ fontSize: 12, color: C.textDim, lineHeight: 1.6 }}>{t.gateway}</span>
            <span style={{ fontSize: 9.5, fontFamily: FONT.mono, color: C.textMute, textTransform: "uppercase", letterSpacing: "0.08em", paddingTop: 2 }}>Action</span>
            <span style={{ fontSize: 12, color: C.text, lineHeight: 1.6 }}>{t.action}</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Recent findings (event-level, real-time) ─────────────────────────────────
// One row per risk-scored telemetry event from /risk-findings. This is the
// live feed: scored at ingestion by the telemetry worker, not by the batch
// intelligence run below.

const POLICY_TONE = { block: C.riskCritical, warn: C.riskMedium, allow: C.textDim };
const findingChip = {
  fontSize: 10.5, fontFamily: FONT.mono, color: C.textDim, background: C.surfaceRaised,
  borderRadius: 999, padding: "2px 9px", whiteSpace: "nowrap", flexShrink: 0,
};

function FindingRow({ f, onNavigate }) {
  const levelColor = riskColor(f.risk_level === "none" ? "info" : f.risk_level);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, background: C.surface,
      border: `1px solid ${C.border}`, borderLeft: `3px solid ${levelColor}`,
      borderRadius: RADIUS.md, padding: "11px 15px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <span style={{ fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute, flexShrink: 0 }}>{relTime(f.timestamp)}</span>
        <span style={{ fontSize: 13, fontWeight: 600, color: C.text }}>{f.rule_name || f.primary_reason || "Risk finding"}</span>
        <RiskBadge level={f.risk_level === "none" ? "info" : f.risk_level} />
        {f.policy_action !== "allow" && (
          <StatusPill tone={POLICY_TONE[f.policy_action]}>policy: {f.policy_action}</StatusPill>
        )}
        {f.status !== "ok" && <StatusPill tone={f.status === "error" ? C.riskHigh : C.riskCritical}>{f.status}</StatusPill>}
        <span style={{ marginLeft: "auto", fontSize: 10, fontFamily: FONT.mono, color: C.textMute }}>score {f.risk_score}</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        <button onClick={() => onNavigate?.("agent_timeline", { timelineAgent: f.timeline_agent_id })}
          title="Open Agent Timeline"
          style={{ background: "transparent", border: `1px solid ${C.border}`, color: C.text,
            fontSize: 10, fontFamily: FONT.mono, padding: "2px 9px", borderRadius: 999, cursor: "pointer" }}>
          {f.agent_name} →
        </button>
        {f.team && <span style={findingChip}>{f.team}</span>}
        {f.environment && <span style={findingChip}>{f.environment}</span>}
        <span style={findingChip}>{f.event_type}</span>
        {(f.model || f.tool_name) && (
          <span style={findingChip}>{f.tool_name ? `tool: ${f.tool_name}` : `${f.model}${f.provider ? ` · ${f.provider}` : ""}`}</span>
        )}
      </div>
      {f.risk_reasons.length > 0 && (
        <div style={{ fontSize: 11.5, color: C.textDim, lineHeight: 1.55 }}>
          {f.risk_reasons.join(" · ")}
        </div>
      )}
    </div>
  );
}

const FILTER_SELECT = {
  background: C.surfaceRaised, color: C.text, border: `1px solid ${C.border}`,
  borderRadius: RADIUS.sm, padding: "6px 10px", fontSize: 11.5, fontFamily: FONT.ui,
};

// ── Managed rules (admin-editable, template-based) ───────────────────────────

const SMALL_BTN = {
  background: "transparent", border: `1px solid ${C.border}`, color: C.textDim,
  borderRadius: RADIUS.sm, padding: "4px 11px", fontSize: 10.5, fontFamily: FONT.mono, cursor: "pointer",
};
const INPUT = {
  background: C.surfaceRaised, color: C.text, border: `1px solid ${C.border}`,
  borderRadius: RADIUS.sm, padding: "6px 10px", fontSize: 11.5, fontFamily: FONT.ui,
};

/** Editable config fields for one rule's template params. Values held as raw
 * strings; string_list params are comma-separated. */
function configToFields(templates, templateType, config) {
  const tpl = templates.find((t) => t.template_type === templateType);
  if (!tpl) return [];
  return tpl.params.map((p) => ({
    ...p,
    raw: p.type === "string_list"
      ? (config?.[p.key] || []).join(", ")
      : (config?.[p.key] ?? ""),
  }));
}

function fieldsToConfig(fields) {
  const out = {};
  for (const f of fields) {
    if (f.type === "string_list") {
      out[f.key] = String(f.raw).split(",").map((s) => s.trim()).filter(Boolean);
    } else {
      out[f.key] = Number(f.raw);
    }
  }
  return out;
}

function ManagedRuleRow({ rule, templates, canManage, onSaved, onError, last }) {
  const cat = CATEGORY_META[rule.category] || CATEGORY_META.security;
  const CatIcon = cat.icon;
  const [editing, setEditing] = useState(false);
  const [fields, setFields] = useState([]);
  const [severity, setSeverity] = useState(rule.severity);
  const [busy, setBusy] = useState(false);
  const idOrKey = rule.id ?? rule.rule_key;
  const hasParams = !!rule.template_type && configToFields(templates, rule.template_type, rule.config).length > 0;

  const startEdit = () => {
    setFields(configToFields(templates, rule.template_type, rule.config));
    setSeverity(rule.severity);
    setEditing(true);
  };
  const call = (fn) => { setBusy(true); fn().then(onSaved).catch((e) => onError(e.message)).finally(() => setBusy(false)); };
  const save = () => call(() => updateDetectionRule(idOrKey, {
    severity,
    ...(hasParams && fields.length ? { config: fieldsToConfig(fields) } : {}),
  }).then(() => setEditing(false)));
  const toggle = () => call(() => updateDetectionRule(idOrKey, { enabled: !rule.enabled }));
  const remove = () => call(() => deleteDetectionRule(rule.id));

  return (
    <div style={{ borderBottom: last ? "none" : `1px solid ${C.border}`, opacity: rule.enabled ? 1 : 0.55 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 16px", flexWrap: "wrap" }}>
        <span style={{ width: 24, height: 24, borderRadius: 8, background: `${cat.color}14`,
          display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <CatIcon size={13} color={cat.color} strokeWidth={2} />
        </span>
        <span style={{ fontSize: 12.5, fontWeight: 600, color: C.text }}>{rule.name}</span>
        <StatusPill tone={rule.source === "custom" ? C.violet : C.accent}>
          {rule.source === "custom" ? "custom" : "built-in"}
        </StatusPill>
        <RiskBadge level={rule.severity} />
        {!rule.enabled && <StatusPill tone={C.textMute}>disabled</StatusPill>}
        <span style={{ marginLeft: "auto", display: "flex", gap: 6, alignItems: "center" }}>
          {rule.updated_by && (
            <span title={rule.updated_at || ""} style={{ fontSize: 9.5, fontFamily: FONT.mono, color: C.textMute }}>
              updated by {rule.updated_by}
            </span>
          )}
          {canManage && (
            <>
              <button onClick={toggle} disabled={busy} style={SMALL_BTN}>{rule.enabled ? "Disable" : "Enable"}</button>
              {!editing && <button onClick={startEdit} disabled={busy} style={SMALL_BTN}>Edit</button>}
              {rule.source === "custom" && (
                <button onClick={remove} disabled={busy} style={{ ...SMALL_BTN, color: C.riskHigh, borderColor: `${C.riskHigh}44` }}>Delete</button>
              )}
            </>
          )}
        </span>
      </div>
      {editing && (
        <div style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap",
          padding: "4px 16px 14px 50px", background: C.surfaceRaised }}>
          <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 9.5, fontFamily: FONT.mono, color: C.textMute, textTransform: "uppercase" }}>
            severity
            <select value={severity} onChange={(e) => setSeverity(e.target.value)} style={INPUT}>
              <option value="low">low</option><option value="medium">medium</option><option value="high">high</option>
            </select>
          </label>
          {fields.map((f, i) => (
            <label key={f.key} style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 9.5, fontFamily: FONT.mono, color: C.textMute, textTransform: "uppercase" }}>
              {f.label}
              <input value={f.raw} style={{ ...INPUT, minWidth: f.type === "string_list" ? 220 : 120 }}
                onChange={(e) => setFields((cur) => cur.map((x, j) => j === i ? { ...x, raw: e.target.value } : x))} />
            </label>
          ))}
          <button onClick={save} disabled={busy}
            style={{ ...SMALL_BTN, background: C.accent, color: C.accentInk, border: "none", fontWeight: 700 }}>
            {busy ? "Saving…" : "Save"}
          </button>
          <button onClick={() => setEditing(false)} disabled={busy} style={SMALL_BTN}>Cancel</button>
        </div>
      )}
    </div>
  );
}

function AddRuleForm({ templates, onSaved, onError, onClose }) {
  const [templateType, setTemplateType] = useState(templates[0]?.template_type || "");
  const [name, setName] = useState("");
  const [severity, setSeverity] = useState("medium");
  const [fields, setFields] = useState(() => configToFields(templates, templates[0]?.template_type, {}));
  const [busy, setBusy] = useState(false);

  const pickTemplate = (t) => { setTemplateType(t); setFields(configToFields(templates, t, {})); };
  const save = () => {
    setBusy(true);
    createDetectionRule({ name: name.trim() || templates.find((t) => t.template_type === templateType)?.label,
      template_type: templateType, severity, config: fieldsToConfig(fields) })
      .then(() => { onSaved(); onClose(); })
      .catch((e) => onError(e.message))
      .finally(() => setBusy(false));
  };

  return (
    <div style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap",
      border: `1px dashed ${C.borderStrong}66`, borderRadius: RADIUS.md, padding: "14px 16px", marginBottom: 10 }}>
      <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 9.5, fontFamily: FONT.mono, color: C.textMute, textTransform: "uppercase" }}>
        template
        <select value={templateType} onChange={(e) => pickTemplate(e.target.value)} style={INPUT}>
          {templates.map((t) => <option key={t.template_type} value={t.template_type}>{t.label}</option>)}
        </select>
      </label>
      <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 9.5, fontFamily: FONT.mono, color: C.textMute, textTransform: "uppercase" }}>
        name
        <input value={name} placeholder="Rule name" onChange={(e) => setName(e.target.value)} style={{ ...INPUT, minWidth: 180 }} />
      </label>
      <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 9.5, fontFamily: FONT.mono, color: C.textMute, textTransform: "uppercase" }}>
        severity
        <select value={severity} onChange={(e) => setSeverity(e.target.value)} style={INPUT}>
          <option value="low">low</option><option value="medium">medium</option><option value="high">high</option>
        </select>
      </label>
      {fields.map((f, i) => (
        <label key={f.key} style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 9.5, fontFamily: FONT.mono, color: C.textMute, textTransform: "uppercase" }}>
          {f.label}
          <input value={f.raw} placeholder={f.type === "string_list" ? "comma, separated" : "number"}
            style={{ ...INPUT, minWidth: f.type === "string_list" ? 220 : 120 }}
            onChange={(e) => setFields((cur) => cur.map((x, j) => j === i ? { ...x, raw: e.target.value } : x))} />
        </label>
      ))}
      <button onClick={save} disabled={busy}
        style={{ ...SMALL_BTN, background: C.accent, color: C.accentInk, border: "none", fontWeight: 700 }}>
        {busy ? "Saving…" : "Save rule"}
      </button>
      <button onClick={onClose} disabled={busy} style={SMALL_BTN}>Cancel</button>
    </div>
  );
}

function MatchRow({ f, assetName, isCandidate, onNavigate }) {
  const sevColor = riskColor(f.severity);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 7, background: C.surface,
      border: `1px solid ${C.border}`, borderLeft: `3px solid ${sevColor}`,
      borderRadius: RADIUS.md, padding: "12px 15px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: C.text }}>{f.title}</span>
        <RiskBadge level={f.severity} />
        {(f.occurrence_count || 1) > 1 && (
          <span style={{ fontFamily: FONT.mono, fontSize: 10, color: C.textDim }}>×{f.occurrence_count}</span>
        )}
        <StatusPill tone={STATUS_TONE[f.status] || C.textDim}>{f.status || "open"}</StatusPill>
        <span style={{ marginLeft: "auto", fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute }}>{relTime(f.last_seen)}</span>
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {assetName && (
          <button onClick={() => onNavigate?.("intelligence")}
            style={{ background: "transparent", border: `1px solid ${C.border}`, color: C.text,
              fontSize: 10, fontFamily: FONT.mono, padding: "2px 9px", borderRadius: 999, cursor: "pointer" }}>
            {assetName}
          </button>
        )}
        <StatusPill tone={C.textDim}>{f.finding_type}</StatusPill>
      </div>
      {f.summary && <div style={{ fontSize: 11.5, color: C.textDim, lineHeight: 1.55 }}>{f.summary}</div>}
      {isCandidate && f.status === "open" && surfaceAllowsPage("gateway_control_center") && (
        <button onClick={() => onNavigate?.("gateway_control_center", { gccFocus: f.asset_key })}
          style={{ alignSelf: "flex-start", background: "transparent", color: C.riskMedium,
            border: `1px solid ${C.riskMedium}44`, borderRadius: RADIUS.sm, padding: "5px 13px",
            fontSize: 10.5, fontFamily: FONT.mono, cursor: "pointer" }}>
          Review in Gateway Control Center →
        </button>
      )}
    </div>
  );
}

export default function RulesAlertsV2({ onNavigate }) {
  const [matches, setMatches] = useState(null);
  const [assets, setAssets] = useState(null);
  const [candidates, setCandidates] = useState(null);
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState(null);
  const [error, setError] = useState(null);
  const [openRules, setOpenRules] = useState(() => new Set());

  // Event-level findings (real-time risk scoring at ingestion)
  const [findings, setFindings] = useState(null);
  const [findingsSummary, setFindingsSummary] = useState(null);
  const [managedRules, setManagedRules] = useState(null);   // {rules, can_manage}
  const [ruleTemplates, setRuleTemplates] = useState([]);
  const [addingRule, setAddingRule] = useState(false);
  const [ruleError, setRuleError] = useState(null);
  const [nextCursor, setNextCursor] = useState(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [filters, setFilters] = useState({ days: 7, risk_level: "", policy_action: "", team: "", environment: "" });

  const loadFindings = useCallback(async (f = filters) => {
    const params = { days: f.days, limit: 50 };
    if (f.risk_level) params.risk_level = f.risk_level;
    if (f.policy_action) params.policy_action = f.policy_action;
    if (f.team) params.team = f.team;
    if (f.environment) params.environment = f.environment;
    const [list, summary] = await Promise.all([
      fetchRiskFindings(params).catch(() => ({ findings: [], next_cursor: null })),
      fetchRiskFindingsSummary(f.days).catch(() => null),
    ]);
    setFindings(list.findings);
    setNextCursor(list.next_cursor);
    setFindingsSummary(summary);
  }, [filters]);

  useEffect(() => { loadFindings(); }, [loadFindings]);

  const loadManagedRules = useCallback(() => {
    setRuleError(null);
    return fetchDetectionRules().then(setManagedRules).catch(() => setManagedRules({ rules: [], can_manage: false }));
  }, []);
  useEffect(() => {
    loadManagedRules();
    fetchDetectionRuleTemplates().then((d) => setRuleTemplates(d.templates || [])).catch(() => setRuleTemplates([]));
  }, [loadManagedRules]);

  const loadMoreFindings = () => {
    if (!nextCursor) return;
    setLoadingMore(true);
    const params = { days: filters.days, limit: 50, cursor: nextCursor };
    if (filters.risk_level) params.risk_level = filters.risk_level;
    if (filters.policy_action) params.policy_action = filters.policy_action;
    if (filters.team) params.team = filters.team;
    if (filters.environment) params.environment = filters.environment;
    fetchRiskFindings(params)
      .then((more) => { setFindings((cur) => [...(cur || []), ...more.findings]); setNextCursor(more.next_cursor); })
      .catch(() => {})
      .finally(() => setLoadingMore(false));
  };

  const setFilter = (key, value) => setFilters((f) => ({ ...f, [key]: value }));

  const toggleRule = (type) => setOpenRules((prev) => {
    const next = new Set(prev);
    if (next.has(type)) next.delete(type); else next.add(type);
    return next;
  });

  const load = useCallback(async () => {
    const [m, a, c] = await Promise.all([getRuleMatches(), getAssetSummary(), getControlCandidates()]);
    setMatches(m); setAssets(a); setCandidates(c);
  }, []);
  useEffect(() => { (async () => { await load(); })(); }, [load]);

  const handleRun = () => {
    setRunning(true); setRunResult(null); setError(null);
    runIntelligence()
      .then((res) => {
        setRunResult(`${res.findings_created + res.findings_updated} findings refreshed`);
        return load();
      })
      .catch((e) => setError(e.message))
      .finally(() => setRunning(false));
  };

  const nameByKey = useMemo(() => {
    const m = {};
    (assets?.data.assets || []).forEach((a) => { m[a.asset_key] = a.asset_name || a.service_name; });
    return m;
  }, [assets]);

  const candidateKeys = useMemo(
    () => new Set((candidates?.data || []).filter((c) => c.status === "open").map((c) => c.asset_key)),
    [candidates]);

  const rows = useMemo(() => [...(matches?.data || [])].sort((a, b) =>
    new Date(b.last_seen || 0) - new Date(a.last_seen || 0)
    || (SEV_RANK[b.severity] || 0) - (SEV_RANK[a.severity] || 0)), [matches]);

  const openRows = rows.filter((f) => f.status === "open" || !f.status);
  const highOpen = openRows.filter((f) => SEV_RANK[f.severity] >= 4).length;
  const agentsAffected = new Set(openRows.map((f) => f.asset_key)).size;
  const builtIn = RULE_TEMPLATES.filter((t) => t.implemented).length;
  // Implemented rules first; the planned roadmap stays visible below them.
  const orderedTemplates = [...RULE_TEMPLATES].sort((a, b) => (b.implemented ? 1 : 0) - (a.implemented ? 1 : 0));

  if (matches === null || assets === null || candidates === null) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 280, color: C.textMute, fontFamily: FONT.mono, fontSize: 13 }}>
      Loading rules &amp; alerts…
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 26, fontFamily: FONT.ui, maxWidth: 1160 }}>

      <div className="oa-rise">
        <PageHeader
          eyebrow="Observe · Detection"
          title="Rules & Alerts"
          purpose="Which rules exist, and which agents and events matched them. Real-time risk findings from ingested telemetry sit alongside batch detection rules — every finding explains why it fired and links to the agent's timeline.">
          {(matches.demo || assets.demo) && <StatusPill tone={C.textMute}>sample data</StatusPill>}
          <StatusPill tone={C.accent}>observe-only</StatusPill>
          <button onClick={handleRun} disabled={running}
            style={{ background: C.accent, color: C.accentInk, border: "none", borderRadius: RADIUS.sm,
              padding: "8px 16px", fontSize: 12, fontWeight: 700, fontFamily: FONT.ui,
              cursor: running ? "wait" : "pointer", opacity: running ? 0.6 : 1 }}>
            {running ? "Running…" : "Run rules"}
          </button>
        </PageHeader>
        <div style={{ fontSize: 11.5, fontFamily: FONT.mono, color: C.textDim, marginTop: 10 }}>
          Rules observe and alert. Gateway can optionally enforce later.
        </div>
        <div style={{ fontSize: 11.5, color: C.textMute, marginTop: 6 }}>
          Real-time risk rules score events at ingestion; batch detection rules evaluate during the
          intelligence run. Neither enforces anything.
        </div>
        {runResult && <div style={{ fontSize: 11, fontFamily: FONT.mono, color: C.accent, marginTop: 8 }}>Rules evaluated — {runResult}</div>}
        {error && <div style={{ fontSize: 11, fontFamily: FONT.mono, color: C.riskHigh, marginTop: 8 }}>{error}</div>}
      </div>

      <div className="oa-rise oa-rise-1" style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <MetricCard label="Findings" value={findingsSummary?.total_findings ?? "—"}
          sub={`risk-scored events · last ${filters.days}d`}
          tone={(findingsSummary?.total_findings || 0) > 0 ? C.text : C.ok} />
        <MetricCard label="High risk" value={findingsSummary?.high_risk_findings ?? "—"}
          tone={(findingsSummary?.high_risk_findings || 0) > 0 ? C.riskHigh : C.ok} />
        <MetricCard label="Blocked" value={findingsSummary?.blocked_events ?? "—"}
          tone={(findingsSummary?.blocked_events || 0) > 0 ? C.riskCritical : C.ok} />
        <MetricCard label="Warnings" value={findingsSummary?.warning_events ?? "—"}
          tone={(findingsSummary?.warning_events || 0) > 0 ? C.riskMedium : C.ok} />
        <MetricCard label="Open rule matches" value={openRows.length}
          sub={`${highOpen} high severity · ${agentsAffected} agents`}
          tone={openRows.length > 0 ? C.riskMedium : C.ok} />
      </div>

      <Section label={`Recent findings (${findings ? findings.length : "…"})`}
        right={
          <span style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <select value={filters.days} onChange={(e) => setFilter("days", Number(e.target.value))} style={FILTER_SELECT} aria-label="Range">
              <option value={1}>24h</option><option value={7}>7d</option><option value={30}>30d</option>
            </select>
            <select value={filters.risk_level} onChange={(e) => setFilter("risk_level", e.target.value)} style={FILTER_SELECT} aria-label="Risk level">
              <option value="">any risk</option><option value="high">high</option>
              <option value="medium">medium</option><option value="low">low</option>
            </select>
            <select value={filters.policy_action} onChange={(e) => setFilter("policy_action", e.target.value)} style={FILTER_SELECT} aria-label="Policy action">
              <option value="">any action</option><option value="block">block</option>
              <option value="warn">warn</option><option value="allow">allow</option>
            </select>
            <select value={filters.team} onChange={(e) => setFilter("team", e.target.value)} style={FILTER_SELECT} aria-label="Team">
              <option value="">all teams</option>
              {(findingsSummary?.findings_by_team || []).filter((t) => t.team !== "unassigned").map((t) => (
                <option key={t.team} value={t.team}>{t.team}</option>
              ))}
            </select>
          </span>
        }>
        <div style={{ fontSize: 11, color: C.textMute, marginBottom: 10 }}>
          Risk-scored telemetry events, evaluated in real time at ingestion. Every finding links to
          the agent's timeline for investigation.
        </div>
        {findings === null ? (
          <div style={{ color: C.textMute, fontFamily: FONT.mono, fontSize: 12, padding: "14px 4px" }}>Loading findings…</div>
        ) : findings.length === 0 ? (
          <EmptyState icon="◦"
            text={<span><strong style={{ color: C.text }}>No risk findings in this window.</strong>{" "}
              Ingest telemetry via <code style={{ fontFamily: FONT.mono }}>POST /api/v1/telemetry/batch</code> — events that
              trip a risk rule appear here with the reason they were flagged.</span>} />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {findings.map((f) => <FindingRow key={f.id} f={f} onNavigate={onNavigate} />)}
            {nextCursor && (
              <button onClick={loadMoreFindings} disabled={loadingMore}
                style={{ alignSelf: "flex-start", background: "transparent", color: C.textDim,
                  border: `1px solid ${C.border}`, padding: "6px 14px", borderRadius: RADIUS.sm,
                  fontSize: 11.5, fontFamily: FONT.mono, cursor: loadingMore ? "wait" : "pointer" }}>
                {loadingMore ? "Loading…" : "Load more"}
              </button>
            )}
          </div>
        )}
        {(findingsSummary?.most_common_reasons || []).length > 0 && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
            <span style={{ ...microLabel, fontSize: 9.5 }}>Top reasons</span>
            {findingsSummary.most_common_reasons.slice(0, 5).map((r) => (
              <span key={r.reason} style={findingChip}>{r.reason} ×{r.count}</span>
            ))}
          </div>
        )}
      </Section>

      <Section label="Real-time risk rules"
        right={
          <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <StatusPill tone={C.accent}>evaluated at ingestion</StatusPill>
            {managedRules?.can_manage && !addingRule && (
              <button onClick={() => setAddingRule(true)}
                style={{ background: C.accent, color: C.accentInk, border: "none", borderRadius: RADIUS.sm,
                  padding: "6px 14px", fontSize: 11, fontWeight: 700, fontFamily: FONT.ui, cursor: "pointer" }}>
                Add rule
              </button>
            )}
          </span>
        }>
        <div style={{ fontSize: 11, color: C.textMute, marginBottom: 10 }}>
          Rules define what the platform watches for; findings above are their real matches from agent
          runtime activity. {managedRules?.can_manage
            ? "Tune severity and thresholds to match your organization's risk tolerance — changes apply to future events only."
            : "Only admins can manage detection rules."}
        </div>
        {ruleError && <div style={{ fontSize: 11, fontFamily: FONT.mono, color: C.riskHigh, marginBottom: 8 }}>{ruleError}</div>}
        {addingRule && ruleTemplates.length > 0 && (
          <AddRuleForm templates={ruleTemplates} onSaved={loadManagedRules}
            onError={setRuleError} onClose={() => setAddingRule(false)} />
        )}
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: RADIUS.md, overflow: "hidden" }}>
          {(managedRules?.rules || []).map((r, i) => (
            <ManagedRuleRow key={r.rule_key} rule={r} templates={ruleTemplates}
              canManage={!!managedRules?.can_manage} onSaved={loadManagedRules}
              onError={setRuleError} last={i === managedRules.rules.length - 1} />
          ))}
        </div>
        <div style={{ fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute, marginTop: 8 }}>
          Template-based only — rules never run custom code. Severity maps to score weight
          (low +10 · medium +15 · high +25), additive and capped at 100; policy rules can block.
        </div>
      </Section>

      <Section label="Built-in rule templates"
        right={
          <span style={{ display: "flex", gap: 12 }}>
            <button onClick={() => setOpenRules(new Set(RULE_TEMPLATES.map((t) => t.type)))}
              style={{ background: "transparent", border: "none", color: C.textDim, fontSize: 11, fontFamily: FONT.mono, cursor: "pointer", textDecoration: "underline", padding: 0 }}>
              expand all
            </button>
            <button onClick={() => setOpenRules(new Set())}
              style={{ background: "transparent", border: "none", color: C.textDim, fontSize: 11, fontFamily: FONT.mono, cursor: "pointer", textDecoration: "underline", padding: 0 }}>
              collapse all
            </button>
          </span>
        }>
        <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: RADIUS.md,
          boxShadow: "0 1px 0 rgba(255,255,255,0.03) inset, 0 10px 30px rgba(2,4,12,0.45)", overflow: "hidden" }}>
          {orderedTemplates.map((t, i) => (
            <RuleListRow key={t.type} t={t} open={openRules.has(t.type)}
              onToggle={() => toggleRule(t.type)} last={i === orderedTemplates.length - 1} />
          ))}
        </div>
        <div style={{ fontSize: 10.5, fontFamily: FONT.mono, color: C.textMute, marginTop: 8 }}>
          Read-only defaults — configurable rules arrive with the rule builder.
        </div>
      </Section>

      <Section label={`Batch rule matches (${rows.length})`}
        right={<StatusPill tone={C.textDim}>from intelligence run</StatusPill>}>
        {rows.length === 0 ? (
          <EmptyState icon="⧉"
            text={<span><strong style={{ color: C.text }}>No rule matches yet.</strong>{" "}
              Send OpenTelemetry traces and run the rules — matches appear when agent behavior
              crosses a built-in threshold.</span>}
            actionLabel={surfaceAllowsPage("runtime") ? "Open Runtime" : undefined}
            onAction={() => onNavigate?.("runtime")} />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {rows.slice(0, 50).map((f) => (
              <MatchRow key={f.id} f={f} assetName={nameByKey[f.asset_key]}
                isCandidate={candidateKeys.has(f.asset_key)} onNavigate={onNavigate} />
            ))}
          </div>
        )}
      </Section>

      <div style={{ ...microLabel, textTransform: "none", letterSpacing: "0.04em", lineHeight: 1.6 }}>
        Observe first. Control only what matters. Rule evidence is privacy-scrubbed — identifiers
        and counts only, never prompts, responses, or tool arguments. Nothing is blocked or
        rerouted by a rule.
      </div>
    </div>
  );
}
