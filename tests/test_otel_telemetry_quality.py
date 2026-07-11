"""
Integration tests for real-world (imperfect) OTLP telemetry handling:

  1. Perfect SemConv span → stored fully_classified / high on OtelSpan + OtelAsset.
  2. service.name-only span → partially_classified, missing=[environment].
  3. No service.name at all → ONE stable observed-ai-system asset (converges
     across batches and volatile resource attrs), evidence.needs_admin_review,
     NEEDS_REVIEW discovery stage, low registry confidence.
  4. Fallback span in a trace whose sibling carries service.name inherits the
     service identity instead of a hash.
  5. MCP rpc.method=tools/call without mcp.server.name → detected as MCP,
     low confidence, missing mcp_server.
  6. Raw spans are stored even when unclassified.
"""
from __future__ import annotations

import json
import os
import sys
import uuid

# ── Env setup BEFORE any app import ───────────────────────────────────────────
_db_path = f"/tmp/test_otel_quality_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-otel-quality")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Organization, User, OtelSpan, AssetRegistry, OtelAsset
from app.auth import hash_password, create_token
from app.discovery_status import derive_discovery_status

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")  # trigger startup + migrations


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_org_and_token(db, suffix=""):
    sfx = suffix or uuid.uuid4().hex[:6]
    org = Organization(name=f"otelq-org-{sfx}", slug=f"otelq-{sfx}")
    db.add(org)
    db.flush()
    user = User(
        email=f"otelq-{sfx}@example.com",
        name=f"OTel Quality {sfx}",
        hashed_password=hash_password("pass"),
        organization_id=org.id,
        role="admin",
        team="eng",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(org)
    db.refresh(user)
    return org, user, create_token(user)


def _otlp_attr_value(v):
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": v}
    if isinstance(v, float):
        return {"doubleValue": v}
    return {"stringValue": str(v)}


def _span(trace_id, span_id, name, attrs=None, parent_span_id=None):
    span = {
        "traceId": trace_id,
        "spanId": span_id,
        "name": name,
        "kind": 3,
        "startTimeUnixNano": 1_700_000_000_000_000_000,
        "endTimeUnixNano": 1_700_000_001_000_000_000,
        "status": {},
        "attributes": [
            {"key": k, "value": _otlp_attr_value(v)} for k, v in (attrs or {}).items()
        ],
    }
    if parent_span_id:
        span["parentSpanId"] = parent_span_id
    return span


def _payload(spans, resource_attrs=None):
    return {
        "resourceSpans": [{
            "resource": {"attributes": [
                {"key": k, "value": _otlp_attr_value(v)}
                for k, v in (resource_attrs or {}).items()
            ]},
            "scopeSpans": [{"spans": spans}],
        }]
    }


def _post(token, payload):
    return _client.post(
        "/otel/v1/traces", json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )


def _tid():
    return uuid.uuid4().hex


def _sid():
    return uuid.uuid4().hex[:16]


# ── 1. Perfect span → fully classified, high confidence ──────────────────────

def test_perfect_span_fully_classified_high():
    db = SessionLocal()
    try:
        org, _, token = _make_org_and_token(db)
        trace_id, span_id = _tid(), _sid()
        resp = _post(token, _payload(
            [_span(trace_id, span_id, "chat claude", {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": "anthropic",
                "gen_ai.request.model": "claude-sonnet-5",
                "gen_ai.usage.input_tokens": 100,
                "gen_ai.usage.output_tokens": 50,
            })],
            resource_attrs={
                "service.name": "support-agent",
                "deployment.environment": "production",
            },
        ))
        assert resp.status_code == 202

        row = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org.id, OtelSpan.trace_id == trace_id
        ).one()
        assert row.classification_status == "fully_classified"
        assert row.classification_confidence == "high"
        assert row.classification_missing is None  # NULL, not "[]"

        oa = db.query(OtelAsset).filter(
            OtelAsset.organization_id == org.id,
            OtelAsset.service_name == "support-agent",
        ).one()
        assert oa.classification_status == "fully_classified"
        assert oa.confidence_score == 100.0
        assert json.loads(oa.classification_counts_json) == {
            "full": 1, "partial": 0, "unclassified": 0}
    finally:
        db.close()


# ── 2. service.name only → partially classified, missing environment ─────────

def test_service_only_span_partial_missing_environment():
    db = SessionLocal()
    try:
        org, _, token = _make_org_and_token(db)
        trace_id = _tid()
        resp = _post(token, _payload(
            [_span(trace_id, _sid(), "chat", {
                "gen_ai.provider.name": "openai",
                "gen_ai.request.model": "gpt-4o",
            })],
            resource_attrs={"service.name": "billing-agent"},
        ))
        assert resp.status_code == 202

        row = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org.id, OtelSpan.trace_id == trace_id
        ).one()
        assert row.classification_status == "partially_classified"
        assert row.classification_confidence == "medium"
        assert json.loads(row.classification_missing) == ["environment"]

        oa = db.query(OtelAsset).filter(
            OtelAsset.organization_id == org.id,
            OtelAsset.service_name == "billing-agent",
        ).one()
        assert oa.classification_status == "partially_classified"
        assert oa.confidence_score == 60.0
    finally:
        db.close()


# ── 3. No service.name → stable converged fallback + needs review ─────────────

def test_no_identity_converges_to_one_asset_and_needs_review():
    db = SessionLocal()
    try:
        org, _, token = _make_org_and_token(db)
        # Two batches, two traces, same stable resource attrs but different
        # volatile ones (pod name / instance id) — must converge to ONE asset.
        for pod in ("pod-a", "pod-b"):
            resp = _post(token, _payload(
                [_span(_tid(), _sid(), "GET /api", {
                    "http.url": "https://internal.example.com/api",
                })],
                resource_attrs={
                    "telemetry.sdk.language": "python",
                    "host.name": pod,
                    "k8s.pod.name": pod,
                    "cloud.region": "us-east-1",
                },
            ))
            assert resp.status_code == 202

        rows = db.query(AssetRegistry).filter(
            AssetRegistry.organization_id == org.id,
            AssetRegistry.agent_id_raw.like("observed-ai-system:%"),
        ).all()
        assert len(rows) == 1, [r.agent_id_raw for r in rows]
        row = rows[0]
        assert not row.agent_id_raw.startswith("observed-ai-system:trace-")

        evidence = json.loads(row.evidence or "{}")
        assert evidence.get("needs_admin_review") is True
        assert evidence.get("identity_confidence") == "low"
        assert row.confidence_score == 30.0

        stage, _, _ = derive_discovery_status({
            "discovery_status": row.discovery_status,
            "evidence": row.evidence,
            "owner": row.owner,
            "team": row.team,
            "confidence_score": row.confidence_score,
        })
        assert stage == "NEEDS_REVIEW"

        # Spans are still stored, marked unclassified/low.
        spans = db.query(OtelSpan).filter(OtelSpan.organization_id == org.id).all()
        assert len(spans) == 2
        for s in spans:
            assert s.classification_status == "unclassified"
            assert s.classification_confidence == "low"
            assert "identity" in json.loads(s.classification_missing)
    finally:
        db.close()


def test_no_identity_no_resource_attrs_scoped_to_trace():
    db = SessionLocal()
    try:
        org, _, token = _make_org_and_token(db)
        trace_id = _tid()
        # Two spans, SAME trace, zero resource attributes → one trace-scoped asset.
        resp = _post(token, _payload([
            _span(trace_id, _sid(), "step-1", {"http.url": "https://x.example.com"}),
            _span(trace_id, _sid(), "step-2", {"http.url": "https://y.example.com"}),
        ]))
        assert resp.status_code == 202

        rows = db.query(AssetRegistry).filter(
            AssetRegistry.organization_id == org.id,
            AssetRegistry.agent_id_raw.like("observed-ai-system:trace-%"),
        ).all()
        assert len(rows) == 1
        assert rows[0].agent_id_raw == f"observed-ai-system:trace-{trace_id[:8]}"
    finally:
        db.close()


# ── 4. Fallback span inherits sibling service identity within a trace ─────────

def test_fallback_span_inherits_service_identity_from_trace():
    db = SessionLocal()
    try:
        org, _, token = _make_org_and_token(db)
        trace_id = _tid()
        root_id = _sid()
        # Root span carries service.name in span attrs; child span has nothing.
        # (Single resourceSpans block would share resource attrs, so put the
        # identity on the span attributes of the root only.)
        resp = _post(token, _payload([
            _span(trace_id, root_id, "root", {"service.name": "orchestrator-agent"}),
            _span(trace_id, _sid(), "child-step", {"db.system": "postgresql"},
                  parent_span_id=root_id),
        ]))
        assert resp.status_code == 202

        # No fallback asset was created — the child inherited the service identity.
        fallback_rows = db.query(AssetRegistry).filter(
            AssetRegistry.organization_id == org.id,
            AssetRegistry.agent_id_raw.like("observed-ai-system:%"),
        ).all()
        assert fallback_rows == []
        named = db.query(AssetRegistry).filter(
            AssetRegistry.organization_id == org.id,
            AssetRegistry.agent_id_raw == "orchestrator-agent",
        ).one()
        assert named is not None
    finally:
        db.close()


# ── 5. MCP-shaped rpc.method without server name → detected, needs review ────

def test_mcp_method_value_without_server_low_confidence():
    db = SessionLocal()
    try:
        org, _, token = _make_org_and_token(db)
        trace_id = _tid()
        resp = _post(token, _payload(
            [_span(trace_id, _sid(), "tool call", {
                "rpc.method": "tools/call",
                "gen_ai.tool.name": "get_invoice",
            })],
            resource_attrs={
                "service.name": "finance-agent",
                "deployment.environment": "production",
            },
        ))
        assert resp.status_code == 202

        row = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org.id, OtelSpan.trace_id == trace_id
        ).one()
        assert row.classification_status == "partially_classified"
        assert row.classification_confidence == "low"
        assert "mcp_server" in json.loads(row.classification_missing)

        # MCP activity itself was recognised → tool relationship classified as MCP-adjacent
        oa = db.query(OtelAsset).filter(
            OtelAsset.organization_id == org.id,
            OtelAsset.service_name == "finance-agent",
        ).one()
        assert "get_invoice" in json.loads(oa.tools_json or "[]")
    finally:
        db.close()


# ── 6. Custom (unmapped) model key → stored, candidate key surfaced ───────────

def test_custom_model_key_stored_and_candidate_recorded():
    db = SessionLocal()
    try:
        org, _, token = _make_org_and_token(db)
        trace_id = _tid()
        resp = _post(token, _payload(
            [_span(trace_id, _sid(), "llm call", {
                "gen_ai.operation.name": "chat",
                "mycompany.llm.model": "acme-v1",
            })],
            resource_attrs={
                "service.name": "acme-agent",
                "deployment.environment": "staging",
            },
        ))
        assert resp.status_code == 202

        row = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org.id, OtelSpan.trace_id == trace_id
        ).one()
        # Raw span stored; custom key NOT promoted to the model column…
        assert row.gen_ai_request_model is None
        assert row.classification_status == "partially_classified"
        missing = json.loads(row.classification_missing)
        assert "genai_model" in missing
        # …but surfaced as a mapping candidate on the asset.
        oa = db.query(OtelAsset).filter(
            OtelAsset.organization_id == org.id,
            OtelAsset.service_name == "acme-agent",
        ).one()
        assert "mycompany.llm.model" in json.loads(oa.candidate_attr_keys_json or "[]")
    finally:
        db.close()
