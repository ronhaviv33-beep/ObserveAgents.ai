"""
Tests for Risk Findings v1 read APIs (app/routes/risk_findings.py).

Covers: findings derived from telemetry_events, summary counts, filtering,
risk-level mapping, rule attribution, timeline linkage fields, empty state,
and org isolation.
"""
from __future__ import annotations

import os
import sys
import uuid

_db_path = f"/tmp/test_risk_findings_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-risk-findings")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["TELEMETRY_WORKER_MODE"] = "inline"

_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Organization, User
from app.auth import hash_password, create_token

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")

_NOW = datetime.now(timezone.utc).replace(hour=12)


def _make_org_and_token(db, suffix=""):
    sfx = suffix or uuid.uuid4().hex[:6]
    org = Organization(name=f"rf-org-{sfx}", slug=f"rf-{sfx}")
    db.add(org)
    db.flush()
    user = User(email=f"rf-{sfx}@example.com", name=f"RF {sfx}",
                hashed_password=hash_password("pass"), organization_id=org.id,
                role="admin", team="eng", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(org)
    db.refresh(user)
    return org, user, create_token(user)


def _ingest(token, events):
    r = _client.post("/api/v1/telemetry/batch", json={"events": events},
                     headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 202, r.text
    return r.json()


def _get(token, path):
    return _client.get(path, headers={"Authorization": f"Bearer {token}"})


def _seed(token):
    """3 risky events + 1 clean event for one org."""
    ts = _NOW.isoformat()
    _ingest(token, [
        # clean: full metadata, known model, ok
        {"event_id": "rf-clean", "agent_id": "clean-agent", "team": "alpha",
         "owner": "o@x.io", "environment": "production", "provider": "openai",
         "model": "gpt-4o", "cost_usd": 0.01, "latency_ms": 500, "timestamp": ts},
        # error + risky tool + high latency -> warn (score 65)
        {"event_id": "rf-risky-1", "agent_id": "risky-agent", "team": "alpha",
         "owner": "o@x.io", "environment": "production", "event_type": "tool_call",
         "tool_name": "shell", "status": "error", "error_message": "boom",
         "latency_ms": 45000, "timestamp": ts},
        # upstream block -> block, floor 80
        {"event_id": "rf-risky-2", "agent_id": "risky-agent", "team": "alpha",
         "owner": "o@x.io", "environment": "production", "provider": "openai",
         "model": "gpt-4o", "status": "blocked", "timestamp": ts},
        # missing owner/team -> low score 20 (owner/team omitted AND not in registry yet)
        {"event_id": "rf-risky-3", "agent_id": "orphan-agent", "environment": "production",
         "provider": "openai", "model": "gpt-4o", "cost_usd": 0.01, "latency_ms": 100,
         "timestamp": (_NOW - timedelta(days=1)).isoformat()},
    ])


def test_findings_derived_from_telemetry_events():
    db = SessionLocal()
    _org, _u, token = _make_org_and_token(db)
    _seed(token)

    r = _get(token, "/risk-findings?days=7")
    assert r.status_code == 200, r.text
    d = r.json()
    ids = {f["event_id"] for f in d["findings"]}
    assert ids == {"rf-risky-1", "rf-risky-2", "rf-risky-3"}   # clean event excluded
    db.close()


def test_finding_fields_and_timeline_linkage():
    db = SessionLocal()
    _org, _u, token = _make_org_and_token(db)
    _seed(token)

    d = _get(token, "/risk-findings?days=7").json()
    f = next(x for x in d["findings"] if x["event_id"] == "rf-risky-1")
    assert f["agent_id"] == "risky-agent"
    assert f["asset_key"] and len(f["asset_key"]) == 64
    assert f["team"] == "alpha" and f["environment"] == "production"
    assert f["event_type"] == "tool_call" and f["tool_name"] == "shell"
    assert f["status"] == "error"
    assert f["risk_score"] == 65 and f["risk_level"] == "medium"
    assert f["policy_action"] == "warn"
    assert f["primary_reason"] == f["risk_reasons"][0]
    assert f["rule_id"] == "status_error"           # first reason is the error rule
    assert f["rule_name"] == "Event reported an error"
    # Timeline linkage
    assert f["timeline_agent_id"] == "risky-agent"
    assert f["timeline_url"] == "/agents/risky-agent/timeline"
    tl = _get(token, f["timeline_url"] + "?days=7")
    assert tl.status_code == 200
    assert any(e["event_id"] == "rf-risky-1" for e in tl.json()["events"])
    db.close()


def test_risk_level_mapping_and_filters():
    db = SessionLocal()
    _org, _u, token = _make_org_and_token(db)
    _seed(token)

    # min_risk
    d = _get(token, "/risk-findings?days=7&min_risk=80").json()
    assert {f["event_id"] for f in d["findings"]} == {"rf-risky-2"}
    assert d["findings"][0]["risk_level"] == "high"

    # risk_level buckets are exclusive
    d = _get(token, "/risk-findings?days=7&risk_level=medium").json()
    assert {f["event_id"] for f in d["findings"]} == {"rf-risky-1"}
    d = _get(token, "/risk-findings?days=7&risk_level=high").json()
    assert {f["event_id"] for f in d["findings"]} == {"rf-risky-2"}

    # policy_action / status / event_type / agent / team / environment / model / provider
    assert {f["event_id"] for f in _get(token, "/risk-findings?days=7&policy_action=block").json()["findings"]} == {"rf-risky-2"}
    assert {f["event_id"] for f in _get(token, "/risk-findings?days=7&status=error").json()["findings"]} == {"rf-risky-1"}
    assert {f["event_id"] for f in _get(token, "/risk-findings?days=7&event_type=tool_call").json()["findings"]} == {"rf-risky-1"}
    assert {f["event_id"] for f in _get(token, "/risk-findings?days=7&agent_id=orphan-agent").json()["findings"]} == {"rf-risky-3"}
    assert {f["event_id"] for f in _get(token, "/risk-findings?days=7&team=alpha").json()["findings"]} == {"rf-risky-1", "rf-risky-2"}
    assert {f["event_id"] for f in _get(token, "/risk-findings?days=7&model=gpt-4o&provider=openai").json()["findings"]} == {"rf-risky-2", "rf-risky-3"}
    # days=1 window excludes yesterday's finding... rf-risky-3 was 1 day ago at noon; days=1 covers exactly 24h back
    db.close()


def test_summary_counts():
    db = SessionLocal()
    _org, _u, token = _make_org_and_token(db)
    _seed(token)

    s = _get(token, "/risk-findings/summary?days=7").json()
    assert s["total_findings"] == 3
    assert s["high_risk_findings"] == 1          # rf-risky-2 (80)
    assert s["blocked_events"] == 1
    assert s["warning_events"] == 1              # rf-risky-1 (65 >= warn 50)
    top = s["top_risky_agents"]
    assert top[0]["agent_id"] == "risky-agent" and top[0]["max_risk_score"] == 80
    assert any(r["reason"] == "Event reported an error" for r in s["most_common_reasons"])
    teams = {t["team"]: t for t in s["findings_by_team"]}
    assert teams["alpha"]["findings"] == 2
    assert teams["alpha"]["policy_violations"] == 2   # warn + block
    assert sum(x["findings"] for x in s["findings_by_day"]) == 3
    db.close()


def test_rules_endpoint():
    db = SessionLocal()
    _org, _u, token = _make_org_and_token(db)
    r = _get(token, "/risk-findings/rules")
    assert r.status_code == 200
    d = r.json()
    rule_ids = {x["rule_id"] for x in d["rules"]}
    assert {"status_error", "risky_tool", "non_approved_model", "cost_threshold"} <= rule_ids
    assert d["thresholds"]["warn_score"] == 50
    assert "shell" in d["thresholds"]["risky_tools"]
    db.close()


def test_empty_state():
    db = SessionLocal()
    _org, _u, token = _make_org_and_token(db)
    d = _get(token, "/risk-findings?days=7").json()
    assert d["findings"] == [] and d["next_cursor"] is None
    s = _get(token, "/risk-findings/summary?days=7").json()
    assert s["total_findings"] == 0 and s["top_risky_agents"] == []
    assert s["findings_by_day"] == [] and s["most_common_reasons"] == []
    db.close()


def test_org_isolation():
    db = SessionLocal()
    _org_a, _ua, token_a = _make_org_and_token(db, "a")
    _org_b, _ub, token_b = _make_org_and_token(db, "b")
    _seed(token_a)

    d_b = _get(token_b, "/risk-findings?days=7").json()
    assert d_b["findings"] == []
    s_b = _get(token_b, "/risk-findings/summary?days=7").json()
    assert s_b["total_findings"] == 0

    d_a = _get(token_a, "/risk-findings?days=7").json()
    assert len(d_a["findings"]) == 3
    db.close()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
