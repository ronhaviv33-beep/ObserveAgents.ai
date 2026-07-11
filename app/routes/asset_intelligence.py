from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import AssetCapability, AssetFinding, AssetRegistry, OtelAsset, OtelSpan, ProvenanceEvent
from app.org_config import get_org_config
from app.asset_intelligence import derive_asset_intelligence

router = APIRouter(tags=["Asset Intelligence"])

# Error-family finding types (typed via SemConv error.type since GenAI compat layer)
_ERROR_FINDING_TYPES = frozenset({"runtime_error", "provider_error", "tool_error", "mcp_error"})

# Display-name normalization (serializer-level only — stored values unchanged).
# Includes the gen_ai.provider.name well-known values from the GenAI SemConv.
_PROVIDER_DISPLAY = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google",
    "azure": "Azure",
    "aws": "AWS",
    "bedrock": "Bedrock",
    "mistral": "Mistral",
    "cohere": "Cohere",
    "ollama": "Ollama",
    "aws.bedrock": "AWS Bedrock",
    "azure.ai.openai": "Azure OpenAI",
    "azure.ai.inference": "Azure AI Inference",
    "gcp.gemini": "Google Gemini",
    "gcp.vertex_ai": "Vertex AI",
    "gcp.gen_ai": "Google GenAI",
    "mistral_ai": "Mistral",
    "x_ai": "xAI",
    "deepseek": "DeepSeek",
    "groq": "Groq",
    "perplexity": "Perplexity",
    "moonshot_ai": "Moonshot AI",
    "ibm.watsonx.ai": "IBM watsonx.ai",
}


def _display_provider(name: str) -> str:
    return _PROVIDER_DISPLAY.get(str(name).lower(), str(name).capitalize())


def _json_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _serialize_otel_asset(row: OtelAsset) -> dict:
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "ai_asset_id": row.ai_asset_id,
        "service_name": row.service_name,
        "service_namespace": row.service_namespace,
        "environment": row.environment,
        "agent_name": row.agent_name,
        "models": _json_list(row.models_json),
        "providers": _json_list(row.providers_json),
        "tools": _json_list(row.tools_json),
        "dependencies": _json_list(row.dependencies_json),
        "first_seen": row.first_seen.isoformat(),
        "last_seen": row.last_seen.isoformat(),
        "trace_count": row.trace_count,
        "span_count": row.span_count,
        "confidence_score": row.confidence_score,
    }


def _serialize_cap(row: AssetCapability) -> dict:
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "asset_id": row.asset_id,
        "asset_key": row.asset_key,
        "capability_type": row.capability_type,
        "capability_name": row.capability_name,
        "source": row.source,
        "evidence": json.loads(row.evidence_json) if row.evidence_json else None,
        "first_seen": row.first_seen.isoformat(),
        "last_seen": row.last_seen.isoformat(),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _serialize_finding(row: AssetFinding) -> dict:
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "asset_id": row.asset_id,
        "asset_key": row.asset_key,
        "category": row.category,
        "finding_type": row.finding_type,
        "severity": row.severity,
        "title": row.title,
        "summary": row.summary,
        "evidence": json.loads(row.evidence_json) if row.evidence_json else None,
        "source": row.source,
        "status": row.status,
        "occurrence_count": row.occurrence_count or 1,
        "first_seen": row.first_seen.isoformat(),
        "last_seen": row.last_seen.isoformat(),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@router.post("/intelligence/run")
async def run_intelligence(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org_id = current_user.organization_id
    result = derive_asset_intelligence(db, org_id)
    return result


@router.post("/intelligence/reclassify")
async def reclassify_telemetry(
    current_user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Re-run telemetry classification + gen_ai extraction over the org's
    stored spans, applying the current attribute mapping (admin only,
    synchronous — same posture as /intelligence/run). Idempotent: a second
    run reports zero changes. Stored raw attributes are never modified."""
    from app.otel_reprocess import reclassify_org_spans
    return reclassify_org_spans(db, current_user.organization_id)


# Remediation hints per missing-signal code (see app/telemetry_classification.py).
_MISSING_REMEDIATION = {
    "identity": {
        "issue": "missing_identity",
        "add_attributes": ["service.name", "gen_ai.agent.name"],
    },
    "environment": {
        "issue": "missing_environment",
        "add_attributes": ["deployment.environment"],
    },
    "genai_model": {
        "issue": "genai_missing_model",
        "add_attributes": ["gen_ai.request.model"],
        "or_map_via": "PUT /settings/otel-attribute-mapping",
    },
    "genai_provider": {
        "issue": "genai_missing_provider",
        "add_attributes": ["gen_ai.provider.name"],
        "or_map_via": "PUT /settings/otel-attribute-mapping",
    },
    "tool_name": {
        "issue": "tool_missing_name",
        "add_attributes": ["gen_ai.tool.name"],
        "or_map_via": "PUT /settings/otel-attribute-mapping",
    },
    "mcp_server": {
        "issue": "mcp_missing_server",
        "add_attributes": ["mcp.server.name"],
        "or_map_via": "PUT /settings/otel-attribute-mapping",
    },
}


@router.get("/intelligence/telemetry-quality")
async def telemetry_quality(
    days: int = Query(30, ge=1, le=365),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Telemetry-quality report: how well each service's spans classify, which
    signals are missing, custom attribute keys that may deserve a mapping, and
    unidentified (fallback-identity) assets that need review. Review surface,
    not hot path — spans with NULL classification (pre-migration) are reported
    in the 'unscored' bucket."""
    org_id = current_user.organization_id
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # 1. Per-service span counts by classification status (one grouped query).
    status_rows = (
        db.query(
            OtelSpan.service_name,
            OtelSpan.classification_status,
            func.count(OtelSpan.id),
        )
        .filter(OtelSpan.organization_id == org_id, OtelSpan.start_time >= since)
        .group_by(OtelSpan.service_name, OtelSpan.classification_status)
        .all()
    )
    per_service: dict[str, dict] = {}

    def _svc(name: str) -> dict:
        return per_service.setdefault(name or "—", {
            "span_counts": {
                "total": 0, "fully_classified": 0, "partially_classified": 0,
                "unclassified": 0, "unscored": 0,
            },
            "missing": defaultdict(int),
        })

    for service_name, status, count in status_rows:
        entry = _svc(service_name)
        entry["span_counts"]["total"] += count
        bucket = status if status in (
            "fully_classified", "partially_classified", "unclassified") else "unscored"
        entry["span_counts"][bucket] += count

    # 2. Missing-signal tallies (only spans that recorded something missing).
    missing_rows = (
        db.query(OtelSpan.service_name, OtelSpan.classification_missing)
        .filter(
            OtelSpan.organization_id == org_id,
            OtelSpan.start_time >= since,
            OtelSpan.classification_missing.isnot(None),
        )
        .all()
    )
    for service_name, missing_json in missing_rows:
        entry = _svc(service_name)
        try:
            for code in json.loads(missing_json):
                entry["missing"][str(code)] += 1
        except (json.JSONDecodeError, TypeError):
            continue

    # 3. Asset-level rollups (status, score, candidate keys, environment).
    otel_assets = (
        db.query(OtelAsset).filter(OtelAsset.organization_id == org_id).all()
    )
    asset_by_service: dict[str, OtelAsset] = {}
    for oa in otel_assets:
        asset_by_service.setdefault(oa.service_name, oa)

    services = []
    for service_name, entry in sorted(per_service.items()):
        oa = asset_by_service.get(service_name)
        candidate_keys = _json_list(oa.candidate_attr_keys_json if oa else None)
        remediation = []
        for code in sorted(entry["missing"], key=lambda c: -entry["missing"][c]):
            hint = _MISSING_REMEDIATION.get(code)
            if hint:
                remediation.append(dict(hint))
        services.append({
            "service_name": service_name,
            "environment": oa.environment if oa else None,
            "classification_status": oa.classification_status if oa else None,
            "confidence_score": oa.confidence_score if oa else None,
            "span_counts": entry["span_counts"],
            "missing": dict(entry["missing"]),
            "candidate_attribute_keys": candidate_keys,
            "remediation": remediation,
        })

    # 4. Unidentified (fallback-identity) assets pending review.
    unidentified = (
        db.query(AssetRegistry)
        .filter(
            AssetRegistry.organization_id == org_id,
            AssetRegistry.agent_id_raw.like("observed-ai-system:%"),
        )
        .order_by(AssetRegistry.updated_at.desc())
        .limit(50)
        .all()
    )

    from app.otel_attribute_mapping import ORG_CONFIG_KEY
    mapping = get_org_config(db, org_id, ORG_CONFIG_KEY)

    return {
        "window_days": days,
        "services": services,
        "unidentified_assets": [
            {
                "agent_name": r.agent_name or r.agent_id_raw,
                "agent_id_raw": r.agent_id_raw,
                "asset_key": r.asset_key,
                "first_seen": r.first_seen_at.isoformat() if r.first_seen_at else None,
                "last_seen": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in unidentified
        ],
        "attribute_mapping_configured": bool(mapping),
    }


@router.get("/intelligence/assets")
async def list_otel_assets(
    environment: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Runtime Discovery evidence — one row per (service, environment) seen via OTel."""
    org_id = current_user.organization_id
    q = db.query(OtelAsset).filter(OtelAsset.organization_id == org_id)
    if environment:
        q = q.filter(OtelAsset.environment == environment)
    rows = q.order_by(OtelAsset.last_seen.desc()).all()
    return [_serialize_otel_asset(r) for r in rows]


@router.get("/intelligence/asset-summary")
async def asset_summary(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Intelligence grouped by AI system: one object per discovered asset with its
    runtime evidence, capability surface, and finding counts. Built entirely
    from derived columns — raw span attributes are never read.
    """
    org_id = current_user.organization_id

    otel_assets = (
        db.query(OtelAsset)
        .filter(OtelAsset.organization_id == org_id)
        .order_by(OtelAsset.last_seen.desc())
        .all()
    )
    registry_by_id = {
        r.id: r
        for r in db.query(AssetRegistry).filter(AssetRegistry.organization_id == org_id).all()
    }

    caps_by_key: dict[str, list[AssetCapability]] = defaultdict(list)
    for c in db.query(AssetCapability).filter(AssetCapability.organization_id == org_id).all():
        caps_by_key[c.asset_key].append(c)

    finds_by_key: dict[str, list[AssetFinding]] = defaultdict(list)
    for f in db.query(AssetFinding).filter(AssetFinding.organization_id == org_id).all():
        finds_by_key[f.asset_key].append(f)

    # Runtime GenAI usage per asset from the provenance scalar columns
    # (SQL aggregation only — raw span attributes stay unread). source_name
    # is the same stable identity that produces AssetRegistry.asset_key.
    usage_rows = (
        db.query(
            ProvenanceEvent.source_name,
            func.count(ProvenanceEvent.id).label("event_count"),
            func.sum(case((ProvenanceEvent.event_type == "llm_call", 1), else_=0)).label("llm_call_count"),
            func.sum(ProvenanceEvent.input_tokens).label("input_tokens"),
            func.sum(ProvenanceEvent.output_tokens).label("output_tokens"),
            func.sum(case((ProvenanceEvent.request_stream.is_(True), 1), else_=0)).label("streaming_count"),
            func.avg(ProvenanceEvent.time_to_first_chunk_ms).label("avg_ttfc"),
            func.max(ProvenanceEvent.timestamp).label("last_activity"),
        )
        .filter(
            ProvenanceEvent.organization_id == org_id,
            ProvenanceEvent.source_name.isnot(None),
        )
        .group_by(ProvenanceEvent.source_name)
        .all()
    )
    usage_by_key: dict[str, dict] = {}
    usage_by_name: dict[str, dict] = {}
    for r in usage_rows:
        entry = {
            "event_count": r.event_count,
            "llm_call_count": int(r.llm_call_count or 0),
            "input_tokens": int(r.input_tokens or 0),
            "output_tokens": int(r.output_tokens or 0),
            "streaming_count": int(r.streaming_count or 0),
            "avg_time_to_first_chunk_ms": (
                round(float(r.avg_ttfc), 1) if r.avg_ttfc is not None else None
            ),
            "last_activity": r.last_activity.isoformat() if r.last_activity else None,
        }
        usage_by_key[hashlib.sha256(f"{org_id}:{r.source_name}".encode()).hexdigest()[:64]] = entry
        usage_by_name[r.source_name] = entry

    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    assets = []
    for oa in otel_assets:
        reg = registry_by_id.get(oa.ai_asset_id) if oa.ai_asset_id else None
        asset_name = oa.agent_name or oa.service_name
        if reg is not None:
            asset_key = reg.asset_key
        else:
            asset_key = hashlib.sha256(f"{org_id}:{asset_name}".encode()).hexdigest()[:64]

        caps = caps_by_key.get(asset_key, [])
        finds = finds_by_key.get(asset_key, [])
        open_finds = [f for f in finds if f.status == "open"]

        categories: dict[str, int] = defaultdict(int)
        for f in open_finds:
            categories[f.category] += 1

        # SQLite reads DateTime(timezone=True) back naive-UTC; normalize both sides
        last_seen = oa.last_seen
        last_seen_naive = last_seen.replace(tzinfo=None) if last_seen.tzinfo else last_seen
        status = []
        if now_naive - last_seen_naive <= timedelta(days=7):
            status.append("active")
        if (oa.span_count or 0) > 0:
            status.append("runtime_observed")
        if open_finds:
            status.append("has_findings")
        if any(f.finding_type in _ERROR_FINDING_TYPES for f in open_finds):
            status.append("error_observed")

        assets.append({
            "ai_asset_id": oa.ai_asset_id,
            "asset_key": asset_key,
            "asset_name": asset_name,
            "service_name": oa.service_name,
            "environment": oa.environment,
            "last_seen": oa.last_seen.isoformat(),
            "trace_count": oa.trace_count,
            "span_count": oa.span_count,
            "models": _json_list(oa.models_json),
            "providers": [_display_provider(p) for p in _json_list(oa.providers_json)],
            "tools": _json_list(oa.tools_json),
            "dependencies": _json_list(oa.dependencies_json),
            "capabilities_count": len(caps),
            "findings_count": len(finds),
            "open_findings_count": len(open_finds),
            "high_findings_count": sum(1 for f in open_finds if f.severity in ("high", "critical")),
            "finding_categories": dict(categories),
            "status": status,
            "runtime_usage": usage_by_key.get(asset_key) or usage_by_name.get(asset_name),
            "capabilities": [_serialize_cap(c) for c in caps],
            "findings": [_serialize_finding(f) for f in finds],
        })

    # Gateway-era assets: registry rows with no OTel runtime evidence yet.
    # Orgs whose AI activity predates OTel ingestion (gateway/proxy discovery)
    # must still see their systems here — with an explicit "no runtime traces
    # yet" signal instead of an empty page.
    demo_mode = bool(get_org_config(db, org_id, "demo_mode"))
    emitted_ids = {oa.ai_asset_id for oa in otel_assets if oa.ai_asset_id}
    emitted_keys = {a["asset_key"] for a in assets}
    for reg in registry_by_id.values():
        if reg.id in emitted_ids or reg.asset_key in emitted_keys:
            continue
        if bool(reg.is_demo) != demo_mode:
            continue
        caps = caps_by_key.get(reg.asset_key, [])
        finds = finds_by_key.get(reg.asset_key, [])
        open_finds = [f for f in finds if f.status == "open"]
        categories = defaultdict(int)
        for f in open_finds:
            categories[f.category] += 1

        status = []
        if (reg.discovery_source or "") in ("gateway_telemetry", "gateway_runtime"):
            status.append("gateway_observed")
        if open_finds:
            status.append("has_findings")
        if any(f.finding_type in _ERROR_FINDING_TYPES for f in open_finds):
            status.append("error_observed")

        last = reg.updated_at or reg.first_seen_at or reg.created_at
        assets.append({
            "ai_asset_id": reg.id,
            "asset_key": reg.asset_key,
            "asset_name": reg.agent_name or reg.agent_id_raw,
            "service_name": None,
            "environment": reg.environment,
            "last_seen": last.isoformat() if last else None,
            "trace_count": 0,
            "span_count": 0,
            "models": [],
            "providers": [],
            "tools": [],
            "dependencies": [],
            "capabilities_count": len(caps),
            "findings_count": len(finds),
            "open_findings_count": len(open_finds),
            "high_findings_count": sum(1 for f in open_finds if f.severity in ("high", "critical")),
            "finding_categories": dict(categories),
            "status": status,
            "runtime_usage": usage_by_key.get(reg.asset_key),
            "capabilities": [_serialize_cap(c) for c in caps],
            "findings": [_serialize_finding(f) for f in finds],
        })

    return {"assets": assets}


@router.get("/intelligence/capabilities")
async def list_capabilities(
    asset_id: Optional[int] = Query(None),
    capability_type: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org_id = current_user.organization_id
    q = db.query(AssetCapability).filter(AssetCapability.organization_id == org_id)
    if asset_id is not None:
        q = q.filter(AssetCapability.asset_id == asset_id)
    if capability_type:
        q = q.filter(AssetCapability.capability_type == capability_type)
    if source:
        q = q.filter(AssetCapability.source == source)
    rows = q.order_by(AssetCapability.last_seen.desc()).all()
    return [_serialize_cap(r) for r in rows]


@router.get("/intelligence/findings")
async def list_findings(
    asset_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    finding_type: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org_id = current_user.organization_id
    q = db.query(AssetFinding).filter(AssetFinding.organization_id == org_id)
    if asset_id is not None:
        q = q.filter(AssetFinding.asset_id == asset_id)
    if category:
        q = q.filter(AssetFinding.category == category)
    if severity:
        q = q.filter(AssetFinding.severity == severity)
    if status:
        q = q.filter(AssetFinding.status == status)
    if finding_type:
        q = q.filter(AssetFinding.finding_type == finding_type)
    rows = q.order_by(AssetFinding.last_seen.desc()).all()
    return [_serialize_finding(r) for r in rows]


def _require_control_action_allowed(row: AssetFinding, user) -> None:
    """Gateway control candidates: everyone can view, only admins can act
    (decided in docs/gateway_control_center_architecture.md)."""
    if row.category == "control" and user.role != "admin" and not getattr(user, "is_platform_admin", False):
        raise HTTPException(
            status_code=403,
            detail="Only admins can act on Gateway control recommendations",
        )


@router.post("/intelligence/findings/{finding_id}/dismiss")
async def dismiss_finding(
    finding_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org_id = current_user.organization_id
    row = (
        db.query(AssetFinding)
        .filter(AssetFinding.id == finding_id, AssetFinding.organization_id == org_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    _require_control_action_allowed(row, current_user)
    row.status = "dismissed"
    db.commit()
    return {"id": finding_id, "status": "dismissed"}


@router.post("/intelligence/findings/{finding_id}/resolve")
async def resolve_finding(
    finding_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org_id = current_user.organization_id
    row = (
        db.query(AssetFinding)
        .filter(AssetFinding.id == finding_id, AssetFinding.organization_id == org_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    _require_control_action_allowed(row, current_user)
    row.status = "resolved"
    db.commit()
    return {"id": finding_id, "status": "resolved"}


@router.post("/intelligence/findings/{finding_id}/reopen")
async def reopen_finding(
    finding_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return a resolved or dismissed finding to the open state."""
    org_id = current_user.organization_id
    row = (
        db.query(AssetFinding)
        .filter(AssetFinding.id == finding_id, AssetFinding.organization_id == org_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    _require_control_action_allowed(row, current_user)
    row.status = "open"
    db.commit()
    return {"id": finding_id, "status": "open"}
