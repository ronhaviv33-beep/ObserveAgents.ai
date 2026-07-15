"""
Raw telemetry event -> normalized TelemetryEvent column values.

Responsibilities:
  - parse/normalize the timestamp to timezone-aware UTC
  - fill in total_tokens and cost_usd (via the versioned pricing registry)
    when the caller omitted them
  - upsert the agent into the existing AssetRegistry (same asset_key
    convention as OTel ingestion) so batch-ingested agents appear in the
    Agent Inventory alongside OTel-discovered ones
  - enrich missing owner/team/environment from the AssetRegistry record

The output is a plain dict of TelemetryEvent constructor kwargs — persistence
stays in the worker.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import pricing_registry
from app.models import AssetRegistry
from app.otel_normalizer import _make_asset_key, _upsert_asset

_log = logging.getLogger("ai_asset_mgmt.telemetry_normalizer")


def _parse_timestamp(value, fallback: datetime) -> datetime:
    """Parse an ISO8601 timestamp to aware-UTC; fall back to receive time."""
    if isinstance(value, datetime):
        ts = value
    elif isinstance(value, str) and value.strip():
        try:
            ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return fallback
    else:
        return fallback
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _str_or_none(value, max_len: int) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s[:max_len] if s else None


def _int_or_none(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _float_or_none(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def normalize(db: Session, org_id: int, raw: dict, received_at: datetime | None = None) -> dict:
    """Return TelemetryEvent constructor kwargs (minus org/event ids, which the
    worker supplies from the raw queue row). Raises on unusable payloads —
    the worker converts that into a failed queue row."""
    received_at = received_at or datetime.now(timezone.utc)

    agent_id = _str_or_none(raw.get("agent_id"), 256)
    if not agent_id:
        raise ValueError("agent_id is required")

    team = _str_or_none(raw.get("team"), 128)
    owner = _str_or_none(raw.get("owner"), 256)
    environment = _str_or_none(raw.get("environment"), 64)
    agent_name = _str_or_none(raw.get("agent_name"), 256) or agent_id

    # Register/associate the agent with the existing inventory. Same
    # asset_key convention as OTel ingestion, so both pipelines converge on
    # one AssetRegistry record per agent identity.
    resource_attrs = {
        k: v for k, v in {
            "team": team,
            "service.owner": owner,
            "deployment.environment": environment,
        }.items() if v
    }
    asset_id = _upsert_asset(
        db, org_id, agent_id, resource_attrs,
        display_name=agent_name,
        identity_tier="declared",
    )
    asset_key = _make_asset_key(org_id, agent_id)

    # Enrich missing governance fields from the registry record (it may have
    # been claimed/annotated by an admin, or populated by a previous event).
    if asset_id is not None and not (owner and team and environment):
        asset = db.query(AssetRegistry).filter(AssetRegistry.id == asset_id).first()
        if asset is not None:
            owner = owner or _str_or_none(asset.owner, 256)
            team = team or _str_or_none(asset.team, 128)
            environment = environment or _str_or_none(asset.environment, 64)

    input_tokens = _int_or_none(raw.get("input_tokens"))
    output_tokens = _int_or_none(raw.get("output_tokens"))
    total_tokens = _int_or_none(raw.get("total_tokens"))
    if total_tokens is None and (input_tokens is not None or output_tokens is not None):
        total_tokens = (input_tokens or 0) + (output_tokens or 0)

    model = _str_or_none(raw.get("model"), 255)
    cost_usd = _float_or_none(raw.get("cost_usd"))
    cost_estimated = False
    if cost_usd is None and model and (input_tokens or output_tokens):
        try:
            cost_usd, _meta = pricing_registry.calculate_cost(
                db, model, input_tokens or 0, output_tokens or 0, organization_id=org_id,
            )
            cost_estimated = True
        except Exception:
            _log.warning("cost estimation failed for model %r (org=%s)", model, org_id, exc_info=True)

    status = _str_or_none(raw.get("status"), 32) or "ok"
    if status not in ("ok", "error", "blocked"):
        status = "ok"

    return {
        "agent_id": agent_id,
        "asset_key": asset_key,
        "agent_name": agent_name,
        "team": team,
        "environment": environment,
        "owner": owner,
        "timestamp": _parse_timestamp(raw.get("timestamp"), received_at),
        "event_type": _str_or_none(raw.get("event_type"), 64) or "llm_call",
        "trace_id": _str_or_none(raw.get("trace_id"), 64),
        "span_id": _str_or_none(raw.get("span_id"), 32),
        "parent_span_id": _str_or_none(raw.get("parent_span_id"), 32),
        "provider": _str_or_none(raw.get("provider"), 128),
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cost_usd": cost_usd,
        "cost_estimated": cost_estimated,
        "latency_ms": _float_or_none(raw.get("latency_ms")),
        "status": status,
        "error_message": _str_or_none(raw.get("error_message"), 512),
        "tool_name": _str_or_none(raw.get("tool_name"), 255),
        "action_name": _str_or_none(raw.get("action_name"), 255),
        # Passed through for the risk processor; not a TelemetryEvent column.
        "upstream_policy_action": _str_or_none(raw.get("policy_action"), 16),
    }
