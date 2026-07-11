"""
AI Agent Runtime Security Intelligence — MVP.

Derives AI-agent-specific security findings from evidence that already exists
in the normalized store (OtelAsset summaries, privacy-scrubbed OtelSpan
attributes, AssetRegistry ownership). This is deliberately NOT generic AppSec,
SIEM, or API security: every finding answers an agent-governance question —
what can this agent do, what can it reach, who owns it, does it need review.

Design contract:
- Pure derivation. This module returns finding *drafts*; app/asset_intelligence.py
  remains the orchestrator that upserts them (category="security",
  source="runtime_security") via its existing dedup/occurrence machinery.
  Draft-returning keeps this module import-cycle-free and unit-testable.
- Observe-only. Nothing here blocks, enforces, or changes gateway behavior.
- Privacy: consumes only scrubbed attributes (content keys are removed at
  ingestion by app/otel_privacy.py). Evidence stores identifiers and counts —
  span ids, tool/provider/model/db names, URL scheme+host+path with query
  strings and userinfo stripped, MCP method names and resource hosts. Never
  prompts, responses, tool arguments, tool results, or full URLs.

Finding catalog (see docs/ai_agent_runtime_security_intelligence.md):
  agent_has_database_access · agent_uses_unmanaged_external_api ·
  agent_uses_mcp_tool_in_production · agent_has_broad_tool_surface ·
  agent_uses_unknown_model_provider ·
  repeated_tool_errors · human_review_recommended
(production_agent_without_guardrails is documented as planned — the schema has
no per-asset guardrail marker yet, so it is not derived.)
"""
from __future__ import annotations

import json
import logging
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.models import AssetRegistry, OtelAsset, OtelSpan
from app.genai_semconv import extract_error_type, extract_tool_name, is_mcp_span

_log = logging.getLogger("ai_asset_mgmt.runtime_security")

# Known providers — mirrors the display catalog in
# app/routes/asset_intelligence.py:_PROVIDER_DISPLAY. Copied (not imported) to
# keep this module free of route imports; update both together.
KNOWN_PROVIDERS = frozenset({
    "openai", "anthropic", "google", "azure", "aws", "bedrock", "mistral",
    "cohere", "ollama", "aws.bedrock", "azure.ai.openai", "azure.ai.inference",
    "gcp.gemini", "gcp.vertex_ai", "gcp.gen_ai", "mistral_ai", "x_ai",
    "deepseek", "groq", "perplexity", "moonshot_ai", "ibm.watsonx.ai",
})

BROAD_TOOL_THRESHOLD = 5
BROAD_TOOL_HIGH_THRESHOLD = 8
REPEATED_ERROR_THRESHOLD = 3
_SAMPLE_LIMIT = 5

_DB_KEYS = ("db.system.name", "db.system")
_URL_KEYS = ("url.full", "http.url")


def _is_production(environment: str | None) -> bool:
    return (environment or "").lower() in ("production", "prod")


def _safe_url_parts(raw: str) -> tuple[str | None, str | None]:
    """Return (domain, scheme://host/path) with query, fragment, and userinfo
    stripped. Full URLs (which may carry secrets in query strings) are never
    stored in evidence."""
    try:
        parts = urlsplit(str(raw))
        host = parts.hostname
        if not host:
            return None, None
        scheme = parts.scheme or "https"
        path = parts.path or ""
        return host, f"{scheme}://{host}{path}"
    except (ValueError, TypeError):
        return None, None


def _host_only(raw: str) -> str | None:
    try:
        parts = urlsplit(str(raw))
        return parts.hostname or None
    except (ValueError, TypeError):
        return None


class _AssetAcc:
    """Per-asset accumulator over that asset's spans."""

    def __init__(self, asset_key: str, asset_id: int | None,
                 service_name: str, environment: str | None):
        self.asset_key = asset_key
        self.asset_id = asset_id
        self.service_name = service_name
        self.environment = environment or "unknown"
        self.production = _is_production(environment)
        # database
        self.db_systems: set[str] = set()
        self.db_names: set[str] = set()
        self.db_span_ids: list[str] = []
        self.db_span_count = 0
        # external API
        self.api_domains: set[str] = set()
        self.api_paths: list[str] = []
        self.api_span_ids: list[str] = []
        self.api_span_count = 0
        # MCP
        self.mcp_methods: set[str] = set()
        self.mcp_tools: set[str] = set()
        self.mcp_resource_hosts: set[str] = set()
        self.mcp_span_ids: list[str] = []
        self.mcp_span_count = 0
        # tools (spans ∪ asset summary)
        self.tool_names: set[str] = set()
        # tool errors
        self.error_tools: set[str] = set()
        self.error_types: set[str] = set()
        self.error_span_ids: list[str] = []
        self.error_count = 0
        # provider/model spans (for unknown-provider sample evidence)
        self.model_span_ids: list[str] = []

    def _sample(self, bucket: list[str], span_id: str | None):
        if span_id and len(bucket) < _SAMPLE_LIMIT:
            bucket.append(span_id)

    def feed_span(self, span_id: str | None, attrs: dict) -> None:
        # database access
        db_system = next((attrs[k] for k in _DB_KEYS if attrs.get(k)), None)
        db_name = attrs.get("db.name") or attrs.get("db.namespace")
        if db_system or db_name:
            if db_system:
                self.db_systems.add(str(db_system))
            if db_name:
                self.db_names.add(str(db_name))
            self.db_span_count += 1
            self._sample(self.db_span_ids, span_id)

        # external API reach
        url = next((attrs[k] for k in _URL_KEYS if attrs.get(k)), None)
        server = attrs.get("server.address")
        if url or server:
            domain, safe_path = (None, None)
            if url:
                domain, safe_path = _safe_url_parts(url)
            if not domain and server:
                domain = str(server)
            if domain:
                self.api_domains.add(domain)
                if safe_path and len(self.api_paths) < _SAMPLE_LIMIT and safe_path not in self.api_paths:
                    self.api_paths.append(safe_path)
                self.api_span_count += 1
                self._sample(self.api_span_ids, span_id)

        # MCP usage
        mcp_method = attrs.get("mcp.method.name")
        if mcp_method or is_mcp_span(attrs):
            if mcp_method:
                self.mcp_methods.add(str(mcp_method))
            tool = extract_tool_name(attrs)
            if tool:
                self.mcp_tools.add(str(tool))
            resource = attrs.get("mcp.resource.uri")
            if resource:
                host = _host_only(resource)
                if host:
                    self.mcp_resource_hosts.add(host)
            self.mcp_span_count += 1
            self._sample(self.mcp_span_ids, span_id)

        # tool surface
        tool_name = extract_tool_name(attrs)
        if tool_name:
            self.tool_names.add(str(tool_name))

        # repeated tool errors (tool identity + error signal on the same span)
        error_type = extract_error_type(attrs)
        if error_type and (tool_name or mcp_method or is_mcp_span(attrs)):
            self.error_types.add(str(error_type))
            if tool_name:
                self.error_tools.add(str(tool_name))
            elif mcp_method:
                self.error_tools.add(str(mcp_method))
            self.error_count += 1
            self._sample(self.error_span_ids, span_id)

        # model call sample (unknown-provider evidence)
        if attrs.get("gen_ai.request.model") or attrs.get("gen_ai.response.model"):
            self._sample(self.model_span_ids, span_id)


def _draft(acc: _AssetAcc, finding_type: str, severity: str, title: str,
           summary: str, evidence: dict, occurrence_count: int = 1) -> dict:
    evidence = {**evidence, "environment": acc.environment}
    return {
        "asset_key": acc.asset_key,
        "asset_id": acc.asset_id,
        "finding_type": finding_type,
        "severity": severity,
        "title": title,
        "summary": summary,
        "evidence": evidence,
        "occurrence_count": occurrence_count,
    }


def build_asset_accumulators(db: Session, org_id: int) -> tuple[dict[str, "_AssetAcc"], dict[str, dict]]:
    """Build per-asset evidence accumulators over the org's stored spans.

    Shared evidence layer for runtime security intelligence and the detection
    rules evaluator (app/detection_rules.py) so both read identical, already
    privacy-scrubbed evidence. Returns (accumulators by asset_key, asset meta
    by asset_key with providers/models/registry/service_name).
    """
    otel_assets = db.query(OtelAsset).filter(OtelAsset.organization_id == org_id).all()
    registry_by_id = {
        r.id: r
        for r in db.query(AssetRegistry).filter(AssetRegistry.organization_id == org_id).all()
    }

    # One accumulator per asset identity. A service can have several OtelAsset
    # rows (one per observed environment — e.g. spans arriving with and without
    # deployment.environment); they are the same agent, so merge them: any
    # production row makes the agent production, and tool/provider/model
    # evidence unions across rows. Row order must not decide the outcome.
    accs: dict[str, _AssetAcc] = {}      # asset_key → accumulator
    svc_to_acc: dict[str, _AssetAcc] = {}  # service_name → accumulator (span mapping)
    asset_meta: dict[str, dict] = {}     # asset_key → {providers, models, registry}

    for oa in otel_assets:
        reg = registry_by_id.get(oa.ai_asset_id) if oa.ai_asset_id else None
        asset_key = reg.asset_key if reg else None
        if asset_key is None:
            # Mirror the orchestrator's fallback identity for unregistered assets.
            import hashlib
            identity = oa.agent_name or oa.service_name
            asset_key = hashlib.sha256(f"{org_id}:{identity}".encode()).hexdigest()[:64]
        acc = accs.get(asset_key)
        if acc is None:
            acc = _AssetAcc(asset_key, oa.ai_asset_id, oa.service_name, oa.environment)
            accs[asset_key] = acc
        else:
            if acc.asset_id is None:
                acc.asset_id = oa.ai_asset_id
            if not acc.production and _is_production(oa.environment):
                acc.environment = oa.environment
                acc.production = True
        # Tool surface starts from the asset summary; span tools union in below.
        for name in json.loads(oa.tools_json or "[]"):
            acc.tool_names.add(str(name))
        svc_to_acc[oa.service_name] = acc
        meta = asset_meta.get(asset_key)
        if meta is None:
            meta = asset_meta[asset_key] = {
                "providers": [], "models": [], "registry": reg,
                "service_name": oa.service_name,
            }
        elif meta["registry"] is None:
            meta["registry"] = reg
        for p in json.loads(oa.providers_json or "[]"):
            if str(p) not in meta["providers"]:
                meta["providers"].append(str(p))
        for m in json.loads(oa.models_json or "[]"):
            if str(m) not in meta["models"]:
                meta["models"].append(str(m))

    spans = db.query(OtelSpan).filter(OtelSpan.organization_id == org_id).all()
    for span in spans:
        acc = svc_to_acc.get(span.service_name)
        if acc is None:
            continue
        attrs: dict = {}
        if span.attributes_json:
            try:
                attrs = json.loads(span.attributes_json)
            except (json.JSONDecodeError, TypeError):
                attrs = {}
        acc.feed_span(span.span_id, attrs)

    return accs, asset_meta


def derive_runtime_security_findings(db: Session, org_id: int) -> list[dict]:
    """Derive AI-agent runtime security finding drafts for one organization.

    Aggregates in memory first — exactly one draft per (asset, finding_type)
    per run, with span_count/sample_span_ids evidence. The orchestrator
    upserts drafts with category="security", source="runtime_security".
    """
    accs, asset_meta = build_asset_accumulators(db, org_id)

    drafts: list[dict] = []
    fired_by_asset: dict[str, set[str]] = {}

    def add(draft: dict) -> None:
        drafts.append(draft)
        fired_by_asset.setdefault(draft["asset_key"], set()).add(draft["finding_type"])

    for acc in accs.values():
        prod = acc.production
        meta = asset_meta.get(acc.asset_key, {})

        # 1. agent_has_database_access
        if acc.db_span_count > 0 or acc.db_systems or acc.db_names:
            add(_draft(
                acc, "agent_has_database_access",
                "high" if prod else "medium",
                "Agent Has Database Access",
                "This AI agent reaches a database at runtime. Review whether it "
                "should access this database and document owner and policy.",
                {"db_systems": sorted(acc.db_systems), "db_names": sorted(acc.db_names),
                 "sample_span_ids": acc.db_span_ids, "span_count": acc.db_span_count},
                occurrence_count=max(acc.db_span_count, 1),
            ))

        # 2. agent_uses_unmanaged_external_api
        # MVP note: no managed-API registry exists yet, so every observed
        # external API dependency is reported for review (documented).
        if acc.api_span_count > 0:
            add(_draft(
                acc, "agent_uses_unmanaged_external_api",
                "high" if prod else "medium",
                "Unmanaged External API Dependency",
                "This AI agent calls an external API that is not documented as a "
                "managed dependency. Review and document it.",
                {"domains": sorted(acc.api_domains), "sample_paths": acc.api_paths,
                 "sample_span_ids": acc.api_span_ids, "span_count": acc.api_span_count},
                occurrence_count=acc.api_span_count,
            ))

        # 3. agent_uses_mcp_tool_in_production (production only — name honesty;
        # non-production MCP presence is covered by the existing mcp_enabled finding)
        if prod and acc.mcp_span_count > 0:
            add(_draft(
                acc, "agent_uses_mcp_tool_in_production", "high",
                "MCP Tool Used in Production",
                "This AI agent invokes MCP tools in a production environment. "
                "Review MCP server/tool approval and create a policy profile if needed.",
                {"mcp_methods": sorted(acc.mcp_methods), "tool_names": sorted(acc.mcp_tools),
                 "resource_hosts": sorted(acc.mcp_resource_hosts),
                 "sample_span_ids": acc.mcp_span_ids, "span_count": acc.mcp_span_count},
                occurrence_count=acc.mcp_span_count,
            ))

        # 4. agent_has_broad_tool_surface
        tool_count = len(acc.tool_names)
        if tool_count >= BROAD_TOOL_THRESHOLD:
            add(_draft(
                acc, "agent_has_broad_tool_surface",
                "high" if prod and tool_count >= BROAD_TOOL_HIGH_THRESHOLD else "medium",
                "Broad Tool Surface",
                "This AI agent can use many distinct tools. Reduce tool scope or "
                "add tool-routing / human-review policy.",
                {"tool_count": tool_count, "tool_names": sorted(acc.tool_names)[:20],
                 "threshold": BROAD_TOOL_THRESHOLD},
            ))

        # 5. agent_uses_unknown_model_provider
        providers = meta.get("providers", [])
        models = meta.get("models", [])
        unknown = [p for p in providers if p.lower() not in KNOWN_PROVIDERS]
        if unknown or (models and not providers):
            add(_draft(
                acc, "agent_uses_unknown_model_provider",
                "high" if prod else "low",
                "Unknown Model Provider",
                "This AI agent uses a model provider that is missing or not in the "
                "known provider catalog. Confirm provider/model ownership and approval.",
                {"providers": sorted(unknown) if unknown else [],
                 "models": sorted(models)[:10],
                 "sample_span_ids": acc.model_span_ids},
            ))

        # 6. (removed) agent_missing_owner — ownership is optional metadata; the
        #    platform no longer flags a missing owner as a finding.

        # 8. repeated_tool_errors
        if acc.error_count >= REPEATED_ERROR_THRESHOLD:
            add(_draft(
                acc, "repeated_tool_errors",
                "high" if prod else "medium",
                "Repeated Tool Errors",
                "Tool or MCP calls for this AI agent keep failing. Add fallback, "
                "retry, or human-review behavior for this tool.",
                {"tool_names": sorted(acc.error_tools), "error_types": sorted(acc.error_types),
                 "error_count": acc.error_count, "sample_span_ids": acc.error_span_ids},
                occurrence_count=acc.error_count,
            ))

    # 9. human_review_recommended — post-pass over what fired per asset.
    for acc in accs.values():
        fired = fired_by_asset.get(acc.asset_key, set())
        reasons: list[str] = []
        if acc.production:
            if "agent_uses_mcp_tool_in_production" in fired:
                reasons.append("production agent invokes MCP tools")
            if "agent_has_broad_tool_surface" in fired:
                reasons.append("production agent has a broad tool surface")
            if "agent_has_database_access" in fired:
                reasons.append("production agent has database access")
            if "agent_uses_unknown_model_provider" in fired:
                reasons.append("production agent uses an unknown model provider")
        if "repeated_tool_errors" in fired and (
            "agent_has_database_access" in fired or "agent_uses_unmanaged_external_api" in fired
        ):
            reasons.append("repeated tool errors on a high-risk dependency")
        if reasons:
            related = sorted(fired)
            add(_draft(
                acc, "human_review_recommended",
                "high" if len(reasons) >= 2 else "medium",
                "Human Review Recommended",
                "High-risk combination observed at runtime. Require human review "
                "before high-risk actions until behavior is validated.",
                {"reasons": reasons, "related_finding_types": related},
            ))

    return drafts
