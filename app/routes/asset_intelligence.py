from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import AssetCapability, AssetFinding, AssetRegistry, OtelAsset, ProvenanceEvent
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
