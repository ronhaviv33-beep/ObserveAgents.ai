"""
POST /otel/v1/traces — OTLP/HTTP trace ingestion endpoint (JSON + protobuf).

Auth: Bearer JWT or gk-{key} API key (same as proxy routes).
Content-Type:
  - application/json (charset params allowed; missing content-type is
    treated as JSON for backward compatibility)
  - application/x-protobuf / application/protobuf /
    application/vnd.google.protobuf (OTLP ExportTraceServiceRequest)
Traces only — metrics/logs payloads are rejected with a clear message.

Privacy guarantee: raw gen_ai.input.messages, gen_ai.output.messages,
gen_ai.system_instructions, tool.arguments, and tool.result are never
stored. SHA-256 hash + byte size + redacted=true are stored instead.
Identical for both encodings — protobuf feeds the same scrub pipeline.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_proxy_caller
from app.otel_parser import parse_otlp_json, parse_otlp_protobuf
from app.otel_normalizer import normalize_spans

_log = logging.getLogger("ai_asset_mgmt.otel")

router = APIRouter(tags=["OTel Ingestion"])

_PROTOBUF_CONTENT_TYPES = frozenset({
    "application/x-protobuf",
    "application/protobuf",
    "application/vnd.google.protobuf",
})


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
    Accept an OTLP/HTTP payload (JSON or protobuf) and ingest spans.

    Returns a 202 Accepted with a summary of what was created/updated.
    Duplicate spans (same org + trace_id + span_id) are silently skipped.
    Both encodings feed the identical privacy/normalization pipeline.
    """
    if caller is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    org_id = _get_org_id(caller)
    if org_id is None:
        raise HTTPException(
            status_code=401,
            detail="No organization associated with this credential",
        )

    # Media type without parameters (e.g. "application/json; charset=utf-8").
    # Missing content-type is treated as JSON for backward compatibility.
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()

    if content_type in _PROTOBUF_CONTENT_TYPES:
        raw = await request.body()
        if not raw:
            raise HTTPException(status_code=400, detail="Empty request body")
        try:
            spans, resource_span_count = parse_otlp_protobuf(raw)
        except Exception:
            # Never echo the raw body — a decode failure message is enough.
            raise HTTPException(status_code=400, detail="Invalid OTLP protobuf body")
        if resource_span_count == 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No trace data found in protobuf body — expected an OTLP "
                    "ExportTraceServiceRequest. Metrics and logs ingestion is "
                    "not supported on this endpoint."
                ),
            )
    elif content_type in ("application/json", ""):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")
        try:
            spans = parse_otlp_json(body)
        except Exception as exc:
            _log.warning("OTLP parse error for org=%s: %s", org_id, exc)
            raise HTTPException(status_code=400, detail=f"OTLP parse error: {exc}")
        resource_span_count = len(body.get("resourceSpans") or [])
    else:
        raise HTTPException(
            status_code=415,
            detail=(
                "Unsupported Content-Type. Send OTLP traces as application/json "
                "or application/x-protobuf (also accepted: application/protobuf, "
                "application/vnd.google.protobuf)."
            ),
        )

    if not spans:
        # Valid envelope with zero spans is accepted (202) with zero counts —
        # same behavior for JSON and protobuf.
        return {
            "accepted": True,
            "resource_spans": resource_span_count,
            "spans": 0,
            "ai_systems": 0,
            "relationships": 0,
            "provenance_events": 0,
            "content_redacted": True,
        }

    result = normalize_spans(db, org_id, spans)

    return {
        "accepted": True,
        "resource_spans": resource_span_count,
        "spans": result["spans_ingested"],
        "ai_systems": result["assets_created_or_updated"],
        "relationships": result["relationships_upserted"],
        "provenance_events": result["provenance_events"],
        "otel_assets": result.get("otel_assets_upserted", 0),
        "content_redacted": True,
    }
