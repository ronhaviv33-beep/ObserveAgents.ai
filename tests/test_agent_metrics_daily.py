"""
Tests for the agent_metrics_daily rollup + GET /telemetry/metrics/daily.

Covers:
  A. Rollup correctness against ingested events
  B. Recompute idempotence — draining twice yields identical numbers
  C. models_json per-model usage breakdown
  D. Multi-day bucketing (UTC day boundaries)
  E. /telemetry/metrics/daily group_by=team policy violations
"""
from __future__ import annotations

import json
import os
import sys
import uuid

_db_path = f"/tmp/test_agent_metrics_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-agent-metrics")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["TELEMETRY_WORKER_ENABLED"] = "false"

_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Organization, User, AgentMetricsDaily, TelemetryEventRaw
from app.auth import hash_password, create_token
from app.telemetry_ingest import worker

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")

_NOW = datetime.now(timezone.utc).replace(hour=12)  # mid-day: no boundary flake


def _make_org_and_token(db, suffix=""):
    sfx = suffix or uuid.uuid4().hex[:6]
    org = Organization(name=f"mx-org-{sfx}", slug=f"mx-{sfx}")
    db.add(org)
    db.flush()
    user = User(email=f"mx-{sfx}@example.com", name=f"MX {sfx}",
                hashed_password=hash_password("pass"), organization_id=org.id,
                role="admin", team="eng", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(org)
    db.refresh(user)
    return org, user, create_token(user)


def _enqueue(token, events):
    r = _client.post("/api/v1/telemetry/batch", json={"events": events},
                     headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 202, r.text
    return r.json()


def test_rollup_correctness_and_models_json():
    db = SessionLocal()
    org, _u, token = _make_org_and_token(db)
    ts = _NOW.isoformat()
    _enqueue(token, [
        {"event_id": "m-1", "agent_id": "roll-agent", "team": "growth", "owner": "o@x.io",
         "environment": "production", "model": "gpt-4o", "provider": "openai",
         "input_tokens": 100, "output_tokens": 100, "cost_usd": 0.10, "latency_ms": 1000,
         "timestamp": ts},
        {"event_id": "m-2", "agent_id": "roll-agent", "team": "growth", "owner": "o@x.io",
         "environment": "production", "model": "gpt-4o", "provider": "openai",
         "input_tokens": 50, "output_tokens": 50, "cost_usd": 0.05, "latency_ms": 2000,
         "timestamp": ts},
        {"event_id": "m-3", "agent_id": "roll-agent", "team": "growth", "owner": "o@x.io",
         "environment": "production", "model": "claude-haiku-4-5", "provider": "anthropic",
         "input_tokens": 10, "output_tokens": 10, "cost_usd": 0.01, "latency_ms": 600,
         "status": "error", "error_message": "timeout", "timestamp": ts},
    ])
    worker.drain_all(db)

    rows = db.query(AgentMetricsDaily).filter_by(
        organization_id=org.id, agent_id="roll-agent").all()
    assert len(rows) == 1
    m = rows[0]
    assert m.events_count == 3
    assert m.error_count == 1
    assert m.total_tokens == 320
    assert abs(m.total_cost_usd - 0.16) < 1e-9
    assert m.avg_latency_ms == 1200.0
    assert m.max_latency_ms == 2000.0
    assert m.team == "growth"
    models = json.loads(m.models_json)
    assert models["gpt-4o"]["events"] == 2
    assert models["gpt-4o"]["tokens"] == 300
    assert abs(models["gpt-4o"]["cost_usd"] - 0.15) < 1e-9
    assert models["claude-haiku-4-5"]["events"] == 1
    db.close()


def test_recompute_idempotence():
    db = SessionLocal()
    org, _u, token = _make_org_and_token(db)
    ts = _NOW.isoformat()
    _enqueue(token, [
        {"event_id": "idem-m-1", "agent_id": "idem-agent", "model": "gpt-4o",
         "cost_usd": 0.20, "latency_ms": 100, "timestamp": ts},
    ])
    worker.drain_all(db)
    first = db.query(AgentMetricsDaily).filter_by(organization_id=org.id, agent_id="idem-agent").one()
    snapshot = (first.events_count, first.total_cost_usd, first.avg_latency_ms)

    # Replay the raw row (at-least-once) and drain again.
    raw = db.query(TelemetryEventRaw).filter_by(organization_id=org.id, event_id="idem-m-1").one()
    raw.status = "pending"
    db.commit()
    worker.drain_all(db)
    db.expire_all()

    rows = db.query(AgentMetricsDaily).filter_by(organization_id=org.id, agent_id="idem-agent").all()
    assert len(rows) == 1
    assert (rows[0].events_count, rows[0].total_cost_usd, rows[0].avg_latency_ms) == snapshot
    db.close()


def test_multi_day_bucketing():
    db = SessionLocal()
    org, _u, token = _make_org_and_token(db)
    yesterday = (_NOW - timedelta(days=1)).isoformat()
    today = _NOW.isoformat()
    _enqueue(token, [
        {"event_id": "d-1", "agent_id": "day-agent", "timestamp": yesterday, "cost_usd": 0.01},
        {"event_id": "d-2", "agent_id": "day-agent", "timestamp": today, "cost_usd": 0.02},
        {"event_id": "d-3", "agent_id": "day-agent", "timestamp": today, "cost_usd": 0.03},
    ])
    worker.drain_all(db)

    rows = db.query(AgentMetricsDaily).filter_by(
        organization_id=org.id, agent_id="day-agent").order_by(AgentMetricsDaily.day).all()
    assert len(rows) == 2
    assert rows[0].events_count == 1 and abs(rows[0].total_cost_usd - 0.01) < 1e-9
    assert rows[1].events_count == 2 and abs(rows[1].total_cost_usd - 0.05) < 1e-9
    db.close()


def test_daily_metrics_endpoint_group_by_team():
    db = SessionLocal()
    org, _u, token = _make_org_and_token(db)
    ts = _NOW.isoformat()
    _enqueue(token, [
        # error + risky tool -> warn => policy violation for team alpha
        {"event_id": "t-1", "agent_id": "alpha-agent", "team": "alpha", "owner": "o@x.io",
         "environment": "production", "status": "error", "tool_name": "shell", "timestamp": ts},
        {"event_id": "t-2", "agent_id": "beta-agent", "team": "beta", "owner": "o@x.io",
         "environment": "production", "provider": "openai", "model": "gpt-4o",
         "cost_usd": 0.01, "latency_ms": 100, "timestamp": ts},
    ])
    worker.drain_all(db)

    r = _client.get("/telemetry/metrics/daily?days=7&group_by=team",
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    rows = {row["team"]: row for row in r.json()["rows"]}
    assert rows["alpha"]["policy_violations"] == 1
    assert rows["alpha"]["errors"] == 1
    assert rows["beta"]["policy_violations"] == 0

    r2 = _client.get("/telemetry/metrics/daily?days=7&group_by=agent",
                     headers={"Authorization": f"Bearer {token}"})
    agents = [row["agent_id"] for row in r2.json()["rows"]]
    # Top risky agent sorts first
    assert agents[0] == "alpha-agent"
    db.close()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
