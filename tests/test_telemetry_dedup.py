"""
Tests for telemetry ingestion idempotency/deduplication on (org_id, event_id).

Covers:
  A. Intra-batch duplicate — second occurrence reported as duplicated
  B. Cross-batch duplicate — replay of an already-queued event
  C. Replay after processing — still deduplicated, no second normalized row
  D. Same event_id in two orgs — both accepted (dedup is org-scoped)
"""
from __future__ import annotations

import os
import sys
import uuid

_db_path = f"/tmp/test_telemetry_dedup_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-telemetry-dedup")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["TELEMETRY_WORKER_MODE"] = "inline"

_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Organization, User, TelemetryEvent, TelemetryEventRaw
from app.auth import hash_password, create_token

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")


def _make_org_and_token(db, suffix=""):
    sfx = suffix or uuid.uuid4().hex[:6]
    org = Organization(name=f"dd-org-{sfx}", slug=f"dd-{sfx}")
    db.add(org)
    db.flush()
    user = User(email=f"dd-{sfx}@example.com", name=f"DD {sfx}",
                hashed_password=hash_password("pass"), organization_id=org.id,
                role="admin", team="eng", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(org)
    db.refresh(user)
    return org, user, create_token(user)


def _post(token, events):
    return _client.post("/api/v1/telemetry/batch", json={"events": events},
                        headers={"Authorization": f"Bearer {token}"})


def test_intra_batch_duplicate():
    db = SessionLocal()
    org, _u, token = _make_org_and_token(db)
    r = _post(token, [
        {"event_id": "intra-1", "agent_id": "a1", "model": "gpt-4o"},
        {"event_id": "intra-1", "agent_id": "a1", "model": "gpt-4o-mini"},  # dup, first wins
    ])
    assert r.status_code == 202
    body = r.json()
    assert body["accepted"] == 1 and body["duplicated"] == 1

    rows = db.query(TelemetryEventRaw).filter(
        TelemetryEventRaw.organization_id == org.id,
        TelemetryEventRaw.event_id == "intra-1",
    ).all()
    assert len(rows) == 1
    assert '"gpt-4o"' in rows[0].raw_payload  # first occurrence won
    db.close()


def test_cross_batch_duplicate():
    db = SessionLocal()
    org, _u, token = _make_org_and_token(db)
    r1 = _post(token, [{"event_id": "cross-1", "agent_id": "a1"}])
    assert r1.json()["accepted"] == 1
    r2 = _post(token, [{"event_id": "cross-1", "agent_id": "a1"},
                       {"event_id": "cross-2", "agent_id": "a1"}])
    body = r2.json()
    assert body["accepted"] == 1 and body["duplicated"] == 1
    db.close()


def test_replay_after_processing_no_duplicate_normalized_rows():
    db = SessionLocal()
    org, _u, token = _make_org_and_token(db)
    ev = {"event_id": "replay-1", "agent_id": "replay-agent", "model": "gpt-4o",
          "input_tokens": 10, "output_tokens": 5}
    r1 = _post(token, [ev])
    assert r1.json()["accepted"] == 1
    # Inline mode already processed it — replay the identical event.
    r2 = _post(token, [ev])
    assert r2.json() ["accepted"] == 0
    assert r2.json()["duplicated"] == 1

    norm = db.query(TelemetryEvent).filter(
        TelemetryEvent.organization_id == org.id,
        TelemetryEvent.event_id == "replay-1",
    ).all()
    assert len(norm) == 1
    raw = db.query(TelemetryEventRaw).filter(
        TelemetryEventRaw.organization_id == org.id,
        TelemetryEventRaw.event_id == "replay-1",
    ).all()
    assert len(raw) == 1
    db.close()


def test_same_event_id_across_orgs_both_accepted():
    db = SessionLocal()
    _org_a, _ua, token_a = _make_org_and_token(db, "orga")
    _org_b, _ub, token_b = _make_org_and_token(db, "orgb")
    shared = {"event_id": "shared-ev", "agent_id": "agent-x"}
    ra = _post(token_a, [shared])
    rb = _post(token_b, [shared])
    assert ra.json()["accepted"] == 1 and ra.json()["duplicated"] == 0
    assert rb.json()["accepted"] == 1 and rb.json()["duplicated"] == 0
    assert db.query(TelemetryEventRaw).filter(
        TelemetryEventRaw.event_id == "shared-ev").count() == 2
    db.close()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
