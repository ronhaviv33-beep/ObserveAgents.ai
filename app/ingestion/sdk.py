"""ObserveAgents SDK integration: validated runtime events -> RuntimeSpan[]."""
from __future__ import annotations

from app.ingestion import RuntimeSpan
from app.runtime_events import RuntimeEvent, to_span_dict


def parse(payload: list[RuntimeEvent]) -> list[RuntimeSpan]:
    """Validated SDK RuntimeEvent models -> runtime spans."""
    return [to_span_dict(ev) for ev in payload]
