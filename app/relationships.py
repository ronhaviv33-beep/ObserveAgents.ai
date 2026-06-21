"""
Persistence service for AgentRelationship records.

upsert_relationship() is non-fatal — any DB error is logged as a warning
so relationship mapping never breaks customer proxy traffic.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.relationship_resolver import ResolvedRelationship

_log = logging.getLogger("ai_asset_mgmt.relationships")


def upsert_relationship(
    db: Session,
    organization_id: int,
    rel: ResolvedRelationship,
    source_agent_id: str | None = None,
) -> None:
    """
    Insert or update an AgentRelationship row.

    Upsert key: (organization_id, source_agent_name, target_type, target_name, relationship_type)
    On conflict:
      - last_seen_at → now
      - request_count += 1
      - confidence_score = max(existing, new)
      - metadata_json merged (new keys win, no prompt/response stored)
    """
    try:
        from app.models import AgentRelationship
        now = datetime.now(timezone.utc)

        existing = db.query(AgentRelationship).filter(
            AgentRelationship.organization_id   == organization_id,
            AgentRelationship.source_agent_name == rel.source_agent_name,
            AgentRelationship.target_type       == rel.target_type,
            AgentRelationship.target_name       == rel.target_name,
            AgentRelationship.relationship_type == rel.relationship_type,
        ).first()

        if existing:
            existing.last_seen_at    = now
            existing.request_count   += 1
            existing.confidence_score = max(existing.confidence_score, rel.confidence_score)
            if rel.metadata:
                try:
                    current_meta = json.loads(existing.metadata_json or "{}")
                except Exception:
                    current_meta = {}
                current_meta.update(rel.metadata)
                existing.metadata_json = json.dumps(current_meta)
        else:
            meta_str = json.dumps(rel.metadata) if rel.metadata else None
            db.add(AgentRelationship(
                organization_id   = organization_id,
                source_agent_id   = source_agent_id,
                source_agent_name = rel.source_agent_name,
                target_type       = rel.target_type,
                target_name       = rel.target_name,
                relationship_type = rel.relationship_type,
                evidence_source   = rel.evidence_source,
                confidence_score  = rel.confidence_score,
                first_seen_at     = now,
                last_seen_at      = now,
                request_count     = 1,
                metadata_json     = meta_str,
            ))

        db.commit()
    except Exception:
        db.rollback()
        _log.warning("Failed to upsert relationship for %s → %s",
                     rel.source_agent_name, rel.target_name, exc_info=True)


def get_relationships(
    db: Session,
    organization_id: int,
    source_agent_name: str | None = None,
    target_type: str | None = None,
    relationship_type: str | None = None,
) -> list:
    from app.models import AgentRelationship
    q = db.query(AgentRelationship).filter(
        AgentRelationship.organization_id == organization_id
    )
    if source_agent_name:
        q = q.filter(AgentRelationship.source_agent_name == source_agent_name)
    if target_type:
        q = q.filter(AgentRelationship.target_type == target_type)
    if relationship_type:
        q = q.filter(AgentRelationship.relationship_type == relationship_type)
    return q.order_by(AgentRelationship.last_seen_at.desc()).all()
