"""
Tests for OTLP/HTTP protobuf trace ingestion at POST /otel/v1/traces.

Covers the Phase 3 acceptance list:
  1.  JSON ingestion still works (regression sanity — full JSON suite runs separately)
  2.  Minimal protobuf trace creates an OtelSpan row (hex ids, timestamps, status)
  3.  Protobuf GenAI span feeds asset + intelligence derivation
  4.  Protobuf privacy — sensitive attrs scrubbed identically to JSON
  5.  Protobuf without auth → 401
  6.  Malformed protobuf → 400
  7.  Unsupported content type → 415
  8.  JSON content type with protobuf body → 400
  9.  Protobuf content type with JSON body → 400
  10. Org isolation for protobuf spans
  11. Array attributes (string/int/double/bool) convert safely
  12. gen_ai.system backward compatibility (no gen_ai.provider.name)
Plus: metrics-shaped/empty protobuf → 400 with a clear message.
"""
from __future__ import annotations

import json
import os
import sys
import uuid

# ── Env setup BEFORE any app import ───────────────────────────────────────────
_db_path = f"/tmp/test_otel_protobuf_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-otel-protobuf")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

from fastapi.testclient import TestClient
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, ArrayValue, KeyValue
from opentelemetry.proto.trace.v1.trace_pb2 import Status

from app.main import app
from app.database import SessionLocal
from app.models import Organization, User, OtelSpan, OtelAsset, AssetCapability
from app.auth import hash_password, create_token
import app.asset_discovery as _ad

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")

_PB = {"Content-Type": "application/x-protobuf"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_org_and_token(db, suffix=""):
    sfx = suffix or uuid.uuid4().hex[:6]
    org = Organization(name=f"pb-org-{sfx}", slug=f"pb-{sfx}")
    db.add(org)
    db.flush()
    user = User(
        email=f"pb-{sfx}@example.com",
        name=f"PB {sfx}",
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


def _av(value) -> AnyValue:
    if isinstance(value, bool):
        return AnyValue(bool_value=value)
    if isinstance(value, int):
        return AnyValue(int_value=value)
    if isinstance(value, float):
        return AnyValue(double_value=value)
    if isinstance(value, list):
        return AnyValue(array_value=ArrayValue(values=[_av(v) for v in value]))
    return AnyValue(string_value=str(value))


def _kvs(attrs: dict) -> list[KeyValue]:
    return [KeyValue(key=k, value=_av(v)) for k, v in attrs.items()]


def _pb_request(spans_spec: list[dict], resource_attrs: dict | None = None) -> bytes:
    """Build an ExportTraceServiceRequest with one resource span."""
    req = ExportTraceServiceRequest()
    rs = req.resource_spans.add()
    rs.resource.attributes.extend(_kvs(resource_attrs or {}))
    ss = rs.scope_spans.add()
    ss.scope.name = "test-instrumentation"
    for spec in spans_spec:
        span = ss.spans.add()
        span.trace_id = bytes.fromhex(spec["trace_id"])
        span.span_id = bytes.fromhex(spec["span_id"])
        if spec.get("parent_span_id"):
            span.parent_span_id = bytes.fromhex(spec["parent_span_id"])
        span.name = spec.get("name", "span")
        span.kind = spec.get("kind", 3)
        span.start_time_unix_nano = spec.get("start", 1_700_000_000_000_000_000)
        span.end_time_unix_nano = spec.get("end", 1_700_000_001_000_000_000)
        if spec.get("status_code") is not None:
            span.status.CopyFrom(Status(code=spec["status_code"], message=spec.get("status_message", "")))
        span.attributes.extend(_kvs(spec.get("attrs", {})))
    return req.SerializeToString()


def _post_pb(token: str | None, raw: bytes, content_type="application/x-protobuf"):
    headers = {"Content-Type": content_type}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return _client.post("/otel/v1/traces", content=raw, headers=headers)


def _tid():
    return uuid.uuid4().hex


def _sid():
    return uuid.uuid4().hex[:16]


# ── 1. JSON regression sanity ─────────────────────────────────────────────────

def test_json_ingestion_still_works():
    _ad._known_assets.clear()
    db = SessionLocal()
    org, _, token = _make_org_and_token(db)
    db.close()

    trace_id = _tid()
    r = _client.post("/otel/v1/traces", json={
        "resourceSpans": [{
            "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "json-regression-agent"}}]},
            "scopeSpans": [{"spans": [{
                "traceId": trace_id, "spanId": _sid(), "name": "chat", "kind": 3,
                "startTimeUnixNano": 1_700_000_000_000_000_000,
                "endTimeUnixNano": 1_700_000_001_000_000_000,
                "status": {},
                "attributes": [{"key": "gen_ai.request.model", "value": {"stringValue": "gpt-4o"}}],
            }]}],
        }],
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 202, r.text

    db = SessionLocal()
    try:
        assert db.query(OtelSpan).filter(
            OtelSpan.organization_id == org.id, OtelSpan.trace_id == trace_id
        ).count() == 1
    finally:
        db.close()


# ── 2. Minimal protobuf trace ─────────────────────────────────────────────────

def test_protobuf_minimal_trace_creates_span_row():
    _ad._known_assets.clear()
    db = SessionLocal()
    org, _, token = _make_org_and_token(db)
    db.close()

    trace_id, span_id = _tid(), _sid()
    raw = _pb_request(
        [{"trace_id": trace_id, "span_id": span_id, "name": "handle_request",
          "status_code": 2, "status_message": "boom"}],
        {"service.name": "pb-minimal-agent", "deployment.environment": "staging"},
    )
    r = _post_pb(token, raw)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["accepted"] is True and body["spans"] == 1 and body["resource_spans"] == 1

    db = SessionLocal()
    try:
        row = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org.id, OtelSpan.trace_id == trace_id
        ).first()
        assert row is not None
        assert row.span_id == span_id            # lowercase hex preserved
        assert row.service_name == "pb-minimal-agent"
        assert row.status_code == "2"            # ERROR enum, same as JSON path
        assert row.status_message == "boom"
        assert row.duration_ms == 1000
    finally:
        db.close()


# ── 3. GenAI span → asset + intelligence ─────────────────────────────────────

def test_protobuf_genai_span_derives_asset_and_intelligence():
    _ad._known_assets.clear()
    db = SessionLocal()
    org, _, token = _make_org_and_token(db)
    db.close()

    raw = _pb_request(
        [{"trace_id": _tid(), "span_id": _sid(), "name": "chat gpt-4o", "attrs": {
            "gen_ai.provider.name": "openai",
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": "gpt-4o",
            "gen_ai.response.model": "gpt-4o-2024-11-20",
            "gen_ai.usage.input_tokens": 812,
            "gen_ai.usage.output_tokens": 214,
        }}],
        {"service.name": "pb-genai-agent"},
    )
    assert _post_pb(token, raw).status_code == 202

    token_hdr = {"Authorization": f"Bearer {token}"}
    r = _client.post("/intelligence/run", headers=token_hdr)
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        oa = db.query(OtelAsset).filter(
            OtelAsset.organization_id == org.id,
            OtelAsset.service_name == "pb-genai-agent",
        ).first()
        assert oa is not None
        assert "gpt-4o" in json.loads(oa.models_json)
        assert "Openai" in json.loads(oa.providers_json)
        caps = db.query(AssetCapability).filter(
            AssetCapability.organization_id == org.id,
            AssetCapability.capability_type == "model",
        ).all()
        assert any(c.capability_name == "gpt-4o" for c in caps)
    finally:
        db.close()


# ── 4. Privacy — identical scrub behavior ─────────────────────────────────────

def test_protobuf_sensitive_content_is_scrubbed():
    _ad._known_assets.clear()
    db = SessionLocal()
    org, _, token = _make_org_and_token(db)
    db.close()

    trace_id = _tid()
    raw = _pb_request(
        [{"trace_id": trace_id, "span_id": _sid(), "name": "chat", "attrs": {
            "gen_ai.request.model": "gpt-4o",
            "gen_ai.input.messages": "PBSECRET user prompt",
            "gen_ai.output.messages": "PBSECRET assistant reply",
            "gen_ai.system_instructions": "PBSECRET system",
            "gen_ai.tool.call.arguments": json.dumps({"q": "PBSECRET"}),
            "tool.arguments": json.dumps({"path": "PBSECRET"}),
            "tool.result": "PBSECRET result",
            "gen_ai.prompt.0.content": "PBSECRET legacy prompt content",
            "gen_ai.completion.0.content": "PBSECRET legacy completion",
            "traceloop.entity.input": "PBSECRET entity input",
            "prompt": "PBSECRET bare prompt",
            "gen_ai.prompt.name": "escalation-v2",   # safe metadata — must survive
        }}],
        {"service.name": "pb-privacy-agent"},
    )
    assert _post_pb(token, raw).status_code == 202

    db = SessionLocal()
    try:
        row = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org.id, OtelSpan.trace_id == trace_id
        ).first()
        assert "PBSECRET" not in (row.attributes_json or "")
        attrs = json.loads(row.attributes_json)
        for key in ("gen_ai.input.messages", "gen_ai.tool.call.arguments", "tool.result",
                    "gen_ai.prompt.0.content", "gen_ai.completion.0.content",
                    "traceloop.entity.input", "prompt"):
            assert attrs[key]["redacted"] is True, key
            assert attrs[key]["sha256"] and attrs[key]["size_bytes"] > 0, key
        assert attrs["gen_ai.tool.call.arguments"]["argument_keys"] == ["q"]
        assert attrs["gen_ai.prompt.name"] == "escalation-v2"
    finally:
        db.close()


# ── 5. Auth required ──────────────────────────────────────────────────────────

def test_protobuf_requires_auth():
    raw = _pb_request([{"trace_id": _tid(), "span_id": _sid()}], {"service.name": "x"})
    r = _post_pb(None, raw)
    assert r.status_code == 401


# ── 6–9. Error handling ───────────────────────────────────────────────────────

def test_malformed_protobuf_returns_400():
    db = SessionLocal()
    _, _, token = _make_org_and_token(db)
    db.close()
    r = _post_pb(token, b"\xff\xfe\x00\x01 definitely not protobuf \x99")
    assert r.status_code == 400
    assert "protobuf" in r.json()["detail"].lower()


def test_empty_protobuf_body_returns_400():
    db = SessionLocal()
    _, _, token = _make_org_and_token(db)
    db.close()
    r = _post_pb(token, b"")
    assert r.status_code == 400


def test_unsupported_content_type_returns_415():
    db = SessionLocal()
    _, _, token = _make_org_and_token(db)
    db.close()
    r = _client.post("/otel/v1/traces", content=b"<xml/>", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "text/xml",
    })
    assert r.status_code == 415
    assert "application/x-protobuf" in r.json()["detail"]


def test_json_content_type_with_protobuf_body_returns_400():
    db = SessionLocal()
    _, _, token = _make_org_and_token(db)
    db.close()
    raw = _pb_request([{"trace_id": _tid(), "span_id": _sid()}], {"service.name": "x"})
    r = _client.post("/otel/v1/traces", content=raw, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json",
    })
    assert r.status_code == 400


def test_protobuf_content_type_with_json_body_returns_400():
    db = SessionLocal()
    _, _, token = _make_org_and_token(db)
    db.close()
    json_body = json.dumps({"resourceSpans": []}).encode()
    r = _post_pb(token, json_body)
    assert r.status_code == 400


def test_metrics_shaped_protobuf_returns_400_with_clear_message():
    """A protobuf body that decodes but has no resource_spans (e.g. a metrics
    payload posted to the traces endpoint) gets a clear 400."""
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
    db = SessionLocal()
    _, _, token = _make_org_and_token(db)
    db.close()
    empty = ExportTraceServiceRequest().SerializeToString()  # decodes fine, zero resource_spans
    # ...but an empty serialization is zero bytes; pad with a valid but
    # meaningless unknown field so the body is non-empty and still decodes
    # to zero resource_spans (what a foreign payload typically looks like).
    r = _post_pb(token, empty or b"\x22\x00")
    assert r.status_code == 400
    assert "metrics" in r.json()["detail"].lower()


# ── 10. Org isolation ─────────────────────────────────────────────────────────

def test_protobuf_org_isolation():
    _ad._known_assets.clear()
    db = SessionLocal()
    org_a, _, token_a = _make_org_and_token(db, "isoA")
    org_b, _, token_b = _make_org_and_token(db, "isoB")
    db.close()

    trace_id = _tid()
    raw = _pb_request([{"trace_id": trace_id, "span_id": _sid()}],
                      {"service.name": "pb-iso-agent"})
    assert _post_pb(token_a, raw).status_code == 202

    db = SessionLocal()
    try:
        assert db.query(OtelSpan).filter(
            OtelSpan.organization_id == org_a.id, OtelSpan.trace_id == trace_id).count() == 1
        assert db.query(OtelSpan).filter(
            OtelSpan.organization_id == org_b.id).count() == 0
    finally:
        db.close()

    r = _client.get(f"/runtime/traces/{trace_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 404


# ── 11. Array attributes ──────────────────────────────────────────────────────

def test_protobuf_array_attributes_convert_safely():
    _ad._known_assets.clear()
    db = SessionLocal()
    org, _, token = _make_org_and_token(db)
    db.close()

    trace_id = _tid()
    raw = _pb_request(
        [{"trace_id": trace_id, "span_id": _sid(), "name": "chat", "attrs": {
            "gen_ai.request.model": "gpt-4o-mini",
            "gen_ai.response.finish_reasons": ["stop", "tool_calls"],
            "int.array": [1, 2, 3],
            "double.array": [1.5, 2.5],
            "bool.array": [True, False],
        }}],
        {"service.name": "pb-array-agent"},
    )
    assert _post_pb(token, raw).status_code == 202

    db = SessionLocal()
    try:
        row = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org.id, OtelSpan.trace_id == trace_id).first()
        attrs = json.loads(row.attributes_json)
        assert attrs["gen_ai.response.finish_reasons"] == ["stop", "tool_calls"]
        assert attrs["int.array"] == [1, 2, 3]
        assert attrs["double.array"] == [1.5, 2.5]
        assert attrs["bool.array"] == [True, False]
    finally:
        db.close()


# ── 12. gen_ai.system backward compatibility ──────────────────────────────────

def test_protobuf_gen_ai_system_backcompat():
    _ad._known_assets.clear()
    db = SessionLocal()
    org, _, token = _make_org_and_token(db)
    db.close()

    raw = _pb_request(
        [{"trace_id": _tid(), "span_id": _sid(), "name": "chat claude", "attrs": {
            "gen_ai.system": "anthropic",
            "gen_ai.request.model": "claude-sonnet-5",
        }}],
        {"service.name": "pb-legacy-agent"},
    )
    assert _post_pb(token, raw).status_code == 202

    db = SessionLocal()
    try:
        oa = db.query(OtelAsset).filter(
            OtelAsset.organization_id == org.id,
            OtelAsset.service_name == "pb-legacy-agent",
        ).first()
        assert oa is not None
        assert "Anthropic" in json.loads(oa.providers_json)
    finally:
        db.close()


# ── 13. Protobuf GenAI scalar columns parity ──────────────────────────────────

def test_pb_genai_scalar_columns_extracted():
    """Protobuf-encoded gen_ai.* attrs (int/bool/double/array values) populate
    the scalar columns identically to the JSON path."""
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "genaicol")
        trace_id = uuid.uuid4().hex
        span_id = uuid.uuid4().hex[:16]

        raw = _pb_request(
            [{
                "trace_id": trace_id,
                "span_id": span_id,
                "name": "chat gpt-4o",
                "attrs": {
                    "gen_ai.operation.name": "chat",
                    "gen_ai.provider.name": "openai",
                    "gen_ai.request.model": "gpt-4o",
                    "gen_ai.response.model": "gpt-4o-2024-08-06",
                    "gen_ai.usage.input_tokens": 900,
                    "gen_ai.usage.output_tokens": 210,
                    "gen_ai.response.finish_reasons": ["stop"],
                    "gen_ai.request.stream": True,
                    "gen_ai.response.time_to_first_chunk": 1.25,
                },
            }],
            resource_attrs={"service.name": "pb-genai-col-agent"},
        )
        resp = _post_pb(token, raw)
        assert resp.status_code == 202, resp.text

        row = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org.id,
            OtelSpan.trace_id == trace_id,
        ).first()
        assert row is not None
        assert row.gen_ai_operation_name == "chat"
        assert row.gen_ai_provider_name == "openai"
        assert row.gen_ai_request_model == "gpt-4o"
        assert row.gen_ai_response_model == "gpt-4o-2024-08-06"
        assert row.gen_ai_input_tokens == 900
        assert row.gen_ai_output_tokens == 210
        assert json.loads(row.gen_ai_finish_reasons_json) == ["stop"]
        assert row.gen_ai_request_stream is True
        assert row.gen_ai_time_to_first_chunk_ms == 1250

    finally:
        db.close()
