import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.relationships import get_relationships

router = APIRouter()


def _serialize(r) -> dict:
    meta = None
    if r.metadata_json:
        try:
            meta = json.loads(r.metadata_json)
        except Exception:
            meta = None
    return {
        "id":                r.id,
        "source_agent_name": r.source_agent_name,
        "target_type":       r.target_type,
        "target_name":       r.target_name,
        "target_identifier": r.target_identifier,
        "relationship_type": r.relationship_type,
        "evidence_source":   r.evidence_source,
        "confidence_score":  r.confidence_score,
        "request_count":     r.request_count,
        "first_seen_at":     r.first_seen_at.isoformat(),
        "last_seen_at":      r.last_seen_at.isoformat(),
        "metadata":          meta,
    }


@router.get("/relationships", tags=["GET — Read / Monitor"])
def list_relationships(
    source_agent_name: str | None = Query(default=None),
    target_type: str | None = Query(default=None),
    relationship_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return all agent relationships for the current organisation, newest first."""
    rows = get_relationships(
        db,
        organization_id=current_user.organization_id,
        source_agent_name=source_agent_name,
        target_type=target_type,
        relationship_type=relationship_type,
    )
    return [_serialize(r) for r in rows]


@router.get("/relationships/graph", tags=["GET — Read / Monitor"])
def relationships_graph(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Return relationships as a graph with nodes and edges.

    Node types: agent | mcp_tool | mcp_server | workflow | api | database | crm | spreadsheet | unknown
    """
    rows = get_relationships(db, organization_id=current_user.organization_id)

    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    for r in rows:
        agent_node_id = f"agent:{r.source_agent_name}"
        if agent_node_id not in nodes:
            nodes[agent_node_id] = {
                "id":    agent_node_id,
                "label": r.source_agent_name,
                "type":  "agent",
            }

        target_node_id = f"{r.target_type}:{r.target_name}"
        if target_node_id not in nodes:
            nodes[target_node_id] = {
                "id":    target_node_id,
                "label": r.target_name,
                "type":  r.target_type,
            }

        edges.append({
            "source":     agent_node_id,
            "target":     target_node_id,
            "type":       r.relationship_type,
            "count":      r.request_count,
            "confidence": r.confidence_score,
        })

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
    }
