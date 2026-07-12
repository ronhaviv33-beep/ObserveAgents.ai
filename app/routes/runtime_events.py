"""
POST /runtime-events — normalized GenAI runtime event ingestion (Collector R1/R2).

An evidence-ingestion endpoint only. It validates and scrubs normalized GenAI runtime
events (app/runtime_events.py), converts them to span-like dicts, and hands them to the
existing app/otel_normalizer.py:normalize_spans pipeline — the SAME seam the OTLP route
uses. The existing intelligence flow (/intelligence/run) derives assets, findings,
detection rules, and gateway control candidates later, unchanged.

It does NOT: evaluate detection rules inline, create control candidates directly,
enforce policy, block/reroute traffic, mutate Gateway config, or add a separate findings
pipeline.

Auth: Bearer JWT or gk-{key} API key — identical to the OTLP route. org_id is always
resolved server-side from the credential; it is never read from the body.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_proxy_caller
from app.otel_normalizer import normalize_spans
from app.runtime_events import RuntimeEvent, to_span_dict

_log = logging.getLogger("ai_asset_mgmt.runtime_events")

router = APIRouter(tags=["Runtime Events"])

_MAX_EVENTS = 500  # per request; keeps a single call bounded


def _get_org_id(caller) -> int | None:
    if hasattr(caller, "organization_id"):
        return caller.organization_id
    if isinstance(caller, dict):
        return caller.get("organization_id")
    return None


def _get_api_key_id(caller) -> int | None:
    if isinstance(caller, dict):
        return caller.get("api_key_id")
    return None


@router.post("/runtime-events", status_code=202)
async def ingest_runtime_events(
    request: Request,
    db: Session = Depends(get_db),
    caller=Depends(get_proxy_caller),
):
    """Accept `{ "events": [ ... ] }` (or a single event, or a bare list) of normalized
    GenAI runtime events, scrub + convert to span-like dicts, and feed the existing
    normalizer. Returns a 202 with the same counts shape as /otel/v1/traces."""
    if caller is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    org_id = _get_org_id(caller)
    if org_id is None:
        raise HTTPException(status_code=401, detail="No organization associated with this credential")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if isinstance(body, dict) and "events" in body:
        raw_events = body.get("events")
    elif isinstance(body, list):
        raw_events = body
    elif isinstance(body, dict):
        raw_events = [body]  # single event object
    else:
        raise HTTPException(status_code=400, detail="Expected an event object or { \"events\": [ ... ] }")

    if not isinstance(raw_events, list):
        raise HTTPException(status_code=400, detail="`events` must be a list")
    if len(raw_events) > _MAX_EVENTS:
        raise HTTPException(status_code=413, detail=f"Too many events (max {_MAX_EVENTS} per request)")

    events: list[RuntimeEvent] = []
    for i, raw in enumerate(raw_events):
        try:
            events.append(RuntimeEvent.model_validate(raw))
        except ValidationError as exc:
            # Rejects unknown/forbidden fields (extra="forbid") and missing required ids.
            raise HTTPException(status_code=422, detail={"event_index": i, "errors": exc.errors()})

    if not events:
        return {"accepted": True, "events": 0, "spans": 0, "ai_systems": 0,
                "relationships": 0, "provenance_events": 0, "content_redacted": True}

    spans = [to_span_dict(ev) for ev in events]
    result = normalize_spans(db, org_id, spans, api_key_id=_get_api_key_id(caller))

    return {
        "accepted": True,
        "events": len(events),
        "spans": result["spans_ingested"],
        "ai_systems": result["assets_created_or_updated"],
        "relationships": result["relationships_upserted"],
        "provenance_events": result["provenance_events"],
        "otel_assets": result.get("otel_assets_upserted", 0),
        "content_redacted": True,
    }
