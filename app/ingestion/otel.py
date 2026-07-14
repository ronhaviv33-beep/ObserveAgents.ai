"""OpenTelemetry integration: OTLP/HTTP payload -> RuntimeSpan[]."""
from __future__ import annotations

from app.ingestion import RuntimeSpan
from app.otel_parser import parse_otlp_json, parse_otlp_protobuf


def parse(payload: dict | bytes) -> list[RuntimeSpan]:
    """OTLP payload (decoded JSON dict or raw protobuf bytes) -> runtime spans."""
    return parse_otlp(payload)[0]


def parse_otlp(payload: dict | bytes) -> tuple[list[RuntimeSpan], int]:
    """parse() plus the resourceSpans envelope count, which the OTLP route must
    echo in its 202 response — an OTLP-specific detail, so it lives here."""
    if isinstance(payload, (bytes, bytearray)):
        return parse_otlp_protobuf(bytes(payload))
    return parse_otlp_json(payload), len(payload.get("resourceSpans") or [])
