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


def extract_usage(attrs: dict) -> dict:
    """gen_ai.usage.* token counts (ints or None)."""
    return {
        "input_tokens": _int_or_none(attrs.get("gen_ai.usage.input_tokens")),
        "output_tokens": _int_or_none(attrs.get("gen_ai.usage.output_tokens")),
        "cache_creation_input_tokens": _int_or_none(attrs.get("gen_ai.usage.cache_creation.input_tokens")),
        "cache_read_input_tokens": _int_or_none(attrs.get("gen_ai.usage.cache_read.input_tokens")),
        "reasoning_output_tokens": _int_or_none(attrs.get("gen_ai.usage.reasoning.output_tokens")),
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
