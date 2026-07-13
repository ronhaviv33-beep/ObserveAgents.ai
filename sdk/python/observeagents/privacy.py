"""Client-side privacy guard.

The SDK's primary privacy defense is structural: events.py constructs payloads from an
explicit safe-field list, so there is no code path that copies prompts, messages,
responses, system instructions, tool arguments/results, headers, or credentials into an
outgoing event. This module guards the one free-form field (metadata) with the same
denylist the backend enforces server-side (app/runtime_events.py) — the server would
reject or scrub a violating payload anyway, but a payload the server would have to
scrub is an SDK bug.
"""
from __future__ import annotations

# Mirrors _META_FORBIDDEN_SUBSTRINGS in app/runtime_events.py.
FORBIDDEN_KEY_SUBSTRINGS = (
    "prompt", "response", "message", "argument", "result", "content",
    "authorization", "api_key", "apikey", "secret", "token", "password",
    "credential", "header", "cookie", "url",
)


def scrub_metadata(meta: dict | None) -> dict:
    """Keep only small, safe scalar identifiers/counts.

    Drops any key whose lowercased name contains a forbidden substring, any value that
    looks like a URL (may carry a query string), and any nested structure.
    """
    if not isinstance(meta, dict):
        return {}
    out: dict = {}
    for k, v in meta.items():
        kl = str(k).lower()
        if any(tok in kl for tok in FORBIDDEN_KEY_SUBSTRINGS):
            continue
        if isinstance(v, str) and "://" in v:
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[str(k)] = v
    return out


def error_type_only(exc: BaseException) -> str:
    """Reduce an exception to its class name — the message may contain content."""
    return type(exc).__name__
