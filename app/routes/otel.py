"""
POST /otel/v1/traces — OTLP/HTTP trace ingestion endpoint (JSON + protobuf).

Auth: Bearer JWT or gk-{key} API key (same as proxy routes).
Content-Type:
  - application/json (charset params allowed; missing content-type is
    treated as JSON for backward compatibility)
  - application/x-protobuf / application/protobuf /
    application/vnd.google.protobuf (OTLP ExportTraceServiceRequest)
Content-Encoding: gzip is supported for both encodings (Collector exporters
compress by default); other encodings are rejected with 415.
Traces only — metrics/logs payloads are rejected with a clear message.

Privacy guarantee: raw gen_ai.input.messages, gen_ai.output.messages,
gen_ai.system_instructions, tool.arguments, and tool.result are never
stored. SHA-256 hash + byte size + redacted=true are stored instead.
Identical for both encodings — protobuf feeds the same scrub pipeline.
"""
from __future__ import annotations

import json
import logging
import zlib

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

# Zip-bomb guard: cap on the decompressed size of a gzip request body.
_MAX_DECOMPRESSED_BYTES = 64 * 1024 * 1024  # 64 MB


def _decompressed_body(raw: bytes, content_encoding: str) -> bytes:
    """Return the request payload bytes, gunzipping if the client declared it.

    OpenTelemetry Collector exporters compress with gzip BY DEFAULT, and
    Starlette does not transparently decompress request bodies, so this is
    required for out-of-the-box Collector compatibility. Per the OTLP/HTTP
    spec, an unsupported Content-Encoding is rejected with 415.
    """
    if content_encoding in ("", "identity"):
        return raw
    if content_encoding == "gzip":
        # 16 + MAX_WBITS = expect a gzip (not zlib) header.
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            payload = decompressor.decompress(raw, _MAX_DECOMPRESSED_BYTES)
        except zlib.error:
            # Never echo the body — a decode failure message is enough.
            raise HTTPException(
                status_code=400,
                detail="Invalid gzip-compressed request body (Content-Encoding: gzip was declared but the body could not be decompressed)",
            )
        if decompressor.unconsumed_tail:
            raise HTTPException(
                status_code=413,
                detail=f"Decompressed payload exceeds the {_MAX_DECOMPRESSED_BYTES // (1024 * 1024)} MB limit",
            )
        return payload
    raise HTTPException(
        status_code=415,
        detail=f"Unsupported Content-Encoding '{content_encoding}'. Use gzip or no compression.",
    )


def _get_org_id(caller) -> int | None:
    """Extract organization_id from a User ORM object or API-key dict."""
    if hasattr(caller, "organization_id"):
        return caller.organization_id
    if isinstance(caller, dict):
        return caller.get("organization_id")
    return None


def _get_api_key_id(caller) -> int | None:
    """The ingestion credential id, when the caller authenticated with a gk- key.

    Dashboard/JWT callers (User objects) return None — only Collector-style API
    keys attribute their spans.
    """
    if isinstance(caller, dict):
        return caller.get("api_key_id")
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
    content_encoding = request.headers.get("content-encoding", "").strip().lower()

    if content_type in _PROTOBUF_CONTENT_TYPES:
        raw = _decompressed_body(await request.body(), content_encoding)
        if not raw:
            raise HTTPException(status_code=400, detail="Empty request body")
        try:
            spans, resource_span_count = parse_otlp_protobuf(raw)
        except Exception:
            # Never echo the raw body — size + declared encoding are enough to
            # diagnose the two common causes (compressed body without the
            # header, or a non-OTLP payload).
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid OTLP protobuf body ({len(raw)} bytes, "
                    f"content-encoding: {content_encoding or 'none'}). "
                    "Expected an ExportTraceServiceRequest. If exporting from an "
                    "OpenTelemetry Collector, use the otlp_http exporter with "
                    "encoding: proto; compressed bodies must declare "
                    "Content-Encoding: gzip."
                ),
            )
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
        raw = _decompressed_body(await request.body(), content_encoding)
        try:
            body = json.loads(raw)
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

    result = normalize_spans(db, org_id, spans, api_key_id=_get_api_key_id(caller))

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
