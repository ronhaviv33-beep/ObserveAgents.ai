"""Gateway Control Center — candidate derivation (GCR2).

Turns observed runtime risk into Gateway control *recommendations*:

  A Gateway Control Candidate is an observed AI asset whose runtime evidence
  indicates that it may need Gateway-level control.

Candidates are stored as AssetFindings with category="control",
finding_type="gateway_control_recommended", source="observe_to_control" —
reusing the proven dedup/occurrence/status machinery instead of a new table
(see docs/gateway_control_center_architecture.md, "Data model proposal").

Threshold (decided in the architecture doc): an asset becomes a candidate when
it has any open **high-severity** finding, or an open `human_review_recommended`
finding at **any** severity. Other medium findings alone never create
candidates — the queue stays short and the recommendation stays meaningful.

Observe-only: a candidate is a review-queue entry, never an action. Nothing
here blocks, reroutes, or configures the Gateway.

    Observe can recommend. Gateway can enforce only when explicitly configured.

Pure module: reads finding rows, returns draft dicts. The orchestrator in
app/asset_intelligence.py handles upsert plus the dismissed-candidate
semantics (dismissal is sticky for existing evidence; only a *new* trigger
finding type reopens the question).
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models import AssetFinding

CONTROL_CATEGORY = "control"
CONTROL_FINDING_TYPE = "gateway_control_recommended"
CONTROL_SOURCE = "observe_to_control"

# Trigger finding_type → suggested controls. Kinds:
#   soft    — works from OTel evidence alone (alerts, ownership, review)
#   routing — the prerequisite step: route the agent's traffic through Gateway
#   hard    — enforcement; only possible AFTER traffic is routed through Gateway
_CONTROL_MAP: dict[str, list[tuple[str, str]]] = {
    "agent_uses_unknown_model_provider": [("provider allowlist", "hard"),
                                          ("block unknown provider", "hard")],
    "unknown_model":                     [("model allowlist", "hard")],
    "agent_uses_mcp_tool_in_production": [("mcp/tool usage policy", "hard"),
                                          ("rate limit", "hard")],
    "mcp_tool_access":                   [("mcp/tool usage policy", "hard")],
    "mcp_enabled":                       [("mcp/tool usage policy", "hard")],
    "agent_has_broad_tool_surface":      [("mcp/tool usage policy", "hard"),
                                          ("human review requirement", "soft")],
    "broad_tool_access":                 [("mcp/tool usage policy", "hard")],
    "repeated_tool_errors":              [("alert-only rule", "soft")],
    "tool_error":                        [("alert-only rule", "soft")],
    "mcp_error":                         [("alert-only rule", "soft")],
    "agent_has_database_access":         [("route through gateway", "routing"),
                                          ("human review requirement", "soft")],
    "database_access":                   [("route through gateway", "routing")],
    "sensitive_system_access":           [("route through gateway", "routing"),
                                          ("human review requirement", "soft")],
    "shell_enabled":                     [("human review requirement", "soft"),
                                          ("route through gateway", "routing")],
    "agent_missing_owner":               [("owner assignment", "soft")],
    "unmanaged_runtime":                 [("owner assignment", "soft")],
    "human_review_recommended":          [("human review requirement", "soft")],
    # Detection rule findings (app/detection_rules.py, source="detection_rules")
    "rule_mcp_tool_access_threshold":    [("mcp/tool usage policy", "hard"),
                                          ("rate limit", "hard")],
    "rule_repeated_tool_errors":         [("alert-only rule", "soft")],
    "rule_unknown_provider_in_production": [("provider allowlist", "hard"),
                                            ("block unknown provider", "hard")],
}
_DEFAULT_CONTROLS: list[tuple[str, str]] = [("alert-only rule", "soft")]

_HIGH_SEVERITIES = ("high", "critical")


def derive_gateway_control_candidates(db: Session, org_id: int) -> list[dict]:
    """Derive Gateway control candidate drafts for one organization.

    Returns one draft per qualifying asset. Evidence carries identifiers and
    counts only — trigger finding ids/types/severities, environment, suggested
    controls — never raw content (the trigger rows themselves are already
    privacy-scrubbed upstream).
    """
    triggers = (
        db.query(AssetFinding)
        .filter(
            AssetFinding.organization_id == org_id,
            AssetFinding.status == "open",
            AssetFinding.category != CONTROL_CATEGORY,  # never self-trigger
        )
        .all()
    )

    by_asset: dict[str, list[AssetFinding]] = {}
    for f in triggers:
        qualifies = (
            (f.severity or "").lower() in _HIGH_SEVERITIES
            or f.finding_type == "human_review_recommended"
        )
        if qualifies:
            by_asset.setdefault(f.asset_key, []).append(f)

    drafts: list[dict] = []
    for asset_key, rows in by_asset.items():
        asset_id = next((r.asset_id for r in rows if r.asset_id is not None), None)
        types = sorted({r.finding_type for r in rows})

        # Group the trigger finding types by their producing module so the UI
        # can show "why this agent is here" split by evidence source rather than
        # one mixed list. Grouping on the stored `source` is unambiguous — e.g.
        # asset-intel's `database_access` and security-intel's
        # `agent_has_database_access` land in the right buckets.
        by_source: dict[str, set[str]] = {}
        for r in rows:
            by_source.setdefault(r.source or "otel_trace", set()).add(r.finding_type)
        trigger_findings_by_source = {src: sorted(fts) for src, fts in by_source.items()}
        severities = {(r.severity or "").lower() for r in rows}
        severity = "high" if severities & set(_HIGH_SEVERITIES) else "medium"

        environment = "unknown"
        for r in rows:
            if r.evidence_json:
                try:
                    env = (json.loads(r.evidence_json) or {}).get("environment")
                except (json.JSONDecodeError, TypeError):
                    env = None
                if env:
                    environment = str(env)
                    break

        controls: list[dict] = []
        seen: set[str] = set()
        for t in types:
            for name, kind in _CONTROL_MAP.get(t, _DEFAULT_CONTROLS):
                if name not in seen:
                    seen.add(name)
                    controls.append({"control": name, "kind": kind})

        high_count = sum(1 for r in rows if (r.severity or "").lower() in _HIGH_SEVERITIES)
        reason_bits = []
        if high_count:
            reason_bits.append(f"{high_count} open high-severity finding{'s' if high_count != 1 else ''}")
        if "human_review_recommended" in types:
            reason_bits.append("human review recommended")
        reason = (
            "Runtime evidence recommends reviewing this agent for Gateway control: "
            + " and ".join(reason_bits)
            + f" ({', '.join(types)})."
        )

        drafts.append({
            "asset_id": asset_id,
            "asset_key": asset_key,
            "severity": severity,
            "title": "Gateway Control Recommended",
            "summary": reason + " Review the evidence and suggested controls in the Gateway Control Center. "
                       "No control is applied automatically.",
            "evidence": {
                "reason": reason,
                "environment": environment,
                "trigger_count": len(rows),
                "trigger_finding_ids": sorted(r.id for r in rows),
                "trigger_finding_types": types,
                "trigger_findings_by_source": trigger_findings_by_source,
                "recommended_controls": controls,
            },
            "occurrence_count": len(rows),
        })

    return drafts
