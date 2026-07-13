"""ObserveOpenAI wrapper tests.

The fake urlopen patches the REAL transport seam (observeagents.client.urllib.request
.urlopen), so every assertion about outgoing traffic runs against the actual serialized
HTTP request — URL, headers, and body bytes — not a stubbed layer above it.
"""
from __future__ import annotations

import contextlib
import json

import pytest

import observeagents.client as oa_client
from observeagents import ObserveOpenAI

OPENAI_KEY = "sk-OPENAI-SECRET-KEY"
OBSERVE_KEY = "gk_observe_key"
SENTINEL_USER = "USER-PROMPT-SENTINEL-9631"
SENTINEL_SYSTEM = "SYSTEM-INSTRUCTIONS-SENTINEL-4127"
SENTINEL_RESPONSE = "RESPONSE-CONTENT-SENTINEL-8354"


# ── fakes ─────────────────────────────────────────────────────────────────────

class FakeUsage:
    prompt_tokens = 1200
    completion_tokens = 300


class FakeResponse:
    usage = FakeUsage()
    choices = [{"message": {"content": SENTINEL_RESPONSE}}]


class FakeOpenAI:
    """Duck-types client.chat.completions.create; records kwargs, returns or raises."""

    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls: list[dict] = []
        completions = self

        class _C:
            @staticmethod
            def create(*args, **kwargs):
                return completions._create(*args, **kwargs)

        class _Chat:
            completions = _C()

        self.chat = _Chat()

    def _create(self, *args, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return FakeResponse()


class CapturedRequest:
    def __init__(self, request, timeout):
        self.url = request.full_url
        self.headers = dict(request.header_items())
        self.body = request.data
        self.timeout = timeout


@pytest.fixture
def captured(monkeypatch):
    """Patch the real urlopen; capture every outgoing request."""
    seen: list[CapturedRequest] = []

    @contextlib.contextmanager
    def fake_urlopen(request, timeout=None):
        seen.append(CapturedRequest(request, timeout))
        class _R:
            @staticmethod
            def read():
                return b"{}"
        yield _R()

    monkeypatch.setattr(oa_client.urllib.request, "urlopen", fake_urlopen)
    return seen


def _wrapper(fake_openai=None, **over):
    kwargs = dict(
        observeagents_api_key=OBSERVE_KEY,
        observeagents_url="https://api.observeagents.ai",
        agent_name="support-agent",
        environment="production",
        team_hint="support",
        openai_client=fake_openai or FakeOpenAI(),
    )
    kwargs.update(over)
    return ObserveOpenAI(**kwargs)


def _call(client):
    return client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "system", "content": SENTINEL_SYSTEM},
                  {"role": "user", "content": SENTINEL_USER}],
    )


def _sent_event(captured_request):
    body = json.loads(captured_request.body.decode("utf-8"))
    assert list(body.keys()) == ["events"]
    assert len(body["events"]) == 1
    return body["events"][0]


# ── 1. success emits exactly one llm_call event ───────────────────────────────

def test_successful_call_emits_one_llm_call_event(captured):
    response = _call(_wrapper())
    assert response.usage.prompt_tokens == 1200  # provider response returned unchanged
    assert len(captured) == 1
    event = _sent_event(captured[0])
    assert event["source"] == "sdk" and event["event_type"] == "llm_call"
    assert event["provider"] == "openai" and event["model"] == "gpt-4.1-mini"
    assert event["agent_name"] == "support-agent"
    assert event["status"] == "ok"
    assert event["input_tokens"] == 1200 and event["output_tokens"] == 300
    assert event["environment"] == "production" and event["team_hint"] == "support"
    assert event["duration_ms"] >= 0
    assert len(event["trace_id"]) == 32 and len(event["span_id"]) == 16
    assert captured[0].timeout == 2.0


# ── 2. failure emits status=error and re-raises the original exception ────────

def test_failed_call_emits_error_event_and_reraises_original(captured):
    class RateLimitError(Exception):
        pass

    original = RateLimitError(f"quota exceeded for: {SENTINEL_USER}")
    with pytest.raises(RateLimitError) as excinfo:
        _call(_wrapper(FakeOpenAI(error=original)))
    assert excinfo.value is original  # unchanged, same object
    assert len(captured) == 1
    event = _sent_event(captured[0])
    assert event["status"] == "error"
    assert event["error_type"] == "RateLimitError"  # class name only
    assert "quota" not in json.dumps(event)          # never the message


# ── 3. prompts/messages never appear in the outgoing payload ──────────────────

def test_no_prompt_or_message_content_in_outgoing_payload(captured):
    _call(_wrapper())
    raw = captured[0].body.decode("utf-8") + json.dumps(captured[0].headers) + captured[0].url
    for sentinel in (SENTINEL_USER, SENTINEL_SYSTEM, SENTINEL_RESPONSE, "messages"):
        assert sentinel not in raw, f"content leaked: {sentinel}"


# ── 4. the OpenAI API key is never sent to ObserveAgents ──────────────────────

def test_openai_key_never_sent_to_observeagents(captured, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", OPENAI_KEY)
    _call(_wrapper())  # key resolved from env; injected client means it's unused anyway
    raw = captured[0].body.decode("utf-8") + json.dumps(captured[0].headers) + captured[0].url
    assert OPENAI_KEY not in raw
    assert captured[0].headers.get("Authorization") == f"Bearer {OBSERVE_KEY}"


# ── 5. ObserveAgents failure never breaks the OpenAI call ─────────────────────

def test_observeagents_outage_does_not_break_llm_call(monkeypatch):
    def exploding_urlopen(request, timeout=None):
        raise TimeoutError("observeagents unreachable")

    monkeypatch.setattr(oa_client.urllib.request, "urlopen", exploding_urlopen)
    response = _call(_wrapper())
    assert response.usage.completion_tokens == 300  # fail-open: call unaffected


# ── 6. configurable endpoint: Cloud or customer-side Collector ────────────────

def test_url_points_to_cloud_or_collector(captured):
    _call(_wrapper(observeagents_url="https://api.observeagents.ai"))
    _call(_wrapper(observeagents_url="https://observeagents-collector.customer.com/"))
    assert captured[0].url == "https://api.observeagents.ai/runtime-events"
    assert captured[1].url == "https://observeagents-collector.customer.com/runtime-events"


# ── 7 & 8. configuration precedence ───────────────────────────────────────────

def test_constructor_args_override_env_vars(captured, monkeypatch):
    monkeypatch.setenv("OBSERVEAGENTS_API_KEY", "gk_from_env")
    monkeypatch.setenv("OBSERVEAGENTS_URL", "https://env.example.com")
    monkeypatch.setenv("OBSERVEAGENTS_AGENT_NAME", "env-agent")
    monkeypatch.setenv("OBSERVEAGENTS_ENVIRONMENT", "staging")
    monkeypatch.setenv("OBSERVEAGENTS_TEAM_HINT", "env-team")
    _call(_wrapper())  # explicit constructor args everywhere
    event = _sent_event(captured[0])
    assert captured[0].url == "https://api.observeagents.ai/runtime-events"
    assert captured[0].headers.get("Authorization") == f"Bearer {OBSERVE_KEY}"
    assert event["agent_name"] == "support-agent"
    assert event["environment"] == "production" and event["team_hint"] == "support"


def test_env_vars_used_when_constructor_args_omitted(captured, monkeypatch):
    monkeypatch.setenv("OBSERVEAGENTS_API_KEY", "gk_from_env")
    monkeypatch.setenv("OBSERVEAGENTS_URL", "https://collector.internal.example.com")
    monkeypatch.setenv("OBSERVEAGENTS_AGENT_NAME", "env-agent")
    monkeypatch.setenv("OBSERVEAGENTS_ENVIRONMENT", "staging")
    monkeypatch.setenv("OBSERVEAGENTS_TEAM_HINT", "env-team")
    monkeypatch.setenv("OBSERVEAGENTS_OWNER_HINT", "env-owner")
    client = ObserveOpenAI(openai_client=FakeOpenAI())  # nothing explicit
    _call(client)
    event = _sent_event(captured[0])
    assert captured[0].url == "https://collector.internal.example.com/runtime-events"
    assert captured[0].headers.get("Authorization") == "Bearer gk_from_env"
    assert event["agent_name"] == "env-agent"
    assert event["environment"] == "staging"
    assert event["team_hint"] == "env-team" and event["owner_hint"] == "env-owner"


def test_defaults_and_required_validation(monkeypatch):
    for var in ("OPENAI_API_KEY", "OBSERVEAGENTS_API_KEY", "OBSERVEAGENTS_AGENT_NAME",
                "OBSERVEAGENTS_URL", "OBSERVEAGENTS_ENVIRONMENT"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ValueError):
        ObserveOpenAI(openai_client=FakeOpenAI(), agent_name="a")   # missing observe key
    with pytest.raises(ValueError):
        ObserveOpenAI(openai_client=FakeOpenAI(), observeagents_api_key="gk_x")  # missing agent
    with pytest.raises(ValueError):
        ObserveOpenAI(observeagents_api_key="gk_x", agent_name="a")  # missing openai key
    client = ObserveOpenAI(openai_client=FakeOpenAI(), observeagents_api_key="gk_x",
                           agent_name="a")
    assert client._observe.endpoint == "https://api.observeagents.ai/runtime-events"
    assert client._environment == "development"
