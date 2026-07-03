"""
Runtime Discovery read API — Execution Timeline over ingested OTel spans.

Read-only views assembled from otel_spans; no new collection, no writes.
GET /runtime/traces            → recent traces (one row per trace_id)
GET /runtime/traces/{trace_id} → full span tree for the trace waterfall
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import OtelSpan

router = APIRouter(tags=["Runtime"])

# OTLP status code 2 = STATUS_CODE_ERROR (stored as a string by the normalizer)
_STATUS_ERROR = "2"


def _duration_ms(start, end) -> int | None:
    if start is None or end is None:
        return None
    return int((end - start).total_seconds() * 1000)


def _step_type(attrs: dict) -> str:
    """Classify a span into a Runtime Step type for the Execution Timeline."""
    keys = attrs.keys()
    if any(k.startswith("gen_ai.") for k in keys):
        return "llm"
    if any(k.startswith(("tool.", "mcp.")) for k in keys):
        return "tool"
    if any(k.startswith("db.") for k in keys):
        return "database"
    if any(k in ("url.full", "http.url", "server.address") for k in keys):
        return "external_api"
    return "step"


@router.get("/runtime/traces")
async def list_traces(
    service_name: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org_id = current_user.organization_id

    q = (
        db.query(
            OtelSpan.trace_id,
            func.min(OtelSpan.start_time).label("start_time"),
            func.max(OtelSpan.end_time).label("end_time"),
            func.count(OtelSpan.id).label("span_count"),
            func.sum(case((OtelSpan.status_code == _STATUS_ERROR, 1), else_=0)).label("error_count"),
        )
        .filter(OtelSpan.organization_id == org_id)
    )
    if service_name:
        q = q.filter(OtelSpan.service_name == service_name)

    rows = (
        q.group_by(OtelSpan.trace_id)
        .order_by(func.min(OtelSpan.start_time).desc())
        .limit(limit)
        .all()
    )
    trace_ids = [r.trace_id for r in rows]

    # Root span (no parent) per trace gives the request name + owning service.
    roots: dict[str, OtelSpan] = {}
    if trace_ids:
        for span in (
            db.query(OtelSpan)
            .filter(
                OtelSpan.organization_id == org_id,
                OtelSpan.trace_id.in_(trace_ids),
                OtelSpan.parent_span_id.is_(None),
            )
            .all()
        ):
            roots.setdefault(span.trace_id, span)

    out = []
    for r in rows:
        root = roots.get(r.trace_id)
        out.append({
            "trace_id": r.trace_id,
            "root_span_name": root.span_name if root else None,
            "service_name": root.service_name if root else None,
            "start_time": r.start_time.isoformat() if r.start_time else None,
            "end_time": r.end_time.isoformat() if r.end_time else None,
            "duration_ms": _duration_ms(r.start_time, r.end_time),
            "span_count": r.span_count,
            "error_count": int(r.error_count or 0),
        })
    return out


@router.get("/runtime/traces/{trace_id}")
async def get_trace(
    trace_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org_id = current_user.organization_id

    spans = (
        db.query(OtelSpan)
        .filter(
            OtelSpan.organization_id == org_id,
            OtelSpan.trace_id == trace_id,
        )
        .order_by(OtelSpan.start_time.asc(), OtelSpan.id.asc())
        .all()
    )
    if not spans:
        raise HTTPException(status_code=404, detail="Trace not found")

    starts = [s.start_time for s in spans if s.start_time is not None]
    ends = [s.end_time for s in spans if s.end_time is not None]
    trace_start = min(starts) if starts else None
    trace_end = max(ends) if ends else None

    span_dicts = []
    for s in spans:
        attrs: dict = {}
        if s.attributes_json:
            try:
                attrs = json.loads(s.attributes_json)
            except (json.JSONDecodeError, TypeError):
                attrs = {}
        offset_ms = None
        if trace_start is not None and s.start_time is not None:
            offset_ms = int((s.start_time - trace_start).total_seconds() * 1000)
        span_dicts.append({
            "span_id": s.span_id,
            "parent_span_id": s.parent_span_id,
            "name": s.span_name,
            "service_name": s.service_name,
            "kind": s.span_kind,
            "step_type": _step_type(attrs),
            "start_time": s.start_time.isoformat() if s.start_time else None,
            "end_time": s.end_time.isoformat() if s.end_time else None,
            "offset_ms": offset_ms,
            "duration_ms": s.duration_ms,
            "status_code": s.status_code,
            "status_message": s.status_message,
            "error": s.status_code == _STATUS_ERROR,
        })

    root = next((d for d in span_dicts if d["parent_span_id"] is None), None)
    return {
        "trace_id": trace_id,
        "root_span_name": root["name"] if root else None,
        "service_name": root["service_name"] if root else (span_dicts[0]["service_name"] if span_dicts else None),
        "start_time": trace_start.isoformat() if trace_start else None,
        "end_time": trace_end.isoformat() if trace_end else None,
        "duration_ms": _duration_ms(trace_start, trace_end),
        "span_count": len(span_dicts),
        "error_count": sum(1 for d in span_dicts if d["error"]),
        "spans": span_dicts,
    }
