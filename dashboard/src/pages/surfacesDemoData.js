// Static teaching data for the "Gateway vs OTEL" demo explainer page
// (pages/SurfacesDemo.jsx). Pure constants — zero network, zero auth,
// deliberately unlike overviewApi.js: this page teaches a concept, it does
// not report live state. All names are clearly synthetic (seed-org idiom).

/**
 * @typedef {Object} FlowEvent
 * @property {string} id
 * @property {string} agent
 * @property {string} action
 * @property {"allowed"|"blocked"|"flagged"} verdict
 * @property {string} [reason]
 */

/** Gateway lane: in the request path — it can stop the two risky calls. @type {FlowEvent[]} */
export const GATEWAY_FLOW = [
  { id: "g1", agent: "sales-enrichment", action: "chat gpt-4o — summarize account history",
    verdict: "allowed" },
  { id: "g2", agent: "invoice-parser", action: "write to prod billing DB",
    verdict: "blocked", reason: "policy: prod_db_write requires enforce approval" },
  { id: "g3", agent: "support-triage", action: "chat claude-haiku — draft customer reply",
    verdict: "allowed" },
  { id: "g4", agent: "research-agent", action: "shell exec: pip install requests",
    verdict: "blocked", reason: "policy: shell execution denied for this team" },
  { id: "g5", agent: "finance-report", action: "chat claude-sonnet — 18k-token prompt",
    verdict: "flagged", reason: "budget: 92% of monthly limit" },
];

/** OTEL lane: beside the request path — same activity, nothing is stopped. @type {FlowEvent[]} */
export const OTEL_FLOW = [
  { id: "o1", agent: "sales-enrichment", action: "chat gpt-4o — summarize account history",
    verdict: "allowed" },
  { id: "o2", agent: "invoice-parser", action: "write to prod billing DB",
    verdict: "flagged", reason: "finding: database_access in production — seen, not stopped" },
  { id: "o3", agent: "support-triage", action: "chat claude-haiku — draft customer reply",
    verdict: "allowed" },
  { id: "o4", agent: "research-agent", action: "shell exec: pip install requests",
    verdict: "flagged", reason: "finding: shell_enabled — seen, not stopped" },
  { id: "o5", agent: "finance-report", action: "chat claude-sonnet — 18k-token prompt",
    verdict: "flagged", reason: "finding: high token usage — seen, not stopped" },
];

/** @type {{dim: string, gateway: string, otel: string}[]} */
export const COMPARISON = [
  { dim: "Position",          gateway: "In the request path — traffic routes through it",
                              otel: "Beside the path — reads telemetry out of band" },
  { dim: "Can it stop harm?", gateway: "Yes — when a team is explicitly set to enforce",
                              otel: "No — it detects, explains, and recommends" },
  { dim: "Latency",           gateway: "Adds a network hop to every call",
                              otel: "Zero — exporters ship spans asynchronously" },
  { dim: "Integration",       gateway: "Change base_url in your existing SDK",
                              otel: "Point any OTLP exporter at Observe" },
  { dim: "Budgets & policy",  gateway: "Budgets, allowlists, rate limits — enforced per team",
                              otel: "Advisory findings and guardrail recommendations only" },
  { dim: "Best when",         gateway: "High-stakes traffic needs a control point",
                              otel: "You want instant org-wide visibility first" },
];

export const SURFACE_STATS = {
  gateway:       { requests: "12.4k", blocked: 23, saved: "$1,240", policies: 9 },
  observability: { spans: "48.2k", systems: 14, findings: 31, coverage: "92%" },
};

/** Observability mockup — weekly spend signal. @type {{d: string, v: number}[]} */
export const SPEND_SERIES = [
  { d: "Mon", v: 14 }, { d: "Tue", v: 22 }, { d: "Wed", v: 19 },
  { d: "Thu", v: 31 }, { d: "Fri", v: 27 }, { d: "Sat", v: 9 }, { d: "Sun", v: 12 },
];

/** Observability mockup — findings by category bars. @type {{v: number}[]} */
export const FINDINGS_BARS = [{ v: 11 }, { v: 8 }, { v: 6 }, { v: 4 }, { v: 2 }];

/**
 * Verdict display label per lane. The gateway names decisions; OTEL names
 * observations (it never blocks, so "allowed" reads as LOGGED).
 * @param {"gateway"|"otel"} lane
 * @param {FlowEvent["verdict"]} verdict
 * @returns {string}
 */
export function verdictLabel(lane, verdict) {
  if (lane === "gateway") {
    return verdict === "blocked" ? "BLOCKED" : verdict === "flagged" ? "FLAGGED" : "ALLOWED";
  }
  return verdict === "allowed" ? "LOGGED" : "FLAGGED";
}
