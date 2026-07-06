"""
Tests for AI Agent Runtime Security Intelligence (app/runtime_security_intelligence.py).

Derivation-only, observe-only, agent-specific. Every finding carries
category="security", source="runtime_security". Verifies each MVP finding
type, dedup/occurrence, and the privacy boundary (no raw content, no full
URLs with query strings).
"""
from __future__ import annotations

import json
import os
import sys
import uuid

_db_path = f"/tmp/test_runtime_security_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-runtime-security")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Organization, User, AssetFinding
from app.auth import hash_password, create_token
import app.asset_discovery as _ad

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")


def _org(db, suffix=""):
    sfx = suffix or uuid.uuid4().hex[:6]
    org = Organization(name=f"rsi-org-{sfx}", slug=f"rsi-{sfx}")
    db.add(org)
    db.flush()
    user = User(email=f"rsi-{sfx}@example.com", name=f"RSI {sfx}",
                hashed_password=hash_password("pass"), organization_id=org.id,
                role="admin", team="eng", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(org)
    db.refresh(user)
    return org, create_token(user)


def _span(trace_id, span_id, name, attrs=None, resource_attrs=None, status=None,
          start=1_700_000_000_000_000_000, end=1_700_000_001_000_000_000):
    sattrs = [{"key": k, "value": ({"intValue": v} if isinstance(v, int)
               else {"doubleValue": v} if isinstance(v, float)
               else {"stringValue": str(v)})} for k, v in (attrs or {}).items()]
    rattrs = [{"key": k, "value": {"stringValue": str(v)}} for k, v in (resource_attrs or {}).items()]
    return {"resourceSpans": [{
        "resource": {"attributes": rattrs},
        "scopeSpans": [{"spans": [{
            "traceId": trace_id, "spanId": span_id, "name": name, "kind": 3,
            "startTimeUnixNano": start, "endTimeUnixNano": end,
            "status": status or {}, "attributes": sattrs,
        }]}],
    }]}


def _post(token, payload):
    return _client.post("/otel/v1/traces", json=payload,
                        headers={"Authorization": f"Bearer {token}"})


def _run(token):
    return _client.post("/intelligence/run", headers={"Authorization": f"Bearer {token}"})


def _rs_findings(db, org_id, finding_type=None):
    q = db.query(AssetFinding).filter(
        AssetFinding.organization_id == org_id,
        AssetFinding.source == "runtime_security",
    )
    if finding_type:
        q = q.filter(AssetFinding.finding_type == finding_type)
    return q.all()


def test_database_access_creates_finding():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "db")
        assert _post(token, _span(uuid.uuid4().hex, uuid.uuid4().hex[:16], "query",
            attrs={"db.system": "postgresql", "db.name": "billing"},
            resource_attrs={"service.name": "db-agent", "deployment.environment": "production"})).status_code == 202
        assert _run(token).status_code == 200
        rows = _rs_findings(db, org.id, "agent_has_database_access")
        assert len(rows) == 1
        assert rows[0].severity == "high"  # production
        ev = json.loads(rows[0].evidence_json)
        assert "postgresql" in ev["db_systems"] and "billing" in ev["db_names"]
        assert ev["environment"] == "production"
    finally:
        db.close()


def test_external_api_strips_query_string():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "api")
        secret_url = "https://api.vendor.com/v1/lookup?token=SECRET123&user=alice"
        assert _post(token, _span(uuid.uuid4().hex, uuid.uuid4().hex[:16], "http",
            attrs={"url.full": secret_url},
            resource_attrs={"service.name": "api-agent"})).status_code == 202
        assert _run(token).status_code == 200
        rows = _rs_findings(db, org.id, "agent_uses_unmanaged_external_api")
        assert len(rows) == 1
        ev = json.loads(rows[0].evidence_json)
        assert ev["domains"] == ["api.vendor.com"]
        blob = json.dumps(ev)
        assert "SECRET123" not in blob and "token=" not in blob and "alice" not in blob
        assert ev["sample_paths"] == ["https://api.vendor.com/v1/lookup"]
    finally:
        db.close()


def test_mcp_in_production_creates_finding():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "mcp")
        assert _post(token, _span(uuid.uuid4().hex, uuid.uuid4().hex[:16], "mcp",
            attrs={"mcp.method.name": "tools/call", "gen_ai.tool.name": "jira_search",
                   "mcp.resource.uri": "https://mcp.internal.corp/tools"},
            resource_attrs={"service.name": "mcp-agent", "deployment.environment": "production"})).status_code == 202
        assert _run(token).status_code == 200
        rows = _rs_findings(db, org.id, "agent_uses_mcp_tool_in_production")
        assert len(rows) == 1 and rows[0].severity == "high"
        ev = json.loads(rows[0].evidence_json)
        assert "tools/call" in ev["mcp_methods"]
        assert "mcp.internal.corp" in ev["resource_hosts"]
    finally:
        db.close()


def test_mcp_non_production_no_finding():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "mcpdev")
        assert _post(token, _span(uuid.uuid4().hex, uuid.uuid4().hex[:16], "mcp",
            attrs={"mcp.method.name": "tools/call", "gen_ai.tool.name": "jira_search"},
            resource_attrs={"service.name": "mcp-dev-agent", "deployment.environment": "development"})).status_code == 202
        assert _run(token).status_code == 200
        assert len(_rs_findings(db, org.id, "agent_uses_mcp_tool_in_production")) == 0
    finally:
        db.close()


def test_broad_tool_surface_creates_finding():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "broad")
        tid = uuid.uuid4().hex
        for tool in ["search", "write_file", "send_email", "run_query", "fetch_url"]:
            assert _post(token, _span(tid, uuid.uuid4().hex[:16], f"tool {tool}",
                attrs={"gen_ai.tool.name": tool},
                resource_attrs={"service.name": "broad-agent"})).status_code == 202
        assert _run(token).status_code == 200
        rows = _rs_findings(db, org.id, "agent_has_broad_tool_surface")
        assert len(rows) == 1
        ev = json.loads(rows[0].evidence_json)
        assert ev["tool_count"] >= 5
    finally:
        db.close()


def test_unknown_provider_creates_finding():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "prov")
        assert _post(token, _span(uuid.uuid4().hex, uuid.uuid4().hex[:16], "chat",
            attrs={"gen_ai.provider.name": "mystery-llm-co", "gen_ai.request.model": "mystery-7b"},
            resource_attrs={"service.name": "unknown-prov-agent"})).status_code == 202
        assert _run(token).status_code == 200
        rows = _rs_findings(db, org.id, "agent_uses_unknown_model_provider")
        assert len(rows) == 1
        ev = json.loads(rows[0].evidence_json)
        # provider is capitalized by the normalizer; match case-insensitively
        assert any("mystery-llm-co" == p.lower() for p in ev["providers"])
    finally:
        db.close()


def test_missing_owner_creates_finding():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "owner")
        # A discovered agent with no owner/team on its registry row.
        assert _post(token, _span(uuid.uuid4().hex, uuid.uuid4().hex[:16], "chat",
            attrs={"gen_ai.provider.name": "openai", "gen_ai.request.model": "gpt-4o"},
            resource_attrs={"service.name": "orphan-agent"})).status_code == 202
        assert _run(token).status_code == 200
        rows = _rs_findings(db, org.id, "agent_missing_owner")
        assert len(rows) == 1
        ev = json.loads(rows[0].evidence_json)
        assert "owner" in ev["missing_fields"]
    finally:
        db.close()


def test_repeated_tool_errors_creates_finding():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "err")
        tid = uuid.uuid4().hex
        for _ in range(3):
            assert _post(token, _span(tid, uuid.uuid4().hex[:16], "tool call",
                attrs={"gen_ai.tool.name": "flaky_api", "error.type": "TimeoutError"},
                resource_attrs={"service.name": "err-agent", "deployment.environment": "production"},
                status={"code": 2})).status_code == 202
        assert _run(token).status_code == 200
        rows = _rs_findings(db, org.id, "repeated_tool_errors")
        assert len(rows) == 1 and rows[0].severity == "high"
        ev = json.loads(rows[0].evidence_json)
        assert ev["error_count"] == 3 and "flaky_api" in ev["tool_names"]
    finally:
        db.close()


def test_human_review_recommended_on_combo():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "review")
        tid = uuid.uuid4().hex
        # production + MCP → at least one review reason
        assert _post(token, _span(tid, uuid.uuid4().hex[:16], "mcp",
            attrs={"mcp.method.name": "tools/call", "gen_ai.tool.name": "deploy_tool"},
            resource_attrs={"service.name": "combo-agent", "deployment.environment": "production"})).status_code == 202
        assert _run(token).status_code == 200
        rows = _rs_findings(db, org.id, "human_review_recommended")
        assert len(rows) == 1
        ev = json.loads(rows[0].evidence_json)
        assert len(ev["reasons"]) >= 1
        assert "agent_uses_mcp_tool_in_production" in ev["related_finding_types"]
    finally:
        db.close()


def test_multiple_spans_dedupe_with_occurrence():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "dedupe")
        tid = uuid.uuid4().hex
        for _ in range(6):
            assert _post(token, _span(tid, uuid.uuid4().hex[:16], "query",
                attrs={"db.system": "postgresql", "db.name": "orders"},
                resource_attrs={"service.name": "dedupe-agent"})).status_code == 202
        assert _run(token).status_code == 200
        rows = _rs_findings(db, org.id, "agent_has_database_access")
        assert len(rows) == 1
        assert rows[0].occurrence_count == 6
        ev = json.loads(rows[0].evidence_json)
        assert ev["span_count"] == 6 and len(ev["sample_span_ids"]) == 5
        # idempotent
        assert _run(token).status_code == 200
        db.expire_all()
        rows = _rs_findings(db, org.id, "agent_has_database_access")
        assert len(rows) == 1 and rows[0].occurrence_count == 6
    finally:
        db.close()


def test_evidence_never_contains_raw_content():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "privacy")
        # Ingest spans carrying content-bearing + full-URL attributes.
        tid = uuid.uuid4().hex
        assert _post(token, _span(tid, uuid.uuid4().hex[:16], "tool",
            attrs={"gen_ai.tool.name": "risky", "tool.arguments": '{"password":"hunter2"}',
                   "url.full": "https://api.secret.com/v1?apikey=TOPSECRET",
                   "db.system": "mysql"},
            resource_attrs={"service.name": "privacy-agent", "deployment.environment": "production"})).status_code == 202
        assert _run(token).status_code == 200
        rows = _rs_findings(db, org.id)
        assert len(rows) > 0
        blob = " ".join(r.evidence_json or "" for r in rows) + " ".join((r.summary or "") for r in rows)
        for forbidden in ["hunter2", "TOPSECRET", "apikey=", "password", "tool.arguments"]:
            assert forbidden not in blob, f"leaked: {forbidden}"
    finally:
        db.close()
