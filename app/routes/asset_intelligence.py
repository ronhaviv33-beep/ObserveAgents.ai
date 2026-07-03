from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import AssetCapability, AssetFinding, OtelAsset
from app.asset_intelligence import derive_asset_intelligence

router = APIRouter(tags=["Asset Intelligence"])


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
    row.status = "resolved"
    db.commit()
    return {"id": finding_id, "status": "resolved"}
