"""
Org-level OTel attribute mapping tests.

Covers validation, the settings endpoints (admin-only writes, allowlist
enforcement, generic-config-PUT guard), and the end-to-end ingestion effect:
a custom model key is invisible before mapping, populates the canonical
column after mapping, is classified at mapped/medium confidence, and never
overrides native SemConv emission.
"""
from __future__ import annotations

import json
import os
import sys
import uuid

# ── Env setup BEFORE any app import ───────────────────────────────────────────
_db_path = f"/tmp/test_otel_attr_map_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-otel-attr-map")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Organization, User, OtelSpan
from app.auth import hash_password, create_token
from app.otel_attribute_mapping import (
    ALLOWED_TARGETS,
    MAX_ENTRIES,
    apply_attribute_mapping,
    validate_attribute_mapping,
)

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_org(db, suffix=""):
    sfx = suffix or uuid.uuid4().hex[:6]
    org = Organization(name=f"map-org-{sfx}", slug=f"map-{sfx}")
    db.add(org)
    db.flush()
    admin = User(
        email=f"map-admin-{sfx}@example.com", name="Map Admin",
        hashed_password=hash_password("pass"), organization_id=org.id,
        role="admin", team="eng", is_active=True,
    )
    viewer = User(
        email=f"map-viewer-{sfx}@example.com", name="Map Viewer",
        hashed_password=hash_password("pass"), organization_id=org.id,
        role="viewer", team="eng", is_active=True,
    )
    db.add_all([admin, viewer])
    db.commit()
    for u in (org, admin, viewer):
        db.refresh(u)
    return org, create_token(admin), create_token(viewer)


def _otlp_attr_value(v):
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": v}
    if isinstance(v, float):
        return {"doubleValue": v}
    return {"stringValue": str(v)}


def _payload(trace_id, span_id, attrs, resource_attrs=None):
    return {
        "resourceSpans": [{
            "resource": {"attributes": [
                {"key": k, "value": _otlp_attr_value(v)}
                for k, v in (resource_attrs or {}).items()
            ]},
            "scopeSpans": [{"spans": [{
                "traceId": trace_id,
                "spanId": span_id,
                "name": "llm call",
                "kind": 3,
                "startTimeUnixNano": 1_700_000_000_000_000_000,
                "endTimeUnixNano": 1_700_000_001_000_000_000,
                "status": {},
                "attributes": [
                    {"key": k, "value": _otlp_attr_value(v)} for k, v in attrs.items()
                ],
            }]}],
        }]
    }


def _post_traces(token, payload):
    return _client.post("/otel/v1/traces", json=payload,
                        headers={"Authorization": f"Bearer {token}"})


# ── Validation unit tests ─────────────────────────────────────────────────────

def test_validate_rejects_non_dict_and_oversize():
    assert validate_attribute_mapping(["not", "a", "dict"])
    assert validate_attribute_mapping("nope")
    big = {f"custom.key.{i}": "gen_ai.request.model" for i in range(MAX_ENTRIES + 1)}
    assert any("maximum" in e for e in validate_attribute_mapping(big))


def test_validate_rejects_canonical_source_keys():
    errors = validate_attribute_mapping({"gen_ai.request.model": "gen_ai.tool.name"})
    assert any("canonical" in e for e in errors)
    errors = validate_attribute_mapping({"mcp.custom": "gen_ai.tool.name"})
    assert any("canonical" in e for e in errors)
    errors = validate_attribute_mapping({"team": "owner"})  # team IS a target
    assert any("canonical" in e for e in errors)


def test_validate_rejects_unknown_targets():
    errors = validate_attribute_mapping({"my.key": "gen_ai.input.messages"})
    assert errors  # content keys are not allowed targets
    errors = validate_attribute_mapping({"my.key": "totally.made.up"})
    assert errors


def test_validate_accepts_good_mapping():
    assert validate_attribute_mapping({
        "mycompany.llm.model": "gen_ai.request.model",
        "tool_used": "gen_ai.tool.name",
        "acme.env": "deployment.environment",
    }) == []


def test_allowed_targets_contain_no_content_keys():
    for target in ALLOWED_TARGETS:
        assert "message" not in target
        assert "prompt" not in target
        assert "argument" not in target
        assert "result" not in target


def test_apply_mapping_never_overwrites_native_value():
    attrs = {"gen_ai.request.model": "native", "mycompany.llm.model": "custom"}
    mapped = apply_attribute_mapping(attrs, {}, {"mycompany.llm.model": "gen_ai.request.model"})
    assert attrs["gen_ai.request.model"] == "native"
    assert mapped == frozenset()


def test_apply_mapping_resource_level_targets_go_to_resource():
    attrs = {"acme.env": "production"}
    resource = {}
    mapped = apply_attribute_mapping(attrs, resource, {"acme.env": "deployment.environment"})
    assert resource["deployment.environment"] == "production"
    assert "deployment.environment" not in attrs
    assert mapped == frozenset({"deployment.environment"})


# ── Endpoint tests ────────────────────────────────────────────────────────────

def test_get_mapping_defaults_and_allowlist():
    db = SessionLocal()
    try:
        _, admin_token, _ = _make_org(db)
        resp = _client.get("/settings/otel-attribute-mapping",
                           headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["mapping"] == {}
        assert "gen_ai.request.model" in body["allowed_targets"]
        assert body["max_entries"] == MAX_ENTRIES
    finally:
        db.close()


def test_put_mapping_admin_only():
    db = SessionLocal()
    try:
        _, admin_token, viewer_token = _make_org(db)
        good = {"mapping": {"mycompany.llm.model": "gen_ai.request.model"}}
        resp = _client.put("/settings/otel-attribute-mapping", json=good,
                           headers={"Authorization": f"Bearer {viewer_token}"})
        assert resp.status_code == 403
        resp = _client.put("/settings/otel-attribute-mapping", json=good,
                           headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
        resp = _client.get("/settings/otel-attribute-mapping",
                           headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.json()["mapping"] == good["mapping"]
    finally:
        db.close()


def test_put_mapping_invalid_target_400():
    db = SessionLocal()
    try:
        _, admin_token, _ = _make_org(db)
        resp = _client.put(
            "/settings/otel-attribute-mapping",
            json={"mapping": {"my.key": "gen_ai.input.messages"}},
            headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"]["type"] == "invalid_attribute_mapping"
    finally:
        db.close()


def test_generic_config_put_validates_mapping_key():
    db = SessionLocal()
    try:
        _, admin_token, _ = _make_org(db)
        resp = _client.put(
            "/settings/config/otel_attribute_mapping",
            json={"value": {"my.key": "not.a.real.target"}},
            headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 400
        # other keys stay unvalidated (existing behavior)
        resp = _client.put(
            "/settings/config/pii_redaction_mode",
            json={"value": "full"},
            headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200
    finally:
        db.close()


# ── End-to-end ingestion effect ───────────────────────────────────────────────

def test_custom_model_key_classified_after_mapping():
    db = SessionLocal()
    try:
        org, admin_token, _ = _make_org(db)
        resource = {"service.name": "acme-agent", "deployment.environment": "staging"}

        # Before mapping: custom key stored but invisible to the model column.
        t1 = uuid.uuid4().hex
        resp = _post_traces(admin_token, _payload(t1, uuid.uuid4().hex[:16], {
            "gen_ai.operation.name": "chat",
            "mycompany.llm.model": "acme-v1",
        }, resource))
        assert resp.status_code == 202
        before = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org.id, OtelSpan.trace_id == t1).one()
        assert before.gen_ai_request_model is None
        assert before.classification_status == "partially_classified"

        # Configure the mapping.
        resp = _client.put(
            "/settings/otel-attribute-mapping",
            json={"mapping": {"mycompany.llm.model": "gen_ai.request.model",
                              "mycompany.provider": "gen_ai.provider.name"}},
            headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200

        # After mapping: canonical column populated, mapped/medium classification.
        t2 = uuid.uuid4().hex
        resp = _post_traces(admin_token, _payload(t2, uuid.uuid4().hex[:16], {
            "gen_ai.operation.name": "chat",
            "mycompany.llm.model": "acme-v1",
            "mycompany.provider": "acme",
        }, resource))
        assert resp.status_code == 202
        after = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org.id, OtelSpan.trace_id == t2).one()
        assert after.gen_ai_request_model == "acme-v1"
        assert after.gen_ai_provider_name == "acme"
        assert after.classification_status == "fully_classified"
        assert after.classification_confidence == "medium"  # mapped, not native
        assert after.classification_missing is None
    finally:
        db.close()


def test_mapping_does_not_override_native_semconv_at_ingest():
    db = SessionLocal()
    try:
        org, admin_token, _ = _make_org(db)
        resp = _client.put(
            "/settings/otel-attribute-mapping",
            json={"mapping": {"mycompany.llm.model": "gen_ai.request.model"}},
            headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200

        t = uuid.uuid4().hex
        resp = _post_traces(admin_token, _payload(t, uuid.uuid4().hex[:16], {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": "native-model",
            "gen_ai.provider.name": "anthropic",
            "mycompany.llm.model": "custom-model",
        }, {"service.name": "native-agent", "deployment.environment": "production"}))
        assert resp.status_code == 202
        row = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org.id, OtelSpan.trace_id == t).one()
        assert row.gen_ai_request_model == "native-model"
        # nothing was mapped → native standard keys → high confidence
        assert row.classification_confidence == "high"
    finally:
        db.close()


def test_mapped_environment_reaches_asset_identity():
    db = SessionLocal()
    try:
        org, admin_token, _ = _make_org(db)
        resp = _client.put(
            "/settings/otel-attribute-mapping",
            json={"mapping": {"acme.env": "deployment.environment",
                              "acme.service": "service.name"}},
            headers={"Authorization": f"Bearer {admin_token}"})
        assert resp.status_code == 200

        t = uuid.uuid4().hex
        resp = _post_traces(admin_token, _payload(t, uuid.uuid4().hex[:16], {
            "db.system": "postgresql",
        }, {"acme.service": "mapped-agent", "acme.env": "production"}))
        assert resp.status_code == 202

        from app.models import OtelAsset
        oa = db.query(OtelAsset).filter(
            OtelAsset.organization_id == org.id,
            OtelAsset.service_name == "mapped-agent",
        ).one()
        assert oa.environment == "production"
        row = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org.id, OtelSpan.trace_id == t).one()
        assert row.service_name == "mapped-agent"
        assert row.classification_status == "fully_classified"
        assert row.classification_confidence == "medium"  # identity + env mapped
    finally:
        db.close()
