"""
OTLP/HTTP parser for ObserveAgents.ai OTel trace ingestion.

Two entry points producing the SAME flat span-dict shape, so the whole
downstream pipeline (privacy scrub, normalizer, asset intelligence) is
shared:

  parse_otlp_json(body)      — OTLP/HTTP JSON envelope
  parse_otlp_protobuf(raw)   — OTLP/HTTP protobuf ExportTraceServiceRequest

Does not validate content — callers catch parse errors and return HTTP 400.
"""
from __future__ import annotations


def _resolve_any_value(av: dict) -> object:
    """Recursively resolve an OTel AnyValue to a Python native type."""
    if not isinstance(av, dict):
        return av
    if "stringValue" in av:
        return av["stringValue"]
    if "intValue" in av:
        return int(av["intValue"])
    if "doubleValue" in av:
        return float(av["doubleValue"])
    if "boolValue" in av:
        return bool(av["boolValue"])
    if "bytesValue" in av:
        return av["bytesValue"]  # keep as base64 string
    if "arrayValue" in av:
        return [_resolve_any_value(v) for v in (av["arrayValue"].get("values") or [])]
    if "kvlistValue" in av:
        return {
            kv["key"]: _resolve_any_value(kv.get("value", {}))
            for kv in (av["kvlistValue"].get("values") or [])
            if "key" in kv
        }
    return None


def _resolve_attrs(raw_attrs: list) -> dict:
    """Convert a list of {key, value} OTel attribute objects to a plain dict."""
    result = {}
    for item in (raw_attrs or []):
        key = item.get("key")
        if key:
            result[key] = _resolve_any_value(item.get("value", {}))
    return result


def parse_otlp_json(body: dict) -> list[dict]:
    """
    Parse an OTLP/HTTP JSON payload into a flat list of span dicts.

    Each dict has:
      trace_id, span_id, parent_span_id, name, kind,
      start_time_unix_nano, end_time_unix_nano,
      status (dict), attributes (dict), resource_attributes (dict),
      events (list), links (list)
    """
    spans: list[dict] = []
    for resource_span in (body.get("resourceSpans") or []):
        resource = resource_span.get("resource") or {}
        resource_attrs = _resolve_attrs(resource.get("attributes") or [])

        # Support both scopeSpans and legacy instrumentationLibrarySpans
        scope_spans_list = (
            resource_span.get("scopeSpans")
            or resource_span.get("instrumentationLibrarySpans")
            or []
        )
        for scope_spans in scope_spans_list:
            for raw_span in (scope_spans.get("spans") or []):
                status = raw_span.get("status") or {}
                spans.append({
                    "trace_id":              raw_span.get("traceId") or "",
                    "span_id":               raw_span.get("spanId") or "",
                    "parent_span_id":        raw_span.get("parentSpanId") or None,
                    "name":                  raw_span.get("name") or "",
                    "kind":                  raw_span.get("kind"),
                    "start_time_unix_nano":  raw_span.get("startTimeUnixNano"),
                    "end_time_unix_nano":    raw_span.get("endTimeUnixNano"),
                    "status_code":           status.get("code") or status.get("message"),
                    "status_message":        status.get("message"),
                    "attributes":            _resolve_attrs(raw_span.get("attributes") or []),
                    "resource_attributes":   resource_attrs,
                    "events":                raw_span.get("events") or [],
                    "links":                 raw_span.get("links") or [],
                })
    return spans


# ── OTLP/HTTP protobuf ─────────────────────────────────────────────────────────

def _pb_any_value(av) -> object:
    """Resolve an OTel protobuf AnyValue to a Python native type.

    Unknown/unset value kinds resolve to None (callers skip them) — a payload
    with exotic attribute types must degrade, never crash ingestion.
    """
    kind = av.WhichOneof("value")
    if kind == "string_value":
        return av.string_value
    if kind == "bool_value":
        return av.bool_value
    if kind == "int_value":
        return int(av.int_value)
    if kind == "double_value":
        return float(av.double_value)
    if kind == "bytes_value":
        return av.bytes_value.hex()
    if kind == "array_value":
        return [_pb_any_value(v) for v in av.array_value.values]
    if kind == "kvlist_value":
        return {
            kv.key: _pb_any_value(kv.value)
            for kv in av.kvlist_value.values
            if kv.key
        }
    return None


def _pb_attrs(raw_attrs) -> dict:
    """Convert a repeated KeyValue protobuf field to a plain dict."""
    result = {}
    for kv in raw_attrs:
        if not kv.key:
            continue
        value = _pb_any_value(kv.value)
        if value is not None:
            result[kv.key] = value
    return result


def _pb_events(raw_events) -> list:
    """Convert protobuf span events to JSON-able dicts (same keys as OTLP JSON)."""
    return [
        {
            "name": ev.name,
            "timeUnixNano": int(ev.time_unix_nano),
            "attributes": _pb_attrs(ev.attributes),
        }
        for ev in raw_events
    ]


def parse_otlp_protobuf(raw: bytes) -> tuple[list[dict], int]:
    """
    Parse an OTLP/HTTP protobuf ExportTraceServiceRequest into the same flat
    span dicts as parse_otlp_json, plus the resource_spans count for the
    response summary.

    Raises google.protobuf.message.DecodeError on malformed bodies — callers
    map that to HTTP 400. Span links are ignored (stored empty), matching the
    minimal treatment on the JSON path.
    """
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
        ExportTraceServiceRequest,
    )

    req = ExportTraceServiceRequest()
    req.ParseFromString(raw)

    spans: list[dict] = []
    for resource_span in req.resource_spans:
        resource_attrs = _pb_attrs(resource_span.resource.attributes)
        for scope_spans in resource_span.scope_spans:
            for raw_span in scope_spans.spans:
                spans.append({
                    "trace_id":              raw_span.trace_id.hex(),
                    "span_id":               raw_span.span_id.hex(),
                    "parent_span_id":        raw_span.parent_span_id.hex() or None,
                    "name":                  raw_span.name or "",
                    "kind":                  int(raw_span.kind) if raw_span.kind else None,
                    "start_time_unix_nano":  int(raw_span.start_time_unix_nano) or None,
                    "end_time_unix_nano":    int(raw_span.end_time_unix_nano) or None,
                    # status.code enum: 0 UNSET / 1 OK / 2 ERROR — same numeric
                    # codes the JSON path passes through
                    "status_code":           int(raw_span.status.code) if raw_span.HasField("status") and raw_span.status.code else None,
                    "status_message":        raw_span.status.message or None,
                    "attributes":            _pb_attrs(raw_span.attributes),
                    "resource_attributes":   resource_attrs,
                    "events":                _pb_events(raw_span.events),
                    "links":                 [],
                })
    return spans, len(req.resource_spans)
