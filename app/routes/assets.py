"""
Asset management REST endpoints.
All endpoints are read-only views derived from existing telemetry data.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user, resolve_team_scope, is_deny_sentinel
from app import assets as asset_lib
from app.models import Telemetry

router = APIRouter(tags=["assets"])


def _org_and_scope(user, db):
    """Return (organization_id, team_scope) for the current user, respecting RBAC."""
    org_id = user.organization_id if hasattr(user, "organization_id") else user.get("organization_id")
    team_scope = resolve_team_scope(user, db)
    return org_id, team_scope


@router.get("/assets")
async def list_assets(
    team:    Optional[str] = Query(None),
    status:  Optional[str] = Query(None, pattern="^(active|dormant|inactive)$"),
    risk:    Optional[str] = Query(None, pattern="^(high|medium|low)$"),
    owner:   Optional[str] = Query(None),
    search:  Optional[str] = Query(None),
    sort_by: str = Query("monthly_cost_usd"),
    order:   str = Query("desc", pattern="^(asc|desc)$"),
    days:    int = Query(90, ge=1, le=365),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all AI agent assets derived from telemetry, with optional filters."""
    org_id, team_scope = _org_and_scope(user, db)
    if is_deny_sentinel(team_scope):
        return []

    assets = asset_lib.get_all_assets_derived(db, org_id, days_lookback=days, team_scope=team_scope)

    filters = {k: v for k, v in {
        "team": team, "status": status, "risk": risk, "owner": owner, "search": search,
    }.items() if v is not None}
    if filters:
        assets = asset_lib.filter_assets(assets, filters)

    return asset_lib.sort_assets(assets, sort_by=sort_by, order=order)


@router.get("/assets/summary")
async def assets_summary(
    days: int = Query(90, ge=1, le=365),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return KPI metrics for the asset dashboard summary cards."""
    org_id, team_scope = _org_and_scope(user, db)
    if is_deny_sentinel(team_scope):
        return asset_lib.get_asset_summary.__wrapped__ if hasattr(asset_lib.get_asset_summary, '__wrapped__') else {
            "total_agents": 0, "active_agents": 0, "dormant_agents": 0, "inactive_agents": 0,
            "high_risk_agents": 0, "medium_risk_agents": 0, "low_risk_agents": 0,
            "total_cost_usd": 0.0, "monthly_cost_usd": 0.0,
            "agents_with_pii": 0, "agents_with_blocks": 0,
        }
    return asset_lib.get_asset_summary(db, org_id, days_lookback=days, team_scope=team_scope)


@router.get("/assets/{agent_name}")
async def get_asset(
    agent_name: str,
    days: int = Query(90, ge=1, le=365),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get full details for a single AI agent asset."""
    org_id, team_scope = _org_and_scope(user, db)
    if is_deny_sentinel(team_scope):
        raise HTTPException(status_code=404, detail="Asset not found")

    asset = asset_lib.get_asset_by_name(db, org_id, agent_name, days_lookback=days)
    if not asset:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found in telemetry")

    # Enforce team-scoped access
    if team_scope and asset.get("team") != team_scope:
        raise HTTPException(status_code=403, detail="Access denied: asset belongs to a different team")

    return asset


@router.get("/assets/{agent_name}/telemetry")
async def get_asset_telemetry(
    agent_name: str,
    skip:  int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    days:  int = Query(90, ge=1, le=365),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return paginated raw telemetry records for a specific agent."""
    from datetime import timedelta, timezone
    from datetime import datetime

    org_id, team_scope = _org_and_scope(user, db)
    if is_deny_sentinel(team_scope):
        return {"items": [], "total": 0}

    since = datetime.now(timezone.utc) - timedelta(days=days)
    q = (
        db.query(Telemetry)
        .filter(
            Telemetry.organization_id == org_id,
            Telemetry.agent == agent_name,
            Telemetry.timestamp >= since,
        )
    )
    if team_scope:
        q = q.filter(Telemetry.team == team_scope)

    total = q.count()
    rows  = q.order_by(Telemetry.timestamp.desc()).offset(skip).limit(limit).all()

    items = [
        {
            "id":               r.id,
            "timestamp":        r.timestamp.isoformat(),
            "team":             r.team,
            "agent":            r.agent,
            "model":            r.model,
            "prompt_tokens":    r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "total_tokens":     r.total_tokens,
            "cost_usd":         r.cost_usd,
            "latency_ms":       r.latency_ms,
            "sensitive":        r.sensitive,
            "blocked":          r.blocked,
            "block_reason":     r.block_reason,
            "pricing_estimated": getattr(r, "pricing_estimated", False),
        }
        for r in rows
    ]
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get("/assets/registry/unassigned")
async def list_unassigned_assets(
    days: int = Query(90, ge=1, le=365),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all assets in 'unassigned' lifecycle state — the discovery queue."""
    from app.models import AssetRegistry
    org_id, team_scope = _org_and_scope(user, db)
    if is_deny_sentinel(team_scope):
        return []
    q = db.query(AssetRegistry).filter(
        AssetRegistry.organization_id == org_id,
        AssetRegistry.status == "unassigned",
    )
    rows = q.order_by(AssetRegistry.first_seen_at.desc()).all()
    return [
        {
            "asset_key":      r.asset_key,
            "agent_id_raw":   r.agent_id_raw,
            "agent_name":     r.agent_name,
            "status":         r.status,
            "source":         r.source,
            "first_seen_at":  r.first_seen_at.isoformat(),
            "created_at":     r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/assets/{agent_name}/claim")
async def claim_asset(
    agent_name: str,
    body: dict,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Claim a discovered asset — promotes lifecycle_status from 'unassigned' to 'managed'
    and stores governance metadata (owner, team, environment, criticality, business_purpose).
    """
    import hashlib as _hashlib
    from datetime import datetime, timezone
    from app.models import AssetRegistry
    from app.auth import require_admin as _require_admin

    org_id, team_scope = _org_and_scope(user, db)
    if is_deny_sentinel(team_scope):
        raise HTTPException(status_code=403, detail="Access denied")

    asset_key = _hashlib.sha256(f"{org_id}:{agent_name}".encode()).hexdigest()
    reg = db.query(AssetRegistry).filter(
        AssetRegistry.organization_id == org_id,
        AssetRegistry.asset_key == asset_key,
    ).first()

    if not reg:
        raise HTTPException(status_code=404, detail=f"Asset '{agent_name}' not found in registry")

    caller_email = getattr(user, "email", None) or user.get("email") if isinstance(user, dict) else None

    reg.owner            = body.get("owner") or reg.owner
    reg.team             = body.get("team") or reg.team
    reg.environment      = body.get("environment") or reg.environment
    reg.criticality      = body.get("criticality") or reg.criticality
    reg.business_purpose = body.get("business_purpose") or reg.business_purpose
    reg.agent_name       = body.get("agent_name") or reg.agent_name
    reg.status           = "managed"
    reg.source           = "claimed"
    reg.claimed_by       = caller_email
    reg.claimed_at       = datetime.now(timezone.utc)

    db.commit()
    db.refresh(reg)

    return {
        "asset_key":        reg.asset_key,
        "agent_id_raw":     reg.agent_id_raw,
        "agent_name":       reg.agent_name,
        "owner":            reg.owner,
        "team":             reg.team,
        "environment":      reg.environment,
        "criticality":      reg.criticality,
        "business_purpose": reg.business_purpose,
        "status":           reg.status,
        "claimed_by":       reg.claimed_by,
        "claimed_at":       reg.claimed_at.isoformat(),
    }


@router.patch("/assets/{agent_name}/registry")
async def update_asset_registry(
    agent_name: str,
    body: dict,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update any governance field on a managed asset (owner, environment, criticality, etc.)."""
    import hashlib as _hashlib
    from app.models import AssetRegistry

    org_id, team_scope = _org_and_scope(user, db)
    if is_deny_sentinel(team_scope):
        raise HTTPException(status_code=403, detail="Access denied")

    asset_key = _hashlib.sha256(f"{org_id}:{agent_name}".encode()).hexdigest()
    reg = db.query(AssetRegistry).filter(
        AssetRegistry.organization_id == org_id,
        AssetRegistry.asset_key == asset_key,
    ).first()
    if not reg:
        raise HTTPException(status_code=404, detail=f"Asset '{agent_name}' not found in registry")

    allowed = {"owner", "team", "environment", "criticality", "business_purpose", "agent_name", "status"}
    for field, value in body.items():
        if field in allowed:
            setattr(reg, field, value)

    db.commit()
    db.refresh(reg)

    return {
        "asset_key":        reg.asset_key,
        "agent_id_raw":     reg.agent_id_raw,
        "agent_name":       reg.agent_name,
        "owner":            reg.owner,
        "team":             reg.team,
        "environment":      reg.environment,
        "criticality":      reg.criticality,
        "business_purpose": reg.business_purpose,
        "status":           reg.status,
    }
