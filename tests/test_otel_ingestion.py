"""
Tests for OTel GenAI trace ingestion.

Covers:
  A. Simple GenAI LLM call → OtelSpan row + AssetRegistry + model relationship
  B. Agent trace with tool call → parent_span_id preserved + tool relationship
  C. Tool call with arguments → raw tool.arguments NOT stored, hash/size IS stored
  D. No content capture → raw content absent, redacted metadata present
  E. Resource attributes → service.name used for identity, env/k8s metadata stored
  F. Tenancy isolation → org A spans not visible to org B
"""
from __future__ import annotations

import json
import os
import sys
import uuid

# ── Env setup BEFORE any app import ───────────────────────────────────────────
_db_path = f"/tmp/test_otel_ingestion_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-otel-ingestion")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Organization, User, AgentRelationship, OtelSpan, ProvenanceEvent, AssetRegistry
from app.auth import hash_password, create_token
import app.asset_discovery as _ad

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")  # trigger startup + migrations


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_org_and_token(db, suffix=""):
    sfx = suffix or uuid.uuid4().hex[:6]
    org = Organization(name=f"otel-test-org-{sfx}", slug=f"otel-test-{sfx}")
    db.add(org)
    db.flush()
    user = User(
        email=f"otel-test-{sfx}@example.com",
        name=f"OTel Test {sfx}",
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
    token = create_token(user)
    return org, user, token


def _post_traces(token: str, payload: dict) -> dict:
    resp = _client.post(
        "/otel/v1/traces",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp


def _make_span(
    trace_id: str,
    span_id: str,
    name: str,
    attrs: dict | None = None,
    resource_attrs: dict | None = None,
    parent_span_id: str | None = None,
    start_nano: int = 1_700_000_000_000_000_000,
    end_nano: int   = 1_700_000_001_000_000_000,
) -> dict:
    """Build a minimal OTLP JSON payload with one span."""
    span: dict = {
        "traceId": trace_id,
        "spanId": span_id,
        "name": name,
        "kind": 3,
        "startTimeUnixNano": start_nano,
        "endTimeUnixNano": end_nano,
        "status": {},
        "attributes": [
            {"key": k, "value": {"stringValue": str(v) if not isinstance(v, (int, float)) else None,
                                  "intValue": v if isinstance(v, int) else None,
                                  "doubleValue": v if isinstance(v, float) else None,
                                  }.copy()}
            for k, v in (attrs or {}).items()
        ],
    }
    # Simplify: use stringValue for everything except explicit ints
    span["attributes"] = [
        {
            "key": k,
            "value": (
                {"intValue": v} if isinstance(v, int)
                else {"doubleValue": v} if isinstance(v, float)
                else {"stringValue": str(v)}
            ),
        }
        for k, v in (attrs or {}).items()
    ]
    if parent_span_id:
        span["parentSpanId"] = parent_span_id

    res_attrs = [
        {"key": k, "value": {"stringValue": str(v)}}
        for k, v in (resource_attrs or {}).items()
    ]
    return {
        "resourceSpans": [{
            "resource": {"attributes": res_attrs},
            "scopeSpans": [{"spans": [span]}],
        }]
    }


# ── A. Simple GenAI LLM call ──────────────────────────────────────────────────

def test_ingest_basic_llm_span():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "llm")
        trace_id = uuid.uuid4().hex
        span_id  = uuid.uuid4().hex[:16]

        payload = _make_span(
            trace_id=trace_id,
            span_id=span_id,
            name="chat",
            attrs={
                "gen_ai.system": "openai",
                "gen_ai.request.model": "gpt-4o",
                "gen_ai.usage.input_tokens": 120,
                "gen_ai.usage.output_tokens": 80,
            },
            resource_attrs={
                "service.name": "support-agent",
                "deployment.environment": "production",
            },
        )

        resp = _post_traces(token, payload)
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["accepted"] is True
        assert body["spans"] == 1
        assert body["ai_systems"] >= 1
        assert body["content_redacted"] is True

        # OtelSpan row created
        span_row = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org.id,
            OtelSpan.trace_id == trace_id,
            OtelSpan.span_id == span_id,
        ).first()
        assert span_row is not None
        assert span_row.service_name == "support-agent"

        # AssetRegistry entry created
        asset = db.query(AssetRegistry).filter(
            AssetRegistry.organization_id == org.id,
            AssetRegistry.agent_name == "support-agent",
        ).first()
        assert asset is not None
        assert asset.discovery_source == "otel_trace"
        assert asset.discovery_status == "potential"

    finally:
        db.close()


# ── B. Agent trace with tool call ─────────────────────────────────────────────

def test_ingest_agent_trace_with_tool_creates_relationship():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "agttool")
        trace_id  = uuid.uuid4().hex
        parent_id = uuid.uuid4().hex[:16]
        child_id  = uuid.uuid4().hex[:16]

        # Parent: agent step
        parent_payload = _make_span(
            trace_id=trace_id,
            span_id=parent_id,
            name="invoke_agent",
            attrs={"agent.name": "research-bot"},
            resource_attrs={"service.name": "research-bot"},
        )
        # Child: tool call
        child_payload = _make_span(
            trace_id=trace_id,
            span_id=child_id,
            name="execute_tool",
            attrs={"agent.name": "research-bot", "tool.name": "web_search"},
            resource_attrs={"service.name": "research-bot"},
            parent_span_id=parent_id,
        )

        # Merge into one payload
        combined = {
            "resourceSpans": [{
                "resource": {"attributes": [
                    {"key": "service.name", "value": {"stringValue": "research-bot"}}
                ]},
                "scopeSpans": [{
                    "spans": [
                        parent_payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0],
                        child_payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0],
                    ]
                }],
            }]
        }

        resp = _post_traces(token, combined)
        assert resp.status_code == 202, resp.text

        # parent_span_id preserved on child OtelSpan
        child_row = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org.id,
            OtelSpan.span_id == child_id,
        ).first()
        assert child_row is not None
        assert child_row.parent_span_id == parent_id

        # tool relationship created
        rel = db.query(AgentRelationship).filter(
            AgentRelationship.organization_id == org.id,
            AgentRelationship.source_agent_name == "research-bot",
            AgentRelationship.target_name == "web_search",
        ).first()
        assert rel is not None
        assert rel.evidence_source == "otel_trace"
        assert rel.target_type in ("tool", "mcp_tool")

    finally:
        db.close()


# ── C. Tool call — raw arguments not stored, hash/size IS stored ──────────────

def test_tool_arguments_not_stored_raw():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "toolargs")
        trace_id = uuid.uuid4().hex
        span_id  = uuid.uuid4().hex[:16]

        raw_args = json.dumps({"query": "top 10 customers", "limit": 50})
        payload = _make_span(
            trace_id=trace_id,
            span_id=span_id,
            name="execute_tool",
            attrs={
                "tool.name": "jira.search",
                "tool.arguments": raw_args,
            },
            resource_attrs={"service.name": "support-bot"},
        )

        resp = _post_traces(token, payload)
        assert resp.status_code == 202, resp.text

        span_row = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org.id,
            OtelSpan.span_id == span_id,
        ).first()
        assert span_row is not None

        attrs = json.loads(span_row.attributes_json)
        tool_arg_val = attrs.get("tool.arguments")

        # Raw value must not be stored
        assert tool_arg_val != raw_args
        # Privacy metadata must be present
        assert isinstance(tool_arg_val, dict)
        assert tool_arg_val.get("redacted") is True
        assert "sha256" in tool_arg_val
        assert "size_bytes" in tool_arg_val
        # Safe argument_keys are stored (key names only, not values)
        assert "argument_keys" in tool_arg_val
        assert sorted(tool_arg_val["argument_keys"]) == ["limit", "query"]

    finally:
        db.close()


# ── D. No content capture — gen_ai messages never stored ─────────────────────

def test_no_content_capture_for_genai_messages():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "nocontent")
        trace_id = uuid.uuid4().hex
        span_id  = uuid.uuid4().hex[:16]

        raw_input  = json.dumps([{"role": "user", "content": "Summarize Q2 revenue"}])
        raw_output = json.dumps([{"role": "assistant", "content": "Q2 revenue was $4.2M..."}])
        raw_sys    = "You are a financial analyst assistant."

        payload = _make_span(
            trace_id=trace_id,
            span_id=span_id,
            name="chat",
            attrs={
                "gen_ai.system": "openai",
                "gen_ai.request.model": "gpt-4o",
                "gen_ai.system_instructions": raw_sys,
                "gen_ai.input.messages": raw_input,
                "gen_ai.output.messages": raw_output,
            },
            resource_attrs={"service.name": "finance-bot"},
        )

        resp = _post_traces(token, payload)
        assert resp.status_code == 202, resp.text

        span_row = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org.id,
            OtelSpan.span_id == span_id,
        ).first()
        assert span_row is not None

        attrs = json.loads(span_row.attributes_json)

        for sensitive_key in (
            "gen_ai.system_instructions",
            "gen_ai.input.messages",
            "gen_ai.output.messages",
        ):
            val = attrs.get(sensitive_key)
            # Raw strings must NOT be stored
            assert val not in (raw_input, raw_output, raw_sys), (
                f"{sensitive_key} stored raw content"
            )
            # Privacy metadata must be present
            assert isinstance(val, dict), f"{sensitive_key} missing privacy metadata"
            assert val.get("redacted") is True
            assert "sha256" in val
            assert "size_bytes" in val

        # ProvenanceEvent should have content_redacted=True
        prov = db.query(ProvenanceEvent).filter(
            ProvenanceEvent.organization_id == org.id,
            ProvenanceEvent.span_id == span_id,
        ).first()
        assert prov is not None
        assert prov.content_redacted is True

    finally:
        db.close()


# ── E. Resource attributes → identity and environment metadata ────────────────

def test_resource_attributes_used_for_asset_identity():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "resattrs")
        trace_id = uuid.uuid4().hex
        span_id  = uuid.uuid4().hex[:16]

        payload = _make_span(
            trace_id=trace_id,
            span_id=span_id,
            name="llm.call",
            attrs={"gen_ai.request.model": "gpt-4o"},
            resource_attrs={
                "service.name": "k8s-agent",
                "service.version": "1.3.2",
                "deployment.environment": "staging",
                "k8s.pod.name": "k8s-agent-7f8b9d-xkp2q",
                "cloud.region": "us-east-1",
            },
        )

        resp = _post_traces(token, payload)
        assert resp.status_code == 202, resp.text

        # Asset created using service.name
        asset = db.query(AssetRegistry).filter(
            AssetRegistry.organization_id == org.id,
            AssetRegistry.agent_name == "k8s-agent",
        ).first()
        assert asset is not None
        assert asset.environment == "staging"
        assert asset.discovery_source == "otel_trace"

        # Resource evidence stored in asset evidence JSON
        evidence = json.loads(asset.evidence or "{}")
        assert evidence.get("service.version") == "1.3.2"
        assert evidence.get("k8s.pod.name") == "k8s-agent-7f8b9d-xkp2q"
        assert evidence.get("cloud.region") == "us-east-1"

        # OtelSpan has resource attrs stored
        span_row = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org.id,
            OtelSpan.span_id == span_id,
        ).first()
        assert span_row is not None
        resource_attrs = json.loads(span_row.resource_attributes_json or "{}")
        assert resource_attrs.get("service.name") == "k8s-agent"
        assert resource_attrs.get("cloud.region") == "us-east-1"

    finally:
        db.close()


# ── F. Tenancy isolation ──────────────────────────────────────────────────────

def test_tenancy_isolation():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org_a, user_a, token_a = _make_org_and_token(db, "iso-a")
        org_b, user_b, token_b = _make_org_and_token(db, "iso-b")

        trace_id = uuid.uuid4().hex
        span_id  = uuid.uuid4().hex[:16]

        payload = _make_span(
            trace_id=trace_id,
            span_id=span_id,
            name="chat",
            attrs={"gen_ai.request.model": "gpt-4o"},
            resource_attrs={"service.name": "secret-agent"},
        )

        # Post to org_a
        resp = _post_traces(token_a, payload)
        assert resp.status_code == 202, resp.text

        # Org B sees zero spans for that trace_id
        org_b_spans = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org_b.id,
            OtelSpan.trace_id == trace_id,
        ).all()
        assert len(org_b_spans) == 0

        # Org B sees zero assets for "secret-agent"
        org_b_asset = db.query(AssetRegistry).filter(
            AssetRegistry.organization_id == org_b.id,
            AssetRegistry.agent_name == "secret-agent",
        ).first()
        assert org_b_asset is None

        # Org A sees the span
        org_a_spans = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org_a.id,
            OtelSpan.trace_id == trace_id,
        ).all()
        assert len(org_a_spans) == 1

    finally:
        db.close()
