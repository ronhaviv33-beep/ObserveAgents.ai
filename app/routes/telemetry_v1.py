"""
POST /api/v1/telemetry/batch — high-throughput batch telemetry ingestion.

Intake only: validates events, deduplicates on (org_id, event_id), preserves
the raw payload verbatim in telemetry_events_raw (which doubles as the ingest
queue), and wakes the background worker. Normalization, risk scoring, and
metrics aggregation all happen in app/telemetry_ingest/worker.py — the API
stays fast and never does heavy processing inline.

Partial acceptance: one bad event never fails the batch. The response reports
accepted / duplicated / failed counts plus per-event errors.

Auth: Bearer JWT or gk-{key} API key — identical to /otel/v1/traces and
/runtime-events. org_id is always resolved server-side from the credential;
it is never read from the body.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_proxy_caller
from app.models import TelemetryEventRaw
from app.telemetry_ingest import worker as ingest_worker
from app.telemetry_ingest.schemas import (
    MAX_BATCH_EVENTS,
    BatchIngestResponse,
    EventError,
    TelemetryEventIn,
)

_log = logging.getLogger("ai_asset_mgmt.telemetry_v1")

router = APIRouter(tags=["Telemetry Ingestion"])

_DEDUP_CHUNK = 500  # IN() clause chunk size for the existing-event_id lookup


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


def _first_error_message(exc: ValidationError) -> str:
    errs = exc.errors()
    if not errs:
        return "Invalid event"
    first = errs[0]
    loc = ".".join(str(p) for p in first.get("loc", ()))
    msg = first.get("msg", "invalid")
    return f"{loc}: {msg}" if loc else msg


def _existing_event_ids(db: Session, org_id: int, event_ids: list[str]) -> set[str]:
    """Return event_ids already present in telemetry_events_raw for this org."""
    found: set[str] = set()
    for i in range(0, len(event_ids), _DEDUP_CHUNK):
        chunk = event_ids[i:i + _DEDUP_CHUNK]
        rows = db.query(TelemetryEventRaw.event_id).filter(
            TelemetryEventRaw.organization_id == org_id,
            TelemetryEventRaw.event_id.in_(chunk),
        ).all()
        found.update(r[0] for r in rows)
    return found


@router.post("/api/v1/telemetry/batch", status_code=202, response_model=BatchIngestResponse)
async def ingest_telemetry_batch(
    request: Request,
    db: Session = Depends(get_db),
    caller=Depends(get_proxy_caller),
):
    """Accept `{ "events": [ ... ] }` (or a bare list) of telemetry events.
    Returns 202 with accepted/duplicated/failed counts and per-event errors."""
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
    else:
        raise HTTPException(status_code=400, detail='Expected { "events": [ ... ] } or a JSON array')

    if not isinstance(raw_events, list):
        raise HTTPException(status_code=400, detail="`events` must be a list")
    if len(raw_events) > MAX_BATCH_EVENTS:
        raise HTTPException(status_code=413, detail=f"Too many events (max {MAX_BATCH_EVENTS} per request)")

    api_key_id = _get_api_key_id(caller)

    # Event-level validation with partial acceptance: invalid events are
    # reported per-index and never fail the batch.
    errors: list[EventError] = []
    valid: list[tuple[dict, TelemetryEventIn]] = []
    for i, raw in enumerate(raw_events):
        if not isinstance(raw, dict):
            errors.append(EventError(index=i, event_id=None, error="Event must be a JSON object"))
            continue
        try:
            valid.append((raw, TelemetryEventIn.model_validate(raw)))
        except ValidationError as exc:
            eid = raw.get("event_id")
            errors.append(EventError(
                index=i,
                event_id=eid if isinstance(eid, str) else None,
                error=_first_error_message(exc),
            ))

    duplicated = 0

    # Intra-batch dedup: first occurrence wins.
    seen: set[str] = set()
    deduped: list[tuple[dict, TelemetryEventIn]] = []
    for raw, event in valid:
        if event.event_id in seen:
            duplicated += 1
            continue
        seen.add(event.event_id)
        deduped.append((raw, event))

    # Cross-batch dedup against rows already ingested for this org.
    existing = _existing_event_ids(db, org_id, [e.event_id for _, e in deduped]) if deduped else set()
    to_insert: list[tuple[dict, TelemetryEventIn]] = []
    for raw, event in deduped:
        if event.event_id in existing:
            duplicated += 1
        else:
            to_insert.append((raw, event))

    def _make_row(raw: dict, event: TelemetryEventIn) -> TelemetryEventRaw:
        return TelemetryEventRaw(
            organization_id=org_id,
            event_id=event.event_id,
            api_key_id=api_key_id,
            raw_payload=json.dumps(raw, ensure_ascii=False),
            status="pending",
        )

    accepted = 0
    if to_insert:
        try:
            db.add_all([_make_row(raw, event) for raw, event in to_insert])
            db.commit()
            accepted = len(to_insert)
        except IntegrityError:
            # Concurrent request raced us on (org_id, event_id). Fall back to
            # row-by-row savepoints — dialect-agnostic, no ON CONFLICT needed.
            db.rollback()
            for raw, event in to_insert:
                try:
                    with db.begin_nested():
                        db.add(_make_row(raw, event))
                    accepted += 1
                except IntegrityError:
                    duplicated += 1
            db.commit()

    if accepted:
        ingest_worker.kick(db)

    return BatchIngestResponse(
        accepted=accepted,
        duplicated=duplicated,
        failed=len(errors),
        errors=errors,
        queued=accepted > 0,
    )
