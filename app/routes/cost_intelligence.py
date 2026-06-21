"""Cost Intelligence REST endpoints."""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user, resolve_team_scope, is_deny_sentinel
from app import cost_intelligence as ci
from app.pricing import registry as pricing_registry
from app.org_config import get_org_config

router = APIRouter(tags=["cost_intelligence"])

_EMPTY_OVERVIEW = {
    "period": {},
    "runtime_cost": {"total_usd": 0, "trend_percent": 0, "trend_direction": "flat"},
    "provider_billing": {},
    "total_billed_usd": 0,
    "reconciliation": {},
}


def _org_and_scope(user, db):
    org_id = user.organization_id if hasattr(user, "organization_id") else user.get("organization_id")
    return org_id, resolve_team_scope(user, db)


def _caller_email(user) -> str | None:
    return user.get("email") if isinstance(user, dict) else getattr(user, "email", None)


@router.get("/cost-intelligence")
async def get_cost_intelligence(
    period_start: Optional[str] = Query(None, description="ISO date, e.g. 2026-06-01"),
    period_end:   Optional[str] = Query(None, description="ISO date, e.g. 2026-06-30"),
    breakdown_by: str = Query("agent", pattern="^(agent|team|model|environment|provider)$"),
    days:         int = Query(30, ge=1, le=365, description="Trend window in days"),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Unified cost intelligence payload.
    Includes: overview KPIs, cost breakdown, 30-day daily trends, pricing metadata.
    """
    org_id, team_scope = _org_and_scope(user, db)
    if is_deny_sentinel(team_scope):
        return {**_EMPTY_OVERVIEW, "breakdown": {"by": breakdown_by, "items": []}, "trends": []}

    demo_mode = bool(get_org_config(db, org_id, "demo_mode"))
    overview  = ci.get_cost_overview(db, org_id, period_start, period_end, team_scope, demo_mode=demo_mode)
    breakdown = ci.get_cost_breakdown(db, org_id, breakdown_by, period_start, period_end, team_scope, demo_mode=demo_mode)
    trends    = ci.get_cost_trends(db, org_id, days=days, team_scope=team_scope, demo_mode=demo_mode)

    return {
        **overview,
        "breakdown": {"by": breakdown_by, "items": breakdown},
        "trends": trends,
        "pricing_registry": {
            "last_updated": pricing_registry.last_updated(),
            "model_count":  len(pricing_registry.get_all_models()),
        },
    }


# ── Billing import ────────────────────────────────────────────────────────────

# Must be registered before /billing/periods/{period_id} to avoid ambiguity
@router.post("/billing/{provider}/import", status_code=201)
async def import_billing(
    provider: str,
    body: dict,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Import a provider billing record and auto-run cost reconciliation.
    Required fields: billing_period_start, billing_period_end, actual_billed_cost_usd.
    """
    org_id, team_scope = _org_and_scope(user, db)
    if is_deny_sentinel(team_scope):
        raise HTTPException(status_code=403, detail="Access denied")

    VALID_PROVIDERS = {"openai", "anthropic", "gemini", "google", "bedrock", "azure"}
    if provider not in VALID_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider '{provider}'. Valid: {sorted(VALID_PROVIDERS)}",
        )

    required = {"billing_period_start", "billing_period_end", "actual_billed_cost_usd"}
    missing = required - body.keys()
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing required fields: {sorted(missing)}")

    try:
        result = ci.import_provider_billing(db, org_id, provider, body, imported_by=_caller_email(user))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return result


@router.get("/billing/periods")
async def list_billing_periods(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all provider billing records for the org, most recent first."""
    org_id, team_scope = _org_and_scope(user, db)
    if is_deny_sentinel(team_scope):
        return []
    return ci.get_billing_periods(db, org_id)


@router.get("/billing/periods/{period_id}")
async def get_billing_period(
    period_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single billing record with full reconciliation detail."""
    org_id, team_scope = _org_and_scope(user, db)
    if is_deny_sentinel(team_scope):
        raise HTTPException(status_code=404, detail="Not found")

    record = ci.get_billing_period(db, org_id, period_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Billing period {period_id} not found")
    return record


@router.put("/billing/periods/{period_id}")
async def update_billing_period(
    period_id: int,
    body: dict,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an existing billing record and re-run reconciliation."""
    org_id, team_scope = _org_and_scope(user, db)
    if is_deny_sentinel(team_scope):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        result = ci.update_provider_billing(db, org_id, period_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return result


# ── Per-agent cost ────────────────────────────────────────────────────────────

@router.get("/agents/{agent_id}/cost")
async def get_agent_cost(
    agent_id: str,
    days: int = Query(90, ge=1, le=365),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Per-agent cost detail: monthly/lifetime totals, MoM trend, model breakdown."""
    org_id, team_scope = _org_and_scope(user, db)
    if is_deny_sentinel(team_scope):
        raise HTTPException(status_code=404, detail="Not found")

    detail = ci.get_agent_cost_detail(db, org_id, agent_id, days=days)
    if not detail:
        raise HTTPException(status_code=404, detail=f"No cost data found for agent '{agent_id}'")
    return detail
