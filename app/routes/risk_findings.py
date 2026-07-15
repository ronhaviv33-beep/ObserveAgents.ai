"""
Risk Findings v1 — org-scoped read APIs over risk-scored telemetry events.

A "finding" is any normalized telemetry event the ingest-time risk processor
flagged (risk_score > 0 or risk_reasons present). This is a pure product/read
layer: nothing here writes, re-scores, or touches ingestion — it makes the
existing risk_score / risk_reasons / policy_action columns visible, filterable,
and explainable, and links every finding to the Agent Timeline.

Endpoints (auth: get_current_user, org isolation identical to agent_timeline):
  GET /risk-findings            — filterable finding feed (keyset-paginated)
  GET /risk-findings/summary    — counts, top risky agents, common reasons
  GET /risk-findings/rules      — the real-time risk rule catalog
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user, resolve_team_scope, is_deny_sentinel
from app.models import TelemetryEvent
from app.risk_processor import RISK_DEFAULTS, RULE_CATALOG, match_rule, risk_level

router = APIRouter(tags=["Risk Findings"])

_LEVEL_MIN = {"low": 20, "medium": 40, "high": 70}


def _org_and_scope(user, db):
    org_id = user.organization_id if hasattr(user, "organization_id") else user.get("organization_id")
    return org_id, resolve_team_scope(user, db)


def _findings_query(db: Session, org_id: int, since: datetime, team_scope: str | None):
    q = db.query(TelemetryEvent).filter(
        TelemetryEvent.organization_id == org_id,
        TelemetryEvent.timestamp >= since,
        or_(TelemetryEvent.risk_score > 0, TelemetryEvent.risk_reasons.isnot(None)),
    )
    if team_scope:
        q = q.filter(TelemetryEvent.team == team_scope)
    return q


def _reasons(e: TelemetryEvent) -> list[str]:
    if not e.risk_reasons:
        return []
    try:
        parsed = json.loads(e.risk_reasons)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _finding_dict(e: TelemetryEvent) -> dict:
    reasons = _reasons(e)
    primary = reasons[0] if reasons else None
    rule_id, rule_name = match_rule(primary)
    return {
        "id": e.id,
        "event_id": e.event_id,
        "agent_id": e.agent_id,
        "asset_key": e.asset_key,
        "agent_name": e.agent_name or e.agent_id,
        "team": e.team,
        "environment": e.environment,
        "timestamp": e.timestamp.isoformat() if e.timestamp else None,
        "event_type": e.event_type,
        "provider": e.provider,
        "model": e.model,
        "tool_name": e.tool_name,
        "action_name": e.action_name,
        "status": e.status,
        "risk_score": e.risk_score,
        "risk_level": risk_level(e.risk_score or 0),
        "policy_action": e.policy_action,
        "risk_reasons": reasons,
        "primary_reason": primary,
        "rule_id": rule_id,
        "rule_name": rule_name,
        # Timeline linkage: GET /agents/{timeline_agent_id}/timeline resolves
        # either the raw agent identity or the asset_key.
        "timeline_agent_id": e.agent_id,
        "timeline_url": f"/agents/{e.agent_id}/timeline",
    }


@router.get("/risk-findings")
async def list_risk_findings(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(50, ge=1, le=200),
    cursor: int | None = Query(None, description="Keyset cursor: findings with id < cursor"),
    min_risk: int | None = Query(None, ge=0, le=100),
    risk_level_f: str | None = Query(None, alias="risk_level", pattern="^(low|medium|high)$"),
    policy_action: str | None = Query(None, pattern="^(allow|warn|block)$"),
    agent_id: str | None = Query(None),
    team: str | None = Query(None),
    environment: str | None = Query(None),
    event_type: str | None = Query(None),
    status: str | None = Query(None, pattern="^(ok|error|blocked)$"),
    model: str | None = Query(None),
    provider: str | None = Query(None),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Event-level risk findings, newest first."""
    org_id, team_scope = _org_and_scope(user, db)
    if is_deny_sentinel(team_scope):
        return {"findings": [], "next_cursor": None, "days": days}

    since = datetime.now(timezone.utc) - timedelta(days=days)
    q = _findings_query(db, org_id, since, team_scope)

    if min_risk is not None:
        q = q.filter(TelemetryEvent.risk_score >= min_risk)
    if risk_level_f:
        q = q.filter(TelemetryEvent.risk_score >= _LEVEL_MIN[risk_level_f])
        # exact-bucket filter: also exclude the levels above
        if risk_level_f == "low":
            q = q.filter(TelemetryEvent.risk_score < _LEVEL_MIN["medium"])
        elif risk_level_f == "medium":
            q = q.filter(TelemetryEvent.risk_score < _LEVEL_MIN["high"])
    if policy_action:
        q = q.filter(TelemetryEvent.policy_action == policy_action)
    if agent_id:
        q = q.filter(or_(TelemetryEvent.agent_id == agent_id, TelemetryEvent.asset_key == agent_id))
    if team:
        q = q.filter(TelemetryEvent.team == team)
    if environment:
        q = q.filter(TelemetryEvent.environment == environment)
    if event_type:
        q = q.filter(TelemetryEvent.event_type == event_type)
    if status:
        q = q.filter(TelemetryEvent.status == status)
    if model:
        q = q.filter(TelemetryEvent.model == model)
    if provider:
        q = q.filter(TelemetryEvent.provider == provider)
    if cursor is not None:
        q = q.filter(TelemetryEvent.id < cursor)

    rows = q.order_by(TelemetryEvent.timestamp.desc(), TelemetryEvent.id.desc()).limit(limit).all()
    return {
        "findings": [_finding_dict(e) for e in rows],
        "next_cursor": rows[-1].id if len(rows) == limit else None,
        "days": days,
    }


@router.get("/risk-findings/summary")
async def risk_findings_summary(
    days: int = Query(7, ge=1, le=90),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aggregate view: totals, top risky agents, most common reasons,
    findings by team and by day."""
    org_id, team_scope = _org_and_scope(user, db)
    empty = {
        "days": days, "total_findings": 0, "high_risk_findings": 0,
        "blocked_events": 0, "warning_events": 0, "top_risky_agents": [],
        "most_common_reasons": [], "findings_by_team": [], "findings_by_day": [],
    }
    if is_deny_sentinel(team_scope):
        return empty

    since = datetime.now(timezone.utc) - timedelta(days=days)
    high = RISK_DEFAULTS["high_risk_score"]
    base = _findings_query(db, org_id, since, team_scope)

    total = base.count()
    if total == 0:
        return empty

    high_count = base.filter(TelemetryEvent.risk_score >= high).count()
    blocked = base.filter(TelemetryEvent.policy_action == "block").count()
    warned = base.filter(TelemetryEvent.policy_action == "warn").count()

    agent_rows = base.with_entities(
        TelemetryEvent.agent_id,
        func.max(TelemetryEvent.agent_name),
        func.count(TelemetryEvent.id),
        func.max(TelemetryEvent.risk_score),
        func.avg(TelemetryEvent.risk_score),
    ).group_by(TelemetryEvent.agent_id).all()
    top_agents = sorted(
        ({"agent_id": a, "agent_name": n or a, "findings": int(c),
          "max_risk_score": int(mx or 0), "avg_risk_score": round(float(av or 0), 1)}
         for a, n, c, mx, av in agent_rows),
        key=lambda r: (-r["max_risk_score"], -r["findings"]),
    )[:10]

    # Reason frequencies: reasons live as JSON arrays, counted app-side over
    # the window (bounded: findings only, one org).
    reason_counts: dict[str, int] = {}
    for (raw,) in base.with_entities(TelemetryEvent.risk_reasons).all():
        if not raw:
            continue
        try:
            for r in json.loads(raw):
                # Normalize parameterized reasons to their rule identity.
                rule_id, rule_name = match_rule(r)
                key = rule_name or r
                reason_counts[key] = reason_counts.get(key, 0) + 1
        except Exception:
            continue
    common_reasons = [
        {"reason": k, "count": v}
        for k, v in sorted(reason_counts.items(), key=lambda kv: -kv[1])[:10]
    ]

    from sqlalchemy import case as _case
    team_rows = base.with_entities(
        TelemetryEvent.team,
        func.count(TelemetryEvent.id),
        func.sum(_case((TelemetryEvent.policy_action != "allow", 1), else_=0)),
    ).group_by(TelemetryEvent.team).all()
    by_team = sorted(
        ({"team": t or "unassigned", "findings": int(c), "policy_violations": int(v or 0)}
         for t, c, v in team_rows),
        key=lambda r: -r["findings"],
    )

    day_rows = base.with_entities(
        func.date(TelemetryEvent.timestamp),
        func.count(TelemetryEvent.id),
    ).group_by(func.date(TelemetryEvent.timestamp)).all()
    by_day = sorted(
        ({"day": str(d), "findings": int(c)} for d, c in day_rows),
        key=lambda r: r["day"],
    )

    return {
        "days": days,
        "total_findings": total,
        "high_risk_findings": high_count,
        "blocked_events": blocked,
        "warning_events": warned,
        "top_risky_agents": top_agents,
        "most_common_reasons": common_reasons,
        "findings_by_team": by_team,
        "findings_by_day": by_day,
    }


@router.get("/risk-findings/rules")
async def risk_findings_rules(user=Depends(get_current_user), db: Session = Depends(get_db)):
    """The real-time risk rule catalog — the rules the ingest worker evaluates
    on every event. Descriptive; thresholds come from RISK_DEFAULTS merged with
    the org's `risk_thresholds` OrgConfig key."""
    org_id, _scope = _org_and_scope(user, db)
    from app.risk_processor import load_risk_config
    cfg = load_risk_config(db, org_id)

    seen: set[str] = set()
    rules = []
    for entry in RULE_CATALOG:
        if entry["rule_id"] in seen:
            continue
        seen.add(entry["rule_id"])
        rules.append({
            "rule_id": entry["rule_id"],
            "rule_name": entry["rule_name"],
            "category": entry["category"],
            "weight": entry["weight"],
            "evaluated": "real-time (at ingestion, by the telemetry worker)",
        })
    return {
        "rules": rules,
        "thresholds": {
            "cost_usd_threshold": cfg["cost_usd_threshold"],
            "latency_ms_threshold": cfg["latency_ms_threshold"],
            "warn_score": cfg["warn_score"],
            "high_risk_score": cfg["high_risk_score"],
            "risky_tools": cfg["risky_tools"],
        },
    }
