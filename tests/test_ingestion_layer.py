"""
Tests for the app/ingestion layer — one parse(payload) -> list[RuntimeSpan]
function per integration (OTel, SDK).

Covers golden equivalence (the ingestion functions return exactly what the
underlying parsers return, so routing through the layer changes nothing) and
an end-to-end check that both endpoints still ingest through it.
"""
from __future__ import annotations

import os
import sys
import uuid

# ── Env setup BEFORE any app import ───────────────────────────────────────────
_db_path = f"/tmp/test_ingestion_layer_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-ingestion-layer")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

from fastapi.testclient import TestClient
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue

from app.main import app
from app.database import SessionLocal
from app.models import Organization, User, OtelSpan
from app.auth import hash_password, create_token
from app.ingestion import otel as otel_ingestion
from app.ingestion import sdk as sdk_ingestion
from app.otel_parser import parse_otlp_json, parse_otlp_protobuf
from app.runtime_events import RuntimeEvent, to_span_dict

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")


def _org(db, suffix=""):
    sfx = suffix or uuid.uuid4().hex[:6]
    org = Organization(name=f"ing-org-{sfx}", slug=f"ing-{sfx}")
    db.add(org)
    db.flush()
    user = User(email=f"ing-{sfx}@example.com", name=f"ING {sfx}",
                hashed_password=hash_password("pass"), organization_id=org.id,
                role="admin", team="eng", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(org)
    db.refresh(user)
    return org, create_token(user)


def _otlp_json_body(trace_id=None, span_id=None):
    return {
        "resourceSpans": [{
            "resource": {"attributes": [
                {"key": "service.name", "value": {"stringValue": "ingestion-test-agent"}},
                {"key": "deployment.environment", "value": {"stringValue": "production"}},
            ]},
            "scopeSpans": [{"spans": [{
                "traceId": trace_id or uuid.uuid4().hex,
                "spanId": span_id or uuid.uuid4().hex[:16],
                "name": "chat gpt-4o",
                "kind": 3,
                "startTimeUnixNano": "1720000000000000000",
                "endTimeUnixNano": "1720000001000000000",
                "status": {"code": "STATUS_CODE_OK"},
                "attributes": [
                    {"key": "gen_ai.provider.name", "value": {"stringValue": "openai"}},
                    {"key": "gen_ai.request.model", "value": {"stringValue": "gpt-4o"}},
                ],
            }]}],
        }],
    }


def _otlp_protobuf_body() -> bytes:
    req = ExportTraceServiceRequest()
    rs = req.resource_spans.add()
    rs.resource.attributes.append(
        KeyValue(key="service.name", value=AnyValue(string_value="ingestion-pb-agent")))
    span = rs.scope_spans.add().spans.add()
    span.trace_id = uuid.uuid4().bytes
    span.span_id = uuid.uuid4().bytes[:8]
    span.name = "chat gpt-4o"
    span.kind = 3
    span.start_time_unix_nano = 1720000000000000000
    span.end_time_unix_nano = 1720000001000000000
    span.attributes.append(
        KeyValue(key="gen_ai.request.model", value=AnyValue(string_value="gpt-4o")))
    return req.SerializeToString()


# ── Golden equivalence: ingestion layer == underlying parsers ─────────────────

def test_otel_parse_json_equals_legacy_parser():
    body = _otlp_json_body()
    assert otel_ingestion.parse(body) == parse_otlp_json(body)
    spans, count = otel_ingestion.parse_otlp(body)
    assert spans == parse_otlp_json(body)
    assert count == len(body["resourceSpans"])


def test_otel_parse_protobuf_equals_legacy_parser():
    raw = _otlp_protobuf_body()
    legacy_spans, legacy_count = parse_otlp_protobuf(raw)
    assert otel_ingestion.parse(raw) == legacy_spans
    assert otel_ingestion.parse_otlp(raw) == (legacy_spans, legacy_count)
    assert legacy_count == 1 and len(legacy_spans) == 1


def test_sdk_parse_equals_legacy_adapter():
    event = RuntimeEvent.model_validate({
        "source": "sdk",
        "agent_name": "web-research-agent",
        "trace_id": uuid.uuid4().hex,
        "span_id": uuid.uuid4().hex[:16],
        "event_type": "llm_call",
        "provider": "openai",
        "model": "gpt-4o",
        "environment": "production",
        "timestamp": "2026-07-10T14:22:07Z",
        "duration_ms": 1200,
    })
    assert sdk_ingestion.parse([event]) == [to_span_dict(event)]
    assert sdk_ingestion.parse([]) == []


def test_empty_otlp_envelope_yields_no_spans_but_counts_envelope():
    body = {"resourceSpans": [{"resource": {"attributes": []}, "scopeSpans": []}]}
    spans, count = otel_ingestion.parse_otlp(body)
    assert spans == [] and count == 1


# ── End-to-end: both endpoints still ingest through the layer ─────────────────

def test_otlp_json_post_ingests_span():
    db = SessionLocal()
    try:
        org, token = _org(db, "json")
        trace_id, span_id = uuid.uuid4().hex, uuid.uuid4().hex[:16]
        r = _client.post("/otel/v1/traces",
                         json=_otlp_json_body(trace_id, span_id),
                         headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["accepted"] is True and body["resource_spans"] == 1 and body["spans"] == 1
        assert body["content_redacted"] is True
        row = (db.query(OtelSpan)
                 .filter(OtelSpan.organization_id == org.id,
                         OtelSpan.trace_id == trace_id,
                         OtelSpan.span_id == span_id).one())
        assert row.gen_ai_request_model == "gpt-4o"
    finally:
        db.close()


def test_otlp_protobuf_post_ingests_span():
    db = SessionLocal()
    try:
        org, token = _org(db, "pb")
        r = _client.post("/otel/v1/traces",
                         content=_otlp_protobuf_body(),
                         headers={"Authorization": f"Bearer {token}",
                                  "Content-Type": "application/x-protobuf"})
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["resource_spans"] == 1 and body["spans"] == 1
        assert db.query(OtelSpan).filter(OtelSpan.organization_id == org.id).count() == 1
    finally:
        db.close()


def test_runtime_events_post_ingests_span():
    db = SessionLocal()
    try:
        org, token = _org(db, "sdk")
        r = _client.post("/runtime-events",
                         json={"events": [{
                             "source": "sdk",
                             "agent_name": "web-research-agent",
                             "trace_id": uuid.uuid4().hex,
                             "span_id": uuid.uuid4().hex[:16],
                             "event_type": "llm_call",
                             "provider": "openai",
                             "model": "gpt-4o",
                         }]},
                         headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 202, r.text
        assert r.json()["events"] == 1 and r.json()["spans"] == 1
        assert db.query(OtelSpan).filter(OtelSpan.organization_id == org.id).count() == 1
    finally:
        db.close()
