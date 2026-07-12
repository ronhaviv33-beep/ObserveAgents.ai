"""
Normalized GenAI Runtime Event — schema, privacy scrub, and span-like adapter.

Part of the GenAI Runtime Collector (docs/genai_runtime_collector_roadmap.md, R1/R2).
This is the reuse seam: any source normalizes to a `RuntimeEvent`, which
`to_span_dict()` converts into exactly the span-dict shape
`app/otel_normalizer.py:normalize_spans` already consumes — so events feed the SAME
intelligence engine (assets → findings → detection rules → gateway candidates) with no
new pipeline.

Evidence only. This module never evaluates detection rules, creates control candidates,
enforces policy, or touches the Gateway. It validates, scrubs, and maps.

Privacy: the schema is an allow-list (`extra="forbid"`), so raw prompts, responses,
tool arguments/results, credentials, headers, or full URLs are rejected at the boundary.
`external_domain` is reduced to a host, and `metadata_json` is denylist-scrubbed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

# Event types we understand; anything else still ingests as a generic runtime step.
_KNOWN_EVENT_TYPES = frozenset({
    "llm_call", "tool_call", "mcp_tool", "db_call",
    "external_api_call", "runtime_step", "error",
})

# metadata_json keys are dropped if their (lowercased) name contains any of these —
# defense in depth so no content/secret rides in on the free-form field.
_META_FORBIDDEN_SUBSTRINGS = (
    "prompt", "response", "message", "argument", "result", "content",
    "authorization", "api_key", "apikey", "secret", "token", "password",
    "credential", "header", "cookie", "url",
)


class RuntimeEvent(BaseModel):
    """One normalized GenAI runtime event. org_id is NOT accepted from the body —
    it is always resolved server-side from the caller's credential."""

    model_config = ConfigDict(extra="forbid")  # unknown keys (prompt, headers, …) → 422

    source: str = Field(min_length=1, max_length=64)
    agent_name: str = Field(min_length=1, max_length=256)
    trace_id: str = Field(min_length=1, max_length=128)
    span_id: str = Field(min_length=1, max_length=64)
    event_type: str = Field(min_length=1, max_length=48)

    session_id: str | None = Field(default=None, max_length=128)
    parent_span_id: str | None = Field(default=None, max_length=64)
    provider: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=128)
    tool_name: str | None = Field(default=None, max_length=256)
    mcp_server: str | None = Field(default=None, max_length=256)
    db_system: str | None = Field(default=None, max_length=64)
    db_name: str | None = Field(default=None, max_length=128)
    external_domain: str | None = Field(default=None, max_length=512)
    status: str | None = Field(default=None, max_length=32)
    error_type: str | None = Field(default=None, max_length=128)
    duration_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    environment: str | None = Field(default=None, max_length=64)
    owner_hint: str | None = Field(default=None, max_length=256)
    team_hint: str | None = Field(default=None, max_length=128)
    timestamp: str | None = Field(default=None, max_length=40)
    metadata_json: dict | None = None


def host_only(raw: str | None) -> str | None:
    """Reduce any domain/URL to its host — scheme, path, and query string are dropped
    so a full URL with secrets in the query can never be stored."""
    if not raw:
        return None
    s = str(raw).strip()
    try:
        if "://" in s:
            return urlsplit(s).hostname or None
        # bare "host/path?x=y" → host segment only
        return urlsplit("//" + s).hostname or s.split("/", 1)[0].split("?", 1)[0] or None
    except (ValueError, TypeError):
        return None


def scrub_metadata(meta: dict | None) -> dict:
    """Drop denylisted keys and any full-URL values; keep small scalar identifiers/counts."""
    if not isinstance(meta, dict):
        return {}
    out: dict = {}
    for k, v in meta.items():
        kl = str(k).lower()
        if any(tok in kl for tok in _META_FORBIDDEN_SUBSTRINGS):
            continue
        if isinstance(v, str) and "://" in v:
            continue  # looks like a URL — drop rather than risk a query string
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[str(k)] = v
        # nested dicts/lists are dropped for MVP — identifiers and counts only
    return out


def _to_nanos(timestamp: str | None) -> int:
    """ISO-8601 → unix nanoseconds. Falls back to 'now' when absent/unparseable so the
    span always has a usable time (normalize_spans needs start/end)."""
    if timestamp:
        try:
            iso = timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
            return int(datetime.fromisoformat(iso).timestamp() * 1_000_000_000)
        except (ValueError, TypeError):
            pass
    return int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)


def to_span_dict(event: RuntimeEvent) -> dict:
    """Adapter: normalized runtime event → the span dict `normalize_spans` consumes.

    Sets GenAI/MCP/db SemConv attribute keys the intelligence engine already reads, so
    the shared derivation (capabilities, findings, detection rules, control candidates)
    lights up unchanged. Never emits a content-bearing key.
    """
    attrs: dict = {"gen_ai.agent.name": event.agent_name}

    if event.provider:
        attrs["gen_ai.provider.name"] = event.provider
    if event.model:
        attrs["gen_ai.request.model"] = event.model
    if event.tool_name:
        attrs["gen_ai.tool.name"] = event.tool_name
    if event.mcp_server:
        attrs["mcp.server"] = event.mcp_server
    if event.event_type == "mcp_tool":
        # Presence of an mcp.* key makes is_mcp_span() true; use a declared method.
        attrs.setdefault("mcp.method.name", str((event.metadata_json or {}).get("mcp_method") or "tools/call"))
    if event.db_system:
        attrs["db.system"] = event.db_system
    if event.db_name:
        attrs["db.name"] = event.db_name
    host = host_only(event.external_domain)
    if host:
        attrs["server.address"] = host
    if event.error_type:
        attrs["error.type"] = event.error_type
    if event.input_tokens is not None:
        attrs["gen_ai.usage.input_tokens"] = event.input_tokens
    if event.output_tokens is not None:
        attrs["gen_ai.usage.output_tokens"] = event.output_tokens
    if event.session_id:
        attrs["session.id"] = event.session_id
    # safe extra identifiers/counts only
    for k, v in scrub_metadata(event.metadata_json).items():
        attrs.setdefault(f"metadata.{k}", v)

    resource_attrs: dict = {"service.name": event.agent_name, "source": event.source}
    if event.environment:
        resource_attrs["deployment.environment"] = event.environment
    if event.owner_hint:
        resource_attrs["owner.hint"] = event.owner_hint
    if event.team_hint:
        resource_attrs["team.hint"] = event.team_hint

    is_error = event.status == "error" or bool(event.error_type)
    start_ns = _to_nanos(event.timestamp)
    end_ns = start_ns + int((event.duration_ms or 0) * 1_000_000)

    return {
        "trace_id": event.trace_id,
        "span_id": event.span_id,
        "parent_span_id": event.parent_span_id,
        "name": event.event_type if event.event_type in _KNOWN_EVENT_TYPES else "runtime_step",
        "kind": 3,
        "start_time_unix_nano": start_ns,
        "end_time_unix_nano": end_ns,
        "status_code": 2 if is_error else None,
        "status_message": None,
        "attributes": attrs,
        "resource_attributes": resource_attrs,
    }
