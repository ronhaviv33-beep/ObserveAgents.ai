"""
AI Agent Detection Rules — built-in batch evaluator (R1).

First slice of docs/ai_agent_detection_rules_alerts_design.md: three built-in
rules evaluated over evidence that already exists in the normalized store.
Detection Rules are an intelligence layer — not ingestion, not enforcement:

    Rules observe and alert. Gateway can optionally enforce later.

Design contract:
- Pure derivation. Returns finding *drafts*; app/asset_intelligence.py remains
  the orchestrator that upserts them (source="detection_rules") via its
  existing dedup/occurrence machinery — exactly one row per
  (org, asset, category, finding_type, source), idempotent across runs.
- Batch only. Runs as part of the intelligence run, after the runtime security
  pass and before control-candidate derivation. NEVER called from the OTLP
  ingestion request path (/otel/v1/traces stays accept-and-store only).
- Window = the current intelligence-run evidence scope. Per-bucket time
  windows arrive with the agent_rule_matches table in a later phase (R2).
- Observe-only. Nothing here blocks, reroutes, or changes gateway config.
- Privacy: reads only scrubbed evidence via the shared accumulator from
  app/runtime_security_intelligence.py. Evidence stores identifiers and
  counts — span ids, tool/MCP/provider/model names, error types, environment.
  Never prompts, responses, tool arguments, tool results, or full URLs.

R1 rule catalog:
  rule_mcp_tool_access_threshold · rule_repeated_tool_errors ·
  rule_unknown_provider_in_production
The rule_ prefix keeps these distinct from the runtime_security finding types
that observe related facts without thresholds/configurability.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.runtime_security_intelligence import (
    KNOWN_PROVIDERS,
    REPEATED_ERROR_THRESHOLD,
    _AssetAcc,
    build_asset_accumulators,
)

_log = logging.getLogger("ai_asset_mgmt.detection_rules")

DETECTION_RULES_SOURCE = "detection_rules"

# Built-in defaults (configurable rules arrive in R7).
MCP_CALL_THRESHOLD = 5        # rule fires strictly above this
MCP_HIGH_COUNT = 15           # high severity even outside production


def _draft(acc: _AssetAcc, category: str, finding_type: str, severity: str,
           title: str, summary: str, evidence: dict,
           occurrence_count: int = 1) -> dict:
    return {
        "asset_key": acc.asset_key,
        "asset_id": acc.asset_id,
        "category": category,
        "finding_type": finding_type,
        "severity": severity,
        "title": title,
        "summary": summary,
        "evidence": {**evidence, "environment": acc.environment},
        "occurrence_count": occurrence_count,
    }


def derive_detection_rule_findings(db: Session, org_id: int) -> list[dict]:
    """Evaluate the built-in detection rules for one organization.

    Aggregates in memory first — exactly one draft per (asset, rule) per run.
    The orchestrator upserts drafts with source="detection_rules".
    """
    accs, asset_meta = build_asset_accumulators(db, org_id)

    drafts: list[dict] = []
    for acc in accs.values():
        prod = acc.production
        meta = asset_meta.get(acc.asset_key, {})

        # 1. rule_mcp_tool_access_threshold — MCP/tool calls above threshold.
        if acc.mcp_span_count > MCP_CALL_THRESHOLD:
            high = prod or acc.mcp_span_count >= MCP_HIGH_COUNT
            drafts.append(_draft(
                acc, "security", "rule_mcp_tool_access_threshold",
                "high" if high else "medium",
                "MCP Tool Access Above Threshold",
                f"{acc.service_name} called MCP tools {acc.mcp_span_count} times "
                f"in the current evidence window (threshold: {MCP_CALL_THRESHOLD}). "
                "Review whether this agent should have this MCP/tool access level.",
                {"rule_type": "mcp_tool_access_threshold",
                 "threshold": MCP_CALL_THRESHOLD,
                 "span_count": acc.mcp_span_count,
                 "mcp_methods": sorted(acc.mcp_methods),
                 "tool_names": sorted(acc.mcp_tools),
                 "sample_span_ids": acc.mcp_span_ids},
                occurrence_count=acc.mcp_span_count,
            ))

        # 2. rule_repeated_tool_errors — same agent keeps failing tool/MCP calls.
        if acc.error_count >= REPEATED_ERROR_THRESHOLD:
            drafts.append(_draft(
                acc, "operations", "rule_repeated_tool_errors",
                "high" if prod else "medium",
                "Repeated Tool Errors (Detection Rule)",
                f"{acc.service_name} recorded {acc.error_count} tool/MCP errors "
                f"in the current evidence window (threshold: {REPEATED_ERROR_THRESHOLD}). "
                "Check dependency health, add fallback behavior, or route to human review.",
                {"rule_type": "repeated_tool_errors",
                 "threshold": REPEATED_ERROR_THRESHOLD,
                 "error_count": acc.error_count,
                 "tool_names": sorted(acc.error_tools),
                 "mcp_methods": sorted(acc.mcp_methods),
                 "error_types": sorted(acc.error_types),
                 "sample_span_ids": acc.error_span_ids},
                occurrence_count=acc.error_count,
            ))

        # 3. rule_unknown_provider_in_production — production-only by design.
        if prod:
            providers = meta.get("providers", [])
            models = meta.get("models", [])
            unknown = sorted(p for p in providers if p.lower() not in KNOWN_PROVIDERS)
            if unknown or (models and not providers):
                drafts.append(_draft(
                    acc, "security", "rule_unknown_provider_in_production", "high",
                    "Unknown Provider in Production",
                    f"{acc.service_name} uses an unknown or unapproved model "
                    "provider in production. Confirm provider approval and ownership.",
                    {"rule_type": "unknown_provider_in_production",
                     "providers": unknown,
                     "models": sorted(models)[:10],
                     "sample_span_ids": acc.model_span_ids},
                ))

    return drafts
