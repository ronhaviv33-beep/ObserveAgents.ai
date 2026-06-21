"""
Inspect lowercased request headers to detect agent-to-system relationships.

Returns a simple namespace with relationship fields, or None if no relationship
can be detected (missing source agent name or no target signals).

Never inspects request body — header-first approach for MVP.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_TARGET_TYPE_KEYWORDS: list[tuple[list[str], str]] = [
    (["hubspot", "salesforce", "zoho", "pipedrive", "crm"],           "crm"),
    (["sheet", "spreadsheet", "airtable", "notion"],                   "spreadsheet"),
    (["postgres", "postgresql", "mysql", "mongo", "snowflake",
      "redshift", "bigquery", "db", "database", "supabase"],           "database"),
]


def _infer_target_type(target: str) -> str:
    low = target.lower()
    for keywords, ttype in _TARGET_TYPE_KEYWORDS:
        if any(kw in low for kw in keywords):
            return ttype
    return "api"


@dataclass
class ResolvedRelationship:
    source_agent_name: str
    target_type: str
    target_name: str
    relationship_type: str
    evidence_source: str
    confidence_score: float
    metadata: dict[str, Any] = field(default_factory=dict)


def resolve_relationship(
    headers: dict[str, str],
) -> ResolvedRelationship | None:
    """
    Inspect lowercased headers and return a ResolvedRelationship, or None.

    Priority:
      1. MCP tool  (x-mcp-tool)
      2. MCP server (x-mcp-server, no x-mcp-tool)
      3. Workflow   (x-agent-workflow or x-workflow-name)
      4. Generic target (x-agent-target)
    """
    h = headers  # already lowercased by caller

    source = h.get("x-agent-name") or h.get("x-guard-agent")
    if not source:
        return None

    relation_override = h.get("x-agent-relation")
    parent_agent      = h.get("x-agent-parent")
    mcp_server        = h.get("x-mcp-server")
    mcp_tool          = h.get("x-mcp-tool")
    workflow          = h.get("x-agent-workflow") or h.get("x-workflow-name")
    workflow_provider = h.get("x-workflow-provider")
    target            = h.get("x-agent-target")

    # ── A. MCP tool ───────────────────────────────────────────────────────────
    if mcp_tool:
        meta: dict[str, Any] = {}
        if mcp_server:
            meta["mcp_server"] = mcp_server
        if parent_agent:
            meta["parent_agent"] = parent_agent
        if workflow_provider:
            meta["workflow_provider"] = workflow_provider
        if workflow:
            meta["workflow_name"] = workflow
        return ResolvedRelationship(
            source_agent_name=source,
            target_type="mcp_tool",
            target_name=mcp_tool,
            relationship_type=relation_override or "uses_tool",
            evidence_source="mcp_headers",
            confidence_score=0.85,
            metadata=meta,
        )

    # ── B. MCP server (no tool) ───────────────────────────────────────────────
    if mcp_server:
        meta = {}
        if parent_agent:
            meta["parent_agent"] = parent_agent
        return ResolvedRelationship(
            source_agent_name=source,
            target_type="mcp_server",
            target_name=mcp_server,
            relationship_type=relation_override or "calls",
            evidence_source="mcp_headers",
            confidence_score=0.80,
            metadata=meta,
        )

    # ── C. Workflow ───────────────────────────────────────────────────────────
    if workflow:
        meta = {}
        if workflow_provider:
            meta["workflow_provider"] = workflow_provider
        return ResolvedRelationship(
            source_agent_name=source,
            target_type="workflow",
            target_name=workflow,
            relationship_type=relation_override or "invokes_workflow",
            evidence_source="workflow_headers",
            confidence_score=0.80,
            metadata=meta,
        )

    # ── D. Generic target ─────────────────────────────────────────────────────
    if target:
        return ResolvedRelationship(
            source_agent_name=source,
            target_type=_infer_target_type(target),
            target_name=target,
            relationship_type=relation_override or "calls",
            evidence_source="headers",
            confidence_score=0.70,
            metadata={},
        )

    return None
