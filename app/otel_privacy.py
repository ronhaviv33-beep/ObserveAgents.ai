"""
Privacy sanitizer for OTel span attributes.

Default rule: never persist raw content for gen_ai.input.messages,
gen_ai.output.messages, gen_ai.system_instructions, gen_ai.request.messages,
gen_ai.response.choices, gen_ai.tool.call.arguments, gen_ai.tool.call.result,
tool.arguments, tool.result, or any gen_ai.prompt.variable.* value.

Instead, store metadata only:
  {"redacted": true, "sha256": "<hex>", "size_bytes": N}
  (+ "message_count" when the value is a list — safe input/output message counts)

For tool argument keys (tool.arguments / gen_ai.tool.call.arguments), if the
value is a JSON object, argument_keys are also stored (key names only — not
values — so the schema is observable without leaking data).

gen_ai.prompt.variable.* keys are collapsed into a single safe
"gen_ai.prompt.variables" list of variable NAMES; values are dropped entirely.
gen_ai.prompt.name / gen_ai.prompt.version are safe metadata and pass through.

TODO: Add per-org content capture opt-in when the product is ready. Until then,
raw content is never written anywhere in the ingestion pipeline.
"""
from __future__ import annotations

import hashlib
import json

REDACTED_KEYS: frozenset[str] = frozenset({
    "gen_ai.system_instructions",
    "gen_ai.input.messages",
    "gen_ai.output.messages",
    "gen_ai.request.messages",
    "gen_ai.response.choices",
    "gen_ai.tool.call.arguments",
    "gen_ai.tool.call.result",
    "tool.arguments",
    "tool.result",
})

# Keys whose redaction metadata includes argument_keys (schema without values)
_ARGUMENT_KEYS: frozenset[str] = frozenset({
    "tool.arguments",
    "gen_ai.tool.call.arguments",
})

_PROMPT_VARIABLE_PREFIX = "gen_ai.prompt.variable."


def _hash_and_size(value: object) -> tuple[str, int]:
    """Return (sha256_hex, utf8_byte_size) for a value serialized as JSON."""
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    encoded = serialized.encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), len(encoded)


def scrub_attributes(attrs: dict) -> dict:
    """
    Return a copy of attrs with sensitive values replaced by privacy metadata.

    Sensitive keys become:
      {"redacted": true, "sha256": "<hex>", "size_bytes": N}
      (+ "message_count" for list values, + "argument_keys" for tool arguments
       that parse as a JSON object)

    gen_ai.prompt.variable.<name> keys are dropped and collected into a single
    "gen_ai.prompt.variables" list of names. All other keys pass through.
    """
    result = {}
    prompt_variable_names: list[str] = []
    for key, value in attrs.items():
        if key.startswith(_PROMPT_VARIABLE_PREFIX):
            prompt_variable_names.append(key[len(_PROMPT_VARIABLE_PREFIX):])
            continue
        if key in REDACTED_KEYS:
            sha256_hex, size = _hash_and_size(value)
            meta: dict = {"redacted": True, "sha256": sha256_hex, "size_bytes": size}
            if isinstance(value, list):
                meta["message_count"] = len(value)
            if key in _ARGUMENT_KEYS:
                try:
                    parsed = value if isinstance(value, dict) else json.loads(value)
                    if isinstance(parsed, dict):
                        meta["argument_keys"] = sorted(parsed.keys())
                except Exception:
                    pass
            result[key] = meta
        else:
            result[key] = value
    if prompt_variable_names:
        result["gen_ai.prompt.variables"] = sorted(prompt_variable_names)
    return result
