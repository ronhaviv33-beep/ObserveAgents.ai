"""
OpenTelemetry GenAI Semantic Conventions compatibility layer.

Single source of truth for extracting GenAI SemConv fields from span
attributes, consumed by the normalizer, the runtime timeline, and asset
intelligence derivation. Aligned with the semantic-conventions-genai
repository (gen_ai.* / mcp.* namespaces).

Compatibility rules:
  - gen_ai.provider.name is the current provider discriminator;
    gen_ai.system is deprecated upstream but remains fully supported here.
  - gen_ai.tool.name is preferred; tool.name / mcp.tool.name / mcp.tool
    remain supported.
  - No function in this module returns raw prompt/response/tool content —
    content scrubbing lives in app/otel_privacy.py and runs before storage.
"""
from __future__ import annotations

import json

# ── Operations (gen_ai.operation.name well-known values) ─────────────────────
INFERENCE_OPERATIONS = frozenset({"chat", "text_completion", "generate_content"})
MEMORY_OPERATIONS = frozenset({
    "search_memory", "create_memory", "update_memory", "delete_memory", "upsert_memory",
})
KNOWN_OPERATIONS = frozenset(
    {"embeddings", "retrieval", "execute_tool", "invoke_agent", "invoke_workflow",
     "plan", "create_agent"}
    | INFERENCE_OPERATIONS
    | MEMORY_OPERATIONS
)

# operation.name → runtime step type
_OPERATION_STEP = {
    "invoke_agent": "agent",
    "create_agent": "agent",
    "invoke_workflow": "workflow",
    "plan": "plan",
    "chat": "llm",
    "text_completion": "llm",
    "generate_content": "llm",
    "embeddings": "embedding",
    "retrieval": "retrieval",
    "execute_tool": "tool",
}
_OPERATION_STEP.update({op: "memory" for op in MEMORY_OPERATIONS})


def extract_provider(attrs: dict) -> str | None:
    """gen_ai.provider.name (current) || gen_ai.system (deprecated, supported)."""
    v = attrs.get("gen_ai.provider.name") or attrs.get("gen_ai.system")
    return str(v) if v else None


def extract_operation(attrs: dict) -> str | None:
    v = attrs.get("gen_ai.operation.name")
    return str(v) if v else None


def extract_agent_meta(attrs: dict, resource_attrs: dict | None = None) -> dict:
    """gen_ai.agent.* metadata from span attributes (resource attrs as fallback)."""
    resource_attrs = resource_attrs or {}

    def _get(key: str) -> str | None:
        v = attrs.get(key) or resource_attrs.get(key)
        return str(v) if v else None

    return {
        "id": _get("gen_ai.agent.id"),
        "name": _get("gen_ai.agent.name"),
        "description": _get("gen_ai.agent.description"),
        "version": _get("gen_ai.agent.version"),
    }


def extract_tool_name(attrs: dict) -> str | None:
    """gen_ai.tool.name (current) with legacy tool.name / mcp.tool.name / mcp.tool."""
    v = (
        attrs.get("gen_ai.tool.name")
        or attrs.get("tool.name")
        or attrs.get("mcp.tool.name")
        or attrs.get("mcp.tool")
    )
    return str(v) if v else None


def extract_mcp(attrs: dict) -> dict:
    """mcp.* / jsonrpc.* attributes. `method` being non-None marks an MCP span."""
    return {
        "method": attrs.get("mcp.method.name"),
        "session_id": attrs.get("mcp.session.id"),
        "protocol_version": attrs.get("mcp.protocol.version"),
        "resource_uri": attrs.get("mcp.resource.uri"),
        "jsonrpc_request_id": attrs.get("jsonrpc.request.id"),
        "rpc_status": attrs.get("rpc.response.status_code"),
        # legacy server naming kept for backward compatibility
        "server": attrs.get("mcp.server") or attrs.get("mcp.server.name"),
    }


def is_mcp_span(attrs: dict) -> bool:
    return bool(
        attrs.get("mcp.method.name")
        or attrs.get("mcp.server")
        or attrs.get("mcp.server.name")
        or attrs.get("mcp.tool.name")
        or attrs.get("mcp.tool")
    )


def _int_or_none(v: object) -> int | None:
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _first_present(attrs: dict, *keys: str) -> object:
    """First key present in attrs (two-arg .get chains would lose a real 0)."""
    for key in keys:
        if key in attrs:
            return attrs[key]
    return None


def extract_usage(attrs: dict) -> dict:
    """gen_ai.usage.* token counts (ints or None).

    Accepts the deprecated prompt_tokens/completion_tokens names and the
    underscore spelling variants of the cache/reasoning keys.
    """
    return {
        "input_tokens": _int_or_none(_first_present(
            attrs, "gen_ai.usage.input_tokens", "gen_ai.usage.prompt_tokens")),
        "output_tokens": _int_or_none(_first_present(
            attrs, "gen_ai.usage.output_tokens", "gen_ai.usage.completion_tokens")),
        "cache_creation_input_tokens": _int_or_none(_first_present(
            attrs, "gen_ai.usage.cache_creation.input_tokens",
            "gen_ai.usage.cache_creation_input_tokens")),
        "cache_read_input_tokens": _int_or_none(_first_present(
            attrs, "gen_ai.usage.cache_read.input_tokens",
            "gen_ai.usage.cache_read_input_tokens")),
        "reasoning_output_tokens": _int_or_none(_first_present(
            attrs, "gen_ai.usage.reasoning.output_tokens",
            "gen_ai.usage.reasoning_output_tokens")),
    }


def extract_response_meta(attrs: dict) -> dict:
    """gen_ai.response.* metadata. time_to_first_chunk also accepts ttft_ms
    (the attribute Claude Code emits) — both are optional latency metadata."""
    finish = attrs.get("gen_ai.response.finish_reasons")
    if isinstance(finish, str):
        finish = [finish]
    return {
        "model": attrs.get("gen_ai.response.model"),
        "id": attrs.get("gen_ai.response.id"),
        "finish_reasons": finish if isinstance(finish, list) else None,
        "time_to_first_chunk": (
            attrs.get("gen_ai.response.time_to_first_chunk")
            if attrs.get("gen_ai.response.time_to_first_chunk") is not None
            else attrs.get("ttft_ms")
        ),
    }


def _bool_or_none(v: object) -> bool | None:
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.lower() in ("true", "false"):
        return v.lower() == "true"
    if isinstance(v, (int, float)):
        return bool(v)
    return None


def extract_time_to_first_chunk_ms(attrs: dict) -> int | None:
    """Time-to-first-chunk in milliseconds.

    gen_ai.response.time_to_first_chunk is SECONDS per SemConv → ×1000;
    ttft_ms (the attribute Claude Code emits) is already milliseconds.
    Conversion is keyed off which attribute carried the value — deterministic,
    no magnitude guessing (a non-compliant emitter sending ms under the
    SemConv key will produce inflated values, capped below). Negative or
    >24h values are treated as junk → None.
    """
    raw = attrs.get("gen_ai.response.time_to_first_chunk")
    if raw is not None:
        try:
            ms = float(raw) * 1000.0
        except (TypeError, ValueError):
            return None
    else:
        raw = attrs.get("ttft_ms")
        if raw is None:
            return None
        try:
            ms = float(raw)
        except (TypeError, ValueError):
            return None
    if ms < 0 or ms > 86_400_000:
        return None
    return int(ms)


def extract_genai_scalar_fields(attrs: dict) -> dict:
    """Column-ready GenAI SemConv scalars for OtelSpan / ProvenanceEvent.

    Reads only enum/metadata keys — never message, tool-argument, prompt, or
    completion content (those are scrubbed separately in app/otel_privacy.py).
    Strings are truncated to their column lengths so Postgres inserts never
    overflow.
    """
    def _s(v: object, n: int) -> str | None:
        return str(v)[:n] if v is not None and str(v) else None

    usage = extract_usage(attrs)
    finish = extract_response_meta(attrs)["finish_reasons"]
    stream = _bool_or_none(_first_present(
        attrs, "gen_ai.request.stream", "gen_ai.openai.request.stream", "llm.is_streaming"))
    return {
        "operation_name": _s(extract_operation(attrs), 64),
        # Raw wire value — not the capitalized display label used elsewhere.
        "provider_name": _s(extract_provider(attrs), 128),
        "request_model": _s(attrs.get("gen_ai.request.model"), 255),
        "response_model": _s(attrs.get("gen_ai.response.model"), 255),
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "reasoning_output_tokens": usage["reasoning_output_tokens"],
        "cache_read_input_tokens": usage["cache_read_input_tokens"],
        "cache_creation_input_tokens": usage["cache_creation_input_tokens"],
        "finish_reasons_json": (
            json.dumps([str(r)[:64] for r in finish][:16]) if finish else None
        ),
        "request_stream": stream,
        "time_to_first_chunk_ms": extract_time_to_first_chunk_ms(attrs),
    }


def extract_prompt_meta(attrs: dict) -> dict:
    """Safe prompt metadata — names and versions only, never content."""
    return {
        "name": attrs.get("gen_ai.prompt.name"),
        "version": attrs.get("gen_ai.prompt.version"),
    }


# JSON-RPC error codes are negative; treat any non-zero code as an error signal.
def _rpc_status_is_error(rpc_status: object) -> bool:
    try:
        return int(rpc_status) != 0  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return bool(rpc_status)


def extract_error_type(attrs: dict, status_code: str | None = None) -> str | None:
    """
    error.type (SemConv) first; else the JSON-RPC error code when present;
    else "error" for spans with OTLP status ERROR ("2"); else None.
    """
    et = attrs.get("error.type")
    if et:
        return str(et)
    rpc_status = attrs.get("rpc.response.status_code")
    if rpc_status is not None and _rpc_status_is_error(rpc_status):
        return f"rpc_{rpc_status}"
    if status_code == "2":
        return "error"
    return None


def classify_step(attrs: dict, span_name: str = "") -> str:
    """
    Classify a span into a Runtime Step type.

    Priority (task/SemConv aligned):
      1. gen_ai.operation.name
      2. mcp.method.name
      3. gen_ai.tool.name / tool.name (mcp_tool when MCP evidence present)
      4. db.*
      5. url.full / http
      6. legacy heuristics (any gen_ai.* → llm; tool./mcp. prefix → tool)
    Returns one of: agent, workflow, plan, llm, retrieval, embedding, tool,
    mcp_tool, memory, database, external_api, step.
    """
    op = extract_operation(attrs)
    if op and op in _OPERATION_STEP:
        step = _OPERATION_STEP[op]
        if step == "tool" and is_mcp_span(attrs):
            return "mcp_tool"
        return step

    if attrs.get("mcp.method.name"):
        return "mcp_tool"

    if extract_tool_name(attrs):
        return "mcp_tool" if is_mcp_span(attrs) else "tool"

    keys = attrs.keys()
    if any(k.startswith("db.") for k in keys):
        return "database"
    if any(k in ("url.full", "http.url", "server.address") for k in keys):
        return "external_api"

    # Legacy heuristics (pre-SemConv payloads)
    if any(k.startswith("gen_ai.") for k in keys):
        return "llm"
    if any(k.startswith(("tool.", "mcp.")) for k in keys):
        return "tool"
    return "step"
