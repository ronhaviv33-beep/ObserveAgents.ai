from observeagents.events import build_llm_call_event


def _event(**over):
    base = dict(agent_name="support-agent", model="gpt-4.1-mini", duration_ms=850.0,
                status="ok", environment="production")
    base.update(over)
    return build_llm_call_event(**base)


def test_required_shape():
    e = _event(input_tokens=1200, output_tokens=300, team_hint="support", session_id="s-1")
    assert e["source"] == "sdk"
    assert e["event_type"] == "llm_call"
    assert e["provider"] == "openai"
    assert e["agent_name"] == "support-agent"
    assert e["model"] == "gpt-4.1-mini"
    assert e["duration_ms"] == 850.0
    assert e["status"] == "ok"
    assert e["input_tokens"] == 1200 and e["output_tokens"] == 300
    assert e["environment"] == "production" and e["team_hint"] == "support"
    assert e["session_id"] == "s-1"
    assert len(e["trace_id"]) == 32 and len(e["span_id"]) == 16


def test_none_optionals_omitted():
    e = _event(model=None, duration_ms=None)
    for absent in ("model", "duration_ms", "error_type", "input_tokens", "output_tokens",
                   "owner_hint", "team_hint", "session_id", "metadata_json"):
        assert absent not in e


def test_provided_trace_id_kept_span_generated():
    e = _event(trace_id="a" * 32)
    assert e["trace_id"] == "a" * 32
    assert len(e["span_id"]) == 16


def test_error_event():
    e = _event(status="error", error_type="RateLimitError")
    assert e["status"] == "error" and e["error_type"] == "RateLimitError"


def test_metadata_is_scrubbed():
    e = _event(metadata={"prompt": "SECRET", "region": "us"})
    assert e["metadata_json"] == {"region": "us"}


def test_provider_defaults_to_openai():
    assert _event()["provider"] == "openai"


def test_provider_override():
    assert _event(provider="anthropic")["provider"] == "anthropic"
