"""
Asset Intelligence: derives AssetCapability and AssetFinding rows from OTel evidence.

Reads from: otel_assets, otel_spans, asset_registry
Writes to:  asset_capabilities, asset_findings
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.models import AssetCapability, AssetFinding, AssetRegistry, OtelAsset, OtelSpan
from app.genai_semconv import (
    extract_error_type,
    extract_genai_scalar_fields,
    extract_tool_name,
    is_mcp_span,
)
from app.detection_rules import DETECTION_RULES_SOURCE, derive_detection_rule_findings
from app.notifications import deliver_detection_rule_notifications
from app.runtime_security_intelligence import derive_runtime_security_findings
from app.gateway_control import (
    CONTROL_CATEGORY, CONTROL_FINDING_TYPE, CONTROL_SOURCE,
    derive_gateway_control_candidates,
)

_log = logging.getLogger("ai_asset_mgmt.intelligence")

# A single LLM call at or above this many input+output tokens is flagged.
HIGH_TOKEN_USAGE_THRESHOLD = 100_000


def _make_asset_key(org_id: int, name: str) -> str:
    return hashlib.sha256(f"{org_id}:{name}".encode()).hexdigest()[:64]


def _classify_capability(name: str) -> str:
    n = name.lower()
    if "mcp" in n:
        return "mcp"
    if any(x in n for x in ("postgres", "mysql", "mongo", "redis", "snowflake", "bigquery", "sqlite", "db", "database", "sql")):
        return "database"
    if any(x in n for x in ("file", "filesystem", "fs", "s3", "bucket", "storage", "blob")):
        return "filesystem"
    if any(x in n for x in ("shell", "bash", "terminal", "cmd", "powershell", "exec", "subprocess")):
        return "shell"
    if any(x in n for x in ("slack", "teams", "discord", "email", "smtp")):
        return "messaging"
    if any(x in n for x in ("github", "gitlab", "bitbucket", "git")):
        return "source_control"
    if any(x in n for x in ("salesforce", "hubspot", "zendesk", "crm")):
        return "crm"
    if any(x in n for x in ("retrieve", "retrieval", "vector", "search", "embed")):
        return "retrieval"
    if any(x in n for x in ("memory", "cache")):
        return "memory"
    if any(x in n for x in ("http", "url", "api", "external")):
        return "external_api"
    return "unknown"


def _sanitize_uri(uri: str) -> str:
    """Keep scheme://host/path only — query strings, fragments, and userinfo
    can carry credentials or secrets and must never be persisted."""
    try:
        parts = urlsplit(uri)
    except ValueError:
        return uri.split("?", 1)[0].split("#", 1)[0][:255]
    if not parts.scheme:
        return uri.split("?", 1)[0].split("#", 1)[0][:255]
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return f"{parts.scheme}://{host}{parts.path}"[:255]


def _upsert_capability(
    db: Session,
    org_id: int,
    asset_id: int | None,
    asset_key: str,
    cap_type: str,
    cap_name: str,
    source: str,
    now: datetime,
    evidence: dict | None = None,
) -> tuple[bool, bool]:
    row = (
        db.query(AssetCapability)
        .filter(
            AssetCapability.organization_id == org_id,
            AssetCapability.asset_key == asset_key,
            AssetCapability.capability_type == cap_type,
            AssetCapability.capability_name == cap_name,
            AssetCapability.source == source,
        )
        .first()
    )
    if row is None:
        row = AssetCapability(
            organization_id=org_id,
            asset_id=asset_id,
            asset_key=asset_key,
            capability_type=cap_type,
            capability_name=cap_name,
            source=source,
            evidence_json=json.dumps(evidence) if evidence else None,
            first_seen=now,
            last_seen=now,
        )
        db.add(row)
        # Session runs with autoflush=False: flush so the next dedup query
        # in the same run can see this row.
        db.flush()
        return (True, False)
    row.last_seen = now
    row.updated_at = now
    if evidence:
        # Merge new evidence keys into the existing row — e.g. gen_ai.tool.type
        # arriving for a tool capability first created from the OtelAsset
        # aggregate (which carries no evidence).
        existing_ev: dict = {}
        if row.evidence_json:
            try:
                existing_ev = json.loads(row.evidence_json) or {}
            except (json.JSONDecodeError, TypeError):
                existing_ev = {}
        merged = {**existing_ev, **{k: v for k, v in evidence.items() if v is not None}}
        if merged != existing_ev:
            row.evidence_json = json.dumps(merged)
    return (False, True)


def _is_model_variant(a: str, b: str) -> bool:
    """True when one model name is a dated/versioned snapshot of the other
    (gpt-4o → gpt-4o-2024-08-06), as opposed to a genuinely different model
    (gpt-4o → gpt-4o-mini)."""
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if not longer.startswith(shorter):
        return False
    suffix = longer[len(shorter):].lstrip("-_.@:")
    return bool(suffix) and all(ch.isdigit() or ch in "-_." for ch in suffix)


def _upsert_finding(
    db: Session,
    org_id: int,
    asset_id: int | None,
    asset_key: str,
    category: str,
    finding_type: str,
    severity: str,
    title: str,
    summary: str,
    source: str,
    now: datetime,
    evidence: dict | None = None,
    occurrence_count: int = 1,
    replace_evidence: bool = False,
) -> tuple[bool, bool]:
    row = (
        db.query(AssetFinding)
        .filter(
            AssetFinding.organization_id == org_id,
            AssetFinding.asset_key == asset_key,
            AssetFinding.category == category,
            AssetFinding.finding_type == finding_type,
            AssetFinding.source == source,
        )
        .first()
    )
    if row is None:
        row = AssetFinding(
            organization_id=org_id,
            asset_id=asset_id,
            asset_key=asset_key,
            category=category,
            finding_type=finding_type,
            severity=severity,
            title=title,
            summary=summary,
            evidence_json=json.dumps(evidence) if evidence else None,
            source=source,
            status="open",
            occurrence_count=occurrence_count,
            first_seen=now,
            last_seen=now,
        )
        db.add(row)
        # Session runs with autoflush=False: flush so the next dedup query
        # in the same run can see this row.
        db.flush()
        return (True, False)
    row.last_seen = now
    row.updated_at = now
    row.occurrence_count = occurrence_count
    if evidence:
        if replace_evidence:
            # Aggregated findings recompute their evidence from all spans on
            # every run — the fresh aggregate is the truth, not a delta.
            row.evidence_json = json.dumps(evidence)
            return (False, True)
        existing: dict = {}
        if row.evidence_json:
            try:
                existing = json.loads(row.evidence_json)
            except (json.JSONDecodeError, TypeError):
                existing = {}
        if isinstance(existing, dict):
            existing.update(evidence)
            row.evidence_json = json.dumps(existing)
        else:
            row.evidence_json = json.dumps(evidence)
    return (False, True)


def _merge_duplicate_rows(db: Session, org_id: int) -> None:
    """
    Collapse duplicate finding/capability rows created before in-run dedup was
    enforced (the session runs with autoflush=False, so pending inserts were
    invisible to the dedup query within a single derive run). Keeps the oldest
    row per dedup key, widens its first_seen/last_seen window, prefers "open"
    status, and folds the duplicate count into occurrence_count.
    """
    find_groups: dict[tuple, list[AssetFinding]] = {}
    for row in db.query(AssetFinding).filter(AssetFinding.organization_id == org_id).all():
        find_groups.setdefault(
            (row.asset_key, row.category, row.finding_type, row.source), []
        ).append(row)
    for rows in find_groups.values():
        if len(rows) < 2:
            continue
        rows.sort(key=lambda r: r.id)
        keep = rows[0]
        keep.first_seen = min(r.first_seen for r in rows)
        keep.last_seen = max(r.last_seen for r in rows)
        if any(r.status == "open" for r in rows):
            keep.status = "open"
        keep.occurrence_count = max(keep.occurrence_count or 1, len(rows))
        for extra in rows[1:]:
            db.delete(extra)

    cap_groups: dict[tuple, list[AssetCapability]] = {}
    for row in db.query(AssetCapability).filter(AssetCapability.organization_id == org_id).all():
        cap_groups.setdefault(
            (row.asset_key, row.capability_type, row.capability_name, row.source), []
        ).append(row)
    for rows in cap_groups.values():
        if len(rows) < 2:
            continue
        rows.sort(key=lambda r: r.id)
        keep = rows[0]
        keep.first_seen = min(r.first_seen for r in rows)
        keep.last_seen = max(r.last_seen for r in rows)
        for extra in rows[1:]:
            db.delete(extra)

    db.flush()


def derive_asset_intelligence(db: Session, org_id: int) -> dict:
    caps_created = caps_updated = finds_created = finds_updated = 0

    _merge_duplicate_rows(db, org_id)

    otel_assets = db.query(OtelAsset).filter(OtelAsset.organization_id == org_id).all()
    registry_by_id = {
        r.id: r
        for r in db.query(AssetRegistry).filter(AssetRegistry.organization_id == org_id).all()
    }

    svc_to_key: dict[str, str] = {}
    svc_to_asset_id: dict[str, int | None] = {}
    svc_to_env: dict[str, str | None] = {}

    for oa in otel_assets:
        reg = registry_by_id.get(oa.ai_asset_id) if oa.ai_asset_id else None
        identity_name = oa.agent_name or oa.service_name
        asset_key = reg.asset_key if reg else _make_asset_key(org_id, identity_name)
        asset_id: int | None = oa.ai_asset_id
        now = datetime.now(timezone.utc)

        svc_to_key[oa.service_name] = asset_key
        svc_to_asset_id[oa.service_name] = asset_id
        svc_to_env[oa.service_name] = oa.environment

        for name in json.loads(oa.providers_json or "[]"):
            c, u = _upsert_capability(db, org_id, asset_id, asset_key, "provider", name, "otel_trace", now)
            caps_created += c
            caps_updated += u

        for name in json.loads(oa.models_json or "[]"):
            c, u = _upsert_capability(db, org_id, asset_id, asset_key, "model", name, "otel_trace", now)
            caps_created += c
            caps_updated += u

        for name in json.loads(oa.tools_json or "[]"):
            cap_type = _classify_capability(name)
            c, u = _upsert_capability(db, org_id, asset_id, asset_key, cap_type, name, "otel_trace", now)
            caps_created += c
            caps_updated += u

        for name in json.loads(oa.dependencies_json or "[]"):
            cap_type = _classify_capability(name)
            c, u = _upsert_capability(db, org_id, asset_id, asset_key, cap_type, name, "otel_trace", now)
            caps_created += c
            caps_updated += u

        if oa.environment and oa.environment.lower() in ("production", "prod"):
            c, u = _upsert_capability(db, org_id, asset_id, asset_key, "runtime", "production", "otel_trace", now)
            caps_created += c
            caps_updated += u

        db.flush()

        cap_rows = (
            db.query(AssetCapability)
            .filter(
                AssetCapability.organization_id == org_id,
                AssetCapability.asset_key == asset_key,
            )
            .all()
        )
        cap_types = {c.capability_type for c in cap_rows}
        tool_names = {c.capability_name for c in cap_rows if c.capability_type not in ("provider", "model", "runtime")}
        runtime_names = {c.capability_name for c in cap_rows if c.capability_type == "runtime"}

        # security
        if "shell" in cap_types:
            c, u = _upsert_finding(
                db, org_id, asset_id, asset_key, "security", "shell_enabled", "high",
                "Shell Command Execution Enabled",
                "This AI system has demonstrated shell/terminal command execution capability, enabling arbitrary code execution.",
                "otel_trace", now,
            )
            finds_created += c
            finds_updated += u

        if "database" in cap_types:
            c, u = _upsert_finding(
                db, org_id, asset_id, asset_key, "security", "database_access", "medium",
                "Database Access Detected",
                "This AI system has direct database read/write capability.",
                "otel_trace", now,
            )
            finds_created += c
            finds_updated += u

        if "filesystem" in cap_types:
            c, u = _upsert_finding(
                db, org_id, asset_id, asset_key, "security", "filesystem_enabled", "medium",
                "Filesystem Access Enabled",
                "This AI system has filesystem read/write capability.",
                "otel_trace", now,
            )
            finds_created += c
            finds_updated += u

        if "mcp" in cap_types:
            c, u = _upsert_finding(
                db, org_id, asset_id, asset_key, "security", "mcp_enabled", "medium",
                "MCP Server Access Enabled",
                "This AI system connects to one or more MCP servers, extending its tool surface.",
                "otel_trace", now,
            )
            finds_created += c
            finds_updated += u

        if "provider" in cap_types and cap_types & {"crm", "source_control", "database", "messaging"}:
            c, u = _upsert_finding(
                db, org_id, asset_id, asset_key, "security", "sensitive_system_access", "high",
                "Sensitive System Access",
                "This AI system has access to sensitive systems (CRM, source control, database, or messaging) alongside external provider access.",
                "otel_trace", now,
            )
            finds_created += c
            finds_updated += u

        # dependency
        if len(tool_names) >= 5:
            c, u = _upsert_finding(
                db, org_id, asset_id, asset_key, "dependency", "broad_tool_access", "medium",
                "Broad Tool Access",
                "This AI system has access to 5 or more distinct tools or dependencies.",
                "otel_trace", now,
            )
            finds_created += c
            finds_updated += u

        if "external_api" in cap_types:
            c, u = _upsert_finding(
                db, org_id, asset_id, asset_key, "dependency", "external_api_access", "low",
                "External API Access Detected",
                "This AI system makes calls to external APIs.",
                "otel_trace", now,
            )
            finds_created += c
            finds_updated += u

        # operations
        if "production" in runtime_names:
            c, u = _upsert_finding(
                db, org_id, asset_id, asset_key, "operations", "production_runtime", "info",
                "Running in Production",
                "This AI system has been observed running in a production environment.",
                "otel_trace", now,
            )
            finds_created += c
            finds_updated += u

        if reg and reg.owner is None and reg.claimed_by is None:
            c, u = _upsert_finding(
                db, org_id, asset_id, asset_key, "operations", "unmanaged_runtime", "medium",
                "Unmanaged AI System",
                "This AI system has no assigned owner and has not been claimed in the asset registry.",
                "otel_trace", now,
            )
            finds_created += c
            finds_updated += u

        # inventory
        if reg and reg.discovery_status == "potential":
            c, u = _upsert_finding(
                db, org_id, asset_id, asset_key, "inventory", "new_ai_system_detected", "info",
                "New AI System Detected",
                "A new AI system has been discovered via OTel telemetry and is pending review.",
                "otel_trace", now,
            )
            finds_created += c
            finds_updated += u

        if not json.loads(oa.models_json or "[]"):
            c, u = _upsert_finding(
                db, org_id, asset_id, asset_key, "inventory", "unknown_model", "low",
                "Model Identity Unknown",
                "This AI system did not report which AI model it uses.",
                "otel_trace", now,
            )
            finds_created += c
            finds_updated += u

    # span-based performance and operations findings — accumulated in memory
    # first so each dedup key becomes exactly one row per run, carrying an
    # occurrence_count instead of one row per matching span.
    finding_acc: dict[tuple[str, str, str], dict] = {}
    mcp_cap_acc: dict[tuple[str, str], dict] = {}
    # Span-derived GenAI/MCP capabilities, keyed (asset_key, cap_type, cap_name).
    genai_cap_acc: dict[tuple[str, str, str], dict] = {}

    def _acc_find(
        asset_key: str,
        asset_id: int | None,
        category: str,
        finding_type: str,
        severity: str,
        title: str,
        summary: str,
        span_id: str | None,
        duration_ms: float | None = None,
        error_type: str | None = None,
        mcp_method: str | None = None,
        detail: str | None = None,
        token_count: int | None = None,
        reasoning_tokens: int | None = None,
    ) -> None:
        key = (asset_key, category, finding_type)
        agg = finding_acc.get(key)
        if agg is None:
            agg = finding_acc[key] = {
                "asset_id": asset_id, "severity": severity,
                "title": title, "summary": summary,
                "count": 0, "span_ids": [],
                "max_duration_ms": None,
                "error_types": set(), "mcp_methods": set(),
                "details": set(),
                "max_total_tokens": None, "max_reasoning_tokens": None,
            }
        agg["count"] += 1
        if span_id and len(agg["span_ids"]) < 5:
            agg["span_ids"].append(span_id)
        if duration_ms is not None:
            agg["max_duration_ms"] = max(agg["max_duration_ms"] or 0, duration_ms)
        if error_type:
            agg["error_types"].add(str(error_type))
        if mcp_method:
            agg["mcp_methods"].add(str(mcp_method))
        if detail and len(agg["details"]) < 10:
            agg["details"].add(str(detail))
        if token_count is not None:
            agg["max_total_tokens"] = max(agg["max_total_tokens"] or 0, token_count)
        if reasoning_tokens is not None:
            agg["max_reasoning_tokens"] = max(agg["max_reasoning_tokens"] or 0, reasoning_tokens)

    def _acc_cap(
        asset_key: str,
        asset_id: int | None,
        cap_type: str,
        name: object,
        evidence: dict | None = None,
    ) -> None:
        if not name:
            return
        key = (asset_key, cap_type, str(name)[:255])
        entry = genai_cap_acc.setdefault(key, {"asset_id": asset_id, "evidence": {}})
        if evidence:
            entry["evidence"].update({k: v for k, v in evidence.items() if v is not None})

    spans = db.query(OtelSpan).filter(OtelSpan.organization_id == org_id).all()
    for span in spans:
        asset_key = svc_to_key.get(span.service_name)
        if not asset_key:
            continue
        asset_id = svc_to_asset_id.get(span.service_name)

        attrs: dict = {}
        if span.attributes_json:
            try:
                attrs = json.loads(span.attributes_json)
            except (json.JSONDecodeError, TypeError):
                attrs = {}

        dur = span.duration_ms
        if dur and dur >= 5000:
            is_llm = any(k.startswith("gen_ai.") for k in attrs)
            is_tool = any(k.startswith("tool.") for k in attrs)
            if is_llm and dur >= 10000:
                _acc_find(asset_key, asset_id, "performance", "slow_llm_call", "medium",
                          "Slow LLM Call Detected",
                          "An LLM call for this service exceeded 10,000 ms.",
                          span.span_id, duration_ms=dur)
            elif is_tool:
                _acc_find(asset_key, asset_id, "performance", "slow_tool_call", "medium",
                          "Slow Tool Call Detected",
                          "A tool call for this service exceeded 5,000 ms.",
                          span.span_id, duration_ms=dur)
            else:
                _acc_find(asset_key, asset_id, "performance", "slow_runtime_step", "medium",
                          "Slow Runtime Step Detected",
                          "A workflow step for this service exceeded 5,000 ms.",
                          span.span_id, duration_ms=dur)

        # MCP telemetry (mcp.method.name is the SemConv marker for MCP spans)
        mcp_method = attrs.get("mcp.method.name")
        if mcp_method:
            cap_name = extract_tool_name(attrs) or str(mcp_method)
            cap_key = (asset_key, cap_name)
            if cap_key not in mcp_cap_acc:
                mcp_cap_acc[cap_key] = {
                    "asset_id": asset_id,
                    "evidence": {"mcp.method.name": mcp_method,
                                 "mcp.protocol.version": attrs.get("mcp.protocol.version")},
                }
            env = (svc_to_env.get(span.service_name) or "").lower()
            if env in ("production", "prod"):
                _acc_find(asset_key, asset_id, "security", "mcp_tool_access", "medium",
                          "MCP Tool Access in Production",
                          "This AI system invokes MCP tools in a production environment.",
                          span.span_id, mcp_method=str(mcp_method))

        # GenAI SemConv capabilities — safe scalar metadata only, never content.
        genai = extract_genai_scalar_fields(attrs)
        _acc_cap(asset_key, asset_id, "data_source", attrs.get("gen_ai.data_source.id"))
        _acc_cap(asset_key, asset_id, "workflow", attrs.get("gen_ai.workflow.name"))
        _acc_cap(asset_key, asset_id, "prompt", attrs.get("gen_ai.prompt.name"),
                 {"gen_ai.prompt.version": attrs.get("gen_ai.prompt.version")})
        resource_uri = attrs.get("mcp.resource.uri")
        if resource_uri:
            _acc_cap(asset_key, asset_id, "mcp_resource", _sanitize_uri(str(resource_uri)),
                     {"mcp.method.name": mcp_method})
        tool_type = attrs.get("gen_ai.tool.type")
        tool_name = extract_tool_name(attrs)
        if tool_type and tool_name:
            # Same (type, name) key as the OtelAsset tools_json path → refreshes
            # the same capability row instead of creating a duplicate.
            _acc_cap(asset_key, asset_id, _classify_capability(tool_name), tool_name,
                     {"gen_ai.tool.type": str(tool_type)[:64]})

        # GenAI findings from the scalar metadata.
        req_model = genai["request_model"]
        resp_model = genai["response_model"]
        if req_model and resp_model and not _is_model_variant(req_model, resp_model):
            _acc_find(asset_key, asset_id, "governance", "request_response_model_mismatch", "low",
                      "Request/Response Model Mismatch",
                      "LLM calls for this service returned responses from a different model than requested.",
                      span.span_id, detail=f"{req_model} -> {resp_model}")

        total_tokens = (genai["input_tokens"] or 0) + (genai["output_tokens"] or 0)
        if total_tokens >= HIGH_TOKEN_USAGE_THRESHOLD:
            _acc_find(asset_key, asset_id, "performance", "high_token_usage", "medium",
                      "High Token Usage Detected",
                      f"A single LLM call for this service used {HIGH_TOKEN_USAGE_THRESHOLD:,} or more tokens.",
                      span.span_id, token_count=total_tokens,
                      reasoning_tokens=genai["reasoning_output_tokens"])

        # Errors: OTLP status ERROR or SemConv error.type / JSON-RPC error code.
        error_type = extract_error_type(attrs, span.status_code)
        if error_type is not None:
            if mcp_method or is_mcp_span(attrs):
                finding_type = "mcp_error"
                title = "MCP Errors Detected"
                summary = "MCP tool calls for this service have reported errors."
            elif extract_tool_name(attrs):
                finding_type = "tool_error"
                title = "Tool Errors Detected"
                summary = "Tool calls for this service have reported errors."
            elif any(k.startswith("gen_ai.") for k in attrs):
                finding_type = "provider_error"
                title = "Provider Errors Detected"
                summary = "Model provider calls for this service have reported errors."
            else:
                finding_type = "runtime_error"
                title = "Runtime Errors Detected"
                summary = "This service has logged spans with error status."
            _acc_find(asset_key, asset_id, "operations", finding_type, "medium",
                      title, summary, span.span_id, error_type=error_type)

    now = datetime.now(timezone.utc)

    mcp_finding_assets: dict[str, int | None] = {}
    for (asset_key, cap_name), cap_agg in mcp_cap_acc.items():
        c, u = _upsert_capability(
            db, org_id, cap_agg["asset_id"], asset_key, "mcp", cap_name,
            "otel_trace", now, evidence=cap_agg["evidence"],
        )
        caps_created += c
        caps_updated += u
        mcp_finding_assets.setdefault(asset_key, cap_agg["asset_id"])

    for (asset_key, cap_type, cap_name), cap_agg in genai_cap_acc.items():
        c, u = _upsert_capability(
            db, org_id, cap_agg["asset_id"], asset_key, cap_type, cap_name,
            "otel_trace", now, evidence=cap_agg["evidence"] or None,
        )
        caps_created += c
        caps_updated += u

    # The per-asset findings loop above only sees capabilities that already
    # existed when it queried — span-derived MCP capabilities are created here,
    # after it ran. Upsert mcp_enabled for these assets now so a single run
    # converges instead of the finding first appearing on the next run.
    for asset_key, asset_id in mcp_finding_assets.items():
        c, u = _upsert_finding(
            db, org_id, asset_id, asset_key, "security", "mcp_enabled", "medium",
            "MCP Server Access Enabled",
            "This AI system connects to one or more MCP servers, extending its tool surface.",
            "otel_trace", now,
        )
        finds_created += c
        finds_updated += u

    for (asset_key, category, finding_type), agg in finding_acc.items():
        evidence: dict = {"span_count": agg["count"], "sample_span_ids": agg["span_ids"]}
        if agg["max_duration_ms"] is not None:
            evidence["max_duration_ms"] = agg["max_duration_ms"]
        if agg["error_types"]:
            evidence["error_types"] = sorted(agg["error_types"])
        if agg["mcp_methods"]:
            evidence["mcp_methods"] = sorted(agg["mcp_methods"])
        if agg["details"]:
            evidence["details"] = sorted(agg["details"])
        if agg["max_total_tokens"] is not None:
            evidence["max_total_tokens"] = agg["max_total_tokens"]
        if agg["max_reasoning_tokens"] is not None:
            evidence["max_reasoning_tokens"] = agg["max_reasoning_tokens"]
        c, u = _upsert_finding(
            db, org_id, agg["asset_id"], asset_key, category, finding_type,
            agg["severity"], agg["title"], agg["summary"], "otel_trace", now,
            evidence=evidence, occurrence_count=agg["count"], replace_evidence=True,
        )
        finds_created += c
        finds_updated += u

    # AI Agent Runtime Security Intelligence — agent-specific security findings
    # derived by the pure module; upserted here so dedup/occurrence machinery
    # stays in one place. category="security", source="runtime_security".
    for d in derive_runtime_security_findings(db, org_id):
        c, u = _upsert_finding(
            db, org_id, d["asset_id"], d["asset_key"], "security",
            d["finding_type"], d["severity"], d["title"], d["summary"],
            "runtime_security", now,
            evidence=d["evidence"], occurrence_count=d.get("occurrence_count", 1),
            replace_evidence=True,
        )
        finds_created += c
        finds_updated += u

    # AI Agent Detection Rules (R1) — built-in batch rules over the same
    # evidence, evaluated only here (never in the OTLP ingestion path).
    # source="detection_rules"; category varies per rule family. Runs before
    # candidate derivation so rule findings can trigger candidates this run.
    for d in derive_detection_rule_findings(db, org_id):
        c, u = _upsert_finding(
            db, org_id, d["asset_id"], d["asset_key"], d["category"],
            d["finding_type"], d["severity"], d["title"], d["summary"],
            DETECTION_RULES_SOURCE, now,
            evidence=d["evidence"], occurrence_count=d.get("occurrence_count", 1),
            replace_evidence=True,
        )
        finds_created += c
        finds_updated += u

    # Gateway Control Center (GCR2) — derive control candidates from the open
    # findings this run just settled. Dismissal is sticky: a dismissed/resolved
    # candidate is only reopened when a *new* trigger finding type appears;
    # otherwise its row (and frozen evidence) is left untouched.
    for d in derive_gateway_control_candidates(db, org_id):
        existing = (
            db.query(AssetFinding)
            .filter(
                AssetFinding.organization_id == org_id,
                AssetFinding.asset_key == d["asset_key"],
                AssetFinding.category == CONTROL_CATEGORY,
                AssetFinding.finding_type == CONTROL_FINDING_TYPE,
                AssetFinding.source == CONTROL_SOURCE,
            )
            .first()
        )
        if existing is not None and existing.status != "open":
            prev_types: set[str] = set()
            if existing.evidence_json:
                try:
                    prev_types = set((json.loads(existing.evidence_json) or {}).get("trigger_finding_types") or [])
                except (json.JSONDecodeError, TypeError):
                    prev_types = set()
            if set(d["evidence"]["trigger_finding_types"]) - prev_types:
                existing.status = "open"  # new evidence reopens the question deliberately
            else:
                continue
        c, u = _upsert_finding(
            db, org_id, d["asset_id"], d["asset_key"], CONTROL_CATEGORY,
            CONTROL_FINDING_TYPE, d["severity"], d["title"], d["summary"],
            CONTROL_SOURCE, now,
            evidence=d["evidence"], occurrence_count=d["occurrence_count"],
            replace_evidence=True,
        )
        finds_created += c
        finds_updated += u

    db.commit()

    # Detection Rules webhook notifications (R5) — post-commit, intelligence
    # workflow only (never the OTLP ingestion path). Fail-safe: a webhook error
    # is recorded on its delivery row and never propagates to the run result.
    try:
        deliver_detection_rule_notifications(db, org_id, now)
    except Exception:  # noqa: BLE001 — notifications must never break the run
        _log.exception("detection-rule notification delivery failed")

    return {
        "capabilities_created": caps_created,
        "capabilities_updated": caps_updated,
        "findings_created": finds_created,
        "findings_updated": finds_updated,
    }
