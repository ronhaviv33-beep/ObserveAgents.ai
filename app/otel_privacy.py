"""
Privacy sanitizer for OTel span attributes.

Default rule: never persist raw content for gen_ai.input.messages,
gen_ai.output.messages, gen_ai.system_instructions, gen_ai.request.messages,
gen_ai.response.choices, tool.arguments, and tool.result.

Instead, store metadata only:
  {"redacted": true, "sha256": "<hex>", "size_bytes": N}

For tool.arguments, if the value is a JSON object, argument_keys are also stored
(key names only — not values — so the schema is observable without leaking data).

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
    "tool.arguments",
    "tool.result",
})


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

    tool.arguments also includes "argument_keys" if the value parses as a JSON object.
    All other keys pass through unchanged.
    """
    result = {}
    for key, value in attrs.items():
        if key in REDACTED_KEYS:
            sha256_hex, size = _hash_and_size(value)
            meta: dict = {"redacted": True, "sha256": sha256_hex, "size_bytes": size}
            if key == "tool.arguments":
                try:
                    parsed = value if isinstance(value, dict) else json.loads(value)
                    if isinstance(parsed, dict):
                        meta["argument_keys"] = sorted(parsed.keys())
                except Exception:
                    pass
            result[key] = meta
        else:
            result[key] = value
    return result
