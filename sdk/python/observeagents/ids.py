"""trace_id / span_id generation.

Hex ids in the same shape the backend's OTLP path stores: a 32-hex trace id and a
16-hex span id (RuntimeEvent allows up to 128/64 chars; these fit comfortably).
"""
from __future__ import annotations

import uuid


def new_trace_id() -> str:
    return uuid.uuid4().hex  # 32 hex chars


def new_span_id() -> str:
    return uuid.uuid4().hex[:16]  # 16 hex chars
