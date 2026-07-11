"""Pricing Registry REST endpoints."""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user, require_admin, is_deny_sentinel, resolve_team_scope
from app import pricing_registry as pr

import logging

log = logging.getLogger(__name__)

router = APIRouter(tags=["pricing_registry"])


def _org_id(user) -> Optional[int]:
    return user.organization_id if hasattr(user, "organization_id") else user.get("organization_id")


def _email(user) -> str:
    return (user.get("email") if isinstance(user, dict) else getattr(user, "email", None)) or "unknown"


# ── Query endpoints ───────────────────────────────────────────────────────────

@router.get("/pricing-registry")
async def list_pricing(
    provider:        Optional[str]  = Query(None),
    active_only:     bool           = Query(True),
    include_history: bool           = Query(False),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all pricing records. Org-specific overrides merged with global."""
    org_id = _org_id(user)
    return {
        "pricing": pr.get_all_pricing(
            db, org_id, provider=provider,
            active_only=active_only, include_history=include_history,
        ),
        **{k: v for k, v in pr.get_sync_status().items()
           if k in ("last_sync_at", "next_sync_at")},
    }


@router.get("/pricing-registry/{provider}/{model}/history")
async def model_history(
    provider: str,
    model:    str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """All pricing versions for a specific model."""
    org_id  = _org_id(user)
    history = pr.get_model_history(db, provider, model, org_id)
    if not history:
        raise HTTPException(status_code=404, detail=f"No pricing found for {provider}/{model}")
    return {"provider": provider, "model": model, "history": history}


@router.get("/pricing-registry/status")
async def pricing_status(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Freshness status + warnings for the dashboard."""
    org_id = _org_id(user)
    return pr.get_pricing_status(db, org_id)


# ── Admin actions ─────────────────────────────────────────────────────────────

@router.post("/pricing-registry/override", status_code=201)
async def override_pricing(
    body: dict,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Apply an org-specific pricing override for a model.
    Admin only. Creates a new immutable version, deactivates the previous one.
    """
    org_id = _org_id(user)
    required = {"provider", "model", "input_cost", "output_cost", "reason"}
    missing = required - body.keys()
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing fields: {sorted(missing)}")

    try:
        rec = pr.apply_override(
            db,
            organization_id  = org_id,
            provider         = body["provider"],
            model_name       = body["model"],
            input_cost       = float(body["input_cost"]),
            output_cost      = float(body["output_cost"]),
            created_by       = _email(user),
            cache_read_cost  = body.get("cache_read_cost"),
            cache_write_cost = body.get("cache_write_cost"),
            reason           = body.get("reason", ""),
        )
    except Exception:
        log.warning("pricing override failed for org=%s model=%s", org_id, body.get("model"), exc_info=True)
        raise HTTPException(status_code=400, detail="Failed to apply pricing override. Check the field values and try again.")

    return {
        "status":           "override_applied",
        "new_version":      rec.version,
        "effective_from":   rec.effective_from.isoformat() if rec.effective_from else None,
        "model":            rec.model_name,
        "provider":         rec.provider,
        "input_cost_per_million":  rec.input_cost_per_million_tokens,
        "output_cost_per_million": rec.output_cost_per_million_tokens,
    }


@router.post("/pricing-registry/sync")
async def trigger_sync(
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Trigger an immediate pricing sync (admin only). Runs in background."""
    state = pr.get_sync_status()
    if state["is_running"]:
        return {"status": "already_running", "message": "Sync is already in progress"}
    pr.trigger_sync_async()
    providers = sorted({r["provider"] for r in pr.get_all_pricing(db, active_only=True)})
    return {
        "status":    "sync_started",
        "message":   "Pricing sync triggered",
        "providers": providers or ["openai", "anthropic", "google", "local"],
    }


@router.get("/pricing-registry/sync-status")
async def sync_status_endpoint(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Latest sync results."""
    state = pr.get_sync_status()
    return {
        **state,
        "pricing_last_updated": pr.PRICING_LAST_UPDATED,
    }
