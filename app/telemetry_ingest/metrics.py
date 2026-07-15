"""
Precomputed daily per-agent metrics over normalized telemetry events.

Strategy: recompute-on-write. For every (org, agent, UTC day) bucket touched
by a worker batch, the whole day's aggregates are recomputed from
telemetry_events and upserted into agent_metrics_daily. Recomputation (not
incrementing) keeps the rollup exactly correct under the queue's
at-least-once processing semantics — replays can never double-count.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timezone

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models import AgentMetricsDaily, TelemetryEvent
from app.risk_processor import RISK_DEFAULTS

_log = logging.getLogger("ai_asset_mgmt.telemetry_metrics")

Bucket = tuple[int, str, date]  # (organization_id, agent_id, UTC day)


def event_day(ts: datetime) -> date:
    """UTC calendar day for an event timestamp — the single bucketing function
    shared by the worker and any reader, so day boundaries always agree."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).date()


def _day_range(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = datetime.combine(day, time.max, tzinfo=timezone.utc)
    return start, end


def recompute_bucket(db: Session, org_id: int, agent_id: str, day: date,
                     high_risk_score: int | None = None) -> None:
    """Recompute one (org, agent, day) rollup row from telemetry_events."""
    high_risk = high_risk_score if high_risk_score is not None else RISK_DEFAULTS["high_risk_score"]
    start, end = _day_range(day)

    base = db.query(
        func.count(TelemetryEvent.id),
        func.sum(case((TelemetryEvent.status == "error", 1), else_=0)),
        func.sum(case((TelemetryEvent.status == "blocked", 1), else_=0)),
        func.sum(case((TelemetryEvent.policy_action != "allow", 1), else_=0)),
        func.sum(case((TelemetryEvent.risk_score >= high_risk, 1), else_=0)),
        func.sum(func.coalesce(TelemetryEvent.input_tokens, 0)),
        func.sum(func.coalesce(TelemetryEvent.output_tokens, 0)),
        func.sum(func.coalesce(TelemetryEvent.total_tokens, 0)),
        func.sum(func.coalesce(TelemetryEvent.cost_usd, 0.0)),
        func.avg(TelemetryEvent.latency_ms),
        func.max(TelemetryEvent.latency_ms),
        func.avg(TelemetryEvent.risk_score),
        func.max(TelemetryEvent.risk_score),
    ).filter(
        TelemetryEvent.organization_id == org_id,
        TelemetryEvent.agent_id == agent_id,
        TelemetryEvent.timestamp >= start,
        TelemetryEvent.timestamp <= end,
    ).one()

    (events_count, errors, blocked, violations, high_risk_events,
     in_tokens, out_tokens, tot_tokens, cost, avg_lat, max_lat, avg_risk, max_risk) = base

    existing = db.query(AgentMetricsDaily).filter(
        AgentMetricsDaily.organization_id == org_id,
        AgentMetricsDaily.agent_id == agent_id,
        AgentMetricsDaily.day == day,
    ).first()

    if not events_count:
        # Day has no events (e.g. after a purge) — remove a stale rollup row.
        if existing is not None:
            db.delete(existing)
        return

    model_rows = db.query(
        TelemetryEvent.model,
        func.count(TelemetryEvent.id),
        func.sum(func.coalesce(TelemetryEvent.total_tokens, 0)),
        func.sum(func.coalesce(TelemetryEvent.cost_usd, 0.0)),
    ).filter(
        TelemetryEvent.organization_id == org_id,
        TelemetryEvent.agent_id == agent_id,
        TelemetryEvent.timestamp >= start,
        TelemetryEvent.timestamp <= end,
        TelemetryEvent.model.isnot(None),
    ).group_by(TelemetryEvent.model).all()
    models = {
        m: {"events": int(n), "tokens": int(t or 0), "cost_usd": round(float(c or 0.0), 6)}
        for m, n, t, c in model_rows
    }

    latest = db.query(TelemetryEvent).filter(
        TelemetryEvent.organization_id == org_id,
        TelemetryEvent.agent_id == agent_id,
        TelemetryEvent.timestamp >= start,
        TelemetryEvent.timestamp <= end,
    ).order_by(TelemetryEvent.timestamp.desc(), TelemetryEvent.id.desc()).first()

    values = dict(
        asset_key=latest.asset_key if latest else None,
        agent_name=latest.agent_name if latest else None,
        team=latest.team if latest else None,
        environment=latest.environment if latest else None,
        events_count=int(events_count),
        error_count=int(errors or 0),
        blocked_count=int(blocked or 0),
        policy_violations=int(violations or 0),
        high_risk_events=int(high_risk_events or 0),
        total_input_tokens=int(in_tokens or 0),
        total_output_tokens=int(out_tokens or 0),
        total_tokens=int(tot_tokens or 0),
        total_cost_usd=round(float(cost or 0.0), 6),
        avg_latency_ms=round(float(avg_lat), 2) if avg_lat is not None else None,
        max_latency_ms=float(max_lat) if max_lat is not None else None,
        avg_risk_score=round(float(avg_risk), 2) if avg_risk is not None else None,
        max_risk_score=int(max_risk or 0),
        models_json=json.dumps(models) if models else None,
        updated_at=datetime.now(timezone.utc),
    )

    if existing is not None:
        for k, v in values.items():
            setattr(existing, k, v)
    else:
        db.add(AgentMetricsDaily(
            organization_id=org_id, agent_id=agent_id, day=day, **values,
        ))


def recompute_buckets(db: Session, buckets: set[Bucket]) -> None:
    """Recompute every touched rollup bucket. Caller commits."""
    for org_id, agent_id, day in sorted(buckets):
        try:
            recompute_bucket(db, org_id, agent_id, day)
        except Exception:
            _log.warning("metrics recompute failed for org=%s agent=%s day=%s",
                         org_id, agent_id, day, exc_info=True)
            db.rollback()
