"""
Tests for app/risk_processor.py — per-event risk rules.

Each rule is exercised in isolation via evaluate_event with a fully-populated
"clean" baseline event, then one field perturbed. Also covers the score cap,
policy_action derivation, the production block via PolicyRule, and OrgConfig
`risk_thresholds` overrides.
"""
from __future__ import annotations

import os
import sys
import uuid

_db_path = f"/tmp/test_risk_processor_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-risk-processor")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["TELEMETRY_WORKER_ENABLED"] = "false"

_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

from fastapi.testclient import TestClient
from app.main import app  # boots DB (incl. pricing registry seed)
from app.database import SessionLocal
from app.models import Organization, PolicyRule
from app.org_config import set_org_config
from app import risk_processor as rp

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")

_db = SessionLocal()
_org = Organization(name=f"risk-org-{uuid.uuid4().hex[:6]}", slug=f"risk-{uuid.uuid4().hex[:6]}")
_db.add(_org)
_db.commit()
_db.refresh(_org)
ORG = _org.id


def _clean_event(**overrides) -> dict:
    """An event that trips zero rules."""
    e = {
        "agent_id": "clean-agent", "owner": "owner@x.io", "team": "eng",
        "environment": "production", "provider": "openai", "model": "gpt-4o",
        "cost_usd": 0.01, "latency_ms": 500.0, "status": "ok",
        "tool_name": None, "upstream_policy_action": None,
    }
    e.update(overrides)
    return e


def _eval(**overrides) -> rp.RiskResult:
    return rp.evaluate_event(_db, ORG, _clean_event(**overrides))


def test_clean_event_scores_zero():
    r = _eval()
    assert r.score == 0 and r.reasons == [] and r.policy_action == "allow"


def test_error_status():
    r = _eval(status="error")
    assert r.score == 25
    assert any("error" in x.lower() for x in r.reasons)


def test_upstream_block_forces_block_action_and_floor():
    r = _eval(upstream_policy_action="block")
    assert r.policy_action == "block"
    assert r.score >= 80
    r2 = _eval(status="blocked")
    assert r2.policy_action == "block" and r2.score >= 80


def test_missing_owner_and_team():
    assert _eval(owner=None).score == 10
    assert _eval(team=None).score == 10
    r = _eval(owner="", team="  ")
    assert r.score == 20 and len(r.reasons) == 2


def test_unknown_environment():
    r = _eval(environment="weird-env")
    assert r.score == 15
    assert "weird-env" in r.reasons[0]
    # Missing entirely is a milder signal
    assert _eval(environment=None).score == 10
    # Aliases are accepted
    assert _eval(environment="prod").score == 0
    assert _eval(environment="dev").score == 0


def test_unknown_provider():
    r = _eval(provider="mystery-llm-inc")
    assert r.score == 10
    assert "mystery-llm-inc" in r.reasons[0]


def test_unknown_model_not_in_pricing_registry():
    r = _eval(model="totally-unknown-model-9000")
    assert r.score == 15
    assert "pricing registry" in r.reasons[0]


def test_cost_threshold():
    assert _eval(cost_usd=0.99).score == 0
    r = _eval(cost_usd=1.50)
    assert r.score == 20
    assert "exceeds" in r.reasons[0]


def test_latency_threshold():
    assert _eval(latency_ms=29000).score == 0
    r = _eval(latency_ms=45000)
    assert r.score == 15


def test_risky_tool():
    r = _eval(tool_name="shell")
    assert r.score == 25
    assert "risky-tool" in r.reasons[0]
    assert _eval(tool_name="web_search").score == 0


def test_production_blocked_model_via_policy_rule():
    _db.add(PolicyRule(organization_id=ORG, team="*", rule_type="block_model",
                       value="gpt-4o"))
    _db.commit()
    try:
        r = _eval()  # clean event uses gpt-4o in production
        assert r.policy_action == "block"
        assert r.score >= 80
        assert any("blocked" in x.lower() for x in r.reasons)
        # Outside production the rule does not fire
        r2 = _eval(environment="dev")
        assert r2.policy_action == "allow"
    finally:
        _db.query(PolicyRule).filter_by(organization_id=ORG).delete()
        _db.commit()


def test_score_capped_at_100():
    r = _eval(status="error", owner=None, team=None, environment="mystery",
              provider="mystery", model="unknown-model-x", cost_usd=99.0,
              latency_ms=99999.0, tool_name="exec", upstream_policy_action="block")
    assert r.score == 100
    assert r.policy_action == "block"


def test_warn_action_at_default_threshold():
    # error(25) + risky tool(25) = 50 >= warn_score default 50
    r = _eval(status="error", tool_name="eval")
    assert r.score == 50 and r.policy_action == "warn"


def test_org_config_threshold_override():
    set_org_config(_db, ORG, "risk_thresholds",
                   {"cost_usd_threshold": 10.0, "risky_tools": ["my_custom_tool"]})
    try:
        cfg = rp.load_risk_config(_db, ORG)
        assert cfg["cost_usd_threshold"] == 10.0
        # $1.50 no longer trips the raised threshold
        assert rp.evaluate_event(_db, ORG, _clean_event(cost_usd=1.50), config=cfg).score == 0
        # shell is no longer risky; the custom tool is
        assert rp.evaluate_event(_db, ORG, _clean_event(tool_name="shell"), config=cfg).score == 0
        assert rp.evaluate_event(_db, ORG, _clean_event(tool_name="my_custom_tool"), config=cfg).score == 25
    finally:
        set_org_config(_db, ORG, "risk_thresholds", {})


def test_risk_level_buckets():
    assert rp.risk_level(0) == "none"
    assert rp.risk_level(20) == "low"
    assert rp.risk_level(40) == "medium"
    assert rp.risk_level(70) == "high"
    assert rp.risk_level(100) == "high"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
