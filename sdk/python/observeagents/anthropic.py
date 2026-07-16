"""ObserveAnthropic — a drop-in wrapper around the Anthropic Python client.

Passes every messages.create call through to Anthropic unchanged and emits one safe
`llm_call` runtime event (metadata only) to ObserveAgents afterwards. Messages, prompts,
responses, system instructions, and tool arguments go to Anthropic only — they are never
sent to ObserveAgents. The Anthropic API key is used only to construct the Anthropic
client; the ObserveAgents API key is used only for POST {observeagents_url}/runtime-events.
"""
from __future__ import annotations

import os
import time

from observeagents.client import ObserveAgentsClient
from observeagents.events import build_llm_call_event
from observeagents.privacy import error_type_only

_DEFAULT_OBSERVEAGENTS_URL = "https://api.observeagents.ai"


def _resolve(explicit: str | None, env_var: str, default: str | None = None) -> str | None:
    """Config precedence: explicit constructor arg > environment variable > default."""
    if explicit is not None:
        return explicit
    value = os.environ.get(env_var)
    if value:
        return value
    return default


class _Messages:
    def __init__(self, wrapper: "ObserveAnthropic"):
        self._wrapper = wrapper

    def create(self, *args, **kwargs):
        return self._wrapper._create_message(*args, **kwargs)


class ObserveAnthropic:
    """Wraps an Anthropic client; `client.messages.create(...)` is a drop-in.

    `anthropic_client` may be injected (tests, custom construction); otherwise the
    official `anthropic` package is imported lazily and constructed with
    `anthropic_api_key` only.
    """

    def __init__(
        self,
        anthropic_api_key: str | None = None,
        observeagents_api_key: str | None = None,
        observeagents_url: str | None = None,
        agent_name: str | None = None,
        environment: str | None = None,
        owner_hint: str | None = None,
        team_hint: str | None = None,
        session_id: str | None = None,
        trace_id: str | None = None,
        timeout_seconds: float = 2.0,
        debug: bool = False,
        anthropic_client=None,
    ):
        anthropic_api_key = _resolve(anthropic_api_key, "ANTHROPIC_API_KEY")
        observeagents_api_key = _resolve(observeagents_api_key, "OBSERVEAGENTS_API_KEY")
        self._agent_name = _resolve(agent_name, "OBSERVEAGENTS_AGENT_NAME")
        url = _resolve(observeagents_url, "OBSERVEAGENTS_URL", _DEFAULT_OBSERVEAGENTS_URL)
        self._environment = _resolve(environment, "OBSERVEAGENTS_ENVIRONMENT", "development")
        self._owner_hint = _resolve(owner_hint, "OBSERVEAGENTS_OWNER_HINT")
        self._team_hint = _resolve(team_hint, "OBSERVEAGENTS_TEAM_HINT")
        self._session_id = session_id
        self._trace_id = trace_id

        if anthropic_client is None and not anthropic_api_key:
            raise ValueError("anthropic_api_key is required (or set ANTHROPIC_API_KEY)")
        if not observeagents_api_key:
            raise ValueError("observeagents_api_key is required (or set OBSERVEAGENTS_API_KEY)")
        if not self._agent_name:
            raise ValueError("agent_name is required (or set OBSERVEAGENTS_AGENT_NAME)")

        if anthropic_client is not None:
            self._anthropic = anthropic_client
        else:
            from anthropic import Anthropic  # imported lazily; only needed without injection

            self._anthropic = Anthropic(api_key=anthropic_api_key)

        self._observe = ObserveAgentsClient(
            observeagents_url=url,
            observeagents_api_key=observeagents_api_key,
            timeout_seconds=timeout_seconds,
            debug=debug,
        )
        self.messages = _Messages(self)

    # ── internal ──────────────────────────────────────────────────────────────

    def _create_message(self, *args, **kwargs):
        model = kwargs.get("model")
        started = time.monotonic()
        try:
            response = self._anthropic.messages.create(*args, **kwargs)
        except Exception as exc:
            self._emit(model=model, started=started, status="error",
                       error_type=error_type_only(exc), usage=None)
            raise  # the original provider exception, unchanged
        self._emit(model=model, started=started, status="ok",
                   error_type=None, usage=getattr(response, "usage", None))
        return response

    def _emit(self, *, model, started, status, error_type, usage) -> None:
        try:
            duration_ms = (time.monotonic() - started) * 1000.0
            input_tokens = getattr(usage, "input_tokens", None) if usage is not None else None
            output_tokens = getattr(usage, "output_tokens", None) if usage is not None else None
            event = build_llm_call_event(
                agent_name=self._agent_name,
                model=model,
                duration_ms=round(duration_ms, 3),
                status=status,
                provider="anthropic",
                error_type=error_type,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                environment=self._environment,
                owner_hint=self._owner_hint,
                team_hint=self._team_hint,
                session_id=self._session_id,
                trace_id=self._trace_id,
            )
            self._observe.send_events([event])
        except Exception:  # emission must never affect the customer's call path
            pass
