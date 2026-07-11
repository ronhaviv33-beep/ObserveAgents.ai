"""
Tests for the GenAI Semantic Conventions compatibility layer.

Covers:
  1. gen_ai.provider.name provider parsing (preferred attribute)
  2. Backward compatibility with gen_ai.system
  3. gen_ai.operation.name → Runtime timeline classification (+ trace usage totals)
  4. Agent identity via gen_ai.agent.id / gen_ai.agent.name (service.name fallback intact)
  5. Safe prompt metadata (prompt.name/version pass; prompt.variable.* values never stored)
  6. MCP attributes derive capability + mcp_tool_access / mcp_error findings
  7. error.type derives typed error findings (provider_error / tool_error)
  8. No raw prompt/response/tool args/results stored anywhere
  9. Org isolation holds for the new derivations
"""
from __future__ import annotations

import json
import os
import sys
import uuid

# ── Env setup BEFORE any app import ───────────────────────────────────────────
_db_path = f"/tmp/test_genai_semconv_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-genai-semconv")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import (
    Organization, User, OtelSpan, AssetRegistry, OtelAsset,
    AssetCapability, AssetFinding,
)
from app.auth import hash_password, create_token
import app.asset_discovery as _ad

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_org_and_token(db, suffix=""):
    sfx = suffix or uuid.uuid4().hex[:6]
    org = Organization(name=f"semconv-org-{sfx}", slug=f"semconv-{sfx}")
    db.add(org)
    db.flush()
    user = User(
        email=f"semconv-{sfx}@example.com",
        name=f"SemConv {sfx}",
        hashed_password=hash_password("pass"),
        organization_id=org.id,
        role="admin",
        team="eng",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(org)
    db.refresh(user)
    return org, user, create_token(user)


def _attr_value(v):
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": v}
    if isinstance(v, float):
        return {"doubleValue": v}
    if isinstance(v, list):
        return {"arrayValue": {"values": [_attr_value(x) for x in v]}}
    return {"stringValue": str(v)}


def _span(trace_id, span_id, name, attrs=None, parent=None, status_code=None,
          start=1_700_000_000_000_000_000, end=1_700_000_001_000_000_000):
    s = {
        "traceId": trace_id,
        "spanId": span_id,
        "name": name,
        "kind": 3,
        "startTimeUnixNano": start,
        "endTimeUnixNano": end,
        "status": ({"code": status_code} if status_code is not None else {}),
        "attributes": [{"key": k, "value": _attr_value(v)} for k, v in (attrs or {}).items()],
    }
    if parent:
        s["parentSpanId"] = parent
    return s


def _payload(spans, resource_attrs=None):
    return {
        "resourceSpans": [{
            "resource": {"attributes": [
                {"key": k, "value": _attr_value(v)} for k, v in (resource_attrs or {}).items()
            ]},
            "scopeSpans": [{"spans": spans}],
        }]
    }


def _post(token, payload):
    return _client.post("/otel/v1/traces", json=payload,
                        headers={"Authorization": f"Bearer {token}"})


def _run_intelligence(token):
    r = _client.post("/intelligence/run", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    return r.json()


def _trace_detail(token, trace_id):
    r = _client.get(f"/runtime/traces/{trace_id}",
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    return r.json()


def _tid():
    return uuid.uuid4().hex


def _sid():
    return uuid.uuid4().hex[:16]


# ── 1 + 2. Provider parsing: provider.name preferred, gen_ai.system supported ─

def test_provider_name_parsed():
    _ad._known_assets.clear()
    db = SessionLocal()
    org, _, token = _make_org_and_token(db)
    db.close()

    r = _post(token, _payload(
        [_span(_tid(), _sid(), "chat gpt-4o", {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "openai",
            "gen_ai.request.model": "gpt-4o",
        })],
        {"service.name": "provider-name-agent"},
    ))
    assert r.status_code == 202, r.text

    db = SessionLocal()
    try:
        oa = db.query(OtelAsset).filter(
            OtelAsset.organization_id == org.id,
            OtelAsset.service_name == "provider-name-agent",
        ).first()
        assert oa is not None
        assert "Openai" in json.loads(oa.providers_json)
    finally:
        db.close()


def test_gen_ai_system_backward_compat():
    _ad._known_assets.clear()
    db = SessionLocal()
    org, _, token = _make_org_and_token(db)
    db.close()

    r = _post(token, _payload(
        [_span(_tid(), _sid(), "chat claude", {
            "gen_ai.system": "anthropic",
            "gen_ai.request.model": "claude-sonnet-5",
        })],
        {"service.name": "legacy-system-agent"},
    ))
    assert r.status_code == 202, r.text

    db = SessionLocal()
    try:
        oa = db.query(OtelAsset).filter(
            OtelAsset.organization_id == org.id,
            OtelAsset.service_name == "legacy-system-agent",
        ).first()
        assert oa is not None
        assert "Anthropic" in json.loads(oa.providers_json)
        assert "claude-sonnet-5" in json.loads(oa.models_json)
    finally:
        db.close()


# ── 3. Operation classification + usage totals ────────────────────────────────

def test_operation_name_timeline_classification_and_usage():
    _ad._known_assets.clear()
    db = SessionLocal()
    org, _, token = _make_org_and_token(db)
    db.close()

    trace_id = _tid()
    root = _sid()
    spans = [
        _span(trace_id, root, "invoke_agent support-agent", {
            "gen_ai.operation.name": "invoke_agent",
            "gen_ai.agent.name": "ops-classify-agent",
        }),
        _span(trace_id, _sid(), "plan", {
            "gen_ai.operation.name": "plan",
            "gen_ai.provider.name": "openai",
            "gen_ai.request.model": "gpt-4o",
        }, parent=root),
        _span(trace_id, _sid(), "chat gpt-4o", {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "openai",
            "gen_ai.request.model": "gpt-4o",
            "gen_ai.usage.input_tokens": 800,
            "gen_ai.usage.output_tokens": 200,
            "gen_ai.usage.cache_read.input_tokens": 512,
            "gen_ai.usage.cache_creation.input_tokens": 64,
            "gen_ai.usage.reasoning.output_tokens": 40,
        }, parent=root),
        _span(trace_id, _sid(), "retrieval kb", {
            "gen_ai.operation.name": "retrieval",
            "gen_ai.tool.name": "kb_vector_search",
        }, parent=root),
        _span(trace_id, _sid(), "embeddings", {
            "gen_ai.operation.name": "embeddings",
            "gen_ai.request.model": "text-embedding-3-small",
        }, parent=root),
        _span(trace_id, _sid(), "execute_tool crm_lookup", {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "crm_lookup",
        }, parent=root),
        _span(trace_id, _sid(), "tools/call repo_search", {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "repo_search",
            "mcp.method.name": "tools/call",
            "mcp.server": "repo-context-mcp",
        }, parent=root),
        _span(trace_id, _sid(), "search_memory", {
            "gen_ai.operation.name": "search_memory",
        }, parent=root),
        _span(trace_id, _sid(), "invoke_workflow escalation", {
            "gen_ai.operation.name": "invoke_workflow",
        }, parent=root),
    ]
    r = _post(token, _payload(spans, {"service.name": "ops-classify-agent"}))
    assert r.status_code == 202, r.text

    detail = _trace_detail(token, trace_id)
    by_name = {s["name"]: s for s in detail["spans"]}
    assert by_name["invoke_agent support-agent"]["step_type"] == "agent"
    assert by_name["plan"]["step_type"] == "plan"
    assert by_name["chat gpt-4o"]["step_type"] == "llm"
    assert by_name["retrieval kb"]["step_type"] == "retrieval"
    assert by_name["embeddings"]["step_type"] == "embedding"
    assert by_name["execute_tool crm_lookup"]["step_type"] == "tool"
    assert by_name["tools/call repo_search"]["step_type"] == "mcp_tool"
    assert by_name["search_memory"]["step_type"] == "memory"
    assert by_name["invoke_workflow escalation"]["step_type"] == "workflow"
    assert by_name["chat gpt-4o"]["operation"] == "chat"

    usage = detail["usage"]
    assert usage["input_tokens"] == 800
    assert usage["output_tokens"] == 200
    assert usage["cache_read_input_tokens"] == 512
    assert usage["cache_creation_input_tokens"] == 64
    assert usage["reasoning_output_tokens"] == 40


# ── 4. Agent identity ─────────────────────────────────────────────────────────

def test_agent_identity_via_agent_id_and_name():
    _ad._known_assets.clear()
    db = SessionLocal()
    org, _, token = _make_org_and_token(db)
    db.close()

    attrs = {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.agent.id": "agent-uuid-42",
        "gen_ai.agent.name": "billing-copilot",
        "gen_ai.agent.version": "3.2.1",
    }
    # Two traces from two different service names, same agent id → one asset.
    # The second trace also has a child span WITHOUT agent attrs — it must
    # inherit the trace's declared identity, not fragment into a service asset.
    t2, root2 = _tid(), _sid()
    r1 = _post(token, _payload([_span(_tid(), _sid(), "invoke_agent billing-copilot", attrs)],
                               {"service.name": "svc-east"}))
    r2 = _post(token, _payload([
        _span(t2, root2, "invoke_agent billing-copilot", attrs),
        _span(t2, _sid(), "chat gpt-4o", {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "openai",
            "gen_ai.request.model": "gpt-4o",
        }, parent=root2),
    ], {"service.name": "svc-west"}))
    assert r1.status_code == 202 and r2.status_code == 202

    db = SessionLocal()
    try:
        rows = db.query(AssetRegistry).filter(
            AssetRegistry.organization_id == org.id,
            AssetRegistry.agent_id_raw == "agent-uuid-42",
        ).all()
        assert len(rows) == 1
        assert rows[0].agent_name == "billing-copilot"  # display name, not the id
        evidence = json.loads(rows[0].evidence or "{}")
        assert evidence.get("gen_ai.agent.version") == "3.2.1"

        # The plain child span did NOT create a service-named asset
        fragmented = db.query(AssetRegistry).filter(
            AssetRegistry.organization_id == org.id,
            AssetRegistry.agent_id_raw.in_(["svc-east", "svc-west"]),
        ).count()
        assert fragmented == 0
    finally:
        db.close()


def test_service_name_fallback_grouping_unchanged():
    _ad._known_assets.clear()
    db = SessionLocal()
    org, _, token = _make_org_and_token(db)
    db.close()

    r = _post(token, _payload(
        [_span(_tid(), _sid(), "chat", {"gen_ai.system": "openai", "gen_ai.request.model": "gpt-4o-mini"})],
        {"service.name": "plain-service-agent"},
    ))
    assert r.status_code == 202

    db = SessionLocal()
    try:
        row = db.query(AssetRegistry).filter(
            AssetRegistry.organization_id == org.id,
            AssetRegistry.agent_name == "plain-service-agent",
        ).first()
        assert row is not None
        assert row.agent_id_raw == "plain-service-agent"
    finally:
        db.close()


# ── 5. Safe prompt metadata ───────────────────────────────────────────────────

def test_safe_prompt_metadata_without_content():
    _ad._known_assets.clear()
    db = SessionLocal()
    org, _, token = _make_org_and_token(db)
    db.close()

    trace_id = _tid()
    r = _post(token, _payload(
        [_span(trace_id, _sid(), "chat gpt-4o", {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "openai",
            "gen_ai.request.model": "gpt-4o",
            "gen_ai.prompt.name": "support-escalation-v2",
            "gen_ai.prompt.version": "7",
            "gen_ai.prompt.variable.customer_name": "SECRET Acme Corp",
            "gen_ai.prompt.variable.ticket_id": "SECRET-1234",
        })],
        {"service.name": "prompt-meta-agent"},
    ))
    assert r.status_code == 202, r.text

    db = SessionLocal()
    try:
        span = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org.id, OtelSpan.trace_id == trace_id,
        ).first()
        attrs = json.loads(span.attributes_json)
        # Safe metadata is preserved
        assert attrs["gen_ai.prompt.name"] == "support-escalation-v2"
        assert attrs["gen_ai.prompt.version"] == "7"
        # Variable NAMES are listed; values are gone entirely
        assert attrs["gen_ai.prompt.variables"] == ["customer_name", "ticket_id"]
        assert "gen_ai.prompt.variable.customer_name" not in attrs
        assert "SECRET" not in span.attributes_json
    finally:
        db.close()


# ── 6. MCP capability + findings ──────────────────────────────────────────────

def test_mcp_attributes_derive_capability_and_findings():
    _ad._known_assets.clear()
    db = SessionLocal()
    org, _, token = _make_org_and_token(db)
    db.close()

    trace_id = _tid()
    spans = [
        _span(trace_id, _sid(), "tools/call repo_search", {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "repo_search",
            "mcp.method.name": "tools/call",
            "mcp.session.id": "sess-1",
            "mcp.protocol.version": "2025-06-18",
            "mcp.server": "repo-context-mcp",
        }),
        _span(trace_id, _sid(), "tools/call failing_tool", {
            "gen_ai.tool.name": "failing_tool",
            "mcp.method.name": "tools/call",
            "rpc.response.status_code": -32000,
            "error.type": "tool_error",
        }, status_code=2),
    ]
    r = _post(token, _payload(spans, {
        "service.name": "mcp-prod-agent",
        "deployment.environment": "production",
    }))
    assert r.status_code == 202, r.text
    _run_intelligence(token)

    db = SessionLocal()
    try:
        caps = db.query(AssetCapability).filter(
            AssetCapability.organization_id == org.id,
            AssetCapability.capability_type == "mcp",
        ).all()
        cap_names = {c.capability_name for c in caps}
        assert "repo_search" in cap_names

        finds = db.query(AssetFinding).filter(AssetFinding.organization_id == org.id).all()
        types = {f.finding_type for f in finds}
        assert "mcp_tool_access" in types, types
        assert "mcp_error" in types, types
    finally:
        db.close()


# ── 7. error.type → typed findings ────────────────────────────────────────────

def test_error_type_derives_provider_and_tool_errors():
    _ad._known_assets.clear()
    db = SessionLocal()
    org, _, token = _make_org_and_token(db)
    db.close()

    trace_id = _tid()
    spans = [
        _span(trace_id, _sid(), "chat gpt-4o-mini", {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "openai",
            "gen_ai.request.model": "gpt-4o-mini",
            "error.type": "rate_limit_exceeded",
        }, status_code=2),
        _span(trace_id, _sid(), "execute_tool broken_tool", {
            "tool.name": "broken_tool",
            "error.type": "timeout",
        }, status_code=2),
    ]
    r = _post(token, _payload(spans, {"service.name": "error-typed-agent"}))
    assert r.status_code == 202, r.text
    _run_intelligence(token)

    db = SessionLocal()
    try:
        finds = db.query(AssetFinding).filter(AssetFinding.organization_id == org.id).all()
        types = {f.finding_type for f in finds}
        assert "provider_error" in types, types
        assert "tool_error" in types, types
    finally:
        db.close()


# ── 8. No raw sensitive content stored ────────────────────────────────────────

def test_no_raw_sensitive_content_stored():
    _ad._known_assets.clear()
    db = SessionLocal()
    org, _, token = _make_org_and_token(db)
    db.close()

    trace_id = _tid()
    sensitive = {
        "gen_ai.input.messages": ["RAWSECRET user message one", "RAWSECRET two"],
        "gen_ai.output.messages": ["RAWSECRET assistant reply"],
        "gen_ai.system_instructions": "RAWSECRET system prompt",
        "gen_ai.tool.call.arguments": json.dumps({"query": "RAWSECRET", "limit": 5}),
        "gen_ai.tool.call.result": "RAWSECRET tool output",
        "tool.arguments": json.dumps({"path": "RAWSECRET/etc"}),
        "tool.result": "RAWSECRET result",
    }
    r = _post(token, _payload(
        [_span(trace_id, _sid(), "chat gpt-4o", {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "openai",
            "gen_ai.request.model": "gpt-4o",
            **sensitive,
        })],
        {"service.name": "privacy-agent"},
    ))
    assert r.status_code == 202, r.text

    db = SessionLocal()
    try:
        span = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org.id, OtelSpan.trace_id == trace_id,
        ).first()
        assert "RAWSECRET" not in (span.attributes_json or "")
        attrs = json.loads(span.attributes_json)
        for key in sensitive:
            assert attrs[key]["redacted"] is True
            assert attrs[key]["sha256"]
            assert attrs[key]["size_bytes"] > 0
        # Safe indicators
        assert attrs["gen_ai.input.messages"]["message_count"] == 2
        assert attrs["gen_ai.output.messages"]["message_count"] == 1
        assert attrs["gen_ai.tool.call.arguments"]["argument_keys"] == ["limit", "query"]

        # Nothing else in the row leaks content either
        for col in (span.resource_attributes_json, span.events_json, span.status_message):
            assert "RAWSECRET" not in (col or "")
    finally:
        db.close()


# ── 9. Org isolation ──────────────────────────────────────────────────────────

def test_org_isolation_for_new_derivations():
    _ad._known_assets.clear()
    db = SessionLocal()
    org_a, _, token_a = _make_org_and_token(db, "isoA")
    org_b, _, token_b = _make_org_and_token(db, "isoB")
    db.close()

    r = _post(token_a, _payload(
        [_span(_tid(), _sid(), "tools/call secret_tool", {
            "gen_ai.tool.name": "secret_tool",
            "mcp.method.name": "tools/call",
        }, status_code=2)],
        {"service.name": "iso-agent", "deployment.environment": "production"},
    ))
    assert r.status_code == 202
    _run_intelligence(token_a)
    _run_intelligence(token_b)

    db = SessionLocal()
    try:
        b_caps = db.query(AssetCapability).filter(
            AssetCapability.organization_id == org_b.id).count()
        b_finds = db.query(AssetFinding).filter(
            AssetFinding.organization_id == org_b.id).count()
        assert b_caps == 0 and b_finds == 0

        a_finds = db.query(AssetFinding).filter(
            AssetFinding.organization_id == org_a.id).all()
        assert {"mcp_tool_access", "mcp_error"} <= {f.finding_type for f in a_finds}
    finally:
        db.close()


# ── 10. extract_genai_scalar_fields unit tests ────────────────────────────────

from app.genai_semconv import extract_genai_scalar_fields, extract_time_to_first_chunk_ms


def test_scalar_fields_full_extraction():
    fields = extract_genai_scalar_fields({
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "anthropic",
        "gen_ai.request.model": "claude-sonnet-5",
        "gen_ai.response.model": "claude-sonnet-5-20250929",
        "gen_ai.usage.input_tokens": 100,
        "gen_ai.usage.output_tokens": 50,
        "gen_ai.usage.reasoning.output_tokens": 10,
        "gen_ai.usage.cache_read.input_tokens": 20,
        "gen_ai.usage.cache_creation.input_tokens": 30,
        "gen_ai.response.finish_reasons": ["stop", "length"],
        "gen_ai.request.stream": True,
        "gen_ai.response.time_to_first_chunk": 0.35,
    })
    assert fields["operation_name"] == "chat"
    assert fields["provider_name"] == "anthropic"
    assert fields["request_model"] == "claude-sonnet-5"
    assert fields["response_model"] == "claude-sonnet-5-20250929"
    assert fields["input_tokens"] == 100
    assert fields["output_tokens"] == 50
    assert fields["reasoning_output_tokens"] == 10
    assert fields["cache_read_input_tokens"] == 20
    assert fields["cache_creation_input_tokens"] == 30
    assert json.loads(fields["finish_reasons_json"]) == ["stop", "length"]
    assert fields["request_stream"] is True
    assert fields["time_to_first_chunk_ms"] == 350


def test_scalar_fields_deprecated_token_names():
    fields = extract_genai_scalar_fields({
        "gen_ai.usage.prompt_tokens": 5,
        "gen_ai.usage.completion_tokens": 0,  # legitimate zero must survive
    })
    assert fields["input_tokens"] == 5
    assert fields["output_tokens"] == 0


def test_scalar_fields_underscore_cache_reasoning_variants():
    fields = extract_genai_scalar_fields({
        "gen_ai.usage.cache_read_input_tokens": 7,
        "gen_ai.usage.cache_creation_input_tokens": 8,
        "gen_ai.usage.reasoning_output_tokens": 9,
    })
    assert fields["cache_read_input_tokens"] == 7
    assert fields["cache_creation_input_tokens"] == 8
    assert fields["reasoning_output_tokens"] == 9


def test_scalar_fields_finish_reasons_string_normalized():
    fields = extract_genai_scalar_fields({"gen_ai.response.finish_reasons": "stop"})
    assert json.loads(fields["finish_reasons_json"]) == ["stop"]


def test_scalar_fields_stream_string_values():
    assert extract_genai_scalar_fields({"gen_ai.request.stream": "true"})["request_stream"] is True
    assert extract_genai_scalar_fields({"gen_ai.request.stream": "false"})["request_stream"] is False
    assert extract_genai_scalar_fields({})["request_stream"] is None


def test_time_to_first_chunk_units():
    # SemConv key is seconds → ms
    assert extract_time_to_first_chunk_ms({"gen_ai.response.time_to_first_chunk": 0.35}) == 350
    # ttft_ms is already ms
    assert extract_time_to_first_chunk_ms({"ttft_ms": 420}) == 420
    # junk values → None
    assert extract_time_to_first_chunk_ms({"gen_ai.response.time_to_first_chunk": -1}) is None
    assert extract_time_to_first_chunk_ms({"gen_ai.response.time_to_first_chunk": "abc"}) is None
    assert extract_time_to_first_chunk_ms({"ttft_ms": "abc"}) is None
    assert extract_time_to_first_chunk_ms({}) is None
    # > 24h is junk
    assert extract_time_to_first_chunk_ms({"ttft_ms": 90_000_000}) is None


def test_scalar_fields_never_read_content_keys():
    """A dict containing only content keys yields all-None fields — the
    extractor must never touch message/tool/prompt content."""
    fields = extract_genai_scalar_fields({
        "gen_ai.input.messages": "secret",
        "gen_ai.output.messages": "secret",
        "gen_ai.system_instructions": "secret",
        "gen_ai.tool.call.arguments": "secret",
        "gen_ai.tool.call.result": "secret",
        "tool.arguments": "secret",
        "tool.result": "secret",
        "prompt": "secret",
        "response": "secret",
    })
    assert all(v is None for v in fields.values())
    assert "secret" not in json.dumps({k: v for k, v in fields.items() if v is not None})


# ── 11. Tiered fallback extraction (real-world telemetry variants) ────────────

from app.genai_semconv import (
    TIER_FALLBACK,
    TIER_STANDARD,
    extract_environment_tiered,
    extract_mcp_method_tiered,
    extract_model_tiered,
    extract_provider_tiered,
    extract_tool_name_tiered,
    extract_usage_tiered,
    has_genai_signal,
    is_mcp_span,
)


def test_model_tiered_standard_and_fallbacks():
    assert extract_model_tiered({"gen_ai.request.model": "m"}) == ("m", TIER_STANDARD)
    assert extract_model_tiered({"gen_ai.response.model": "m"}) == ("m", TIER_STANDARD)
    for key in ("gen_ai.model", "llm.model", "llm.model_name", "model.name"):
        assert extract_model_tiered({key: "m"}) == ("m", TIER_FALLBACK), key
    # standard beats fallback when both present
    assert extract_model_tiered(
        {"llm.model": "fb", "gen_ai.request.model": "std"}) == ("std", TIER_STANDARD)
    assert extract_model_tiered({}) == (None, None)


def test_bare_model_and_provider_keys_not_extracted():
    """Bare collision-prone keys are org-mapping-only, never global fallbacks."""
    assert extract_model_tiered({"model": "gpt-4"}) == (None, None)
    assert extract_provider_tiered({"provider": "openai"}) == (None, None)
    assert extract_provider_tiered({"vendor": "openai"}) == (None, None)
    assert extract_tool_name_tiered({"tool": "search"}) == (None, None)


def test_provider_tiered_fallbacks():
    assert extract_provider_tiered({"gen_ai.provider.name": "p"}) == ("p", TIER_STANDARD)
    assert extract_provider_tiered({"gen_ai.system": "p"}) == ("p", TIER_STANDARD)
    for key in ("llm.provider", "llm.vendor"):
        assert extract_provider_tiered({key: "p"}) == ("p", TIER_FALLBACK), key


def test_tool_tiered_fallbacks():
    for key in ("gen_ai.tool.name", "tool.name", "mcp.tool.name", "mcp.tool"):
        assert extract_tool_name_tiered({key: "t"}) == ("t", TIER_STANDARD), key
    for key in ("tool_name", "function.name", "function_name"):
        assert extract_tool_name_tiered({key: "t"}) == ("t", TIER_FALLBACK), key


def test_environment_tiered_resource_before_span_and_fallbacks():
    assert extract_environment_tiered(
        {"deployment.environment": "prod"}, {}) == ("prod", TIER_STANDARD)
    assert extract_environment_tiered(
        {"deployment.environment.name": "prod"}, {}) == ("prod", TIER_STANDARD)
    # span-level standard key still wins over resource-level fallback key
    assert extract_environment_tiered(
        {"env": "staging"}, {"deployment.environment": "prod"}) == ("prod", TIER_STANDARD)
    for key in ("environment", "env", "service.environment"):
        assert extract_environment_tiered({key: "qa"}, {}) == ("qa", TIER_FALLBACK), key
    assert extract_environment_tiered({}, {}) == (None, None)


def test_mcp_method_tiered_closed_value_set():
    assert extract_mcp_method_tiered(
        {"mcp.method.name": "tools/call"}) == ("tools/call", TIER_STANDARD)
    # generic rpc.method / method keys count only on exact MCP method values
    assert extract_mcp_method_tiered(
        {"rpc.method": "tools/call"}) == ("tools/call", TIER_FALLBACK)
    assert extract_mcp_method_tiered(
        {"method": "resources/read"}) == ("resources/read", TIER_FALLBACK)
    # non-MCP method values are rejected — no substring / prefix matching
    assert extract_mcp_method_tiered({"rpc.method": "GET"}) == (None, None)
    assert extract_mcp_method_tiered({"rpc.method": "com.acme.Svc/Call"}) == (None, None)
    assert extract_mcp_method_tiered({"method": "tools/call/extra"}) == (None, None)


def test_is_mcp_span_via_method_value_fallback():
    assert is_mcp_span({"rpc.method": "tools/call"}) is True
    assert is_mcp_span({"method": "prompts/get"}) is True
    assert is_mcp_span({"rpc.method": "GET"}) is False


def test_usage_tiered_llm_variants_and_zero_preserved():
    usage, tier = extract_usage_tiered(
        {"llm.usage.prompt_tokens": 0, "llm.usage.completion_tokens": 12})
    assert usage["input_tokens"] == 0        # zero must survive fallback path
    assert usage["output_tokens"] == 12
    assert tier == TIER_FALLBACK
    usage, tier = extract_usage_tiered(
        {"llm.token_count.prompt": 3, "llm.token_count.completion": 4})
    assert (usage["input_tokens"], usage["output_tokens"]) == (3, 4)
    assert tier == TIER_FALLBACK


def test_usage_bare_keys_gated_on_genai_context():
    # bare counters WITHOUT any GenAI signal → ignored (non-LLM domains use them too)
    usage, tier = extract_usage_tiered({"input_tokens": 9, "output_tokens": 5})
    assert usage["input_tokens"] is None and usage["output_tokens"] is None
    assert tier is None
    # same counters WITH a non-bare GenAI signal → honored at fallback tier
    usage, tier = extract_usage_tiered(
        {"llm.model": "m", "input_tokens": 9, "output_tokens": 5})
    assert (usage["input_tokens"], usage["output_tokens"]) == (9, 5)
    assert tier == TIER_FALLBACK
    # standard keys keep standard tier even when bare keys coexist
    usage, tier = extract_usage_tiered(
        {"gen_ai.usage.input_tokens": 1, "prompt_tokens": 99})
    assert usage["input_tokens"] == 1
    assert tier == TIER_STANDARD


def test_has_genai_signal_tiers():
    assert has_genai_signal({"gen_ai.request.model": "m"}) == (True, TIER_STANDARD)
    assert has_genai_signal({"llm.model": "m"}) == (True, TIER_FALLBACK)
    assert has_genai_signal({"model.name": "m"}) == (True, TIER_FALLBACK)
    assert has_genai_signal({"http.url": "https://x"}) == (False, None)
    # bare token keys are NOT signals by themselves
    assert has_genai_signal({"input_tokens": 5}) == (False, None)


def test_scalar_fields_fallback_model_populates_request_model():
    fields = extract_genai_scalar_fields({"llm.model": "acme-1"})
    assert fields["request_model"] == "acme-1"
    assert fields["response_model"] is None
    # gen_ai.response.model must never leak into request_model via fallback
    fields = extract_genai_scalar_fields({"gen_ai.response.model": "resp-m"})
    assert fields["request_model"] is None
    assert fields["response_model"] == "resp-m"
