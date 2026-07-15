"""
Tests for admin-only detection rule management (app/routes/detection_rules.py).

Covers: admin create/update/enable-disable/delete, non-admin mutations
rejected (backend enforcement), org isolation, invalid template/config
rejected, built-in override on demand, and rule changes affecting subsequent
ingest scoring while orgs without rules keep default behavior.
"""
from __future__ import annotations

import os
import sys
import uuid

_db_path = f"/tmp/test_detection_rules_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-detection-rules")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["TELEMETRY_WORKER_MODE"] = "inline"

_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Organization, User, TelemetryEvent
from app.auth import hash_password, create_token

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")


def _make_org(db, suffix="", role="admin"):
    sfx = suffix or uuid.uuid4().hex[:6]
    org = Organization(name=f"dr-org-{sfx}", slug=f"dr-{sfx}")
    db.add(org)
    db.flush()
    user = User(email=f"dr-{sfx}@example.com", name=f"DR {sfx}",
                hashed_password=hash_password("pass"), organization_id=org.id,
                role=role, team="eng", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(org)
    db.refresh(user)
    return org, user, create_token(user)


def _viewer_token(db, org):
    user = User(email=f"viewer-{uuid.uuid4().hex[:6]}@example.com", name="Viewer",
                hashed_password=hash_password("pass"), organization_id=org.id,
                role="viewer", team="eng", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return create_token(user)


def _h(token):
    return {"Authorization": f"Bearer {token}"}


_CUSTOM = {"name": "Watch prod db tool", "template_type": "tool_condition",
           "severity": "high", "config": {"tools": ["prod_db_write"]}}


def test_list_includes_builtins_and_can_manage_flag():
    db = SessionLocal()
    org, _u, admin = _make_org(db)
    viewer = _viewer_token(db, org)

    d = _client.get("/detection-rules", headers=_h(admin)).json()
    keys = {r["rule_key"] for r in d["rules"]}
    assert {"status_error", "cost_threshold", "latency_threshold", "risky_tool"} <= keys
    assert "upstream_block" not in keys          # facts aren't tunable
    assert d["can_manage"] is True

    dv = _client.get("/detection-rules", headers=_h(viewer)).json()
    assert dv["can_manage"] is False
    assert len(dv["rules"]) == len(d["rules"])   # viewers see the same list
    db.close()


def test_admin_create_update_disable_delete_custom_rule():
    db = SessionLocal()
    org, u, admin = _make_org(db)

    r = _client.post("/detection-rules", json=_CUSTOM, headers=_h(admin))
    assert r.status_code == 201, r.text
    rule = r.json()
    assert rule["source"] == "custom" and rule["severity"] == "high"
    assert rule["created_by"] == u.email and rule["config"] == {"tools": ["prod_db_write"]}

    r = _client.patch(f"/detection-rules/{rule['id']}",
                      json={"severity": "low", "config": {"tools": ["prod_db_write", "Shell"]}},
                      headers=_h(admin))
    assert r.status_code == 200
    upd = r.json()
    assert upd["severity"] == "low" and "shell" in upd["config"]["tools"]
    assert upd["updated_by"] == u.email and upd["updated_at"] is not None

    r = _client.patch(f"/detection-rules/{rule['id']}", json={"enabled": False}, headers=_h(admin))
    assert r.json()["enabled"] is False

    r = _client.delete(f"/detection-rules/{rule['id']}", headers=_h(admin))
    assert r.status_code == 200 and r.json()["deleted"] is True
    remaining = {x["rule_key"] for x in _client.get("/detection-rules", headers=_h(admin)).json()["rules"]}
    assert rule["rule_key"] not in remaining
    db.close()


def test_builtin_override_on_demand_and_delete_protection():
    db = SessionLocal()
    org, _u, admin = _make_org(db)

    r = _client.patch("/detection-rules/cost_threshold",
                      json={"severity": "high", "enabled": True, "config": {"cost_usd": 5.0}},
                      headers=_h(admin))
    assert r.status_code == 200, r.text
    ov = r.json()
    assert ov["source"] == "built_in" and ov["config"]["cost_usd"] == 5.0

    # Built-ins cannot be deleted
    r = _client.delete(f"/detection-rules/{ov['id']}", headers=_h(admin))
    assert r.status_code == 400

    # Disable works
    r = _client.patch("/detection-rules/status_error", json={"enabled": False}, headers=_h(admin))
    assert r.status_code == 200 and r.json()["enabled"] is False
    db.close()


def test_non_admin_cannot_mutate():
    db = SessionLocal()
    org, _u, admin = _make_org(db)
    viewer = _viewer_token(db, org)

    assert _client.post("/detection-rules", json=_CUSTOM, headers=_h(viewer)).status_code == 403
    assert _client.patch("/detection-rules/cost_threshold", json={"enabled": False},
                         headers=_h(viewer)).status_code == 403

    r = _client.post("/detection-rules", json=_CUSTOM, headers=_h(admin))
    rid = r.json()["id"]
    assert _client.patch(f"/detection-rules/{rid}", json={"enabled": False}, headers=_h(viewer)).status_code == 403
    assert _client.delete(f"/detection-rules/{rid}", headers=_h(viewer)).status_code == 403
    # But viewers can read
    assert _client.get("/detection-rules", headers=_h(viewer)).status_code == 200
    assert _client.get("/detection-rules/templates", headers=_h(viewer)).status_code == 200
    db.close()


def test_org_isolation():
    db = SessionLocal()
    _org_a, _ua, admin_a = _make_org(db, "orga")
    _org_b, _ub, admin_b = _make_org(db, "orgb")

    rid = _client.post("/detection-rules", json=_CUSTOM, headers=_h(admin_a)).json()["id"]
    # Org B cannot see, patch, or delete org A's rule
    keys_b = {r["rule_key"] for r in _client.get("/detection-rules", headers=_h(admin_b)).json()["rules"]}
    assert all(not k.startswith("custom_") for k in keys_b)
    assert _client.patch(f"/detection-rules/{rid}", json={"enabled": False}, headers=_h(admin_b)).status_code == 404
    assert _client.delete(f"/detection-rules/{rid}", headers=_h(admin_b)).status_code == 404
    # Org A's override doesn't leak into org B's list
    _client.patch("/detection-rules/cost_threshold", json={"enabled": False}, headers=_h(admin_a))
    b_cost = next(r for r in _client.get("/detection-rules", headers=_h(admin_b)).json()["rules"]
                  if r["rule_key"] == "cost_threshold")
    assert b_cost["enabled"] is True
    db.close()


def test_invalid_template_and_config_rejected():
    db = SessionLocal()
    _org, _u, admin = _make_org(db)
    bad = [
        {**_CUSTOM, "template_type": "arbitrary_python"},                     # unknown template
        {**_CUSTOM, "config": {"tools": []}},                                 # empty list
        {**_CUSTOM, "config": {"wrong_key": ["x"]}},                          # missing param
        {**_CUSTOM, "severity": "critical"},                                  # invalid severity
        {"name": "x", "template_type": "cost_threshold", "severity": "low",
         "config": {"cost_usd": -1}},                                         # out of bounds
    ]
    for payload in bad:
        r = _client.post("/detection-rules", json=payload, headers=_h(admin))
        assert r.status_code == 422, f"{payload} -> {r.status_code}"
    db.close()


def test_rule_changes_affect_future_scoring_and_defaults_unchanged():
    db = SessionLocal()
    org_a, _ua, admin_a = _make_org(db, "score-a")
    org_b, _ub, admin_b = _make_org(db, "score-b")

    def ingest(token, org_tag, event_id, tool):
        _client.post("/api/v1/telemetry/batch", json={"events": [
            {"event_id": event_id, "agent_id": f"agent-{org_tag}", "team": "eng",
             "owner": "o@x.io", "environment": "production", "provider": "openai",
             "model": "gpt-4o", "cost_usd": 0.01, "latency_ms": 100,
             "event_type": "tool_call", "tool_name": tool}
        ]}, headers=_h(token))

    # Custom rule in org A: watch tool "billing_export" (not in default risky set)
    _client.post("/detection-rules", json={
        "name": "Billing export watch", "template_type": "tool_condition",
        "severity": "high", "config": {"tools": ["billing_export"]}}, headers=_h(admin_a))
    # Org A also disables the built-in error rule to prove overrides apply
    _client.patch("/detection-rules/status_error", json={"enabled": False}, headers=_h(admin_a))

    ingest(admin_a, "a", "sc-a-1", "billing_export")
    ingest(admin_b, "b", "sc-b-1", "billing_export")

    ev_a = db.query(TelemetryEvent).filter_by(organization_id=org_a.id, event_id="sc-a-1").one()
    ev_b = db.query(TelemetryEvent).filter_by(organization_id=org_b.id, event_id="sc-b-1").one()
    assert ev_a.risk_score >= 25                     # custom high-severity rule fired
    assert "Billing export watch" in (ev_a.risk_reasons or "")
    assert "billing_export" not in (ev_b.risk_reasons or "")   # org B untouched
    assert ev_b.risk_score == 0                      # default behavior preserved
    db.close()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
