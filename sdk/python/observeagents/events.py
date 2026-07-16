"""Build safe RuntimeEvent payloads.

Payloads are constructed from an explicit safe-field list only — this module never sees
the OpenAI request/response bodies, API keys, or headers, so there is no code path that
could copy content into an event. The shape matches the backend's RuntimeEvent schema
(app/runtime_events.py); unknown fields would be rejected there with a 422.
"""
from __future__ import annotations

from observeagents.ids import new_span_id, new_trace_id
from observeagents.privacy import scrub_metadata


def build_llm_call_event(
    *,
    agent_name: str,
    model: str | None,
    duration_ms: float | None,
    status: str,
    provider: str = "openai",
    error_type: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    environment: str | None = None,
    owner_hint: str | None = None,
    team_hint: str | None = None,
    session_id: str | None = None,
    trace_id: str | None = None,
    span_id: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """One `llm_call` runtime event. Optional fields that are None are omitted."""
    event: dict = {
        "source": "sdk",
        "agent_name": agent_name,
        "event_type": "llm_call",
        "provider": provider,
        "trace_id": trace_id or new_trace_id(),
        "span_id": span_id or new_span_id(),
        "status": status,
    }
    optional = {
        "model": model,
        "duration_ms": duration_ms,
        "error_type": error_type,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "environment": environment,
        "owner_hint": owner_hint,
        "team_hint": team_hint,
        "session_id": session_id,
    }
    for key, value in optional.items():
        if value is not None:
            event[key] = value
    safe_meta = scrub_metadata(metadata)
    if safe_meta:
        event["metadata_json"] = safe_meta
    return event
