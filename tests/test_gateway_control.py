"""Gateway Control Center (GCR2) — candidate derivation tests.

Covers: candidate threshold (high-severity OR human_review_recommended at any
severity; medium-only never qualifies), evidence shape + privacy, suggested
controls mapping, idempotency, dismissal independence + reopen-on-new-type
semantics, org isolation, and admin-only action gating.
"""
from __future__ import annotations

import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_DB = f"/tmp/gcc-test-{uuid.uuid4().hex[:8]}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["JWT_SECRET"] = "gcc-test-secret"
os.environ["CREDENTIAL_ENCRYPTION_KEY"] = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

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
    org = Organization(name=f"gcc-org-{sfx}", slug=f"gcc-{sfx}")
    db.add(org)
    db.flush()
    users = {}
    for role in ("admin", "analyst"):
        u = User(email=f"gcc-{sfx}-{role}@example.com", name=f"GCC {role}",
                 hashed_password=hash_password("pass"), organization_id=org.id,
                 role=role, team="eng", is_active=True)
        db.add(u)
        users[role] = u
    db.commit()
    db.refresh(org)
    return org, {r: create_token(db.merge(u)) for r, u in users.items()}


def _span(trace_id, span_id, name, attrs=None, resource_attrs=None,
          start=1_700_000_000_000_000_000, end=1_700_000_001_000_000_000):
    sattrs = [{"key": k, "value": ({"intValue": v} if isinstance(v, int)
               else {"stringValue": str(v)})} for k, v in (attrs or {}).items()]
    rattrs = [{"key": k, "value": {"stringValue": str(v)}} for k, v in (resource_attrs or {}).items()]
    return {"resourceSpans": [{
        "resource": {"attributes": rattrs},
        "scopeSpans": [{"spans": [{
            "traceId": trace_id, "spanId": span_id, "name": name, "kind": 3,
            "startTimeUnixNano": start, "endTimeUnixNano": end,
            "status": {}, "attributes": sattrs,
        }]}],
    }]}


def _post(token, payload):
    return _client.post("/otel/v1/traces", json=payload,
                        headers={"Authorization": f"Bearer {token}"})


def _run(token):
    return _client.post("/intelligence/run", headers={"Authorization": f"Bearer {token}"})


def _candidates(db, org_id):
    return (
        db.query(AssetFinding)
        .filter(AssetFinding.organization_id == org_id,
                AssetFinding.category == "control",
                AssetFinding.finding_type == "gateway_control_recommended")
        .all()
    )


def _seed_risky_agent(token, service="risky-agent"):
    """Production agent with MCP + database access → high runtime-security findings."""
    assert _post(token, _span(uuid.uuid4().hex, uuid.uuid4().hex[:16], "mcp",
        attrs={"mcp.method.name": "tools/call", "gen_ai.tool.name": "jira_search"},
        resource_attrs={"service.name": service, "deployment.environment": "production"})).status_code == 202
    assert _post(token, _span(uuid.uuid4().hex, uuid.uuid4().hex[:16], "query",
        attrs={"db.system": "postgresql", "db.name": "orders"},
        resource_attrs={"service.name": service, "deployment.environment": "production"})).status_code == 202


def test_high_risk_agent_becomes_candidate():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, toks = _org(db, "cand")
        _seed_risky_agent(toks["admin"])
        assert _run(toks["admin"]).status_code == 200
        rows = _candidates(db, org.id)
        assert len(rows) == 1
        row = rows[0]
        assert row.source == "observe_to_control"
        assert row.severity == "high"
        assert row.status == "open"
        ev = json.loads(row.evidence_json)
        assert ev["trigger_count"] >= 2
        assert "agent_uses_mcp_tool_in_production" in ev["trigger_finding_types"]
        assert ev["environment"] == "production"
        controls = {c["control"]: c["kind"] for c in ev["recommended_controls"]}
        assert controls.get("mcp/tool usage policy") == "hard"
        assert controls.get("route through gateway") == "routing"
        # provenance points at real finding rows in the same org
        assert all(isinstance(i, int) for i in ev["trigger_finding_ids"])
    finally:
        db.close()


def test_medium_only_agent_is_not_candidate():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, toks = _org(db, "med")
        # Non-production db access → medium findings only, no human_review_recommended.
        assert _post(toks["admin"], _span(uuid.uuid4().hex, uuid.uuid4().hex[:16], "query",
            attrs={"db.system": "mysql", "db.name": "dev"},
            resource_attrs={"service.name": "dev-agent"})).status_code == 202
        assert _run(toks["admin"]).status_code == 200
        finds = db.query(AssetFinding).filter(
            AssetFinding.organization_id == org.id).all()
        assert all((f.severity or "").lower() not in ("high", "critical") for f in finds), \
            [(f.finding_type, f.severity) for f in finds]
        assert _candidates(db, org.id) == []
    finally:
        db.close()


def test_human_review_recommended_qualifies_at_any_severity():
    """Decided: human_review_recommended creates a candidate even when medium."""
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, toks = _org(db, "hrr")
        # Synthetic medium human_review_recommended with no high findings at all.
        import hashlib
        akey = hashlib.sha256(f"{org.id}:manual-agent".encode()).hexdigest()[:64]
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        db.add(AssetFinding(
            organization_id=org.id, asset_id=None, asset_key=akey,
            category="security", finding_type="human_review_recommended",
            severity="medium", title="t", summary="s",
            evidence_json=json.dumps({"environment": "staging"}),
            source="runtime_security", status="open",
            first_seen=now, last_seen=now))
        db.commit()
        assert _run(toks["admin"]).status_code == 200
        rows = _candidates(db, org.id)
        assert len(rows) == 1 and rows[0].severity == "medium"
        ev = json.loads(rows[0].evidence_json)
        assert {"control": "human review requirement", "kind": "soft"} in ev["recommended_controls"]
    finally:
        db.close()


def test_idempotent_second_run_creates_nothing():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, toks = _org(db, "idem")
        _seed_risky_agent(toks["admin"])
        assert _run(toks["admin"]).status_code == 200
        r2 = _run(toks["admin"])
        assert r2.status_code == 200
        assert r2.json()["findings_created"] == 0, r2.json()
        assert len(_candidates(db, org.id)) == 1
    finally:
        db.close()


def test_dismissal_is_sticky_until_new_trigger_type():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, toks = _org(db, "dis")
        _seed_risky_agent(toks["admin"])
        assert _run(toks["admin"]).status_code == 200
        cand = _candidates(db, org.id)[0]
        prev_evidence = cand.evidence_json

        r = _client.post(f"/intelligence/findings/{cand.id}/dismiss",
                         headers={"Authorization": f"Bearer {toks['admin']}"})
        assert r.status_code == 200

        # Rerun with the SAME evidence → stays dismissed, evidence frozen.
        assert _run(toks["admin"]).status_code == 200
        db.expire_all()
        cand = _candidates(db, org.id)[0]
        assert cand.status == "dismissed"
        assert cand.evidence_json == prev_evidence

        # New trigger type (unknown provider in production) → reopens deliberately.
        assert _post(toks["admin"], _span(uuid.uuid4().hex, uuid.uuid4().hex[:16], "chat",
            attrs={"gen_ai.provider.name": "mystery-llm-co", "gen_ai.request.model": "mystery-1"},
            resource_attrs={"service.name": "risky-agent", "deployment.environment": "production"})).status_code == 202
        assert _run(toks["admin"]).status_code == 200
        db.expire_all()
        cand = _candidates(db, org.id)[0]
        assert cand.status == "open"
        ev = json.loads(cand.evidence_json)
        assert "agent_uses_unknown_model_provider" in ev["trigger_finding_types"]
    finally:
        db.close()


def test_dismissing_candidate_leaves_findings_open():
    """Decided: dismissal independence — candidate and findings are separate."""
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, toks = _org(db, "indep")
        _seed_risky_agent(toks["admin"])
        assert _run(toks["admin"]).status_code == 200
        cand = _candidates(db, org.id)[0]
        assert _client.post(f"/intelligence/findings/{cand.id}/dismiss",
                            headers={"Authorization": f"Bearer {toks['admin']}"}).status_code == 200
        db.expire_all()
        triggers = db.query(AssetFinding).filter(
            AssetFinding.organization_id == org.id,
            AssetFinding.category != "control",
            AssetFinding.severity == "high").all()
        assert triggers and all(t.status == "open" for t in triggers)
    finally:
        db.close()


def test_only_admin_can_act_on_candidates():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, toks = _org(db, "rbac")
        _seed_risky_agent(toks["admin"])
        assert _run(toks["admin"]).status_code == 200
        cand = _candidates(db, org.id)[0]
        # analyst: can read, cannot act
        r = _client.get("/intelligence/findings?category=control",
                        headers={"Authorization": f"Bearer {toks['analyst']}"})
        assert r.status_code == 200 and len(r.json()) == 1
        for action in ("dismiss", "resolve", "reopen"):
            r = _client.post(f"/intelligence/findings/{cand.id}/{action}",
                             headers={"Authorization": f"Bearer {toks['analyst']}"})
            assert r.status_code == 403, (action, r.status_code)
        # analyst can still act on a NON-control finding
        normal = db.query(AssetFinding).filter(
            AssetFinding.organization_id == org.id,
            AssetFinding.category != "control").first()
        r = _client.post(f"/intelligence/findings/{normal.id}/dismiss",
                         headers={"Authorization": f"Bearer {toks['analyst']}"})
        assert r.status_code == 200
        # admin acts on the candidate
        r = _client.post(f"/intelligence/findings/{cand.id}/dismiss",
                         headers={"Authorization": f"Bearer {toks['admin']}"})
        assert r.status_code == 200
    finally:
        db.close()


def test_org_isolation():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org_a, toks_a = _org(db, "isoa")
        org_b, toks_b = _org(db, "isob")
        _seed_risky_agent(toks_a["admin"])
        assert _run(toks_a["admin"]).status_code == 200
        assert len(_candidates(db, org_a.id)) == 1
        assert _run(toks_b["admin"]).status_code == 200
        assert _candidates(db, org_b.id) == []
        r = _client.get("/intelligence/findings?category=control",
                        headers={"Authorization": f"Bearer {toks_b['admin']}"})
        assert r.json() == []
    finally:
        db.close()


def test_candidate_evidence_never_contains_raw_content():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, toks = _org(db, "priv")
        assert _post(toks["admin"], _span(uuid.uuid4().hex, uuid.uuid4().hex[:16], "tool",
            attrs={"gen_ai.tool.name": "risky", "tool.arguments": '{"password":"hunter2"}',
                   "url.full": "https://api.secret.com/v1?apikey=TOPSECRET",
                   "db.system": "mysql", "mcp.method.name": "tools/call"},
            resource_attrs={"service.name": "priv-agent", "deployment.environment": "production"})).status_code == 202
        assert _run(toks["admin"]).status_code == 200
        rows = _candidates(db, org.id)
        assert len(rows) == 1
        blob = (rows[0].evidence_json or "") + (rows[0].summary or "") + (rows[0].title or "")
        for forbidden in ["hunter2", "TOPSECRET", "apikey=", "password", "tool.arguments"]:
            assert forbidden not in blob, f"leaked: {forbidden}"
    finally:
        db.close()
