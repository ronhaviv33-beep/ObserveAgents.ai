"""
OTel span normalizer: converts parsed OTLP spans into ObserveAgents.ai records.

For each span:
  1. Extract agent/service identity from span and resource attributes.
  2. Upsert AssetRegistry entry (discovery_status="potential", discovery_source="otel_trace").
  3. Detect GenAI, tool, MCP, workflow, DB, and external API relationships.
  4. Call upsert_relationship() for each discovered edge.
  5. Write an OtelSpan row (privacy-scrubbed attributes).
  6. Write a ProvenanceEvent row for each meaningful action.

After all spans in the batch:
  7. Upsert one OtelAsset per unique agent/service identity (aggregates models/tools/etc.).

Discovery status notes:
  - "potential" is used (not "observed") so OTel-discovered assets appear in the
    existing frontend pipeline (which knows verified/likely/potential/historical).
  - discovery_source="otel_trace" distinguishes these from gateway-discovered assets.
  - Assets are promoted to "verified" when claimed by a human via the UI.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from collections import defaultdict

from sqlalchemy.orm import Session

from app.otel_privacy import scrub_attributes, REDACTED_KEYS
from app.relationship_resolver import ResolvedRelationship
from app.relationships import upsert_relationship

_log = logging.getLogger("ai_asset_mgmt.otel")

# OTel GenAI attribute keys that indicate a span involves an LLM call
_GENAI_INDICATORS = frozenset({
    "gen_ai.system",
    "gen_ai.operation.name",
    "gen_ai.request.model",
    "gen_ai.response.model",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
})


def _extract_agent_name(attrs: dict, resource_attrs: dict, span_id: str) -> tuple[str, str]:
    """
    Return (agent_name, identity_type).
    identity_type: "declared" if an explicit agent name attribute exists, "inferred" otherwise.
    """
    for key in ("agent.name", "ai.agent.name", "gen_ai.agent.name"):
        v = attrs.get(key) or resource_attrs.get(key)
        if v:
            return str(v), "declared"
    svc = resource_attrs.get("service.name") or attrs.get("service.name")
    if svc:
        return str(svc), "inferred"
    return f"observed-ai-system:{span_id[:8]}", "inferred"


def _extract_model(attrs: dict) -> str | None:
    return (
        attrs.get("gen_ai.request.model")
        or attrs.get("gen_ai.response.model")
        or None
    )


def _extract_tool_name(attrs: dict) -> str | None:
    return (
        attrs.get("tool.name")
        or attrs.get("mcp.tool.name")
        or attrs.get("mcp.tool")
        or None
    )


def _extract_mcp_server(attrs: dict) -> str | None:
    return attrs.get("mcp.server") or attrs.get("mcp.server.name") or None


def _extract_db_system(attrs: dict) -> str | None:
    return attrs.get("db.system") or attrs.get("db.name") or None


def _extract_external_api(attrs: dict) -> str | None:
    return (
        attrs.get("url.full")
        or attrs.get("http.url")
        or attrs.get("server.address")
        or attrs.get("http.host")
        or None
    )


def _extract_workflow(attrs: dict) -> str | None:
    return attrs.get("workflow.name") or attrs.get("workflow.step.name") or None


def _is_genai_span(attrs: dict) -> bool:
    return any(k in attrs for k in _GENAI_INDICATORS)


def _is_tool_span(attrs: dict, span_name: str) -> bool:
    return bool(
        attrs.get("tool.name")
        or attrs.get("mcp.tool.name")
        or attrs.get("mcp.tool")
        or "execute_tool" in (span_name or "").lower()
    )


def _nano_to_datetime(nano: int | str | None) -> datetime | None:
    if nano is None:
        return None
    try:
        ns = int(nano)
        return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc)
    except Exception:
        return None


def _utc_naive(dt: datetime) -> datetime:
    """Strip tzinfo from a datetime, converting to UTC first if needed.

    SQLite returns DateTime(timezone=True) columns as naive UTC. Normalizing
    to naive UTC before comparisons avoids offset-naive vs offset-aware errors.
    """
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _content_hash(attrs: dict) -> str | None:
    """SHA-256 of the combined raw content fields if any were present."""
    parts = []
    for key in sorted(REDACTED_KEYS):
        val = attrs.get(key)
        if val is not None:
            parts.append(json.dumps(val, ensure_ascii=False, separators=(",", ":")))
    if not parts:
        return None
    return hashlib.sha256("".join(parts).encode("utf-8")).hexdigest()


def _make_asset_key(org_id: int, agent_name: str) -> str:
    return hashlib.sha256(f"{org_id}:{agent_name}".encode()).hexdigest()[:64]


def _upsert_asset(db: Session, org_id: int, agent_name: str, resource_attrs: dict) -> int | None:
    """
    Idempotent upsert of an AssetRegistry row for an OTel-observed agent.
    Returns the AssetRegistry.id, or None if upsert fails.
    """
    from app.asset_discovery import _known_assets, _infer_asset_type
    from app.models import AssetRegistry

    asset_key = _make_asset_key(org_id, agent_name)

    environment = (
        resource_attrs.get("deployment.environment")
        or resource_attrs.get("deployment.environment.name")
        or None
    )
    owner = (
        resource_attrs.get("service.owner")
        or resource_attrs.get("team")
        or resource_attrs.get("owner")
        or None
    )
    team = resource_attrs.get("team") or resource_attrs.get("service.team") or None
    evidence = {
        "source": "otel_trace",
        "service.version": resource_attrs.get("service.version"),
        "k8s.pod.name":    resource_attrs.get("k8s.pod.name"),
        "cloud.region":    resource_attrs.get("cloud.region"),
        "container.name":  resource_attrs.get("container.name"),
    }
    evidence = {k: v for k, v in evidence.items() if v is not None}

    try:
        existing = db.query(AssetRegistry).filter(
            AssetRegistry.organization_id == org_id,
            AssetRegistry.asset_key == asset_key,
        ).first()
        if not existing:
            row = AssetRegistry(
                organization_id=org_id,
                asset_key=asset_key,
                agent_id_raw=agent_name,
                agent_name=agent_name,
                team=team,
                environment=environment,
                owner=owner,
                status="unassigned",
                source="otel_trace",
                discovery_status="potential",
                discovery_source="otel_trace",
                discovery_reason="Agent observed via OpenTelemetry trace ingestion",
                evidence=json.dumps(evidence),
                confidence_score=75.0,
                asset_type=_infer_asset_type(agent_name, ""),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            _known_assets.add((org_id, asset_key))
            return row.id
        else:
            if existing.discovery_source == "gateway_runtime":
                existing.discovery_source = "otel_trace"
                db.commit()
            _known_assets.add((org_id, asset_key))
            return existing.id
    except Exception:
        db.rollback()
        _log.warning("Failed to upsert OTel asset for %s (org=%s)", agent_name, org_id, exc_info=True)
        return None


def _merge_json_array(existing_json: str | None, new_values: set[str]) -> str:
    """Merge new_values into a JSON array, deduplicating, return serialized."""
    current: list[str] = json.loads(existing_json or "[]")
    merged = sorted(set(current) | {v for v in new_values if v})
    return json.dumps(merged)


def upsert_otel_asset(
    db: Session,
    org_id: int,
    ai_asset_id: int | None,
    service_name: str,
    agent_name: str | None,
    environment: str | None,
    resource_attrs: dict,
    new_models: set[str],
    new_providers: set[str],
    new_tools: set[str],
    new_dependencies: set[str],
    trace_ids: set[str],
    span_dts: list[datetime],
) -> None:
    """
    Upsert one OtelAsset row for a (org, service_name, environment) identity.

    Lookup uses application-level dedup (not a DB unique constraint) because
    environment is nullable and SQLite treats NULL != NULL in unique indexes.
    """
    from app.models import OtelAsset

    if not service_name or not span_dts:
        return

    earliest = _utc_naive(min(span_dts))
    latest   = _utc_naive(max(span_dts))
    safe_resource = {
        k: v for k, v in resource_attrs.items()
        if k not in REDACTED_KEYS and not isinstance(v, (list, dict))
    }

    try:
        # Nullable-aware lookup: match None environment explicitly
        q = db.query(OtelAsset).filter(
            OtelAsset.organization_id == org_id,
            OtelAsset.service_name == service_name,
        )
        if environment is None:
            q = q.filter(OtelAsset.environment.is_(None))
        else:
            q = q.filter(OtelAsset.environment == environment)
        existing = q.first()

        if not existing:
            db.add(OtelAsset(
                organization_id=org_id,
                ai_asset_id=ai_asset_id,
                service_name=service_name,
                service_namespace=resource_attrs.get("service.namespace"),
                service_instance_id=resource_attrs.get("service.instance.id"),
                environment=environment,
                agent_name=agent_name,
                models_json=json.dumps(sorted(v for v in new_models if v)) or None,
                providers_json=json.dumps(sorted(v for v in new_providers if v)) or None,
                tools_json=json.dumps(sorted(v for v in new_tools if v)) or None,
                dependencies_json=json.dumps(sorted(v for v in new_dependencies if v)) or None,
                resource_attributes_json=json.dumps(safe_resource) if safe_resource else None,
                first_seen=earliest,
                last_seen=latest,
                trace_count=len(trace_ids),
                span_count=len(span_dts),
                confidence_score=75.0,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ))
        else:
            existing.models_json       = _merge_json_array(existing.models_json, new_models)
            existing.providers_json    = _merge_json_array(existing.providers_json, new_providers)
            existing.tools_json        = _merge_json_array(existing.tools_json, new_tools)
            existing.dependencies_json = _merge_json_array(existing.dependencies_json, new_dependencies)
            existing.span_count  += len(span_dts)
            existing.trace_count += len(trace_ids)
            if latest > _utc_naive(existing.last_seen):
                existing.last_seen = latest
            if earliest < _utc_naive(existing.first_seen):
                existing.first_seen = earliest
            if safe_resource:
                cur = json.loads(existing.resource_attributes_json or "{}")
                cur.update(safe_resource)
                existing.resource_attributes_json = json.dumps(cur)
            if existing.ai_asset_id is None and ai_asset_id is not None:
                existing.ai_asset_id = ai_asset_id
            existing.updated_at = datetime.now(timezone.utc)

        db.commit()
    except Exception:
        db.rollback()
        _log.warning("Failed to upsert OtelAsset for %s (org=%s)", service_name, org_id, exc_info=True)


def normalize_spans(db: Session, org_id: int, spans: list[dict]) -> dict:
    """
    Process a list of parsed OTLP spans for one organization.

    Returns counts: spans_ingested, assets_created_or_updated, relationships_upserted,
    provenance_events, otel_assets_upserted.
    """
    from app.models import OtelSpan, ProvenanceEvent
    from app.ai_asset_resolver import resolve_asset_registry_id

    assets_seen: set[str] = set()
    relationships_upserted = 0
    provenance_count = 0
    spans_ingested = 0

    # Per-agent-name accumulators (keyed by agent_name)
    _agent_asset_ids:  dict[str, int | None]      = {}
    _agent_svc_names:  dict[str, str]              = {}
    _agent_envs:       dict[str, str | None]       = {}
    _agent_res_attrs:  dict[str, dict]             = {}
    _agent_models:     dict[str, set[str]]         = defaultdict(set)
    _agent_providers:  dict[str, set[str]]         = defaultdict(set)
    _agent_tools:      dict[str, set[str]]         = defaultdict(set)
    _agent_deps:       dict[str, set[str]]         = defaultdict(set)
    _agent_trace_ids:  dict[str, set[str]]         = defaultdict(set)
    _agent_span_dts:   dict[str, list[datetime]]   = defaultdict(list)

    for span in spans:
        attrs = span.get("attributes") or {}
        resource_attrs = span.get("resource_attributes") or {}
        span_id = span.get("span_id") or ""
        trace_id = span.get("trace_id") or ""
        span_name = span.get("name") or ""

        if not trace_id or not span_id:
            continue

        # ── Identity ──────────────────────────────────────────────────────────
        agent_name, identity_type = _extract_agent_name(attrs, resource_attrs, span_id)
        service_name = resource_attrs.get("service.name") or attrs.get("service.name") or agent_name
        environment = (
            resource_attrs.get("deployment.environment")
            or resource_attrs.get("deployment.environment.name")
            or None
        )

        # ── Asset discovery ───────────────────────────────────────────────────
        if agent_name not in assets_seen:
            asset_id = _upsert_asset(db, org_id, agent_name, resource_attrs)
            assets_seen.add(agent_name)
            _agent_asset_ids[agent_name] = asset_id
        else:
            asset_id = _agent_asset_ids.get(agent_name)

        # ── OtelAsset accumulators ────────────────────────────────────────────
        _agent_svc_names.setdefault(agent_name, service_name)
        _agent_envs.setdefault(agent_name, environment)
        _agent_res_attrs.setdefault(agent_name, resource_attrs)
        _agent_trace_ids[agent_name].add(trace_id)

        # ── Timing ───────────────────────────────────────────────────────────
        start_dt = _nano_to_datetime(span.get("start_time_unix_nano"))
        end_dt   = _nano_to_datetime(span.get("end_time_unix_nano"))
        duration_ms: int | None = None
        if start_dt and end_dt:
            delta = (end_dt - start_dt).total_seconds()
            duration_ms = int(delta * 1000)

        span_ts = start_dt or datetime.now(timezone.utc)
        _agent_span_dts[agent_name].append(span_ts)

        # ── Privacy scrub for storage ─────────────────────────────────────────
        scrubbed_attrs = scrub_attributes(attrs)
        raw_content_hash = _content_hash(attrs)

        # ── Persist OtelSpan ──────────────────────────────────────────────────
        try:
            existing_span = db.query(OtelSpan).filter(
                OtelSpan.organization_id == org_id,
                OtelSpan.trace_id == trace_id,
                OtelSpan.span_id == span_id,
            ).first()
            if not existing_span:
                db.add(OtelSpan(
                    organization_id=org_id,
                    trace_id=trace_id,
                    span_id=span_id,
                    parent_span_id=span.get("parent_span_id"),
                    service_name=service_name,
                    span_name=span_name,
                    span_kind=span.get("kind"),
                    start_time=start_dt,
                    end_time=end_dt,
                    duration_ms=duration_ms,
                    status_code=str(span.get("status_code")) if span.get("status_code") is not None else None,
                    status_message=span.get("status_message"),
                    attributes_json=json.dumps(scrubbed_attrs),
                    resource_attributes_json=json.dumps(resource_attrs),
                    events_json=json.dumps(span.get("events") or []),
                    links_json=json.dumps(span.get("links") or []),
                ))
                db.commit()
                spans_ingested += 1
        except Exception:
            db.rollback()
            _log.warning("Failed to persist OtelSpan %s/%s", trace_id, span_id, exc_info=True)
            continue

        # ── Relationship and provenance detection ─────────────────────────────
        event_type: str | None = None
        target_type: str | None = None
        target_name: str | None = None
        relation_type: str | None = None

        if _is_genai_span(attrs):
            event_type = "llm_call"
            model = _extract_model(attrs)
            if model:
                target_type = "model"
                target_name = model
                relation_type = "uses_model"
                _agent_models[agent_name].add(model)
                rel = ResolvedRelationship(
                    source_agent_name=agent_name,
                    target_type="model",
                    target_name=model,
                    relationship_type="uses_model",
                    evidence_source="otel_trace",
                    confidence_score=0.90,
                    metadata={
                        "identity_type": identity_type,
                        "gen_ai.system": attrs.get("gen_ai.system"),
                        "input_tokens": attrs.get("gen_ai.usage.input_tokens"),
                        "output_tokens": attrs.get("gen_ai.usage.output_tokens"),
                    },
                )
                upsert_relationship(db, org_id, rel)
                relationships_upserted += 1

            provider = attrs.get("gen_ai.system")
            if provider:
                provider_label = str(provider).capitalize()
                _agent_providers[agent_name].add(provider_label)
                rel_p = ResolvedRelationship(
                    source_agent_name=agent_name,
                    target_type="provider",
                    target_name=provider_label,
                    relationship_type="uses_provider",
                    evidence_source="otel_trace",
                    confidence_score=0.90,
                    metadata={"identity_type": identity_type},
                )
                upsert_relationship(db, org_id, rel_p)
                relationships_upserted += 1

        elif _is_tool_span(attrs, span_name):
            event_type = "tool_call"
            tool_name = _extract_tool_name(attrs)
            mcp_server = _extract_mcp_server(attrs)
            if tool_name:
                target_type = "tool"
                target_name = tool_name
                relation_type = "calls_tool"
                _agent_tools[agent_name].add(tool_name)
                rel = ResolvedRelationship(
                    source_agent_name=agent_name,
                    target_type="mcp_tool" if mcp_server else "tool",
                    target_name=tool_name,
                    relationship_type="uses_tool",
                    evidence_source="otel_trace",
                    confidence_score=0.85,
                    metadata={
                        "identity_type": identity_type,
                        "mcp_server": mcp_server,
                    },
                )
                upsert_relationship(db, org_id, rel)
                relationships_upserted += 1
            if mcp_server:
                _agent_deps[agent_name].add(mcp_server)
                rel_m = ResolvedRelationship(
                    source_agent_name=agent_name,
                    target_type="mcp_server",
                    target_name=mcp_server,
                    relationship_type="connects_to",
                    evidence_source="otel_trace",
                    confidence_score=0.85,
                    metadata={"identity_type": identity_type},
                )
                upsert_relationship(db, org_id, rel_m)
                relationships_upserted += 1

        else:
            db_sys = _extract_db_system(attrs)
            ext_api = _extract_external_api(attrs)
            workflow = _extract_workflow(attrs)

            if db_sys:
                event_type = "db_call"
                target_type = "database"
                target_name = db_sys
                relation_type = "reads_db"
                _agent_deps[agent_name].add(db_sys)
                rel = ResolvedRelationship(
                    source_agent_name=agent_name,
                    target_type="database",
                    target_name=db_sys,
                    relationship_type="reads_from",
                    evidence_source="otel_trace",
                    confidence_score=0.80,
                    metadata={"identity_type": identity_type},
                )
                upsert_relationship(db, org_id, rel)
                relationships_upserted += 1
            elif ext_api:
                event_type = "external_api_call"
                target_type = "api"
                target_name = ext_api[:255]
                relation_type = "calls_api"
                _agent_deps[agent_name].add(ext_api[:255])
                rel = ResolvedRelationship(
                    source_agent_name=agent_name,
                    target_type="api",
                    target_name=ext_api[:255],
                    relationship_type="calls",
                    evidence_source="otel_trace",
                    confidence_score=0.75,
                    metadata={"identity_type": identity_type},
                )
                upsert_relationship(db, org_id, rel)
                relationships_upserted += 1
            elif workflow:
                event_type = "workflow_step"
                target_type = "workflow"
                target_name = workflow
                relation_type = "invokes_workflow"
                _agent_deps[agent_name].add(workflow)
                rel = ResolvedRelationship(
                    source_agent_name=agent_name,
                    target_type="workflow",
                    target_name=workflow,
                    relationship_type="invokes_workflow",
                    evidence_source="otel_trace",
                    confidence_score=0.80,
                    metadata={"identity_type": identity_type},
                )
                upsert_relationship(db, org_id, rel)
                relationships_upserted += 1
            else:
                event_type = "agent_step"

        # ── Persist ProvenanceEvent ───────────────────────────────────────────
        if event_type:
            try:
                safe_attrs = {
                    k: v for k, v in scrubbed_attrs.items()
                    if not isinstance(v, dict) or not v.get("redacted")
                }
                db.add(ProvenanceEvent(
                    organization_id=org_id,
                    trace_id=trace_id,
                    span_id=span_id,
                    parent_span_id=span.get("parent_span_id"),
                    event_type=event_type,
                    source_type="agent",
                    source_name=agent_name,
                    target_type=target_type,
                    target_name=target_name,
                    relation_type=relation_type,
                    timestamp=span_ts,
                    attributes_json=json.dumps(safe_attrs) if safe_attrs else None,
                    content_hash=raw_content_hash,
                    content_redacted=True,
                ))
                db.commit()
                provenance_count += 1
            except Exception:
                db.rollback()
                _log.warning("Failed to persist ProvenanceEvent for span %s", span_id, exc_info=True)

    # ── Upsert one OtelAsset per unique agent/service identity ────────────────
    otel_assets_upserted = 0
    for agent_name in assets_seen:
        ai_asset_id = _agent_asset_ids.get(agent_name)
        # Resolve from DB if not set (e.g. race or cache hit without id)
        if ai_asset_id is None:
            ai_asset_id = resolve_asset_registry_id(db, org_id, agent_name)
        upsert_otel_asset(
            db=db,
            org_id=org_id,
            ai_asset_id=ai_asset_id,
            service_name=_agent_svc_names.get(agent_name, agent_name),
            agent_name=agent_name,
            environment=_agent_envs.get(agent_name),
            resource_attrs=_agent_res_attrs.get(agent_name, {}),
            new_models=_agent_models[agent_name],
            new_providers=_agent_providers[agent_name],
            new_tools=_agent_tools[agent_name],
            new_dependencies=_agent_deps[agent_name],
            trace_ids=_agent_trace_ids[agent_name],
            span_dts=_agent_span_dts[agent_name],
        )
        otel_assets_upserted += 1

    return {
        "spans_ingested": spans_ingested,
        "assets_created_or_updated": len(assets_seen),
        "relationships_upserted": relationships_upserted,
        "provenance_events": provenance_count,
        "otel_assets_upserted": otel_assets_upserted,
    }
