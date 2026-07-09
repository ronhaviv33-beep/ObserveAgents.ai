"""
Detection Rules — webhook notifications (R5).

Delivers a webhook per eligible detection-rule finding, from the intelligence
workflow only. Never runs in the OTLP ingestion request path.

    Rules observe and alert. Gateway can optionally enforce later.

Design contract:
- Post-intelligence only. `deliver_detection_rule_notifications` is called by
  app/asset_intelligence.py AFTER the run commits its findings — never from
  /otel/v1/traces, span ingestion, or any telemetry-ingest path.
- detection_rules findings only, open, severity >= channel min_severity.
- Cooldown: one webhook per (org, channel, finding) per 60 minutes. The
  newest delivered NotificationDelivery row is the cooldown ledger.
- Fail-safe: a webhook error is recorded on the delivery row and never
  propagates — the intelligence run always succeeds.
- Privacy: the payload is built only from fields already stored on the
  finding (identifiers, counts, safe evidence). No prompts, responses, tool
  args/results, headers, credentials, or full URLs. Webhook URLs (secrets)
  are Fernet-encrypted at rest and never logged or returned.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import httpx
from sqlalchemy.orm import Session

from app.config import PUBLIC_APP_URL
from app.models import (
    AssetFinding,
    AssetRegistry,
    NotificationChannel,
    NotificationDelivery,
    decrypt_credential,
)

_log = logging.getLogger("ai_asset_mgmt.notifications")

DETECTION_RULES_SOURCE = "detection_rules"
COOLDOWN_MINUTES = 60
_HTTP_TIMEOUT_SECONDS = 4.0
_SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

# Evidence keys that are safe to forward — allowlist, not denylist, so a new
# unscrubbed key can never leak by default.
_SAFE_EVIDENCE_KEYS = (
    "threshold", "span_count", "error_count", "occurrence_count",
    "tool_names", "mcp_methods", "providers", "models", "error_types",
    "sample_span_ids", "rule_type",
)

_RECOMMENDED_ACTION = {
    "rule_mcp_tool_access_threshold": "Review whether this agent should have this MCP/tool access level.",
    "rule_repeated_tool_errors": "Check dependency health, add fallback behavior, or route to human review.",
    "rule_unknown_provider_in_production": "Confirm provider approval and ownership.",
}


def safe_host(url: str) -> str | None:
    """Host only — never the path or query (which may carry a secret token)."""
    try:
        return urlsplit(str(url)).hostname or None
    except (ValueError, TypeError):
        return None


def _naive_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def _safe_evidence(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        ev = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(ev, dict):
        return {}
    return {k: ev[k] for k in _SAFE_EVIDENCE_KEYS if k in ev}


def _build_payload(finding: AssetFinding, agent_name: str, evidence: dict) -> dict:
    links = {
        "security_intelligence": f"{PUBLIC_APP_URL}/#security_intel",
        "rules_alerts": f"{PUBLIC_APP_URL}/#rules_alerts",
        "gateway_control_center": f"{PUBLIC_APP_URL}/#gateway_control_center",
    }
    return {
        "event_type": "detection_rule_alert",
        "org_id": finding.organization_id,
        "finding_id": finding.id,
        "asset_id": finding.asset_id,
        "asset_key": finding.asset_key,
        "agent_name": agent_name,
        "severity": finding.severity,
        "status": finding.status,
        "finding_type": finding.finding_type,
        "source": finding.source,
        "category": finding.category,
        "occurrence_count": finding.occurrence_count or 1,
        "title": finding.title,
        "summary": finding.summary,
        "evidence": evidence,
        "recommended_action": _RECOMMENDED_ACTION.get(finding.finding_type, ""),
        "links": links,
        "created_at": finding.created_at.isoformat() if finding.created_at else None,
        "updated_at": finding.updated_at.isoformat() if finding.updated_at else None,
    }


def _in_cooldown(db: Session, org_id: int, channel_id: int, finding_id: int, now: datetime) -> bool:
    """True if this (org, channel, finding) was delivered within the cooldown window."""
    last = (
        db.query(NotificationDelivery)
        .filter(
            NotificationDelivery.organization_id == org_id,
            NotificationDelivery.channel_id == channel_id,
            NotificationDelivery.finding_id == finding_id,
            NotificationDelivery.status == "delivered",
        )
        .order_by(NotificationDelivery.delivered_at.desc())
        .first()
    )
    if last is None or last.delivered_at is None:
        return False
    delta = _naive_utc(now) - _naive_utc(last.delivered_at)
    return delta < timedelta(minutes=COOLDOWN_MINUTES)


def _post_webhook(url: str, payload: dict) -> tuple[int | None, str | None]:
    """POST JSON with a short timeout, no redirects. Returns (status, error).
    Never raises — network errors come back as (None, "<Exc> ...")."""
    try:
        resp = httpx.post(
            url, json=payload, timeout=_HTTP_TIMEOUT_SECONDS,
            follow_redirects=False,
            headers={"Content-Type": "application/json", "User-Agent": "ObserveAgents-Notifier/1"},
        )
        if resp.status_code >= 400:
            return resp.status_code, f"HTTP {resp.status_code}"
        return resp.status_code, None
    except Exception as exc:  # noqa: BLE001 — a webhook must never break the run
        # Record the exception class only — never the URL (may embed a secret).
        return None, type(exc).__name__


def deliver_detection_rule_notifications(db: Session, org_id: int, now: datetime | None = None) -> dict:
    """Deliver webhooks for this org's open detection-rule findings.

    Called after the intelligence run commits. Safe to call when no channels
    exist (returns zeros). Never raises.
    """
    now = now or datetime.now(timezone.utc)

    channels = (
        db.query(NotificationChannel)
        .filter(
            NotificationChannel.organization_id == org_id,
            NotificationChannel.enabled == True,  # noqa: E712
            NotificationChannel.type == "webhook",
        )
        .all()
    )
    if not channels:
        return {"channels": 0, "delivered": 0, "failed": 0, "skipped": 0}

    findings = (
        db.query(AssetFinding)
        .filter(
            AssetFinding.organization_id == org_id,
            AssetFinding.source == DETECTION_RULES_SOURCE,
            AssetFinding.status == "open",
        )
        .all()
    )
    findings = [f for f in findings if _SEVERITY_RANK.get((f.severity or "").lower(), 0) >= 2]
    if not findings:
        return {"channels": len(channels), "delivered": 0, "failed": 0, "skipped": 0}

    # asset_key → display name (mutable governance layer; falls back to key).
    name_by_key: dict[str, str] = {}
    for reg in db.query(AssetRegistry).filter(AssetRegistry.organization_id == org_id).all():
        if reg.asset_key:
            name_by_key[reg.asset_key] = reg.agent_name or reg.agent_id_raw or reg.asset_key

    delivered = failed = skipped = 0
    for channel in channels:
        min_rank = _SEVERITY_RANK.get((channel.min_severity or "medium").lower(), 2)
        try:
            url = (json.loads(decrypt_credential(channel.encrypted_config_json)) or {}).get("url")
        except Exception:  # noqa: BLE001 — bad/rotated key must not break the run
            url = None
        if not url:
            continue

        for f in findings:
            if _SEVERITY_RANK.get((f.severity or "").lower(), 0) < min_rank:
                continue
            if _in_cooldown(db, org_id, channel.id, f.id, now):
                skipped += 1
                db.add(NotificationDelivery(
                    organization_id=org_id, channel_id=channel.id, finding_id=f.id,
                    status="skipped_cooldown", attempt_count=0,
                    request_url_host=channel.url_host,
                ))
                continue

            evidence = _safe_evidence(f.evidence_json)
            agent_name = name_by_key.get(f.asset_key or "", f.asset_key or "unknown")
            payload = _build_payload(f, agent_name, evidence)
            status_code, err = _post_webhook(url, payload)
            row = NotificationDelivery(
                organization_id=org_id, channel_id=channel.id, finding_id=f.id,
                attempt_count=1, request_url_host=channel.url_host,
                response_status=status_code, last_error=(err[:255] if err else None),
            )
            if err is None:
                row.status = "delivered"
                row.delivered_at = now
                delivered += 1
            else:
                row.status = "failed"
                failed += 1
            db.add(row)

    db.commit()
    return {"channels": len(channels), "delivered": delivered, "failed": failed, "skipped": skipped}
