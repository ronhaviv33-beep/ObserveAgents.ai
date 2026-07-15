"""
Tests for GET /agents/{agent_id}/timeline — the Agent Timeline API.

Covers:
  A. Response shape (agent, summary, events, next_cursor)
  B. Keyset pagination
  C. Filters (event_type, status, min_risk)
  D. Summary sourced from the agent_metrics_daily rollup
  E. Org isolation — org B cannot read org A's agent timeline
  F. Ingested agents appear in the shared AssetRegistry inventory
"""
from __future__ import annotations

import os
import sys
import uuid

_db_path = f"/tmp/test_agent_timeline_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-agent-timeline")
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
from app.models import Organization, User, AssetRegistry
from app.auth import hash_password, create_token

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")

_NOW = datetime.now(timezone.utc).replace(hour=12)


def _make_org_and_token(db, suffix=""):
    sfx = suffix or uuid.uuid4().hex[:6]
    org = Organization(name=f"tl-org-{sfx}", slug=f"tl-{sfx}")
    db.add(org)
    db.flush()
    user = User(email=f"tl-{sfx}@example.com", name=f"TL {sfx}",
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


def _timeline(token, agent_id, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    return _client.get(f"/agents/{agent_id}/timeline{('?' + q) if q else ''}",
                       headers={"Authorization": f"Bearer {token}"})


def _seed_agent(token, agent_id="timeline-agent", n=5):
    events = []
    for i in range(n):
        events.append({
            "event_id": f"{agent_id}-ev-{i}",
            "agent_id": agent_id,
            "agent_name": "Timeline Agent",
            "team": "platform", "owner": "own@x.io", "environment": "production",
            "event_type": "llm_call" if i % 2 == 0 else "tool_call",
            "provider": "openai", "model": "gpt-4o",
            "tool_name": "web_search" if i % 2 else None,
            "input_tokens": 100, "output_tokens": 20, "cost_usd": 0.01 * (i + 1),
            "latency_ms": 500 + i * 100,
            "status": "error" if i == n - 1 else "ok",
            "error_message": "exploded" if i == n - 1 else None,
            "timestamp": (_NOW - timedelta(minutes=n - i)).isoformat(),
        })
    _ingest(token, events)


def test_timeline_shape_and_content():
    db = SessionLocal()
    org, _u, token = _make_org_and_token(db)
    _seed_agent(token, "shape-agent", n=4)

    r = _timeline(token, "shape-agent", days=7)
    assert r.status_code == 200, r.text
    d = r.json()

    assert d["agent"]["agent_id"] == "shape-agent"
    assert d["agent"]["name"] == "Timeline Agent"
    assert d["agent"]["team"] == "platform"
    assert d["agent"]["environment"] == "production"

    s = d["summary"]
    assert s["events"] == 4
    assert s["errors"] == 1
    assert s["last_seen"] is not None
    assert s["models"][0]["model"] == "gpt-4o"

    assert len(d["events"]) == 4
    newest = d["events"][0]
    # Newest first; the newest seeded event is the error one
    assert newest["status"] == "error"
    assert newest["error_message"] == "exploded"
    assert newest["risk_level"] in ("none", "low", "medium", "high")
    assert isinstance(newest["risk_reasons"], list)
    for e in d["events"]:
        for key in ("event_id", "timestamp", "event_type", "model", "provider",
                    "latency_ms", "cost_usd", "status", "risk_score", "policy_action"):
            assert key in e
    assert d["next_cursor"] is None  # fewer than limit
    db.close()


def test_timeline_pagination():
    db = SessionLocal()
    org, _u, token = _make_org_and_token(db)
    _seed_agent(token, "page-agent", n=7)

    r1 = _timeline(token, "page-agent", days=7, limit=3)
    d1 = r1.json()
    assert len(d1["events"]) == 3 and d1["next_cursor"] is not None

    r2 = _timeline(token, "page-agent", days=7, limit=3, cursor=d1["next_cursor"])
    d2 = r2.json()
    assert len(d2["events"]) == 3

    r3 = _timeline(token, "page-agent", days=7, limit=3, cursor=d2["next_cursor"])
    d3 = r3.json()
    assert len(d3["events"]) == 1 and d3["next_cursor"] is None

    all_ids = [e["event_id"] for e in d1["events"] + d2["events"] + d3["events"]]
    assert len(all_ids) == len(set(all_ids)) == 7
    db.close()


def test_timeline_filters():
    db = SessionLocal()
    org, _u, token = _make_org_and_token(db)
    _seed_agent(token, "filter-agent", n=6)

    r = _timeline(token, "filter-agent", days=7, event_type="tool_call")
    assert all(e["event_type"] == "tool_call" for e in r.json()["events"])
    assert len(r.json()["events"]) == 3

    r = _timeline(token, "filter-agent", days=7, status="error")
    assert len(r.json()["events"]) == 1

    r = _timeline(token, "filter-agent", days=7, min_risk=1)
    assert all(e["risk_score"] >= 1 for e in r.json()["events"])
    db.close()


def test_org_isolation():
    db = SessionLocal()
    _org_a, _ua, token_a = _make_org_and_token(db, "isoa")
    _org_b, _ub, token_b = _make_org_and_token(db, "isob")
    _seed_agent(token_a, "secret-agent", n=2)

    # Org A sees its agent
    assert _timeline(token_a, "secret-agent").status_code == 200
    # Org B gets a 404 — the agent does not exist in its inventory
    assert _timeline(token_b, "secret-agent").status_code == 404

    # Even after org B ingests an identically-named agent, it only sees its own events
    _ingest(token_b, [{"event_id": "b-own-1", "agent_id": "secret-agent"}])
    d = _timeline(token_b, "secret-agent").json()
    assert {e["event_id"] for e in d["events"]} == {"b-own-1"}
    db.close()


def test_unknown_agent_404():
    db = SessionLocal()
    _org, _u, token = _make_org_and_token(db)
    assert _timeline(token, "never-seen-agent").status_code == 404
    db.close()


def test_ingested_agent_registered_in_inventory():
    db = SessionLocal()
    org, _u, token = _make_org_and_token(db)
    _ingest(token, [{"event_id": "inv-1", "agent_id": "inventory-agent",
                     "agent_name": "Inventory Agent", "team": "ops",
                     "owner": "ops@x.io", "environment": "staging"}])
    reg = db.query(AssetRegistry).filter_by(
        organization_id=org.id, agent_id_raw="inventory-agent").first()
    assert reg is not None
    assert reg.agent_name == "Inventory Agent"
    assert reg.team == "ops"
    assert reg.environment == "staging"
    # Timeline resolvable by asset_key too
    assert _timeline(token, reg.asset_key).status_code == 200
    db.close()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
