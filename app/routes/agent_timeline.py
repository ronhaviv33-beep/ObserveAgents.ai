"""
Agent Timeline + telemetry metrics read endpoints (dashboard).

GET /agents/{agent_id}/timeline   — per-agent activity feed from normalized
                                    telemetry_events + summary from the
                                    agent_metrics_daily rollup.
GET /telemetry/metrics/daily      — org-wide daily rollups (top risky agents,
                                    policy violations per team).

agent_id follows the existing inventory convention: the raw agent identity
(agent_id_raw / agent name) or the sha256 asset_key. Org isolation matches
agent_inventory.py — org_id from the authenticated user only.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user, resolve_team_scope, is_deny_sentinel
from app.models import AgentMetricsDaily, AssetRegistry, TelemetryEvent
from app.risk_processor import risk_level

router = APIRouter(tags=["Agent Timeline"])


def _org_and_scope(user, db):
    org_id = user.organization_id if hasattr(user, "organization_id") else user.get("organization_id")
    return org_id, resolve_team_scope(user, db)


def _resolve_asset(db: Session, org_id: int, agent_id: str) -> AssetRegistry | None:
    alt_key = hashlib.sha256(f"{org_id}:{agent_id}".encode()).hexdigest()[:64]
    return db.query(AssetRegistry).filter(
        AssetRegistry.organization_id == org_id,
        or_(
            AssetRegistry.asset_key == agent_id,
            AssetRegistry.asset_key == alt_key,
            AssetRegistry.agent_id_raw == agent_id,
        ),
    ).first()


def _event_to_dict(e: TelemetryEvent) -> dict:
    reasons = []
    if e.risk_reasons:
        try:
            reasons = json.loads(e.risk_reasons)
        except Exception:
            reasons = []
    return {
        "id": e.id,
        "event_id": e.event_id,
        "timestamp": e.timestamp.isoformat() if e.timestamp else None,
        "event_type": e.event_type,
        "provider": e.provider,
        "model": e.model,
        "tool_name": e.tool_name,
        "action_name": e.action_name,
        "input_tokens": e.input_tokens,
        "output_tokens": e.output_tokens,
        "total_tokens": e.total_tokens,
        "cost_usd": e.cost_usd,
        "cost_estimated": e.cost_estimated,
        "latency_ms": e.latency_ms,
        "status": e.status,
        "error_message": e.error_message,
        "risk_score": e.risk_score,
        "risk_level": risk_level(e.risk_score or 0),
        "risk_reasons": reasons,
        "policy_action": e.policy_action,
        "trace_id": e.trace_id,
        "span_id": e.span_id,
    }


def _summary_from_rollups(db: Session, org_id: int, agent_id_raw: str, since_day) -> dict:
    rows = db.query(AgentMetricsDaily).filter(
        AgentMetricsDaily.organization_id == org_id,
        AgentMetricsDaily.agent_id == agent_id_raw,
        AgentMetricsDaily.day >= since_day,
    ).all()

    events = sum(r.events_count for r in rows)
    models: dict[str, dict] = {}
    weighted_latency = 0.0
    latency_events = 0
    for r in rows:
        if r.models_json:
            try:
                for m, stats in json.loads(r.models_json).items():
                    agg = models.setdefault(m, {"events": 0, "tokens": 0, "cost_usd": 0.0})
                    agg["events"] += stats.get("events", 0)
                    agg["tokens"] += stats.get("tokens", 0)
                    agg["cost_usd"] = round(agg["cost_usd"] + stats.get("cost_usd", 0.0), 6)
            except Exception:
                pass
        if r.avg_latency_ms is not None:
            weighted_latency += r.avg_latency_ms * r.events_count
            latency_events += r.events_count

    return {
        "events": events,
        "errors": sum(r.error_count for r in rows),
        "blocked": sum(r.blocked_count for r in rows),
        "policy_violations": sum(r.policy_violations for r in rows),
        "high_risk_events": sum(r.high_risk_events for r in rows),
        "total_cost_usd": round(sum(r.total_cost_usd for r in rows), 6),
        "total_tokens": sum(r.total_tokens for r in rows),
        "avg_latency_ms": round(weighted_latency / latency_events, 2) if latency_events else None,
        "max_risk_score": max((r.max_risk_score for r in rows), default=0),
        "models": [
            {"model": m, **stats}
            for m, stats in sorted(models.items(), key=lambda kv: -kv[1]["cost_usd"])
        ],
    }


@router.get("/agents/{agent_id}/timeline")
async def get_agent_timeline(
    agent_id: str,
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(50, ge=1, le=200),
    cursor: int | None = Query(None, description="Keyset cursor: return events with id < cursor"),
    event_type: str | None = Query(None),
    status: str | None = Query(None),
    min_risk: int | None = Query(None, ge=0, le=100),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Activity timeline for one agent: what it did, when, with which model or
    tool, at what cost/latency, and whether anything was risky or violated policy."""
    org_id, team_scope = _org_and_scope(user, db)
    if is_deny_sentinel(team_scope):
        raise HTTPException(status_code=404, detail="Agent not found")

    asset = _resolve_asset(db, org_id, agent_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    if team_scope and asset.team and asset.team not in ("Unknown", team_scope):
        raise HTTPException(status_code=403, detail="Access denied: agent belongs to a different team")

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    q = db.query(TelemetryEvent).filter(
        TelemetryEvent.organization_id == org_id,
        or_(
            TelemetryEvent.asset_key == asset.asset_key,
            TelemetryEvent.agent_id == asset.agent_id_raw,
        ),
        TelemetryEvent.timestamp >= since,
    )
    if event_type:
        q = q.filter(TelemetryEvent.event_type == event_type)
    if status:
        q = q.filter(TelemetryEvent.status == status)
    if min_risk is not None:
        q = q.filter(TelemetryEvent.risk_score >= min_risk)
    if cursor is not None:
        q = q.filter(TelemetryEvent.id < cursor)

    events = q.order_by(TelemetryEvent.timestamp.desc(), TelemetryEvent.id.desc()).limit(limit).all()
    next_cursor = events[-1].id if len(events) == limit else None

    last_seen = db.query(func.max(TelemetryEvent.timestamp)).filter(
        TelemetryEvent.organization_id == org_id,
        or_(
            TelemetryEvent.asset_key == asset.asset_key,
            TelemetryEvent.agent_id == asset.agent_id_raw,
        ),
    ).scalar()

    summary = _summary_from_rollups(db, org_id, asset.agent_id_raw, since.date())
    summary["last_seen"] = last_seen.isoformat() if last_seen else None

    return {
        "agent": {
            "id": asset.id,
            "agent_id": asset.agent_id_raw,
            "asset_key": asset.asset_key,
            "name": asset.agent_name or asset.agent_id_raw,
            "team": asset.team,
            "owner": asset.owner,
            "environment": asset.environment,
            "status": asset.status,
        },
        "summary": summary,
        "events": [_event_to_dict(e) for e in events],
        "next_cursor": next_cursor,
    }


@router.get("/telemetry/metrics/daily")
async def get_daily_metrics(
    days: int = Query(7, ge=1, le=90),
    group_by: str = Query("agent", pattern="^(agent|team)$"),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Org-wide precomputed daily rollups. group_by=agent → top risky agents;
    group_by=team → policy violations and spend per team."""
    org_id, team_scope = _org_and_scope(user, db)
    if is_deny_sentinel(team_scope):
        return {"days": days, "group_by": group_by, "rows": []}

    since_day = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    q = db.query(AgentMetricsDaily).filter(
        AgentMetricsDaily.organization_id == org_id,
        AgentMetricsDaily.day >= since_day,
    )
    if team_scope:
        q = q.filter(AgentMetricsDaily.team == team_scope)
    rows = q.all()

    grouped: dict[str, dict] = {}
    for r in rows:
        key = r.agent_id if group_by == "agent" else (r.team or "unassigned")
        g = grouped.setdefault(key, {
            ("agent_id" if group_by == "agent" else "team"): key,
            "agent_name": r.agent_name if group_by == "agent" else None,
            "events": 0, "errors": 0, "policy_violations": 0,
            "high_risk_events": 0, "total_cost_usd": 0.0,
            "max_risk_score": 0,
        })
        if group_by == "agent" and r.agent_name:
            g["agent_name"] = r.agent_name
        g["events"] += r.events_count
        g["errors"] += r.error_count
        g["policy_violations"] += r.policy_violations
        g["high_risk_events"] += r.high_risk_events
        g["total_cost_usd"] = round(g["total_cost_usd"] + r.total_cost_usd, 6)
        g["max_risk_score"] = max(g["max_risk_score"], r.max_risk_score)

    out = sorted(
        grouped.values(),
        key=lambda g: (-g["max_risk_score"], -g["high_risk_events"], -g["total_cost_usd"]),
    )
    if group_by != "agent":
        for g in out:
            g.pop("agent_name", None)
    return {"days": days, "group_by": group_by, "rows": out}
