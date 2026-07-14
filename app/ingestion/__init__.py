"""
Ingestion layer — one module per evidence integration.

Every integration answers "what happened?" by exposing a single function:

    parse(payload) -> list[RuntimeSpan]

The Runtime pipeline (app/otel_normalizer.py:normalize_spans and everything
downstream) answers "what does it mean?" and never contains
integration-specific parsing.

Current integrations:
  - app/ingestion/otel.py  — OpenTelemetry OTLP/HTTP (JSON + protobuf)
  - app/ingestion/sdk.py   — ObserveAgents SDK runtime events

To add an integration: create app/ingestion/<name>.py with
parse(payload) -> list[RuntimeSpan], then wire a route that authenticates,
parses, and calls normalize_spans — exactly like app/routes/otel.py and
app/routes/runtime_events.py do. (The pydantic RuntimeEvent in
app/runtime_events.py is the SDK's HTTP wire schema; RuntimeSpan is the
internal structure every integration converges on.)
"""
from __future__ import annotations

from typing import TypedDict


class RuntimeSpan(TypedDict, total=False):
    """The flat span shape normalize_spans() accepts — the one structure
    every integration's parse() must return. Missing fields never block
    ingestion; attribute keys use OTel GenAI SemConv (gen_ai.*)."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    kind: int | None
    start_time_unix_nano: int | None
    end_time_unix_nano: int | None
    status_code: int | str | None  # OTLP JSON sends strings, protobuf/SDK ints — preserved as-is
    status_message: str | None
    attributes: dict
    resource_attributes: dict
    events: list
    links: list
