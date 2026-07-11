"""
Deleting a tenant organization must remove ALL of its data — including the
runtime tables (otel_spans) and credentials (api_keys) the original cascade
missed — never silently orphaning a tenant's telemetry.

ENV vars are set before any app import — do not reorder the top block.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

_db_path = f"/tmp/test_delorg_{uuid.uuid4().hex[:8]}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ.setdefault("JWT_SECRET", "testsecret-delorg")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.chdir(str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Organization, User, ApiKey, OtelSpan, Telemetry
from app.auth import hash_password, create_token, generate_api_key

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")

_db = SessionLocal()

# Platform admin (can delete tenant orgs).
_platform = _db.query(Organization).filter(Organization.is_internal == True).first()  # noqa: E712
if _platform is None:
    _platform = Organization(name="Platform", slug=f"platform-{uuid.uuid4().hex[:6]}", is_internal=True)
    _db.add(_platform); _db.commit(); _db.refresh(_platform)
_padmin = User(email=f"padmin-{uuid.uuid4().hex[:6]}@test.local", name="P Admin",
               hashed_password=hash_password("x"), role="admin", team="platform",
               organization_id=_platform.id, is_platform_admin=True)
_db.add(_padmin); _db.commit(); _db.refresh(_padmin)
PADMIN_H = {"Authorization": f"Bearer {create_token(_padmin)}"}

# Tenant org with data in a table the OLD cascade covered (telemetry) AND two it
# missed (otel_spans, api_keys).
_tenant = Organization(name="DoomedTenant", slug=f"doomed-{uuid.uuid4().hex[:6]}")
_db.add(_tenant); _db.commit(); _db.refresh(_tenant)
TENANT_ID = _tenant.id

_db.add(Telemetry(organization_id=TENANT_ID, team="t", agent="a", model="gpt-4o",
                  prompt="p", response="r", prompt_tokens=1, completion_tokens=1, total_tokens=2,
                  latency_ms=1.0, cost_usd=0.0, pricing_estimated=False, sensitive=False,
                  blocked=False, timestamp=datetime.now(timezone.utc)))
_db.add(OtelSpan(organization_id=TENANT_ID, trace_id=uuid.uuid4().hex,
                 span_id=uuid.uuid4().hex[:16], span_name="agent.workflow"))
_raw, _pfx, _hash = generate_api_key()
_db.add(ApiKey(organization_id=TENANT_ID, name="doomed-key", key_prefix=_pfx,
               key_hash=_hash, team="t", created_by_id=_padmin.id))
_db.commit()
_db.close()


def _counts(org_id):
    db = SessionLocal()
    try:
        return {
            "telemetry": db.query(Telemetry).filter(Telemetry.organization_id == org_id).count(),
            "otel_spans": db.query(OtelSpan).filter(OtelSpan.organization_id == org_id).count(),
            "api_keys": db.query(ApiKey).filter(ApiKey.organization_id == org_id).count(),
            "org": db.query(Organization).filter(Organization.id == org_id).count(),
        }
    finally:
        db.close()


def test_seed_is_present_before_delete():
    c = _counts(TENANT_ID)
    assert c["telemetry"] == 1 and c["otel_spans"] == 1 and c["api_keys"] == 1 and c["org"] == 1


def test_delete_org_removes_all_scoped_tables():
    r = _client.delete(f"/admin/organizations/{TENANT_ID}", headers=PADMIN_H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted"] is True
    # The previously-missed tables must appear in the deletion summary.
    assert body["rows_deleted"].get("otel_spans") == 1
    assert body["rows_deleted"].get("api_keys") == 1

    c = _counts(TENANT_ID)
    assert c == {"telemetry": 0, "otel_spans": 0, "api_keys": 0, "org": 0}, c


def test_internal_org_cannot_be_deleted():
    r = _client.delete(f"/admin/organizations/{_platform.id}", headers=PADMIN_H)
    assert r.status_code == 403


if __name__ == "__main__":
    test_seed_is_present_before_delete()
    test_delete_org_removes_all_scoped_tables()
    test_internal_org_cannot_be_deleted()
    print("test_delete_org_cascade: OK")
