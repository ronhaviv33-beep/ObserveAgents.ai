"""
POST /otel/v1/traces — OTLP/HTTP JSON trace ingestion endpoint.

Auth: Bearer JWT or gk-{key} API key (same as proxy routes).
Content-Type: application/json (protobuf not supported).

Privacy guarantee: raw gen_ai.input.messages, gen_ai.output.messages,
gen_ai.system_instructions, tool.arguments, and tool.result are never
stored. SHA-256 hash + byte size + redacted=true are stored instead.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_proxy_caller
from app.otel_parser import parse_otlp_json
from app.otel_normalizer import normalize_spans

_log = logging.getLogger("ai_asset_mgmt.otel")

router = APIRouter(tags=["OTel Ingestion"])


def _get_org_id(caller) -> int | None:
    """Extract organization_id from a User ORM object or API-key dict."""
    if hasattr(caller, "organization_id"):
        return caller.organization_id
    if isinstance(caller, dict):
        return caller.get("organization_id")
    return None


@router.post("/otel/v1/traces", status_code=202)
async def ingest_traces(
    request: Request,
    db: Session = Depends(get_db),
    caller=Depends(get_proxy_caller),
):
    """
    Accept an OTLP/HTTP JSON payload and ingest spans into ObserveAgents.ai.

    Returns a 202 Accepted with a summary of what was created/updated.
    Duplicate spans (same org + trace_id + span_id) are silently skipped.
    """
    if caller is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    org_id = _get_org_id(caller)
    if org_id is None:
        raise HTTPException(
            status_code=401,
            detail="No organization associated with this credential",
        )

    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type and content_type:
        raise HTTPException(
            status_code=415,
            detail="Content-Type must be application/json. Protobuf is not supported.",
        )

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    try:
        spans = parse_otlp_json(body)
    except Exception as exc:
        _log.warning("OTLP parse error for org=%s: %s", org_id, exc)
        raise HTTPException(status_code=400, detail=f"OTLP parse error: {exc}")

    if not spans:
        return {
            "accepted": True,
            "resource_spans": len(body.get("resourceSpans") or []),
            "spans": 0,
            "ai_systems": 0,
            "relationships": 0,
            "provenance_events": 0,
            "content_redacted": True,
        }

    result = normalize_spans(db, org_id, spans)

    return {
        "accepted": True,
        "resource_spans": len(body.get("resourceSpans") or []),
        "spans": result["spans_ingested"],
        "ai_systems": result["assets_created_or_updated"],
        "relationships": result["relationships_upserted"],
        "provenance_events": result["provenance_events"],
        "otel_assets": result.get("otel_assets_upserted", 0),
        "content_redacted": True,
    }
