"""
Tests for Detection Rules webhook notifications (app/notifications.py, R5).

Backend-only. Webhook channels are admin-managed and Fernet-encrypted; the URL
is never exposed. Notifications fire from the intelligence run only, for open
detection_rules findings of medium+ severity, once per (org, channel, finding)
per cooldown window. Outbound HTTP is mocked — no real network calls.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from unittest.mock import patch

_db_path = f"/tmp/test_notifications_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-notifications")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Organization, User, NotificationChannel, NotificationDelivery
from app.auth import hash_password, create_token
import app.asset_discovery as _ad

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")


def _org(db, suffix="", role="admin"):
    sfx = suffix or uuid.uuid4().hex[:6]
    org = Organization(name=f"notif-org-{sfx}", slug=f"notif-{sfx}")
    db.add(org)
    db.flush()
    user = User(email=f"notif-{sfx}@example.com", name=f"Notif {sfx}",
                hashed_password=hash_password("pass"), organization_id=org.id,
                role=role, team="eng", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(org)
    db.refresh(user)
    return org, create_token(user)


def _span(trace_id, span_id, name, attrs=None, resource_attrs=None,
          start=1_700_000_000_000_000_000, end=1_700_000_001_000_000_000):
    sattrs = [{"key": k, "value": ({"intValue": v} if isinstance(v, int)
               else {"stringValue": str(v)})} for k, v in (attrs or {}).items()]
    rattrs = [{"key": k, "value": {"stringValue": str(v)}} for k, v in (resource_attrs or {}).items()]
    return {"resourceSpans": [{
        "resource": {"attributes": rattrs},
        "scopeSpans": [{"spans": [{
            "traceId": trace_id, "spanId": span_id, "name": name, "kind": 3,
            "startTimeUnixNano": start, "endTimeUnixNano": end,
            "status": {}, "attributes": sattrs,
        }]}],
    }]}


def _post_otel(token, payload):
    return _client.post("/otel/v1/traces", json=payload, headers={"Authorization": f"Bearer {token}"})


def _run(token):
    return _client.post("/intelligence/run", headers={"Authorization": f"Bearer {token}"})


def _seed_mcp_burst(token, service="web-research-agent", count=6, env="production"):
    trace = uuid.uuid4().hex
    for i in range(count):
        assert _post_otel(token, _span(trace, uuid.uuid4().hex[:16], f"mcp-{i}",
            attrs={"mcp.method.name": "tools/call", "gen_ai.tool.name": "search_web"},
            resource_attrs={"service.name": service, "deployment.environment": env})).status_code == 202


class _FakeResp:
    def __init__(self, status_code=200):
        self.status_code = status_code


def _mock_post_ok():
    calls = []
    def _fake(url, **kwargs):
        calls.append({"url": url, "json": kwargs.get("json")})
        return _FakeResp(200)
    return _fake, calls


# ── Channel admin API ─────────────────────────────────────────────────────────

def test_admin_can_create_webhook_channel():
    db = SessionLocal()
    try:
        org, token = _org(db, "create")
        r = _client.post("/notifications/channels",
            json={"type": "webhook", "name": "Eng webhook", "url": "https://example.com/hook?token=SECRET123"},
            headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["type"] == "webhook" and body["name"] == "Eng webhook"
        assert body["enabled"] is True
        assert body["host"] == "example.com"
    finally:
        db.close()


def test_non_admin_cannot_create_channel():
    db = SessionLocal()
    try:
        org, token = _org(db, "viewer", role="viewer")
        r = _client.post("/notifications/channels",
            json={"type": "webhook", "name": "x", "url": "https://example.com/hook"},
            headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403, r.text
    finally:
        db.close()


def test_channel_response_never_exposes_url_or_secret():
    db = SessionLocal()
    try:
        org, token = _org(db, "secret")
        url = "https://example.com/webhooks/deep/path?token=SUPERSECRET&x=1"
        r = _client.post("/notifications/channels",
            json={"type": "webhook", "name": "s", "url": url},
            headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 201
        blob = json.dumps(r.json())
        assert "SUPERSECRET" not in blob and "token=" not in blob
        assert "/webhooks/deep/path" not in blob
        # List endpoint is equally safe.
        lst = _client.get("/notifications/channels", headers={"Authorization": f"Bearer {token}"})
        assert "SUPERSECRET" not in lst.text and "/webhooks/deep/path" not in lst.text
        # And the ciphertext is never returned either.
        assert "encrypted_config_json" not in blob
    finally:
        db.close()


# ── Delivery from the intelligence run ────────────────────────────────────────

def test_detection_rule_finding_sends_one_webhook():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "send")
        _client.post("/notifications/channels",
            json={"type": "webhook", "name": "w", "url": "https://hook.example.com/x"},
            headers={"Authorization": f"Bearer {token}"})
        _seed_mcp_burst(token)
        fake, calls = _mock_post_ok()
        with patch("app.notifications.httpx.post", side_effect=fake):
            assert _run(token).status_code == 200
        assert len(calls) == 1
        rows = db.query(NotificationDelivery).filter(NotificationDelivery.organization_id == org.id).all()
        assert len(rows) == 1 and rows[0].status == "delivered"
        assert rows[0].response_status == 200
    finally:
        db.close()


def test_second_run_in_cooldown_does_not_resend():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "cooldown")
        _client.post("/notifications/channels",
            json={"type": "webhook", "name": "w", "url": "https://hook.example.com/x"},
            headers={"Authorization": f"Bearer {token}"})
        _seed_mcp_burst(token)
        fake, calls = _mock_post_ok()
        with patch("app.notifications.httpx.post", side_effect=fake):
            assert _run(token).status_code == 200
            assert _run(token).status_code == 200  # second run, within cooldown
        assert len(calls) == 1, "cooldown must suppress the second webhook"
        delivered = db.query(NotificationDelivery).filter(
            NotificationDelivery.organization_id == org.id,
            NotificationDelivery.status == "delivered").count()
        skipped = db.query(NotificationDelivery).filter(
            NotificationDelivery.organization_id == org.id,
            NotificationDelivery.status == "skipped_cooldown").count()
        assert delivered == 1 and skipped == 1
    finally:
        db.close()


def test_failed_webhook_does_not_fail_intelligence_run():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "fail")
        _client.post("/notifications/channels",
            json={"type": "webhook", "name": "w", "url": "https://hook.example.com/x"},
            headers={"Authorization": f"Bearer {token}"})
        _seed_mcp_burst(token)
        def _boom(url, **kwargs):
            raise RuntimeError("connection refused")
        with patch("app.notifications.httpx.post", side_effect=_boom):
            r = _run(token)
        assert r.status_code == 200, "intelligence run must survive a webhook failure"
        rows = db.query(NotificationDelivery).filter(NotificationDelivery.organization_id == org.id).all()
        assert len(rows) == 1 and rows[0].status == "failed"
        assert rows[0].response_status is None
        # error records the exception class only — never the URL.
        assert rows[0].last_error == "RuntimeError"
    finally:
        db.close()


def test_payload_includes_safe_metadata_and_excludes_raw_content():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "payload")
        _client.post("/notifications/channels",
            json={"type": "webhook", "name": "w", "url": "https://hook.example.com/x"},
            headers={"Authorization": f"Bearer {token}"})
        # Seed with content-bearing attributes that must never reach the payload.
        trace = uuid.uuid4().hex
        secrets = ("SECRET-PROMPT", "SECRET-RESPONSE", "SECRET-ARG", "SECRET-RESULT", "sk-SECRETKEY")
        for i in range(6):
            assert _post_otel(token, _span(trace, uuid.uuid4().hex[:16], f"mcp-{i}", attrs={
                "mcp.method.name": "tools/call", "gen_ai.tool.name": "search_web",
                "gen_ai.input.messages": secrets[0], "gen_ai.output.messages": secrets[1],
                "gen_ai.tool.call.arguments": secrets[2], "gen_ai.tool.call.result": secrets[3],
                "url.full": f"https://api.vendor.com/v1?apikey={secrets[4]}",
            }, resource_attrs={"service.name": "payload-agent", "deployment.environment": "production"})).status_code == 202
        fake, calls = _mock_post_ok()
        with patch("app.notifications.httpx.post", side_effect=fake):
            assert _run(token).status_code == 200
        assert len(calls) == 1
        payload = calls[0]["json"]
        # Safe metadata present.
        assert payload["event_type"] == "detection_rule_alert"
        assert payload["source"] == "detection_rules"
        assert payload["finding_type"] == "rule_mcp_tool_access_threshold"
        assert payload["severity"] == "high"
        assert payload["agent_name"] == "payload-agent"
        assert payload["evidence"]["span_count"] == 6
        assert "tools/call" in payload["evidence"]["mcp_methods"]
        assert payload["links"]["security_intelligence"].endswith("#security_intel")
        # No raw content anywhere in the payload.
        blob = json.dumps(payload)
        for secret in secrets:
            assert secret not in blob
        assert "apikey=" not in blob and "gen_ai.input.messages" not in blob
    finally:
        db.close()


def test_otlp_ingestion_alone_sends_nothing():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "ingest")
        _client.post("/notifications/channels",
            json={"type": "webhook", "name": "w", "url": "https://hook.example.com/x"},
            headers={"Authorization": f"Bearer {token}"})
        fake, calls = _mock_post_ok()
        with patch("app.notifications.httpx.post", side_effect=fake):
            _seed_mcp_burst(token)  # ingestion only, no intelligence run
        assert len(calls) == 0
        assert db.query(NotificationDelivery).filter(NotificationDelivery.organization_id == org.id).count() == 0
        # The ingestion route must not import the notifier.
        import app.routes.otel as otel_route
        assert "notifications" not in open(otel_route.__file__).read()
    finally:
        db.close()


def test_disabled_channel_receives_nothing():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "disabled")
        created = _client.post("/notifications/channels",
            json={"type": "webhook", "name": "w", "url": "https://hook.example.com/x"},
            headers={"Authorization": f"Bearer {token}"}).json()
        # Disable it.
        r = _client.patch(f"/notifications/channels/{created['id']}",
            json={"enabled": False}, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200 and r.json()["enabled"] is False
        _seed_mcp_burst(token)
        fake, calls = _mock_post_ok()
        with patch("app.notifications.httpx.post", side_effect=fake):
            assert _run(token).status_code == 200
        assert len(calls) == 0
        assert db.query(NotificationDelivery).filter(NotificationDelivery.organization_id == org.id).count() == 0
    finally:
        db.close()


def test_only_detection_rules_findings_are_eligible():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "onlydr")
        _client.post("/notifications/channels",
            json={"type": "webhook", "name": "w", "url": "https://hook.example.com/x"},
            headers={"Authorization": f"Bearer {token}"})
        # Seed a database-access agent: produces runtime_security + otel_trace
        # findings but NOT a detection_rules finding.
        assert _post_otel(token, _span(uuid.uuid4().hex, uuid.uuid4().hex[:16], "query",
            attrs={"db.system": "postgresql", "db.name": "billing"},
            resource_attrs={"service.name": "db-only-agent", "deployment.environment": "production"})).status_code == 202
        fake, calls = _mock_post_ok()
        with patch("app.notifications.httpx.post", side_effect=fake):
            assert _run(token).status_code == 200
        # No detection_rules finding fired, so no webhook — even though high-sev
        # security findings exist.
        assert len(calls) == 0
    finally:
        db.close()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
    print("all notification tests passed")
