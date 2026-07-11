"""
Per-key attribution: OTLP spans ingested with a gk- API key record that key's
id, and GET /api-keys/{id}/agents surfaces the distinct service.name values seen
on that key. Dashboard/JWT ingestion attributes nothing (api_key_id stays NULL).

ENV vars are set before any app import — do not reorder the top block.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

_db_path = f"/tmp/test_apikey_attr_{uuid.uuid4().hex[:8]}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ.setdefault("JWT_SECRET", "testsecret-apikey-attr")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.chdir(str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Organization, User, ApiKey, OtelSpan
from app.auth import hash_password, create_token, generate_api_key

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")

_db = SessionLocal()
_org = Organization(name="AttrOrg", slug=f"attr-{uuid.uuid4().hex[:6]}")
_db.add(_org)
_db.commit()
_db.refresh(_org)
ORG_ID = _org.id

_admin = User(email="attr-admin@test.local", name="Attr Admin",
              hashed_password=hash_password("x"), role="admin",
              team="platform", organization_id=ORG_ID)
_db.add(_admin)
_db.commit()
_db.refresh(_admin)
ADMIN_H = {"Authorization": f"Bearer {create_token(_admin)}"}

# A collector-style ingestion key.
_raw_key, _prefix, _hash = generate_api_key()
_key = ApiKey(name="prod-otel-collector", key_prefix=_prefix, key_hash=_hash,
              team="platform", organization_id=ORG_ID, created_by_id=_admin.id)
_db.add(_key)
_db.commit()
_db.refresh(_key)
KEY_ID = _key.id
KEY_H = {"Authorization": f"Bearer {_raw_key}", "Content-Type": "application/json"}
_db.close()


def _otlp_body(service: str, trace_id: str):
    return {
        "resourceSpans": [{
            "resource": {"attributes": [
                {"key": "service.name", "value": {"stringValue": service}},
            ]},
            "scopeSpans": [{"spans": [{
                "traceId": trace_id, "spanId": uuid.uuid4().hex[:16],
                "name": "chat", "kind": 3,
                "startTimeUnixNano": "1700000000000000000",
                "endTimeUnixNano": "1700000001000000000",
                "status": {},
                "attributes": [
                    {"key": "gen_ai.operation.name", "value": {"stringValue": "chat"}},
                ],
            }]}],
        }],
    }


def test_ingested_span_records_the_api_key_id():
    trace_id = uuid.uuid4().hex
    r = _client.post("/otel/v1/traces", json=_otlp_body("collector-svc-a", trace_id), headers=KEY_H)
    assert r.status_code == 202, r.text

    db = SessionLocal()
    try:
        span = db.query(OtelSpan).filter(
            OtelSpan.organization_id == ORG_ID, OtelSpan.trace_id == trace_id
        ).first()
        assert span is not None
        assert span.api_key_id == KEY_ID
    finally:
        db.close()


def test_jwt_ingestion_leaves_api_key_id_null():
    trace_id = uuid.uuid4().hex
    r = _client.post("/otel/v1/traces", json=_otlp_body("jwt-svc", trace_id),
                     headers={**ADMIN_H, "Content-Type": "application/json"})
    assert r.status_code == 202, r.text

    db = SessionLocal()
    try:
        span = db.query(OtelSpan).filter(
            OtelSpan.organization_id == ORG_ID, OtelSpan.trace_id == trace_id
        ).first()
        assert span is not None
        assert span.api_key_id is None
    finally:
        db.close()


def test_agents_endpoint_lists_services_seen_on_the_key():
    # Two different agents flow through the same collector key.
    for svc in ("agents-endpoint-x", "agents-endpoint-y", "agents-endpoint-x"):
        r = _client.post("/otel/v1/traces", json=_otlp_body(svc, uuid.uuid4().hex), headers=KEY_H)
        assert r.status_code == 202, r.text

    r = _client.get(f"/api-keys/{KEY_ID}/agents", headers=ADMIN_H)
    assert r.status_code == 200, r.text
    body = r.json()
    names = {a["service_name"] for a in body["agents"]}
    assert {"agents-endpoint-x", "agents-endpoint-y"}.issubset(names)
    # x was ingested twice → span_count >= 2
    x = next(a for a in body["agents"] if a["service_name"] == "agents-endpoint-x")
    assert x["span_count"] >= 2
    assert x["last_seen"] is not None


def test_agents_endpoint_404_for_foreign_key():
    r = _client.get("/api-keys/999999/agents", headers=ADMIN_H)
    assert r.status_code == 404


def test_create_key_defaults_to_otel_purpose():
    r = _client.post("/api-keys", json={"name": "default-purpose-key", "team": "t"}, headers=ADMIN_H)
    assert r.status_code == 201, r.text
    assert r.json()["purpose"] == "otel"


def test_create_gateway_key_records_purpose_and_lists_it():
    r = _client.post("/api-keys", json={"name": "gw-key", "team": "t", "purpose": "gateway"}, headers=ADMIN_H)
    assert r.status_code == 201, r.text
    assert r.json()["purpose"] == "gateway"
    # It shows up in the list with its purpose so the UI can split the two tables.
    listed = _client.get("/api-keys", headers=ADMIN_H).json()
    gw = next(k for k in listed if k["name"] == "gw-key")
    assert gw["purpose"] == "gateway"


def test_create_key_rejects_unknown_purpose():
    r = _client.post("/api-keys", json={"name": "bad", "team": "t", "purpose": "nonsense"}, headers=ADMIN_H)
    assert r.status_code == 422


if __name__ == "__main__":
    test_ingested_span_records_the_api_key_id()
    test_jwt_ingestion_leaves_api_key_id_null()
    test_agents_endpoint_lists_services_seen_on_the_key()
    test_agents_endpoint_404_for_foreign_key()
    test_create_key_defaults_to_otel_purpose()
    test_create_gateway_key_records_purpose_and_lists_it()
    test_create_key_rejects_unknown_purpose()
    print("test_api_key_attribution: OK")
