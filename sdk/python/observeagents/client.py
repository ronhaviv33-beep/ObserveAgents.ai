"""ObserveAgents transport: best-effort POST to {observeagents_url}/runtime-events.

Fail-open by design: send_events() swallows every exception (timeout, connection error,
4xx/5xx, serialization surprise) and never raises into the caller. A delivery failure
must not affect the customer's LLM call in any way. Uses only the standard library —
the SDK adds zero runtime dependencies.
"""
from __future__ import annotations

import json
import logging
import urllib.request

_log = logging.getLogger("observeagents")


class ObserveAgentsClient:
    def __init__(
        self,
        observeagents_url: str,
        observeagents_api_key: str,
        timeout_seconds: float = 2.0,
        debug: bool = False,
    ):
        self._endpoint = observeagents_url.rstrip("/") + "/runtime-events"
        self._api_key = observeagents_api_key
        self._timeout = timeout_seconds
        self._debug = debug

    @property
    def endpoint(self) -> str:
        return self._endpoint

    def send_events(self, events: list[dict]) -> None:
        """Best-effort delivery. Never raises."""
        try:
            body = json.dumps({"events": events}).encode("utf-8")
            request = urllib.request.Request(
                self._endpoint,
                data=body,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                },
            )
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                response.read()
        except Exception as exc:  # fail-open: no transport error reaches the app
            if self._debug:
                _log.warning("observeagents: event delivery failed (%s)", type(exc).__name__)
