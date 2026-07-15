"""Pydantic schemas for POST /api/v1/telemetry/batch.

TelemetryEventIn is deliberately permissive (extra="allow"): unknown fields are
not an error — they are preserved verbatim in telemetry_events_raw.raw_payload
for investigation. Only the normalized product fields are validated here.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_BATCH_EVENTS = 1000


class TelemetryEventIn(BaseModel):
    # extra="allow": extras ride along into raw_payload; protected_namespaces=()
    # because the product schema has a field literally named "model".
    model_config = ConfigDict(extra="allow", protected_namespaces=())

    event_id: str = Field(min_length=1, max_length=64)
    agent_id: str = Field(min_length=1, max_length=256)
    timestamp: datetime | None = None  # ISO8601; defaults to server receive time
    event_type: str = Field(default="llm_call", min_length=1, max_length=64)

    agent_name: str | None = Field(default=None, max_length=256)
    team: str | None = Field(default=None, max_length=128)
    environment: str | None = Field(default=None, max_length=64)
    owner: str | None = Field(default=None, max_length=256)

    # OTEL-compatible correlation ids
    trace_id: str | None = Field(default=None, max_length=64)
    span_id: str | None = Field(default=None, max_length=32)
    parent_span_id: str | None = Field(default=None, max_length=32)

    provider: str | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=255)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    latency_ms: float | None = Field(default=None, ge=0)

    status: Literal["ok", "error", "blocked"] = "ok"
    error_message: str | None = Field(default=None, max_length=512)
    tool_name: str | None = Field(default=None, max_length=255)
    action_name: str | None = Field(default=None, max_length=255)
    attributes: dict | None = None  # OTEL-style free-form attributes


class EventError(BaseModel):
    index: int
    event_id: str | None = None
    error: str


class BatchIngestResponse(BaseModel):
    accepted: int
    duplicated: int
    failed: int
    errors: list[EventError] = []
    queued: bool = True
