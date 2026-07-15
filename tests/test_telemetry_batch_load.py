"""
Load test: a single 1,000-event batch through the full ingestion pipeline.

Verifies the batch API accepts the maximum batch quickly, the worker drains
the whole queue, every event lands exactly once in telemetry_events, and the
daily rollup is exact.
"""
from __future__ import annotations

import os
import sys
import uuid

_db_path = f"/tmp/test_telemetry_load_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-telemetry-load")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["TELEMETRY_WORKER_ENABLED"] = "false"   # manual drain: measure intake alone

_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

import time
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Organization, User, AgentMetricsDaily, TelemetryEvent, TelemetryEventRaw
from app.auth import hash_password, create_token
from app.telemetry_ingest import worker

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")

N = 1000
AGENTS = 10
_NOW = datetime.now(timezone.utc).replace(hour=12)


def test_thousand_event_batch():
    db = SessionLocal()
    sfx = uuid.uuid4().hex[:6]
    org = Organization(name=f"load-org-{sfx}", slug=f"load-{sfx}")
    db.add(org)
    db.flush()
    user = User(email=f"load-{sfx}@example.com", name="Load", hashed_password=hash_password("pass"),
                organization_id=org.id, role="admin", team="eng", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_token(user)

    events = []
    for i in range(N):
        events.append({
            "event_id": f"load-ev-{i}",
            "agent_id": f"load-agent-{i % AGENTS}",
            "team": "load", "owner": "load@x.io", "environment": "production",
            "provider": "openai", "model": "gpt-4o",
            "input_tokens": 100, "output_tokens": 10,
            "latency_ms": 100 + (i % 50),
            "status": "error" if i % 100 == 0 else "ok",
            "timestamp": (_NOW - timedelta(seconds=N - i)).isoformat(),
        })

    t0 = time.monotonic()
    r = _client.post("/api/v1/telemetry/batch", json={"events": events},
                     headers={"Authorization": f"Bearer {token}"})
    intake_secs = time.monotonic() - t0
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["accepted"] == N and body["duplicated"] == 0 and body["failed"] == 0
    # Intake must be fast — no normalization/risk/metrics work in the request.
    assert intake_secs < 10, f"batch intake took {intake_secs:.1f}s"

    assert db.query(TelemetryEventRaw).filter_by(organization_id=org.id, status="pending").count() == N

    drained = worker.drain_all(db, max_batches=100)
    assert drained == N

    assert db.query(TelemetryEvent).filter_by(organization_id=org.id).count() == N
    assert db.query(TelemetryEventRaw).filter_by(organization_id=org.id, status="processed").count() == N

    # Rollup exactness for one agent: N/AGENTS events, one error per 100 i-values
    # for agents where i % AGENTS == 0 (i multiples of 100 all hit agent 0).
    rows = db.query(AgentMetricsDaily).filter_by(
        organization_id=org.id, agent_id="load-agent-0").all()
    assert sum(m.events_count for m in rows) == N // AGENTS
    assert sum(m.error_count for m in rows) == N // 100

    # Whole-org rollup totals match the event count exactly.
    all_rows = db.query(AgentMetricsDaily).filter_by(organization_id=org.id).all()
    assert sum(m.events_count for m in all_rows) == N

    # Replaying the same batch is a pure dedup no-op.
    r2 = _client.post("/api/v1/telemetry/batch", json={"events": events},
                      headers={"Authorization": f"Bearer {token}"})
    assert r2.json()["accepted"] == 0
    assert r2.json()["duplicated"] == N
    db.close()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
