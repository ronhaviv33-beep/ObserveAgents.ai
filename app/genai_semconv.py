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

Extraction tiers:
  Real customer telemetry is not always SemConv-clean, so each signal has a
  *_tiered extractor returning (value, tier). TIER_STANDARD means a SemConv
  (or long-supported legacy) key resolved the value; TIER_FALLBACK means a
  known ecosystem variant (OpenInference/OpenLLMetry-style llm.* keys, bare
  token counters) resolved it. TIER_MAPPED is assigned by the normalizer for
  org-configured attribute mappings — never by this module. Bare, collision-
  prone keys (model / provider / tool / vendor) are deliberately NOT global
  fallbacks; orgs opt in per key via the attribute-mapping config.
"""
from __future__ import annotations

import json

# ── Extraction tiers ──────────────────────────────────────────────────────────
TIER_STANDARD = "standard"
TIER_FALLBACK = "fallback"
TIER_MAPPED = "mapped"      # assigned by the normalizer (org attribute mapping)

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


def _first_truthy(attrs: dict, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        v = attrs.get(key)
        if v:
            return str(v)
    return None


_PROVIDER_STANDARD_KEYS = ("gen_ai.provider.name", "gen_ai.system")
_PROVIDER_FALLBACK_KEYS = ("llm.provider", "llm.vendor")

_MODEL_STANDARD_KEYS = ("gen_ai.request.model", "gen_ai.response.model")
_MODEL_FALLBACK_KEYS = ("gen_ai.model", "llm.model", "llm.model_name", "model.name")


def extract_provider_tiered(attrs: dict) -> tuple[str | None, str | None]:
    """Provider name with its extraction tier (see module docstring)."""
    v = _first_truthy(attrs, _PROVIDER_STANDARD_KEYS)
    if v:
        return v, TIER_STANDARD
    v = _first_truthy(attrs, _PROVIDER_FALLBACK_KEYS)
    if v:
        return v, TIER_FALLBACK
    return None, None


def extract_provider(attrs: dict) -> str | None:
    """gen_ai.provider.name (current) || gen_ai.system (deprecated, supported)
    || llm.provider / llm.vendor ecosystem variants."""
    return extract_provider_tiered(attrs)[0]


def extract_model_tiered(attrs: dict) -> tuple[str | None, str | None]:
    """Model name with its extraction tier.

    Standard: gen_ai.request.model / gen_ai.response.model.
    Fallback: gen_ai.model, llm.model, llm.model_name, model.name.
    Bare "model" is intentionally not read — org attribute mapping only.
    """
    v = _first_truthy(attrs, _MODEL_STANDARD_KEYS)
    if v:
        return v, TIER_STANDARD
    v = _first_truthy(attrs, _MODEL_FALLBACK_KEYS)
    if v:
        return v, TIER_FALLBACK
    return None, None


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


_TOOL_STANDARD_KEYS = ("gen_ai.tool.name", "tool.name", "mcp.tool.name", "mcp.tool")
_TOOL_FALLBACK_KEYS = ("tool_name", "function.name", "function_name")


def extract_tool_name_tiered(attrs: dict) -> tuple[str | None, str | None]:
    """Tool name with its extraction tier.

    Standard: gen_ai.tool.name plus long-supported tool.name / mcp.tool(.name).
    Fallback: tool_name, function.name, function_name ecosystem variants.
    Bare "tool" is intentionally not read — org attribute mapping only.
    """
    v = _first_truthy(attrs, _TOOL_STANDARD_KEYS)
    if v:
        return v, TIER_STANDARD
    v = _first_truthy(attrs, _TOOL_FALLBACK_KEYS)
    if v:
        return v, TIER_FALLBACK
    return None, None


def extract_tool_name(attrs: dict) -> str | None:
    """gen_ai.tool.name (current) with legacy tool.name / mcp.tool.name /
    mcp.tool, plus tool_name / function(.name) ecosystem variants."""
    return extract_tool_name_tiered(attrs)[0]


_ENVIRONMENT_STANDARD_KEYS = ("deployment.environment", "deployment.environment.name")
_ENVIRONMENT_FALLBACK_KEYS = ("environment", "env", "service.environment")


def extract_environment_tiered(
    resource_attrs: dict, attrs: dict | None = None
) -> tuple[str | None, str | None]:
    """Deployment environment with its extraction tier.

    Resource attributes are checked before span attributes at each tier —
    environment is resource-level metadata per SemConv.
    """
    attrs = attrs or {}
    for source in (resource_attrs, attrs):
        v = _first_truthy(source, _ENVIRONMENT_STANDARD_KEYS)
        if v:
            return v, TIER_STANDARD
    for source in (resource_attrs, attrs):
        v = _first_truthy(source, _ENVIRONMENT_FALLBACK_KEYS)
        if v:
            return v, TIER_FALLBACK
    return None, None


# MCP JSON-RPC method names (closed set). A generic rpc.method / method
# attribute counts as MCP evidence ONLY on exact membership here — the values
# are MCP-namespace-shaped and collide with nothing (HTTP methods are
# GET/POST; RPC methods are dotted service paths).
_MCP_METHOD_VALUES = frozenset({
    "tools/call", "tools/list", "resources/read", "resources/list",
    "prompts/get", "prompts/list", "initialize",
})


def extract_mcp_method_tiered(attrs: dict) -> tuple[str | None, str | None]:
    """MCP method with its extraction tier.

    Standard: mcp.method.name. Fallback: rpc.method / method whose value is
    exactly one of the known MCP JSON-RPC methods (_MCP_METHOD_VALUES).
    """
    v = attrs.get("mcp.method.name")
    if v:
        return str(v), TIER_STANDARD
    for key in ("rpc.method", "method"):
        v = attrs.get(key)
        if v is not None and str(v) in _MCP_METHOD_VALUES:
            return str(v), TIER_FALLBACK
    return None, None


def extract_mcp(attrs: dict) -> dict:
    """mcp.* / jsonrpc.* attributes. `method` being non-None marks an MCP span."""
    return {
        "method": extract_mcp_method_tiered(attrs)[0],
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
        or extract_mcp_method_tiered(attrs)[0]
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


# Any of these marks a span as GenAI activity without ambiguity. Bare token
# keys (prompt_tokens, input_tokens, …) are NOT signals — they gate on one of
# these being present first (see extract_usage_tiered).
_GENAI_FALLBACK_SIGNAL_KEYS = frozenset(
    _MODEL_FALLBACK_KEYS
    + _PROVIDER_FALLBACK_KEYS
    + (
        "llm.usage.prompt_tokens", "llm.usage.completion_tokens",
        "llm.token_count.prompt", "llm.token_count.completion",
        "llm.is_streaming",
    )
)


def has_genai_signal(attrs: dict) -> tuple[bool, str | None]:
    """(is GenAI activity, tier of the strongest signal).

    Standard: any gen_ai.* key. Fallback: the llm.* / model.name ecosystem
    variants in _GENAI_FALLBACK_SIGNAL_KEYS.
    """
    if any(k.startswith("gen_ai.") for k in attrs):
        return True, TIER_STANDARD
    if any(k in attrs for k in _GENAI_FALLBACK_SIGNAL_KEYS):
        return True, TIER_FALLBACK
    return False, None


_USAGE_STANDARD_KEYS = (
    "gen_ai.usage.input_tokens", "gen_ai.usage.prompt_tokens",
    "gen_ai.usage.output_tokens", "gen_ai.usage.completion_tokens",
    "gen_ai.usage.cache_creation.input_tokens", "gen_ai.usage.cache_creation_input_tokens",
    "gen_ai.usage.cache_read.input_tokens", "gen_ai.usage.cache_read_input_tokens",
    "gen_ai.usage.reasoning.output_tokens", "gen_ai.usage.reasoning_output_tokens",
)
_INPUT_TOKEN_FALLBACK_KEYS = ("llm.usage.prompt_tokens", "llm.token_count.prompt")
_INPUT_TOKEN_BARE_KEYS = ("prompt_tokens", "input_tokens")
_OUTPUT_TOKEN_FALLBACK_KEYS = ("llm.usage.completion_tokens", "llm.token_count.completion")
_OUTPUT_TOKEN_BARE_KEYS = ("completion_tokens", "output_tokens")


def extract_usage_tiered(attrs: dict) -> tuple[dict, str | None]:
    """gen_ai.usage.* token counts with the extraction tier that supplied them.

    Standard: the gen_ai.usage.* chains (incl. deprecated prompt/completion
    names and underscore cache/reasoning variants). Fallback: llm.usage.* /
    llm.token_count.* ecosystem variants, plus bare prompt_tokens /
    completion_tokens / input_tokens / output_tokens — bare keys are honored
    ONLY when the span already carries a non-bare GenAI signal
    (has_genai_signal), because this runs on every span and bare counters
    exist in non-LLM domains too.
    """
    usage = {
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
    tier = TIER_STANDARD if any(k in attrs for k in _USAGE_STANDARD_KEYS) else None

    if usage["input_tokens"] is None or usage["output_tokens"] is None:
        allow_bare = has_genai_signal(attrs)[0]
        if usage["input_tokens"] is None:
            v = _first_present(attrs, *_INPUT_TOKEN_FALLBACK_KEYS)
            if v is None and allow_bare:
                v = _first_present(attrs, *_INPUT_TOKEN_BARE_KEYS)
            iv = _int_or_none(v)
            if iv is not None:
                usage["input_tokens"] = iv
                tier = tier or TIER_FALLBACK
        if usage["output_tokens"] is None:
            v = _first_present(attrs, *_OUTPUT_TOKEN_FALLBACK_KEYS)
            if v is None and allow_bare:
                v = _first_present(attrs, *_OUTPUT_TOKEN_BARE_KEYS)
            iv = _int_or_none(v)
            if iv is not None:
                usage["output_tokens"] = iv
                tier = tier or TIER_FALLBACK

    return usage, tier


def extract_usage(attrs: dict) -> dict:
    """gen_ai.usage.* token counts (ints or None), including the ecosystem
    fallback variants — see extract_usage_tiered."""
    return extract_usage_tiered(attrs)[0]


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
    # Canonical request-model column: SemConv key first, then the ecosystem
    # fallback variants (never gen_ai.response.model — that has its own column).
    request_model = (
        attrs.get("gen_ai.request.model")
        or _first_truthy(attrs, _MODEL_FALLBACK_KEYS)
    )
    return {
        "operation_name": _s(extract_operation(attrs), 64),
        # Raw wire value — not the capitalized display label used elsewhere.
        "provider_name": _s(extract_provider(attrs), 128),
        "request_model": _s(request_model, 255),
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

    if extract_mcp_method_tiered(attrs)[0]:
        return "mcp_tool"

    if extract_tool_name(attrs):
        return "mcp_tool" if is_mcp_span(attrs) else "tool"

    keys = attrs.keys()
    if any(k.startswith("db.") for k in keys):
        return "database"
    if any(k in ("url.full", "http.url", "server.address") for k in keys):
        return "external_api"

    # Legacy heuristics (pre-SemConv payloads); includes llm.* fallback signals.
    if has_genai_signal(attrs)[0]:
        return "llm"
    if any(k.startswith(("tool.", "mcp.")) for k in keys):
        return "tool"
    return "step"
