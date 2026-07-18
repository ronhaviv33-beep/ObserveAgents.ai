"""
Tests for POST /api/v1/telemetry/batch — batch telemetry ingestion.

Covers:
  A. Happy path — accepted counts, 202
  B. Mixed valid/invalid — partial acceptance with per-event errors
  C. Batch size limit — 413 over MAX_BATCH_EVENTS
  D. Unauthenticated — 401
  E. Raw payload preserved verbatim, including unknown extra fields
  F. gk- API key auth + api_key_id attribution
"""
from __future__ import annotations

import json
import os
import sys
import uuid

# ── Env setup BEFORE any app import ───────────────────────────────────────────
_db_path = f"/tmp/test_telemetry_batch_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-telemetry-batch")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["TELEMETRY_WORKER_MODE"] = "inline"

_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Organization, User, ApiKey, TelemetryEvent, TelemetryEventRaw
from app.auth import hash_password, create_token, generate_api_key
from app.telemetry_ingest.schemas import MAX_BATCH_EVENTS

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")


def _make_org_and_token(db, suffix=""):
    sfx = suffix or uuid.uuid4().hex[:6]
    org = Organization(name=f"tb-org-{sfx}", slug=f"tb-{sfx}")
    db.add(org)
    db.flush()
    user = User(
        email=f"tb-{sfx}@example.com", name=f"TB {sfx}",
        hashed_password=hash_password("pass"), organization_id=org.id,
        role="admin", team="eng", is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(org)
    db.refresh(user)
    return org, user, create_token(user)


def _ev(event_id: str, agent_id: str = "test-agent", **extra) -> dict:
    return {"event_id": event_id, "agent_id": agent_id, **extra}


def test_batch_happy_path():
    db = SessionLocal()
    org, _user, token = _make_org_and_token(db)
    events = [
        _ev("hp-1", model="gpt-4o", provider="openai", input_tokens=100, output_tokens=50,
            latency_ms=800, team="eng", owner="a@b.c", environment="production",
            timestamp="2026-07-15T09:00:00Z"),
        _ev("hp-2", event_type="tool_call", tool_name="web_search"),
    ]
    r = _client.post("/api/v1/telemetry/batch", json={"events": events},
                     headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["accepted"] == 2
    assert body["duplicated"] == 0
    assert body["failed"] == 0
    assert body["errors"] == []

    # Inline worker mode: events are already normalized.
    rows = db.query(TelemetryEvent).filter(TelemetryEvent.organization_id == org.id).all()
    assert {e.event_id for e in rows} == {"hp-1", "hp-2"}
    db.close()


def test_bare_list_body_accepted():
    db = SessionLocal()
    org, _user, token = _make_org_and_token(db)
    r = _client.post("/api/v1/telemetry/batch", json=[_ev("bare-1")],
                     headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 202
    assert r.json()["accepted"] == 1
    db.close()


def test_partial_acceptance_with_event_errors():
    db = SessionLocal()
    org, _user, token = _make_org_and_token(db)
    events = [
        _ev("pa-1"),
        {"agent_id": "no-event-id"},                       # missing event_id
        {"event_id": "pa-3"},                              # missing agent_id — ACCEPTED (fallback identity)
        _ev("pa-4", input_tokens=-5),                      # negative tokens
        "not-an-object",                                   # not a dict
        _ev("pa-6"),
    ]
    r = _client.post("/api/v1/telemetry/batch", json={"events": events},
                     headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 202
    body = r.json()
    # agent_id is optional under auto-instrumentation-first: pa-3 resolves
    # through the identity ladder instead of failing.
    assert body["accepted"] == 3          # pa-1, pa-3, pa-6
    assert body["failed"] == 3
    assert len(body["errors"]) == 3
    error_indexes = {e["index"] for e in body["errors"]}
    assert error_indexes == {1, 3, 4}
    # event_id echoed back when available
    by_index = {e["index"]: e for e in body["errors"]}
    assert by_index[3]["event_id"] == "pa-4"
    db.close()


def test_batch_size_limit():
    db = SessionLocal()
    _org, _user, token = _make_org_and_token(db)
    events = [_ev(f"big-{i}") for i in range(MAX_BATCH_EVENTS + 1)]
    r = _client.post("/api/v1/telemetry/batch", json={"events": events},
                     headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 413
    db.close()


def test_unauthenticated_rejected():
    r = _client.post("/api/v1/telemetry/batch", json={"events": [_ev("noauth-1")]})
    assert r.status_code == 401


def test_raw_payload_preserved_verbatim():
    db = SessionLocal()
    org, _user, token = _make_org_and_token(db)
    event = _ev(
        "raw-1", model="gpt-4o",
        custom_field={"nested": [1, 2, {"deep": "value"}]},
        another_extra="untouched ✓",
    )
    r = _client.post("/api/v1/telemetry/batch", json={"events": [event]},
                     headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 202 and r.json()["accepted"] == 1

    raw_row = db.query(TelemetryEventRaw).filter(
        TelemetryEventRaw.organization_id == org.id,
        TelemetryEventRaw.event_id == "raw-1",
    ).first()
    assert raw_row is not None
    assert json.loads(raw_row.raw_payload) == event  # verbatim, extras included
    assert raw_row.status == "processed"
    db.close()


def test_api_key_auth_and_attribution():
    db = SessionLocal()
    org, user, _token = _make_org_and_token(db)
    raw_key, prefix, key_hash = generate_api_key()
    key = ApiKey(name="ingest-key", key_prefix=prefix, key_hash=key_hash,
                 team="eng", purpose="otel", organization_id=org.id,
                 created_by_id=user.id, is_active=True)
    db.add(key)
    db.commit()
    db.refresh(key)

    r = _client.post("/api/v1/telemetry/batch", json={"events": [_ev("key-1")]},
                     headers={"Authorization": f"Bearer {raw_key}"})
    assert r.status_code == 202, r.text
    assert r.json()["accepted"] == 1

    raw_row = db.query(TelemetryEventRaw).filter(
        TelemetryEventRaw.organization_id == org.id,
        TelemetryEventRaw.event_id == "key-1",
    ).first()
    assert raw_row.api_key_id == key.id
    norm = db.query(TelemetryEvent).filter(
        TelemetryEvent.organization_id == org.id,
        TelemetryEvent.event_id == "key-1",
    ).first()
    assert norm is not None and norm.api_key_id == key.id
    db.close()


# ── Tiered fallback identity (agent_id optional) ──────────────────────────────

def _post(token, events):
    return _client.post("/api/v1/telemetry/batch", json={"events": events},
                        headers={"Authorization": f"Bearer {token}"})


def _norm_event(db, org, event_id):
    return db.query(TelemetryEvent).filter(
        TelemetryEvent.organization_id == org.id,
        TelemetryEvent.event_id == event_id).first()


def _registry_row(db, org, agent_id_raw):
    from app.models import AssetRegistry
    return db.query(AssetRegistry).filter(
        AssetRegistry.organization_id == org.id,
        AssetRegistry.agent_id_raw == agent_id_raw).first()


def test_agent_name_only_resolves_declared_identity():
    db = SessionLocal()
    org, _user, token = _make_org_and_token(db)
    r = _post(token, [{"event_id": "tier-name-1", "agent_name": "named-agent",
                       "model": "gpt-4o", "status": "ok"}])
    assert r.status_code == 202 and r.json()["accepted"] == 1
    e = _norm_event(db, org, "tier-name-1")
    assert e is not None and e.agent_id == "named-agent"
    reg = _registry_row(db, org, "named-agent")
    assert reg is not None
    assert reg.asset_key == e.asset_key
    assert reg.confidence_score == 75.0        # declared tier — full confidence
    db.close()


def test_identity_less_event_gets_fallback_fingerprint():
    db = SessionLocal()
    org, _user, token = _make_org_and_token(db)
    r = _post(token, [{"event_id": "tier-fb-1", "team": "finance",
                       "environment": "production", "model": "gpt-4o"}])
    assert r.status_code == 202 and r.json()["accepted"] == 1
    e = _norm_event(db, org, "tier-fb-1")
    assert e is not None
    assert e.agent_id.startswith("observed-ai-system:")
    assert e.asset_key and len(e.asset_key) == 64
    reg = _registry_row(db, org, e.agent_id)
    assert reg is not None
    assert reg.confidence_score == 30.0        # fallback tier — low internal scoring
    ev = json.loads(reg.evidence or "{}")
    assert ev.get("needs_admin_review") is True
    db.close()


def test_identity_less_events_converge_to_one_asset():
    db = SessionLocal()
    org, _user, token = _make_org_and_token(db)
    base = {"team": "billing", "environment": "staging", "model": "gpt-4o"}
    _post(token, [{"event_id": "conv-1", **base}])
    _post(token, [{"event_id": "conv-2", **base}])
    e1 = _norm_event(db, org, "conv-1")
    e2 = _norm_event(db, org, "conv-2")
    assert e1.agent_id == e2.agent_id and e1.asset_key == e2.asset_key
    db.close()


def test_forbidden_content_never_affects_fallback_identity():
    # Privacy rule: prompts/URLs/credential-like extras are excluded from the
    # fingerprint — two events differing ONLY in such fields must converge.
    db = SessionLocal()
    org, _user, token = _make_org_and_token(db)
    base = {"team": "support", "environment": "production"}
    _post(token, [{"event_id": "priv-1", **base,
                   "prompt": "SECRET-USER-TEXT-1", "session_url": "https://x.example/q?token=abc"}])
    _post(token, [{"event_id": "priv-2", **base,
                   "prompt": "COMPLETELY-DIFFERENT-TEXT-2"}])
    e1 = _norm_event(db, org, "priv-1")
    e2 = _norm_event(db, org, "priv-2")
    assert e1.agent_id == e2.agent_id            # content never entered the hash
    db.close()


def test_explicit_agent_id_invariance():
    # Callers who send agent_id keep the exact same identity as before:
    # asset_key = sha256(f"{org}:{agent_id}")[:64], declared tier, confidence 75.
    import hashlib
    db = SessionLocal()
    org, _user, token = _make_org_and_token(db)
    _post(token, [_ev("inv-1", agent_id="stable-agent")])
    e = _norm_event(db, org, "inv-1")
    assert e.agent_id == "stable-agent"
    assert e.asset_key == hashlib.sha256(f"{org.id}:stable-agent".encode()).hexdigest()[:64]
    reg = _registry_row(db, org, "stable-agent")
    assert reg is not None and reg.confidence_score == 75.0
    db.close()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
