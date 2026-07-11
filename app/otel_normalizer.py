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
from app.telemetry_classification import classify_span
from app.relationship_resolver import ResolvedRelationship
from app.relationships import upsert_relationship
from app.genai_semconv import (
    MEMORY_OPERATIONS,
    extract_agent_meta,
    extract_environment_tiered,
    extract_genai_scalar_fields,
    extract_mcp_method_tiered,
    extract_model_tiered,
    extract_operation,
    extract_provider,
    extract_response_meta,
    extract_tool_name as _semconv_tool_name,
    extract_usage,
)

_log = logging.getLogger("ai_asset_mgmt.otel")

# OTel GenAI attribute keys that indicate a span involves GenAI activity.
# Includes the ecosystem fallback variants (llm.* / model.name) recognised by
# app/genai_semconv.py — kept in lockstep so fallback-key spans reach the
# GenAI relationship branch, not just the standard-key ones.
_GENAI_INDICATORS = frozenset({
    "gen_ai.system",
    "gen_ai.provider.name",
    "gen_ai.operation.name",
    "gen_ai.request.model",
    "gen_ai.response.model",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "gen_ai.agent.name",
    "gen_ai.agent.id",
    # fallback tier (see genai_semconv extraction tiers)
    "gen_ai.model",
    "llm.model",
    "llm.model_name",
    "model.name",
    "llm.provider",
    "llm.vendor",
    "llm.usage.prompt_tokens",
    "llm.usage.completion_tokens",
    "llm.token_count.prompt",
    "llm.token_count.completion",
})

# gen_ai.operation.name → provenance event type (execute_tool goes through
# the tool branch; inference/unlisted operations default to llm_call)
_OPERATION_EVENT = {
    "invoke_agent": "agent_invocation",
    "create_agent": "agent_invocation",
    "invoke_workflow": "workflow_step",
    "plan": "plan_step",
    "retrieval": "retrieval_call",
}
_OPERATION_EVENT.update({op: "memory_op" for op in MEMORY_OPERATIONS})


# Resource attributes that vary per pod / instance / SDK build. Excluded from
# the stable fallback-identity hash so unidentified telemetry from the same
# source converges to ONE asset instead of fragmenting per replica.
_VOLATILE_RESOURCE_KEYS = frozenset({
    "service.instance.id", "k8s.pod.name", "k8s.pod.uid", "k8s.replicaset.name",
    "container.id", "process.pid", "process.runtime.description",
    "host.name", "host.id", "host.ip",
    "telemetry.sdk.name", "telemetry.sdk.version", "telemetry.sdk.language",
    "telemetry.distro.name", "telemetry.distro.version",
})

# Identity tiers (see app/telemetry_classification.py): declared > service > fallback.
_IDENTITY_TIER_RANK = {"declared": 2, "service": 1, "fallback": 0}


def _stable_fallback_identity(resource_attrs: dict, trace_id: str) -> str:
    """Stable identity for spans with no agent/service signal at all.

    Hash of the non-volatile resource attributes when any exist (converges
    across traces, pods, and restarts from the same source); else scoped to
    the trace so one trace is at most one asset — never one asset per span.
    """
    stable = {
        k: v for k, v in resource_attrs.items()
        if k not in _VOLATILE_RESOURCE_KEYS and not isinstance(v, (list, dict))
    }
    if stable:
        digest = hashlib.sha256(
            json.dumps(stable, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:12]
        return f"observed-ai-system:{digest}"
    return f"observed-ai-system:trace-{trace_id[:8]}"


def _resolve_identity(
    attrs: dict, resource_attrs: dict, trace_id: str
) -> tuple[str, str, str, str]:
    """
    Return (identity, display_name, identity_type, identity_tier).

    identity is the stable grouping key (feeds asset_key / agent_id_raw):
      gen_ai.agent.id → gen_ai.agent.name → agent.name / ai.agent.name →
      service.name → observed-ai-system:<stable hash>
    display_name is the human-readable alias (gen_ai.agent.name when present,
    else the identity itself) — so a UUID agent id still shows a real name.
    identity_type: "declared" for explicit agent attributes, "inferred" otherwise.
    identity_tier: "declared" / "service" / "fallback" — feeds telemetry
    classification; "fallback" marks the asset for admin review.
    """
    agent = extract_agent_meta(attrs, resource_attrs)
    legacy_name = None
    for key in ("agent.name", "ai.agent.name"):
        v = attrs.get(key) or resource_attrs.get(key)
        if v:
            legacy_name = str(v)
            break

    display = agent["name"] or legacy_name
    if agent["id"]:
        return agent["id"], display or agent["id"], "declared", "declared"
    if display:
        return display, display, "declared", "declared"
    svc = resource_attrs.get("service.name") or attrs.get("service.name")
    if svc:
        return str(svc), str(svc), "inferred", "service"
    fallback = _stable_fallback_identity(resource_attrs, trace_id)
    return fallback, fallback, "inferred", "fallback"


def _extract_model(attrs: dict) -> str | None:
    return extract_model_tiered(attrs)[0]


def _extract_tool_name(attrs: dict) -> str | None:
    return _semconv_tool_name(attrs)


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
        _extract_tool_name(attrs)
        or extract_mcp_method_tiered(attrs)[0]
        or extract_operation(attrs) == "execute_tool"
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


def _upsert_asset(
    db: Session,
    org_id: int,
    agent_name: str,
    resource_attrs: dict,
    display_name: str | None = None,
    agent_meta: dict | None = None,
    identity_tier: str = "declared",
) -> int | None:
    """
    Idempotent upsert of an AssetRegistry row for an OTel-observed agent.

    agent_name is the stable identity (gen_ai.agent.id when declared) and
    feeds asset_key/agent_id_raw; display_name is the human-readable alias.
    identity_tier "fallback" (no agent/service signal) marks the row for
    admin review via evidence.needs_admin_review — picked up by the existing
    derive_discovery_status pipeline — and gets a low confidence score.
    Returns the AssetRegistry.id, or None if upsert fails.
    """
    from app.asset_discovery import _known_assets, _infer_asset_type
    from app.models import AssetRegistry

    asset_key = _make_asset_key(org_id, agent_name)
    display_name = display_name or agent_name

    environment = extract_environment_tiered(resource_attrs)[0]
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
    if agent_meta:
        evidence["gen_ai.agent.id"] = agent_meta.get("id")
        evidence["gen_ai.agent.description"] = agent_meta.get("description")
        evidence["gen_ai.agent.version"] = agent_meta.get("version")
    evidence = {k: v for k, v in evidence.items() if v is not None}

    # An anonymous hash identity is not attribution evidence: flag for review
    # and score below the discovery-status attribution threshold (75).
    confidence = 75.0
    if identity_tier == "fallback":
        evidence["needs_admin_review"] = True
        evidence["identity_confidence"] = "low"
        confidence = 30.0

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
                agent_name=display_name,
                team=team,
                environment=environment,
                owner=owner,
                status="unassigned",
                source="otel_trace",
                discovery_status="potential",
                discovery_source="otel_trace",
                discovery_reason="Agent observed via OpenTelemetry trace ingestion",
                evidence=json.dumps(evidence),
                confidence_score=confidence,
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
    class_counts: dict[str, int] | None = None,
    candidate_keys: set[str] | None = None,
) -> None:
    """
    Upsert one OtelAsset row for a (org, service_name, environment) identity.

    Lookup uses application-level dedup (not a DB unique constraint) because
    environment is nullable and SQLite treats NULL != NULL in unique indexes.

    class_counts / candidate_keys carry this batch's telemetry-classification
    rollup (app/telemetry_classification.py) — merged monotonically into the
    cumulative counters, which derive classification_status and the real
    confidence_score.
    """
    from app.models import OtelAsset
    from app.telemetry_classification import merge_classification_counts

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

        counts_json = None
        class_status = None
        class_confidence = None
        if class_counts:
            counts_json, class_status, class_confidence = merge_classification_counts(
                existing.classification_counts_json if existing else None,
                class_counts,
            )

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
                confidence_score=class_confidence if class_counts else None,
                classification_status=class_status,
                classification_counts_json=counts_json,
                candidate_attr_keys_json=(
                    json.dumps(sorted(candidate_keys)[:40]) if candidate_keys else None
                ),
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
            if class_counts:
                existing.classification_counts_json = counts_json
                existing.classification_status = class_status
                existing.confidence_score = class_confidence
            if candidate_keys:
                merged_keys = set(json.loads(existing.candidate_attr_keys_json or "[]"))
                merged_keys |= candidate_keys
                existing.candidate_attr_keys_json = json.dumps(sorted(merged_keys)[:40])
            existing.updated_at = datetime.now(timezone.utc)

        db.commit()
    except Exception:
        db.rollback()
        _log.warning("Failed to upsert OtelAsset for %s (org=%s)", service_name, org_id, exc_info=True)


def normalize_spans(db: Session, org_id: int, spans: list[dict], api_key_id: int | None = None) -> dict:
    """
    Process a list of parsed OTLP spans for one organization.

    api_key_id, when provided, is the ingestion credential (Collector key) that
    posted these spans — stored on each OtelSpan for per-key attribution. None for
    dashboard/JWT ingestion.

    Returns counts: spans_ingested, assets_created_or_updated, relationships_upserted,
    provenance_events, otel_assets_upserted.
    """
    from app.models import OtelSpan, ProvenanceEvent, AssetRegistry
    from app.otel_attribute_mapping import (
        apply_mapping_to_batch,
        load_org_attribute_mapping,
    )

    # Org-defined custom→canonical attribute aliases, fetched ONCE per ingest
    # request and applied in place before identity resolution / extraction /
    # classification. Native canonical keys are never overwritten.
    org_mapping = load_org_attribute_mapping(db, org_id)
    span_mapped_keys = apply_mapping_to_batch(spans, org_mapping)

    assets_seen: set[str] = set()
    relationships_upserted = 0
    provenance_count = 0
    spans_ingested = 0

    # Per-agent-name accumulators (keyed by stable identity)
    _agent_asset_ids:  dict[str, int | None]      = {}
    _agent_display:    dict[str, str]              = {}
    _agent_svc_names:  dict[str, str]              = {}
    _agent_envs:       dict[str, str | None]       = {}
    _agent_res_attrs:  dict[str, dict]             = {}
    _agent_models:     dict[str, set[str]]         = defaultdict(set)
    _agent_providers:  dict[str, set[str]]         = defaultdict(set)
    _agent_tools:      dict[str, set[str]]         = defaultdict(set)
    _agent_deps:       dict[str, set[str]]         = defaultdict(set)
    _agent_trace_ids:  dict[str, set[str]]         = defaultdict(set)
    _agent_span_dts:   dict[str, list[datetime]]   = defaultdict(list)
    _agent_class_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"full": 0, "partial": 0, "unclassified": 0}
    )
    _agent_candidate_keys: dict[str, set[str]]     = defaultdict(set)

    # ── Pass 0: best identity per trace ───────────────────────────────────────
    # SemConv agent traces usually declare gen_ai.agent.* only on the root
    # invoke_agent span; child spans must inherit that identity instead of
    # fragmenting into a second service.name-based asset. Service-tier identity
    # is recorded too, so a fallback span whose trace siblings carry
    # service.name inherits that instead of a hash. declared > service.
    _trace_identity: dict[str, tuple[str, str, str]] = {}
    for span in spans:
        attrs = span.get("attributes") or {}
        resource_attrs = span.get("resource_attributes") or {}
        trace_id = span.get("trace_id") or ""
        if not trace_id:
            continue
        current = _trace_identity.get(trace_id)
        if current and current[2] == "declared":
            continue
        ident, disp, _ident_type, tier = _resolve_identity(attrs, resource_attrs, trace_id)
        if tier == "fallback":
            continue
        if current is None or _IDENTITY_TIER_RANK[tier] > _IDENTITY_TIER_RANK[current[2]]:
            _trace_identity[trace_id] = (ident, disp, tier)

    for span_idx, span in enumerate(spans):
        attrs = span.get("attributes") or {}
        resource_attrs = span.get("resource_attributes") or {}
        span_id = span.get("span_id") or ""
        trace_id = span.get("trace_id") or ""
        span_name = span.get("name") or ""

        if not trace_id or not span_id:
            continue

        # ── Identity ──────────────────────────────────────────────────────────
        agent_name, display_name, identity_type, identity_tier = _resolve_identity(
            attrs, resource_attrs, trace_id
        )
        inherited = _trace_identity.get(trace_id)
        if inherited and _IDENTITY_TIER_RANK[inherited[2]] > _IDENTITY_TIER_RANK[identity_tier]:
            agent_name, display_name, identity_tier = inherited
            if identity_tier == "declared":
                identity_type = "declared"
        service_name = resource_attrs.get("service.name") or attrs.get("service.name") or display_name
        environment = extract_environment_tiered(resource_attrs, attrs)[0]

        # ── Telemetry classification ──────────────────────────────────────────
        cls = classify_span(
            attrs, resource_attrs,
            identity_tier=identity_tier,
            mapped_keys=span_mapped_keys[span_idx],
        )
        _agent_class_counts[agent_name][cls.counts_key] += 1
        if cls.candidate_keys:
            _agent_candidate_keys[agent_name].update(cls.candidate_keys)

        # ── Asset discovery ───────────────────────────────────────────────────
        if agent_name not in assets_seen:
            asset_id = _upsert_asset(
                db, org_id, agent_name, resource_attrs,
                display_name=display_name,
                agent_meta=extract_agent_meta(attrs, resource_attrs),
                identity_tier=identity_tier,
            )
            assets_seen.add(agent_name)
            _agent_asset_ids[agent_name] = asset_id
        else:
            asset_id = _agent_asset_ids.get(agent_name)

        # ── OtelAsset accumulators ────────────────────────────────────────────
        _agent_display.setdefault(agent_name, display_name)
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
        # Safe scalar GenAI metadata (never content) for the queryable columns.
        genai = extract_genai_scalar_fields(attrs)

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
                    api_key_id=api_key_id,
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
                    gen_ai_operation_name=genai["operation_name"],
                    gen_ai_provider_name=genai["provider_name"],
                    gen_ai_request_model=genai["request_model"],
                    gen_ai_response_model=genai["response_model"],
                    gen_ai_input_tokens=genai["input_tokens"],
                    gen_ai_output_tokens=genai["output_tokens"],
                    gen_ai_reasoning_output_tokens=genai["reasoning_output_tokens"],
                    gen_ai_cache_read_input_tokens=genai["cache_read_input_tokens"],
                    gen_ai_cache_creation_input_tokens=genai["cache_creation_input_tokens"],
                    gen_ai_finish_reasons_json=genai["finish_reasons_json"],
                    gen_ai_request_stream=genai["request_stream"],
                    gen_ai_time_to_first_chunk_ms=genai["time_to_first_chunk_ms"],
                    classification_status=cls.status,
                    classification_confidence=cls.confidence,
                    # NULL (not []) when complete — clean spans stay byte-identical.
                    classification_missing=json.dumps(cls.missing) if cls.missing else None,
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

        operation = extract_operation(attrs)
        # execute_tool spans carry gen_ai.* attributes but are tool activity —
        # route them (and classic tool spans) to the tool branch first.
        span_is_tool = _is_tool_span(attrs, span_name) and operation in (None, "execute_tool")

        if _is_genai_span(attrs) and not span_is_tool:
            event_type = _OPERATION_EVENT.get(operation, "llm_call")
            model = _extract_model(attrs)
            if model:
                target_type = "model"
                target_name = model
                relation_type = "uses_model"
                _agent_models[agent_name].add(model)
                # Response model can differ from the requested one (e.g. dated
                # snapshots) — surface it in the asset's model inventory too.
                if genai["response_model"] and genai["response_model"] != model:
                    _agent_models[agent_name].add(genai["response_model"])
                usage = extract_usage(attrs)
                response_meta = extract_response_meta(attrs)
                rel = ResolvedRelationship(
                    source_agent_name=agent_name,
                    target_type="model",
                    target_name=model,
                    relationship_type="uses_model",
                    evidence_source="otel_trace",
                    confidence_score=0.90,
                    metadata={
                        "identity_type": identity_type,
                        "operation": operation,
                        "gen_ai.provider.name": attrs.get("gen_ai.provider.name"),
                        "gen_ai.system": attrs.get("gen_ai.system"),
                        "input_tokens": usage["input_tokens"],
                        "output_tokens": usage["output_tokens"],
                        "cache_creation_input_tokens": usage["cache_creation_input_tokens"],
                        "cache_read_input_tokens": usage["cache_read_input_tokens"],
                        "reasoning_output_tokens": usage["reasoning_output_tokens"],
                        "response_id": response_meta["id"],
                        "response_model": response_meta["model"],
                        "finish_reasons": response_meta["finish_reasons"],
                        "time_to_first_chunk": response_meta["time_to_first_chunk"],
                    },
                )
                upsert_relationship(db, org_id, rel)
                relationships_upserted += 1

            provider = extract_provider(attrs)
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
            mcp_resource = attrs.get("mcp.resource.uri")
            if mcp_resource:
                mcp_resource = str(mcp_resource)[:255]
                _agent_deps[agent_name].add(mcp_resource)
                rel_r = ResolvedRelationship(
                    source_agent_name=agent_name,
                    target_type="mcp_resource",
                    target_name=mcp_resource,
                    relationship_type="reads_resource",
                    evidence_source="otel_trace",
                    confidence_score=0.80,
                    metadata={"identity_type": identity_type, "mcp.method.name": attrs.get("mcp.method.name")},
                )
                upsert_relationship(db, org_id, rel_r)
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
                    gen_ai_provider_name=genai["provider_name"],
                    gen_ai_request_model=genai["request_model"],
                    gen_ai_response_model=genai["response_model"],
                    input_tokens=genai["input_tokens"],
                    output_tokens=genai["output_tokens"],
                    finish_reasons_json=genai["finish_reasons_json"],
                    request_stream=genai["request_stream"],
                    time_to_first_chunk_ms=genai["time_to_first_chunk_ms"],
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
        if ai_asset_id is None:
            existing_asset = (
                db.query(AssetRegistry)
                .filter(
                    AssetRegistry.organization_id == org_id,
                    AssetRegistry.asset_key == _make_asset_key(org_id, agent_name),
                )
                .first()
            )
            ai_asset_id = existing_asset.id if existing_asset else None
        upsert_otel_asset(
            db=db,
            org_id=org_id,
            ai_asset_id=ai_asset_id,
            service_name=_agent_svc_names.get(agent_name, agent_name),
            agent_name=_agent_display.get(agent_name, agent_name),
            environment=_agent_envs.get(agent_name),
            resource_attrs=_agent_res_attrs.get(agent_name, {}),
            new_models=_agent_models[agent_name],
            new_providers=_agent_providers[agent_name],
            new_tools=_agent_tools[agent_name],
            new_dependencies=_agent_deps[agent_name],
            trace_ids=_agent_trace_ids[agent_name],
            span_dts=_agent_span_dts[agent_name],
            class_counts=_agent_class_counts.get(agent_name),
            candidate_keys=_agent_candidate_keys.get(agent_name),
        )
        otel_assets_upserted += 1

    return {
        "spans_ingested": spans_ingested,
        "assets_created_or_updated": len(assets_seen),
        "relationships_upserted": relationships_upserted,
        "provenance_events": provenance_count,
        "otel_assets_upserted": otel_assets_upserted,
    }
