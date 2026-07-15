"""
Tests for the telemetry ingest worker (app/telemetry_ingest/worker.py).

Worker thread is disabled; drain_once/drain_all are driven manually so the
queue state machine can be observed step by step.

Covers:
  A. pending -> processed transition + normalized field mapping
  B. cost computed from the pricing registry when omitted (cost_estimated)
  C. poison event -> failed after MAX_ATTEMPTS
  D. stale `processing` claim recovered
  E. drain idempotence — reprocessing never duplicates normalized rows
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

_db_path = f"/tmp/test_telemetry_worker_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-telemetry-worker")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["TELEMETRY_WORKER_ENABLED"] = "false"   # no thread; manual drain

_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Organization, User, AssetRegistry, TelemetryEvent, TelemetryEventRaw
from app.auth import hash_password, create_token
from app.telemetry_ingest import worker

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")


def _make_org_and_token(db, suffix=""):
    sfx = suffix or uuid.uuid4().hex[:6]
    org = Organization(name=f"wk-org-{sfx}", slug=f"wk-{sfx}")
    db.add(org)
    db.flush()
    user = User(email=f"wk-{sfx}@example.com", name=f"WK {sfx}",
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


def test_pending_to_processed_and_field_mapping():
    db = SessionLocal()
    org, _u, token = _make_org_and_token(db)
    _enqueue(token, [{
        "event_id": "map-1", "agent_id": "mapper-agent", "agent_name": "Mapper",
        "team": "data", "owner": "o@x.io", "environment": "production",
        "event_type": "llm_call", "provider": "openai", "model": "gpt-4o",
        "input_tokens": 100, "output_tokens": 40, "latency_ms": 1234.5,
        "cost_usd": 0.02, "status": "ok", "timestamp": "2026-07-14T08:30:00Z",
        "trace_id": "t1", "span_id": "s1", "parent_span_id": "p1",
        "tool_name": None, "action_name": "summarize",
    }])
    raw = db.query(TelemetryEventRaw).filter_by(organization_id=org.id, event_id="map-1").first()
    assert raw.status == "pending"

    assert worker.drain_once(db) == 1
    db.expire_all()
    raw = db.query(TelemetryEventRaw).filter_by(organization_id=org.id, event_id="map-1").first()
    assert raw.status == "processed" and raw.processed_at is not None

    e = db.query(TelemetryEvent).filter_by(organization_id=org.id, event_id="map-1").first()
    assert e is not None
    assert (e.agent_id, e.agent_name, e.team, e.owner, e.environment) == \
           ("mapper-agent", "Mapper", "data", "o@x.io", "production")
    assert (e.provider, e.model) == ("openai", "gpt-4o")
    assert (e.input_tokens, e.output_tokens, e.total_tokens) == (100, 40, 140)
    assert e.cost_usd == 0.02 and e.cost_estimated is False
    assert e.latency_ms == 1234.5
    assert (e.trace_id, e.span_id, e.parent_span_id) == ("t1", "s1", "p1")
    assert e.action_name == "summarize"
    assert e.timestamp.astimezone(timezone.utc).isoformat().startswith("2026-07-14T08:30:00")
    assert e.raw_id == raw.id

    # Agent registered in the shared inventory
    reg = db.query(AssetRegistry).filter_by(organization_id=org.id, agent_id_raw="mapper-agent").first()
    assert reg is not None and reg.asset_key == e.asset_key
    db.close()


def test_cost_estimated_from_pricing_registry():
    db = SessionLocal()
    org, _u, token = _make_org_and_token(db)
    _enqueue(token, [{
        "event_id": "cost-1", "agent_id": "cost-agent", "model": "gpt-4o",
        "input_tokens": 1_000_000, "output_tokens": 0,
    }])
    worker.drain_once(db)
    e = db.query(TelemetryEvent).filter_by(organization_id=org.id, event_id="cost-1").first()
    assert e.cost_estimated is True
    assert e.cost_usd is not None and abs(e.cost_usd - 2.50) < 0.01  # gpt-4o input $2.50/1M
    db.close()


def test_poison_event_fails_after_max_attempts(monkeypatch):
    db = SessionLocal()
    org, _u, token = _make_org_and_token(db)
    _enqueue(token, [{"event_id": "poison-1", "agent_id": "poison-agent"}])

    from app.telemetry_ingest import normalizer as _norm

    def _boom(*a, **kw):
        raise RuntimeError("poison payload")
    monkeypatch.setattr(_norm, "normalize", _boom)

    for _ in range(worker.MAX_ATTEMPTS):
        worker.drain_once(db)
        db.expire_all()

    raw = db.query(TelemetryEventRaw).filter_by(organization_id=org.id, event_id="poison-1").first()
    assert raw.status == "failed"
    assert raw.attempts == worker.MAX_ATTEMPTS
    assert "poison payload" in (raw.error or "")
    assert db.query(TelemetryEvent).filter_by(organization_id=org.id, event_id="poison-1").count() == 0

    monkeypatch.undo()
    # A failed row stays out of the queue.
    assert worker.drain_once(db) == 0
    db.close()


def test_stale_processing_claim_recovered():
    db = SessionLocal()
    org, _u, token = _make_org_and_token(db)
    _enqueue(token, [{"event_id": "stale-1", "agent_id": "stale-agent"}])

    # Simulate a crash: row claimed long ago, never finished.
    raw = db.query(TelemetryEventRaw).filter_by(organization_id=org.id, event_id="stale-1").first()
    raw.status = "processing"
    raw.claimed_at = datetime.now(timezone.utc) - timedelta(seconds=worker.STALE_PROCESSING_SECONDS + 60)
    db.commit()

    assert worker.drain_once(db) == 1  # recovered and processed
    db.expire_all()
    raw = db.query(TelemetryEventRaw).filter_by(organization_id=org.id, event_id="stale-1").first()
    assert raw.status == "processed"
    assert db.query(TelemetryEvent).filter_by(organization_id=org.id, event_id="stale-1").count() == 1
    db.close()


def test_reprocessing_is_idempotent():
    db = SessionLocal()
    org, _u, token = _make_org_and_token(db)
    _enqueue(token, [{"event_id": "idem-1", "agent_id": "idem-agent", "model": "gpt-4o",
                      "input_tokens": 5, "output_tokens": 5}])
    worker.drain_once(db)

    # Force the processed row back to pending — simulates an at-least-once replay.
    raw = db.query(TelemetryEventRaw).filter_by(organization_id=org.id, event_id="idem-1").first()
    raw.status = "pending"
    db.commit()
    worker.drain_once(db)
    db.expire_all()

    assert db.query(TelemetryEvent).filter_by(organization_id=org.id, event_id="idem-1").count() == 1
    raw = db.query(TelemetryEventRaw).filter_by(organization_id=org.id, event_id="idem-1").first()
    assert raw.status == "processed"
    db.close()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
