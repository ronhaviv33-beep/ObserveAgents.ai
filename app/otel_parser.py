"""
OTLP/HTTP JSON parser for ObserveAgents.ai OTel trace ingestion.

Parses the OTLP JSON envelope:
  {"resourceSpans": [{"resource": {...}, "scopeSpans": [{"spans": [...]}]}]}

Returns a list of flat span dicts with resolved Python-native attribute values.
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
