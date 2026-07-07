// Data layer for the Overview triage page (pages/OverviewHub.jsx).
//
// One fetcher per endpoint, each wrapping the shared api.js client and
// returning { data, demo }: `demo` is true ONLY when the live call failed and
// the small built-in fixture was substituted, so the page never renders blank
// but never silently passes sample data off as live — panels show a "sample"
// pill when demo is true.

import {
  fetchSummary,
  fetchSecurityAlerts,
  fetchBudgetsStatus,
  fetchCostIntelligence,
  fetchRuntimeTraces,
  fetchIntelligenceAssetSummary,
  fetchIntelligenceFindings,
  fetchAgentsSummary,
} from "./api.js";

/**
 * @typedef {Object} TelemetrySummary
 * @property {number} total_requests
 * @property {number} total_tokens
 * @property {number} total_cost_usd
 * @property {number} avg_latency_ms
 * @property {string[]} models_used
 * @property {string[]} teams
 *
 * @typedef {Object} TrendPoint
 * @property {string} date       // "YYYY-MM-DD"
 * @property {number} cost_usd
 * @property {number} calls
 *
 * @typedef {Object} BudgetStatusItem
 * @property {number} id
 * @property {string} team
 * @property {string|null} agent
 * @property {number} limit_usd
 * @property {number} spend_usd
 * @property {number} pct
 * @property {string} period
 * @property {string} action           // "alert" | "block"
 * @property {"ok"|"warning"|"blocked"} status
 *
 * @typedef {Object} SecurityAlert
 * @property {string} type             // detection rule name
 * @property {"critical"|"warning"|"info"} sev
 * @property {string} entity
 * @property {string} msg
 * @property {string} action
 * @property {string} ts
 *
 * @typedef {Object} AssetSummaryItem
 * @property {string} asset_name
 * @property {string} asset_key
 * @property {string|null} service_name
 * @property {string[]} status         // active | runtime_observed | has_findings | error_observed | gateway_observed
 * @property {number} open_findings_count
 * @property {number} high_findings_count
 * @property {number} trace_count
 * @property {number} span_count
 *
 * @typedef {Object} Finding
 * @property {number} id
 * @property {string} category
 * @property {string} finding_type
 * @property {string} severity         // critical | high | medium | low | info
 * @property {string} title
 * @property {string} status
 * @property {string|null} asset_key
 * @property {number} occurrence_count
 * @property {string} last_seen
 *
 * @typedef {Object} TraceListItem
 * @property {string} trace_id
 * @property {string|null} root_span_name
 * @property {string|null} service_name
 * @property {string|null} session_id
 * @property {string|null} start_time
 * @property {number|null} duration_ms
 * @property {number} span_count
 * @property {number} error_count
 */

// ── Fixtures (used only when the live call fails; clearly synthetic) ─────────

const FIX_SUMMARY = {
  total_requests: 1240, total_tokens: 3_400_000, total_cost_usd: 86.4,
  avg_latency_ms: 1080, models_used: ["gpt-4o", "claude-sonnet-5"], teams: ["support", "platform"],
};

const FIX_TRENDS = Array.from({ length: 14 }, (_, i) => ({
  date: `2026-06-${String(i + 1).padStart(2, "0")}`,
  cost_usd: 4 + Math.round(Math.sin(i / 2) * 15 + 20) / 10,
  calls: 60 + i * 4,
}));

const FIX_ASSETS = [
  { asset_name: "demo-support-agent", asset_key: "demo-1", service_name: "demo-support-agent",
    status: ["active", "runtime_observed", "has_findings"], open_findings_count: 3, high_findings_count: 1,
    trace_count: 34, span_count: 122 },
  { asset_name: "demo-research-agent", asset_key: "demo-2", service_name: "demo-research-agent",
    status: ["active", "runtime_observed"], open_findings_count: 1, high_findings_count: 0,
    trace_count: 12, span_count: 48 },
];

const FIX_FINDINGS = [
  { id: -1, category: "security", finding_type: "shell_enabled", severity: "high",
    title: "Shell Command Execution Enabled", status: "open", asset_key: "demo-1",
    occurrence_count: 1, last_seen: new Date().toISOString() },
  { id: -2, category: "performance", finding_type: "slow_llm_call", severity: "medium",
    title: "Slow LLM Call Detected", status: "open", asset_key: "demo-1",
    occurrence_count: 6, last_seen: new Date().toISOString() },
];

const FIX_BUDGETS = [
  { id: -1, team: "support", agent: null, limit_usd: 50, spend_usd: 31.2, pct: 62.4,
    period: "monthly", action: "alert", status: "ok" },
  { id: -2, team: "platform", agent: null, limit_usd: 25, spend_usd: 24.1, pct: 96.4,
    period: "monthly", action: "block", status: "warning" },
];

const FIX_TRACES = [
  { trace_id: "demo-trace-1", root_span_name: "triage.ticket", service_name: "demo-support-agent",
    session_id: null, start_time: new Date().toISOString(), duration_ms: 8400, span_count: 5, error_count: 0 },
  { trace_id: "demo-trace-2", root_span_name: "research.run", service_name: "demo-research-agent",
    session_id: null, start_time: new Date().toISOString(), duration_ms: 21400, span_count: 9, error_count: 1 },
];

const FIX_ALERTS = [
  { type: "high_token_prompt", sev: "warning", entity: "demo-support-agent",
    msg: "Prompt exceeded 20k tokens", action: "Review prompt construction", ts: new Date().toISOString() },
];

async function withFallback(call, fixture) {
  try {
    const data = await call();
    return { data, demo: false };
  } catch {
    return { data: fixture, demo: true };
  }
}

// ── Fetchers — one per endpoint ───────────────────────────────────────────────

/** @returns {Promise<{data: TelemetrySummary, demo: boolean}>} */
export const getTelemetrySummary = () => withFallback(() => fetchSummary(), FIX_SUMMARY);

/** @returns {Promise<{data: {trends: TrendPoint[], runtime_cost: Object}, demo: boolean}>} */
export const getCostTrend = (days = 30) =>
  withFallback(async () => {
    const res = await fetchCostIntelligence({ days });
    return { trends: res?.trends || [], runtime_cost: res?.runtime_cost || {} };
  }, { trends: FIX_TRENDS, runtime_cost: { total_usd: 86.4 } });

/** @returns {Promise<{data: {assets: AssetSummaryItem[]}, demo: boolean}>} */
export const getAssetSummary = () =>
  withFallback(async () => {
    const res = await fetchIntelligenceAssetSummary();
    return { assets: res?.assets || [] };
  }, { assets: FIX_ASSETS });

/** @returns {Promise<{data: Finding[], demo: boolean}>} */
export const getOpenFindings = () =>
  withFallback(async () => {
    const res = await fetchIntelligenceFindings({ status: "open" });
    return Array.isArray(res) ? res : [];
  }, FIX_FINDINGS);

/** @returns {Promise<{data: BudgetStatusItem[], demo: boolean}>} */
export const getBudgetsStatus = () =>
  withFallback(async () => {
    const res = await fetchBudgetsStatus();
    return Array.isArray(res) ? res : [];
  }, FIX_BUDGETS);

/** @returns {Promise<{data: TraceListItem[], demo: boolean}>} */
export const getRecentTraces = (limit = 20) =>
  withFallback(async () => {
    const res = await fetchRuntimeTraces({ limit });
    return Array.isArray(res) ? res : [];
  }, FIX_TRACES);

/** @returns {Promise<{data: SecurityAlert[], demo: boolean}>} */
export const getSecurityAlerts = () =>
  withFallback(async () => {
    const res = await fetchSecurityAlerts();
    return Array.isArray(res) ? res : [];
  }, FIX_ALERTS);

/** @returns {Promise<{data: {managed: number}, demo: boolean}>} */
export const getAgentsSummary = () =>
  withFallback(async () => {
    const s = await fetchAgentsSummary(30);
    return { managed: s?.managed_agents ?? s?.verified_agents?.managed ?? 0 };
  }, { managed: 1 });

// ── Composite: attention strip + worst-offender hero ─────────────────────────

/**
 * One pass over findings / budgets / traces / assets for the attention strip.
 * @returns {Promise<{
 *   highOpenFindings: number, budgetsBlocked: number, budgetsWarning: number,
 *   errorTraces: number, systemsTotal: number, systemsManaged: number,
 *   worstOffender: {asset_name: string, asset_key: string, highFindings: number,
 *                   errorTraces: number, score: number} | null,
 *   demo: boolean,
 * }>}
 */
export async function getAttention() {
  const [findings, budgets, traces, assets, agents] = await Promise.all([
    getOpenFindings(), getBudgetsStatus(), getRecentTraces(100), getAssetSummary(), getAgentsSummary(),
  ]);

  const highOpenFindings = findings.data.filter(
    (f) => f.severity === "high" || f.severity === "critical"
  ).length;
  const budgetsBlocked = budgets.data.filter((b) => b.status === "blocked").length;
  const budgetsWarning = budgets.data.filter((b) => b.status === "warning").length;
  const errorTracesList = traces.data.filter((t) => (t.error_count || 0) > 0);

  // Worst offender = open high/critical findings + error traces per system.
  const errorsByService = {};
  errorTracesList.forEach((t) => {
    if (t.service_name) errorsByService[t.service_name] = (errorsByService[t.service_name] || 0) + 1;
  });
  const assetList = assets.data.assets || [];
  let worstOffender = null;
  assetList.forEach((a) => {
    const errs = errorsByService[a.service_name] || 0;
    const score = (a.high_findings_count || 0) + errs;
    if (score > 0 && (!worstOffender || score > worstOffender.score)) {
      worstOffender = {
        asset_name: a.asset_name, asset_key: a.asset_key,
        highFindings: a.high_findings_count || 0, errorTraces: errs, score,
      };
    }
  });

  // Governance: distinct observed assets whose open findings say they lack an owner.
  const agentsNeedingOwner = new Set(
    findings.data
      .filter((f) => f.finding_type === "agent_missing_owner" || f.finding_type === "unmanaged_runtime")
      .map((f) => f.asset_key)
  ).size;

  return {
    highOpenFindings,
    budgetsBlocked,
    budgetsWarning,
    errorTraces: errorTracesList.length,
    systemsTotal: assetList.length,
    systemsManaged: agents.data.managed,
    agentsNeedingOwner,
    worstOffender,
    demo: findings.demo || budgets.demo || traces.demo || assets.demo,
  };
}
