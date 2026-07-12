"""
Tests for POST /runtime-events — normalized GenAI runtime event ingestion (R1/R2).

Covers schema validation, the privacy/forbidden-field boundary, the runtime-event →
span-like adapter, and an integration check that a tool_call/mcp event lands an asset and
lets the existing intelligence flow derive findings — proving reuse of the shared engine
with no separate pipeline.
"""
from __future__ import annotations

import json
import os
import sys
import uuid

_db_path = f"/tmp/test_runtime_events_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-runtime-events")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Organization, User, OtelAsset, OtelSpan, AssetFinding
from app.auth import hash_password, create_token
from app.runtime_events import RuntimeEvent, to_span_dict, host_only, scrub_metadata

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")


def _org(db, suffix=""):
    sfx = suffix or uuid.uuid4().hex[:6]
    org = Organization(name=f"rte-org-{sfx}", slug=f"rte-{sfx}")
    db.add(org)
    db.flush()
    user = User(email=f"rte-{sfx}@example.com", name=f"RTE {sfx}",
                hashed_password=hash_password("pass"), organization_id=org.id,
                role="admin", team="eng", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(org)
    db.refresh(user)
    return org, create_token(user)


def _event(**over):
    e = {
        "source": "sdk",
        "agent_name": "web-research-agent",
        "trace_id": uuid.uuid4().hex,
        "span_id": uuid.uuid4().hex[:16],
        "event_type": "llm_call",
        "provider": "openai",
        "model": "gpt-4o",
        "environment": "production",
        "timestamp": "2026-07-10T14:22:07Z",
    }
    e.update(over)
    return e


def _post(token, payload):
    return _client.post("/runtime-events", json=payload, headers={"Authorization": f"Bearer {token}"})


# ── Schema validation ─────────────────────────────────────────────────────────

def test_valid_event_is_accepted():
    db = SessionLocal()
    try:
        _org_, token = _org(db, "ok")
        r = _post(token, {"events": [_event()]})
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["accepted"] is True and body["events"] == 1 and body["spans"] == 1
        assert body["content_redacted"] is True
    finally:
        db.close()


def test_missing_required_ids_rejected():
    db = SessionLocal()
    try:
        _org_, token = _org(db, "req")
        bad = _event()
        del bad["trace_id"]
        assert _post(token, {"events": [bad]}).status_code == 422
        bad2 = _event()
        del bad2["span_id"]
        assert _post(token, {"events": [bad2]}).status_code == 422
    finally:
        db.close()


def test_single_event_and_bare_list_shapes():
    db = SessionLocal()
    try:
        _org_, token = _org(db, "shapes")
        assert _post(token, _event()).status_code == 202              # single object
        assert _post(token, [_event(), _event()]).status_code == 202  # bare list
    finally:
        db.close()


def test_auth_required():
    r = _client.post("/runtime-events", json={"events": [_event()]})
    assert r.status_code == 401


# ── Privacy / forbidden fields ────────────────────────────────────────────────

def test_forbidden_top_level_fields_rejected():
    db = SessionLocal()
    try:
        _org_, token = _org(db, "priv1")
        for bad_key, bad_val in [
            ("prompt", "SECRET-PROMPT"),
            ("response", "SECRET-RESPONSE"),
            ("tool_arguments", "SECRET-ARGS"),
            ("tool_result", "SECRET-RESULT"),
            ("authorization", "Bearer sk-SECRET"),
            ("headers", {"x": "y"}),
        ]:
            r = _post(token, {"events": [_event(**{bad_key: bad_val})]})
            assert r.status_code == 422, f"{bad_key} should be rejected"
    finally:
        db.close()


def test_metadata_and_domain_are_scrubbed_not_persisted():
    db = SessionLocal()
    try:
        org, token = _org(db, "priv2")
        secret_url = "https://api.vendor.com/v1/lookup?token=SUPERSECRET&u=alice"
        ev = _event(
            event_type="external_api_call",
            external_domain=secret_url,
            metadata_json={"prompt": "SECRET-META-PROMPT", "authorization": "SECRET-KEY",
                           "region": "us-east-1", "retries": 2},
        )
        assert _post(token, {"events": [ev]}).status_code == 202
        rows = db.query(OtelSpan).filter(OtelSpan.organization_id == org.id).all()
        blob = json.dumps([r.attributes_json for r in rows] +
                          [r.resource_attributes_json for r in rows if hasattr(r, "resource_attributes_json")])
        for secret in ("SUPERSECRET", "token=", "SECRET-META-PROMPT", "SECRET-KEY", "alice"):
            assert secret not in blob, f"leaked: {secret}"
        # host survived, safe metadata survived
        assert "api.vendor.com" in blob
        assert "us-east-1" in blob and "region" in blob
    finally:
        db.close()


# ── Runtime event → span-like dict (unit) ─────────────────────────────────────

def test_to_span_dict_maps_semconv_keys():
    ev = RuntimeEvent.model_validate(_event(
        event_type="mcp_tool", tool_name="search_web", mcp_server="tools.example",
        db_system="postgresql", db_name="billing", input_tokens=1200, output_tokens=300,
        error_type="TimeoutError", status="error", duration_ms=1500,
        external_domain="https://api.x.com/y?z=1", session_id="sess-1",
    ))
    span = to_span_dict(ev)
    a = span["attributes"]
    assert span["trace_id"] == ev.trace_id and span["span_id"] == ev.span_id
    assert a["gen_ai.agent.name"] == "web-research-agent"
    assert a["gen_ai.tool.name"] == "search_web"
    assert a["mcp.server"] == "tools.example" and a["mcp.method.name"] == "tools/call"
    assert a["db.system"] == "postgresql" and a["db.name"] == "billing"
    assert a["gen_ai.usage.input_tokens"] == 1200 and a["gen_ai.usage.output_tokens"] == 300
    assert a["error.type"] == "TimeoutError" and span["status_code"] == 2
    assert a["server.address"] == "api.x.com"  # host only, no path/query
    assert span["resource_attributes"]["service.name"] == "web-research-agent"
    assert span["resource_attributes"]["deployment.environment"] == "production"
    # no content-bearing keys leaked into attributes
    assert not any(k in a for k in ("prompt", "response", "gen_ai.input.messages", "authorization"))


def test_host_only_and_scrub_helpers():
    assert host_only("https://api.vendor.com/v1?token=x") == "api.vendor.com"
    assert host_only("api.vendor.com/path?q=1") == "api.vendor.com"
    assert host_only(None) is None
    scrubbed = scrub_metadata({"prompt": "x", "api_key": "y", "region": "us", "n": 3,
                               "link": "https://a.com/b?c=d"})
    assert scrubbed == {"region": "us", "n": 3}


# ── Integration: evidence produces an asset; engine derives findings later ─────

def test_tool_call_event_creates_asset_and_engine_derives_findings():
    db = SessionLocal()
    try:
        org, token = _org(db, "integ")
        trace = uuid.uuid4().hex
        # An MCP burst in production — the same evidence the OTLP path would carry.
        for i in range(6):
            ev = _event(trace_id=trace, span_id=uuid.uuid4().hex[:16], event_type="mcp_tool",
                        tool_name="search_web", mcp_server="tools.example")
            assert _post(token, {"events": [ev]}).status_code == 202

        # Asset evidence exists from ingestion alone.
        assets = db.query(OtelAsset).filter(OtelAsset.organization_id == org.id).all()
        assert len(assets) >= 1
        spans = db.query(OtelSpan).filter(OtelSpan.organization_id == org.id).count()
        assert spans == 6

        # The EXISTING intelligence flow (not the ingestion endpoint) derives findings.
        assert _client.post("/intelligence/run", headers={"Authorization": f"Bearer {token}"}).status_code == 200
        db.expire_all()
        findings = db.query(AssetFinding).filter(AssetFinding.organization_id == org.id).all()
        assert findings, "expected the shared engine to derive findings from ingested evidence"
        # detection rules ran in the intelligence pass, not inside /runtime-events
        assert any(f.source == "detection_rules" for f in findings) or any(
            f.finding_type in ("mcp_enabled", "agent_uses_mcp_tool_in_production") for f in findings)
    finally:
        db.close()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
    print("all runtime-events tests passed")
