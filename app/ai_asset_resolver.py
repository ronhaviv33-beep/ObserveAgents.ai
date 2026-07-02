"""
AI asset resolver — maps OTel identity signals to canonical AssetRegistry rows.

AssetRegistry is the single source of truth for AI inventory (conceptually ai_assets).
This module finds or confirms the AssetRegistry id for a given OTel-discovered
service/agent identity so OtelAsset rows can link back to it.

Scoped strictly to organization_id — no cross-org matching ever occurs.
Does not modify discovery fields on 'verified' or 'managed' assets.
"""
from __future__ import annotations

import hashlib
import logging

from sqlalchemy.orm import Session

_log = logging.getLogger("ai_asset_mgmt.otel")


def _make_asset_key(org_id: int, name: str) -> str:
    """Same hash used by otel_normalizer._upsert_asset — keeps keys aligned."""
    return hashlib.sha256(f"{org_id}:{name}".encode()).hexdigest()[:64]


def resolve_asset_registry_id(
    db: Session,
    org_id: int,
    agent_name: str,
) -> int | None:
    """
    Return the AssetRegistry.id for the given org + agent/service name.

    Looks up by asset_key (sha256(org_id:agent_name)) — the same key written by
    otel_normalizer._upsert_asset, guaranteeing alignment.

    Returns None if no matching row exists (e.g. upsert failed upstream).
    Scoped strictly to organization_id.
    """
    from app.models import AssetRegistry
    try:
        asset_key = _make_asset_key(org_id, agent_name)
        row = db.query(AssetRegistry).filter(
            AssetRegistry.organization_id == org_id,
            AssetRegistry.asset_key == asset_key,
        ).first()
        return row.id if row else None
    except Exception:
        _log.warning("resolve_asset_registry_id failed for org=%s name=%s", org_id, agent_name, exc_info=True)
        return None
