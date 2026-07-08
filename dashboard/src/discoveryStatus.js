// Shared customer-facing Discovery Status model (Pass 1).
// Replaces raw confidence percentages with an explainable 7-state lifecycle.
// Self-contained (hex palette matches the per-page T tokens) so any page can import it.

const MONO = "'JetBrains Mono','IBM Plex Mono',monospace";

// Stage → display metadata. Colors chosen from the existing palette.
export const STAGE_META = {
  DISCOVERED:   { label: "Discovered",   color: "#CBD5E1", description: "Observed through gateway traffic." },
  ATTRIBUTED:   { label: "Attributed",   color: "#60A5FA", description: "Associated with a team, owner, or key from traffic." },
  CLAIMED:      { label: "Claimed",      color: "#2DD4BF", description: "Ownership approved by a user." },
  MANAGED:      { label: "Managed",      color: "#4ADE80", description: "Owned and configured under governance." },
  NEEDS_REVIEW: { label: "Needs review", color: "#FBBF24", description: "Partial or conflicting identity evidence." },
  STALE:        { label: "Stale",        color: "#94A3B8", description: "No recent activity." },
  ARCHIVED:     { label: "Archived",     color: "#64748B", description: "Removed from active inventory." },
};

const _STALE_DAYS = 30;

// Client-side mirror of the backend deriver — used only as a fallback when the
// backend has not yet populated `discovery_stage` (graceful during rollout).
// Precedence: ARCHIVED > MANAGED > CLAIMED > NEEDS_REVIEW > STALE > ATTRIBUTED > DISCOVERED.
export function deriveStageFallback(agent = {}) {
  const lifecycle = agent.lifecycle_status || "unassigned";
  if (lifecycle === "retired") return "ARCHIVED";

  const owner = agent.owner;
  const hasOwner = !!(owner && owner !== "Unassigned");
  const hasConfig = !!(agent.environment && agent.environment !== "Unknown") || !!agent.criticality || !!agent.business_purpose;
  if (lifecycle === "managed" && hasOwner && hasConfig) return "MANAGED";
  if (agent.claimed_by || lifecycle === "managed") return "CLAIMED";

  const evidence = typeof agent.evidence === "object" && agent.evidence ? agent.evidence : {};
  const needsReview = agent.discovery_status === "potential" || !!evidence.needs_admin_review;
  if (needsReview) return "NEEDS_REVIEW";

  const lastSeen = agent.last_seen || agent.last_seen_at;
  if (lastSeen) {
    const days = (Date.now() - new Date(lastSeen).getTime()) / 86400000;
    if (days > _STALE_DAYS) return "STALE";
  }

  const team = agent.team;
  const strong = (Number(agent.confidence_score) || 0) >= 75
    || (team && team !== "Unknown") || hasOwner;
  if (strong) return "ATTRIBUTED";

  return "DISCOVERED";
}

// Resolve the stage to display: prefer the backend-provided value, fall back to client derivation.
export function stageOf(agent = {}) {
  return agent.discovery_stage || deriveStageFallback(agent);
}

export function stageMeta(agent = {}) {
  const stage = stageOf(agent);
  return STAGE_META[stage] || { label: stage || "—", color: "#CBD5E1", description: "" };
}

// Qualitative label for a runtime relationship — replaces the relationship
// confidence percentage in the dependency map. Underlying score kept internally for sorting.
export function relationshipEvidenceLabel(rel = {}) {
  const score = Number(rel.confidence_score) || 0;
  let label, color;
  if (score >= 0.85)      { label = "Strong";   color = "#4ADE80"; }
  else if (score >= 0.70) { label = "Likely";   color = "#2DD4BF"; }
  else if (score >= 0.40) { label = "Observed"; color = "#60A5FA"; }
  else                    { label = "Partial";  color = "#FBBF24"; }

  const why = [];
  const n = rel.request_count;
  if (n) why.push(`seen in ${n.toLocaleString?.() || n} request${n === 1 ? "" : "s"}`);
  const src = rel.evidence_source;
  if (src === "mcp_headers" || src === "headers") why.push("declared via headers");
  else if (src === "sdk") why.push("reported by SDK");
  else if (src === "gateway") why.push("observed at gateway");
  else if (src === "workflow_headers") why.push("workflow invocation");

  return { label, color, why: why.join(" · ") };
}

export { MONO as _MONO };
