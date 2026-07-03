"""
Tests for the Runtime Execution Timeline read API.

Tests:
  1. Trace list returns ingested trace with span_count and duration
  2. Trace detail returns span hierarchy with offsets, sorted by start time
  3. step_type classification (llm / tool / step)
  4. Error spans counted and flagged
  5. service_name filter on the trace list
  6. Unknown trace returns 404
  7. Org isolation — org B cannot read org A's trace
"""
from __future__ import annotations

import os
import sys
import uuid

# ── Env setup BEFORE any app import ───────────────────────────────────────────
_db_path = f"/tmp/test_runtime_timeline_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-runtime-timeline")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Organization, User
from app.auth import hash_password, create_token
import app.asset_discovery as _ad

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")  # trigger startup + migrations

_BASE_NANO = 1_700_000_000_000_000_000


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_org_and_token(db, suffix=""):
    sfx = suffix or uuid.uuid4().hex[:6]
    org = Organization(name=f"rt-test-org-{sfx}", slug=f"rt-test-{sfx}")
    db.add(org)
    db.flush()
    user = User(
        email=f"rt-test-{sfx}@example.com",
        name=f"RT Test {sfx}",
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
    token = create_token(user)
    return org, user, token


def _otlp_span(
    trace_id: str,
    span_id: str,
    name: str,
    attrs: dict | None = None,
    parent_span_id: str | None = None,
    start_nano: int = _BASE_NANO,
    end_nano: int = _BASE_NANO + 1_000_000_000,
    status: dict | None = None,
) -> dict:
    span = {
        "traceId": trace_id,
        "spanId": span_id,
        "name": name,
        "kind": 3,
        "startTimeUnixNano": start_nano,
        "endTimeUnixNano": end_nano,
        "status": status or {},
        "attributes": [
            {
                "key": k,
                "value": (
                    {"intValue": v} if isinstance(v, int)
                    else {"doubleValue": v} if isinstance(v, float)
                    else {"stringValue": str(v)}
                ),
            }
            for k, v in (attrs or {}).items()
        ],
    }
    if parent_span_id:
        span["parentSpanId"] = parent_span_id
    return span


def _post_spans(token: str, spans: list[dict], service_name: str):
    payload = {
        "resourceSpans": [{
            "resource": {"attributes": [
                {"key": "service.name", "value": {"stringValue": service_name}},
            ]},
            "scopeSpans": [{"spans": spans}],
        }]
    }
    return _client.post(
        "/otel/v1/traces",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )


def _get(token: str, path: str):
    return _client.get(path, headers={"Authorization": f"Bearer {token}"})


def _ingest_agent_trace(token: str, service_name: str) -> str:
    """Ingest a 3-span trace: root agent step → LLM child → tool child."""
    trace_id = uuid.uuid4().hex
    root_id = uuid.uuid4().hex[:16]
    llm_id = uuid.uuid4().hex[:16]
    tool_id = uuid.uuid4().hex[:16]
    spans = [
        _otlp_span(trace_id, root_id, "agent.request",
                   start_nano=_BASE_NANO, end_nano=_BASE_NANO + 4_000_000_000),
        _otlp_span(trace_id, llm_id, "llm.chat", parent_span_id=root_id,
                   attrs={"gen_ai.system": "openai", "gen_ai.request.model": "gpt-4o"},
                   start_nano=_BASE_NANO + 200_000_000, end_nano=_BASE_NANO + 1_400_000_000),
        _otlp_span(trace_id, tool_id, "tool.search", parent_span_id=root_id,
                   attrs={"tool.name": "vector_search"},
                   start_nano=_BASE_NANO + 1_500_000_000, end_nano=_BASE_NANO + 3_800_000_000),
    ]
    resp = _post_spans(token, spans, service_name)
    assert resp.status_code == 202, resp.text
    return trace_id


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_trace_list_returns_ingested_trace():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "list")
        trace_id = _ingest_agent_trace(token, "list-agent")

        resp = _get(token, "/runtime/traces")
        assert resp.status_code == 200
        traces = resp.json()
        match = [t for t in traces if t["trace_id"] == trace_id]
        assert len(match) == 1
        t = match[0]
        assert t["span_count"] == 3
        assert t["root_span_name"] == "agent.request"
        assert t["service_name"] == "list-agent"
        assert t["duration_ms"] == 4000
        assert t["error_count"] == 0
    finally:
        db.close()


def test_trace_detail_hierarchy_and_offsets():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "detail")
        trace_id = _ingest_agent_trace(token, "detail-agent")

        resp = _get(token, f"/runtime/traces/{trace_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["trace_id"] == trace_id
        assert body["span_count"] == 3
        assert body["duration_ms"] == 4000

        spans = body["spans"]
        # Sorted by start time: root, llm, tool
        assert [s["name"] for s in spans] == ["agent.request", "llm.chat", "tool.search"]
        root, llm, tool = spans
        assert root["parent_span_id"] is None
        assert llm["parent_span_id"] == root["span_id"]
        assert tool["parent_span_id"] == root["span_id"]
        assert root["offset_ms"] == 0
        assert llm["offset_ms"] == 200
        assert tool["offset_ms"] == 1500
        assert llm["duration_ms"] == 1200
        assert tool["duration_ms"] == 2300
    finally:
        db.close()


def test_step_type_classification():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "steps")
        trace_id = _ingest_agent_trace(token, "steps-agent")

        resp = _get(token, f"/runtime/traces/{trace_id}")
        assert resp.status_code == 200
        by_name = {s["name"]: s["step_type"] for s in resp.json()["spans"]}
        assert by_name["llm.chat"] == "llm"
        assert by_name["tool.search"] == "tool"
        assert by_name["agent.request"] == "step"
    finally:
        db.close()


def test_error_spans_counted_and_flagged():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "err")
        trace_id = uuid.uuid4().hex
        span = _otlp_span(
            trace_id, uuid.uuid4().hex[:16], "failing.step",
            status={"code": 2, "message": "boom"},
        )
        resp = _post_spans(token, [span], "err-agent")
        assert resp.status_code == 202

        resp = _get(token, f"/runtime/traces/{trace_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["error_count"] == 1
        assert body["spans"][0]["error"] is True

        resp = _get(token, "/runtime/traces")
        t = [t for t in resp.json() if t["trace_id"] == trace_id][0]
        assert t["error_count"] == 1
    finally:
        db.close()


def test_service_name_filter():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "filter")
        trace_a = _ingest_agent_trace(token, "filter-agent-a")
        trace_b = _ingest_agent_trace(token, "filter-agent-b")

        resp = _get(token, "/runtime/traces?service_name=filter-agent-a")
        assert resp.status_code == 200
        ids = {t["trace_id"] for t in resp.json()}
        assert trace_a in ids
        assert trace_b not in ids
    finally:
        db.close()


def test_unknown_trace_404():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "missing")
        resp = _get(token, f"/runtime/traces/{uuid.uuid4().hex}")
        assert resp.status_code == 404
    finally:
        db.close()


def test_unauthenticated_requests_rejected():
    for path in ("/runtime/traces", f"/runtime/traces/{uuid.uuid4().hex}"):
        resp = _client.get(path)
        assert resp.status_code == 401, f"{path} → {resp.status_code}"


def test_limit_bounds_enforced():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "limits")
        assert _get(token, "/runtime/traces?limit=0").status_code == 422
        assert _get(token, "/runtime/traces?limit=201").status_code == 422
        assert _get(token, "/runtime/traces?limit=200").status_code == 200
    finally:
        db.close()


def test_missing_timestamps_do_not_crash():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "nots")
        trace_id = uuid.uuid4().hex
        span = _otlp_span(trace_id, uuid.uuid4().hex[:16], "no.timestamps")
        del span["startTimeUnixNano"]
        del span["endTimeUnixNano"]
        resp = _post_spans(token, [span], "nots-agent")
        assert resp.status_code == 202

        resp = _get(token, "/runtime/traces")
        assert resp.status_code == 200
        t = [t for t in resp.json() if t["trace_id"] == trace_id][0]
        assert t["duration_ms"] is None
        assert t["start_time"] is None

        resp = _get(token, f"/runtime/traces/{trace_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["duration_ms"] is None
        assert body["spans"][0]["offset_ms"] is None
        assert body["spans"][0]["duration_ms"] is None
    finally:
        db.close()


def test_trace_detail_never_exposes_attributes():
    """Privacy surface: span attributes (even scrubbed) stay out of the timeline API."""
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "privacy")
        trace_id = uuid.uuid4().hex
        span = _otlp_span(
            trace_id, uuid.uuid4().hex[:16], "llm.call",
            attrs={"gen_ai.system": "openai", "gen_ai.input.messages": '[{"role":"user","content":"secret"}]'},
        )
        resp = _post_spans(token, [span], "privacy-agent")
        assert resp.status_code == 202

        resp = _get(token, f"/runtime/traces/{trace_id}")
        assert resp.status_code == 200
        for s in resp.json()["spans"]:
            assert "attributes" not in s
            assert "attributes_json" not in s
            assert "resource_attributes_json" not in s
        assert "secret" not in resp.text
    finally:
        db.close()


def test_org_isolation():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org_a, _, token_a = _make_org_and_token(db, "isoa")
        org_b, _, token_b = _make_org_and_token(db, "isob")
        trace_id = _ingest_agent_trace(token_a, "iso-agent")

        # Org B cannot read the trace detail
        resp = _get(token_b, f"/runtime/traces/{trace_id}")
        assert resp.status_code == 404

        # Org B's trace list does not include it
        resp = _get(token_b, "/runtime/traces")
        assert trace_id not in {t["trace_id"] for t in resp.json()}
    finally:
        db.close()
