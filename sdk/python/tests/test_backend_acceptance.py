"""Backend acceptance: an SDK-built payload is accepted by the real POST /runtime-events.

Boots the actual FastAPI app (same per-file bootstrap pattern as
tests/test_runtime_events.py) and posts an event built by observeagents.events —
proving the SDK payload shape flows through validation, the span-like adapter, and
normalize_spans without any backend change.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

_here = Path(__file__).resolve()
_repo_root = str(_here.parent.parent.parent.parent)   # sdk/python/tests/x.py → repo root
_sdk_root = str(_here.parent.parent)

_db_path = f"/tmp/test_sdk_acceptance_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-sdk-acceptance")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

for p in (_repo_root, _sdk_root):
    if p not in sys.path:
        sys.path.insert(0, p)
os.chdir(_repo_root)

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Organization, User, OtelSpan
from app.auth import hash_password, create_token

from observeagents.events import build_llm_call_event

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")


def _org_token(db):
    sfx = uuid.uuid4().hex[:6]
    org = Organization(name=f"sdk-org-{sfx}", slug=f"sdk-{sfx}")
    db.add(org)
    db.flush()
    user = User(email=f"sdk-{sfx}@example.com", name=f"SDK {sfx}",
                hashed_password=hash_password("pass"), organization_id=org.id,
                role="admin", team="eng", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(org)
    db.refresh(user)
    return org, create_token(user)


def test_sdk_payload_accepted_by_real_runtime_events_endpoint():
    db = SessionLocal()
    try:
        org, token = _org_token(db)
        event = build_llm_call_event(
            agent_name="sdk-acceptance-agent",
            model="gpt-4.1-mini",
            duration_ms=850.0,
            status="ok",
            input_tokens=1200,
            output_tokens=300,
            environment="production",
            team_hint="support",
            session_id="sess-sdk-1",
        )
        r = _client.post("/runtime-events", json={"events": [event]},
                         headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["accepted"] is True and body["events"] == 1 and body["spans"] == 1

        # Evidence landed through the normalize_spans path.
        spans = db.query(OtelSpan).filter(OtelSpan.organization_id == org.id).all()
        assert len(spans) == 1
        assert spans[0].trace_id == event["trace_id"]
    finally:
        db.close()


def test_sdk_error_payload_accepted():
    db = SessionLocal()
    try:
        _org, token = _org_token(db)
        event = build_llm_call_event(
            agent_name="sdk-acceptance-agent",
            model="gpt-4.1-mini",
            duration_ms=120.0,
            status="error",
            error_type="RateLimitError",
        )
        r = _client.post("/runtime-events", json={"events": [event]},
                         headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 202, r.text
    finally:
        db.close()
