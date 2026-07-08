"""
Tests for the Asset Intelligence layer.

Tests:
  1.  Provider + model spans create capabilities
  2.  Production environment creates operations finding
  3.  Database tool creates capability and security finding
  4.  Shell tool creates high-severity security finding
  5.  MCP tool creates capability and finding
  6.  Slow span creates performance finding
  7.  Slow tool span creates slow_tool_call finding
  8.  External LLM + CRM tool creates sensitive_system_access finding
  9.  Duplicate run does not create duplicate rows
  10. Dismiss a finding
  11. Resolve a finding
  12. Org isolation — org B has no capabilities or findings from org A's spans
  13. Many slow spans in one run → single finding with occurrence_count
  14. Many MCP spans in one run → single capability
  15. Merge pass heals duplicate rows created by the pre-fix bug
"""
from __future__ import annotations

import json
import os
import sys
import uuid

# ── Env setup BEFORE any app import ───────────────────────────────────────────
_db_path = f"/tmp/test_asset_intelligence_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-asset-intelligence")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Organization, User, AssetCapability, AssetFinding
from app.auth import hash_password, create_token
import app.asset_discovery as _ad

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")  # trigger startup + migrations


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_org_and_token(db, suffix=""):
    sfx = suffix or uuid.uuid4().hex[:6]
    org = Organization(name=f"intel-test-org-{sfx}", slug=f"intel-test-{sfx}")
    db.add(org)
    db.flush()
    user = User(
        email=f"intel-test-{sfx}@example.com",
        name=f"Intel Test {sfx}",
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


def _post_traces(token: str, payload: dict):
    return _client.post(
        "/otel/v1/traces",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )


def _run_intelligence(token: str):
    return _client.post(
        "/intelligence/run",
        headers={"Authorization": f"Bearer {token}"},
    )


def _make_span(
    trace_id: str,
    span_id: str,
    name: str,
    attrs: dict | None = None,
    resource_attrs: dict | None = None,
    start_nano: int = 1_700_000_000_000_000_000,
    end_nano: int   = 1_700_000_001_000_000_000,
) -> dict:
    span_attrs = [
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
    res_attrs = [
        {"key": k, "value": {"stringValue": str(v)}}
        for k, v in (resource_attrs or {}).items()
    ]
    return {
        "resourceSpans": [{
            "resource": {"attributes": res_attrs},
            "scopeSpans": [{"spans": [{
                "traceId": trace_id,
                "spanId": span_id,
                "name": name,
                "kind": 3,
                "startTimeUnixNano": start_nano,
                "endTimeUnixNano": end_nano,
                "status": {},
                "attributes": span_attrs,
            }]}],
        }]
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_provider_model_creates_capabilities():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "prov")
        payload = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="chat",
            attrs={"gen_ai.system": "openai", "gen_ai.request.model": "gpt-4o"},
            resource_attrs={"service.name": "support-agent"},
        )
        resp = _post_traces(token, payload)
        assert resp.status_code == 202

        resp = _run_intelligence(token)
        assert resp.status_code == 200
        body = resp.json()
        assert body["capabilities_created"] >= 2

        caps = db.query(AssetCapability).filter(AssetCapability.organization_id == org.id).all()
        # gen_ai.system is .capitalize()'d by the normalizer (openai → Openai)
        types_by_name = {c.capability_name.lower(): c.capability_type for c in caps}
        assert types_by_name.get("openai") == "provider"
        assert types_by_name.get("gpt-4o") == "model"
    finally:
        db.close()


def test_production_environment_creates_ops_finding():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "prod")
        payload = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="step",
            attrs={"gen_ai.system": "anthropic"},
            resource_attrs={"service.name": "prod-agent", "deployment.environment": "production"},
        )
        resp = _post_traces(token, payload)
        assert resp.status_code == 202

        resp = _run_intelligence(token)
        assert resp.status_code == 200

        findings = (
            db.query(AssetFinding)
            .filter(
                AssetFinding.organization_id == org.id,
                AssetFinding.category == "operations",
                AssetFinding.finding_type == "production_runtime",
            )
            .all()
        )
        assert len(findings) == 1
        assert findings[0].severity == "info"
    finally:
        db.close()


def test_database_tool_creates_capability_and_finding():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "dbaccess")
        payload = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="query",
            attrs={"tool.name": "postgres_query"},
            resource_attrs={"service.name": "db-agent"},
        )
        resp = _post_traces(token, payload)
        assert resp.status_code == 202

        resp = _run_intelligence(token)
        assert resp.status_code == 200

        caps = db.query(AssetCapability).filter(
            AssetCapability.organization_id == org.id,
            AssetCapability.capability_type == "database",
        ).all()
        assert len(caps) >= 1

        findings = db.query(AssetFinding).filter(
            AssetFinding.organization_id == org.id,
            AssetFinding.category == "security",
            AssetFinding.finding_type == "database_access",
        ).all()
        assert len(findings) == 1
        assert findings[0].severity == "medium"
    finally:
        db.close()


def test_shell_tool_creates_high_security_finding():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "shell")
        payload = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="exec",
            attrs={"tool.name": "bash_exec"},
            resource_attrs={"service.name": "shell-agent"},
        )
        resp = _post_traces(token, payload)
        assert resp.status_code == 202

        resp = _run_intelligence(token)
        assert resp.status_code == 200

        caps = db.query(AssetCapability).filter(
            AssetCapability.organization_id == org.id,
            AssetCapability.capability_type == "shell",
        ).all()
        assert len(caps) >= 1

        findings = db.query(AssetFinding).filter(
            AssetFinding.organization_id == org.id,
            AssetFinding.category == "security",
            AssetFinding.finding_type == "shell_enabled",
        ).all()
        assert len(findings) == 1
        assert findings[0].severity == "high"
    finally:
        db.close()


def test_mcp_tool_creates_capability_and_finding():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "mcp")
        payload = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="mcp_call",
            attrs={"tool.name": "mcp_filesystem"},
            resource_attrs={"service.name": "mcp-agent"},
        )
        resp = _post_traces(token, payload)
        assert resp.status_code == 202

        resp = _run_intelligence(token)
        assert resp.status_code == 200

        caps = db.query(AssetCapability).filter(
            AssetCapability.organization_id == org.id,
            AssetCapability.capability_type == "mcp",
        ).all()
        assert len(caps) >= 1

        findings = db.query(AssetFinding).filter(
            AssetFinding.organization_id == org.id,
            AssetFinding.finding_type == "mcp_enabled",
        ).all()
        assert len(findings) == 1
    finally:
        db.close()


def test_slow_span_creates_performance_finding():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "slow")
        start = 1_700_000_000_000_000_000
        end   = start + 6_000_000_000  # 6 seconds
        payload = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="step",
            attrs={},
            resource_attrs={"service.name": "slow-agent"},
            start_nano=start,
            end_nano=end,
        )
        resp = _post_traces(token, payload)
        assert resp.status_code == 202

        resp = _run_intelligence(token)
        assert resp.status_code == 200

        findings = db.query(AssetFinding).filter(
            AssetFinding.organization_id == org.id,
            AssetFinding.category == "performance",
            AssetFinding.finding_type == "slow_runtime_step",
        ).all()
        assert len(findings) == 1
        assert findings[0].severity == "medium"
    finally:
        db.close()


def test_slow_tool_span_creates_slow_tool_call_finding():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "slowtool")
        start = 1_700_000_000_000_000_000
        end   = start + 6_000_000_000  # 6 seconds
        payload = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="tool_step",
            attrs={"tool.name": "search"},
            resource_attrs={"service.name": "slow-tool-agent"},
            start_nano=start,
            end_nano=end,
        )
        resp = _post_traces(token, payload)
        assert resp.status_code == 202

        resp = _run_intelligence(token)
        assert resp.status_code == 200

        findings = db.query(AssetFinding).filter(
            AssetFinding.organization_id == org.id,
            AssetFinding.category == "performance",
            AssetFinding.finding_type == "slow_tool_call",
        ).all()
        assert len(findings) == 1
    finally:
        db.close()


def test_external_llm_plus_crm_creates_sensitive_finding():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "crm")
        # First span: LLM call (creates provider capability)
        payload1 = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="chat",
            attrs={"gen_ai.system": "openai"},
            resource_attrs={"service.name": "crm-agent"},
        )
        resp = _post_traces(token, payload1)
        assert resp.status_code == 202

        # Second span: CRM tool call
        payload2 = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="crm_update",
            attrs={"tool.name": "salesforce_update"},
            resource_attrs={"service.name": "crm-agent"},
        )
        resp = _post_traces(token, payload2)
        assert resp.status_code == 202

        resp = _run_intelligence(token)
        assert resp.status_code == 200

        findings = db.query(AssetFinding).filter(
            AssetFinding.organization_id == org.id,
            AssetFinding.finding_type == "sensitive_system_access",
        ).all()
        assert len(findings) == 1
        assert findings[0].severity == "high"
    finally:
        db.close()


def test_duplicate_run_no_duplicates():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "dedup")
        payload = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="chat",
            attrs={"gen_ai.system": "openai", "gen_ai.request.model": "gpt-4o"},
            resource_attrs={"service.name": "dedup-agent"},
        )
        resp = _post_traces(token, payload)
        assert resp.status_code == 202

        # Run twice
        resp1 = _run_intelligence(token)
        resp2 = _run_intelligence(token)
        assert resp1.status_code == 200
        assert resp2.status_code == 200

        # Second run should have 0 created, only updates
        body2 = resp2.json()
        assert body2["capabilities_created"] == 0

        # Exactly one row per (type, name) — not doubled
        # provider is .capitalize()'d by the normalizer: "Openai"
        provider_caps = db.query(AssetCapability).filter(
            AssetCapability.organization_id == org.id,
            AssetCapability.capability_type == "provider",
        ).all()
        assert len(provider_caps) == 1
    finally:
        db.close()


def test_dismiss_finding():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "dismiss")
        payload = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="chat",
            attrs={"gen_ai.system": "anthropic"},
            resource_attrs={"service.name": "dismiss-agent", "deployment.environment": "production"},
        )
        resp = _post_traces(token, payload)
        assert resp.status_code == 202

        resp = _run_intelligence(token)
        assert resp.status_code == 200

        findings = db.query(AssetFinding).filter(
            AssetFinding.organization_id == org.id,
            AssetFinding.finding_type == "production_runtime",
        ).all()
        assert len(findings) == 1
        fid = findings[0].id

        resp = _client.post(
            f"/intelligence/findings/{fid}/dismiss",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "dismissed"

        db.expire_all()
        row = db.query(AssetFinding).get(fid)
        assert row.status == "dismissed"
    finally:
        db.close()


def test_resolve_finding():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "resolve")
        payload = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="chat",
            attrs={"gen_ai.system": "anthropic"},
            resource_attrs={"service.name": "resolve-agent", "deployment.environment": "production"},
        )
        resp = _post_traces(token, payload)
        assert resp.status_code == 202

        resp = _run_intelligence(token)
        assert resp.status_code == 200

        findings = db.query(AssetFinding).filter(
            AssetFinding.organization_id == org.id,
            AssetFinding.finding_type == "production_runtime",
        ).all()
        assert len(findings) == 1
        fid = findings[0].id

        resp = _client.post(
            f"/intelligence/findings/{fid}/resolve",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "resolved"

        db.expire_all()
        row = db.query(AssetFinding).get(fid)
        assert row.status == "resolved"
    finally:
        db.close()


def test_intelligence_unauthenticated_rejected():
    for path in ("/intelligence/assets", "/intelligence/capabilities", "/intelligence/findings"):
        resp = _client.get(path)
        assert resp.status_code == 401, f"{path} → {resp.status_code}"
    assert _client.post("/intelligence/run").status_code == 401
    assert _client.post("/intelligence/findings/1/dismiss").status_code == 401


def test_intelligence_assets_endpoint():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "assets")
        payload = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="chat",
            attrs={"gen_ai.system": "openai", "gen_ai.request.model": "gpt-4o"},
            resource_attrs={"service.name": "assets-agent", "deployment.environment": "production"},
        )
        resp = _post_traces(token, payload)
        assert resp.status_code == 202

        resp = _client.get(
            "/intelligence/assets",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1
        a = rows[0]
        assert a["service_name"] == "assets-agent"
        assert a["environment"] == "production"
        assert "gpt-4o" in a["models"]
        assert a["span_count"] == 1
        assert a["ai_asset_id"] is not None

        # environment filter
        resp = _client.get(
            "/intelligence/assets?environment=staging",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        db.close()


def test_asset_summary_requires_auth():
    resp = _client.get("/intelligence/asset-summary")
    assert resp.status_code == 401


def test_asset_summary_org_isolation():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org_a, _, token_a = _make_org_and_token(db, "sumisoa")
        org_b, _, token_b = _make_org_and_token(db, "sumisob")
        payload = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="chat",
            attrs={"gen_ai.system": "openai", "gen_ai.request.model": "gpt-4o"},
            resource_attrs={"service.name": "sum-iso-agent"},
        )
        assert _post_traces(token_a, payload).status_code == 202
        assert _run_intelligence(token_a).status_code == 200

        resp = _client.get("/intelligence/asset-summary", headers={"Authorization": f"Bearer {token_a}"})
        assert resp.status_code == 200
        assert len(resp.json()["assets"]) == 1

        resp = _client.get("/intelligence/asset-summary", headers={"Authorization": f"Bearer {token_b}"})
        assert resp.status_code == 200
        assert resp.json()["assets"] == []
    finally:
        db.close()


def test_asset_summary_groups_by_asset():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "sumgrp")
        for svc, tool in (("grp-agent-a", "postgres_query"), ("grp-agent-b", "bash_exec")):
            payload = _make_span(
                trace_id=uuid.uuid4().hex,
                span_id=uuid.uuid4().hex[:16],
                name="step",
                attrs={"tool.name": tool},
                resource_attrs={"service.name": svc},
            )
            assert _post_traces(token, payload).status_code == 202
        assert _run_intelligence(token).status_code == 200

        resp = _client.get("/intelligence/asset-summary", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        by_name = {a["asset_name"]: a for a in resp.json()["assets"]}
        assert set(by_name) == {"grp-agent-a", "grp-agent-b"}

        a_caps = {c["capability_name"] for c in by_name["grp-agent-a"]["capabilities"]}
        b_caps = {c["capability_name"] for c in by_name["grp-agent-b"]["capabilities"]}
        assert "postgres_query" in a_caps and "bash_exec" not in a_caps
        assert "bash_exec" in b_caps and "postgres_query" not in b_caps
    finally:
        db.close()


def test_asset_summary_finding_counts_and_status():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "sumfnd")
        payload = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="exec",
            attrs={"tool.name": "bash_exec"},
            resource_attrs={"service.name": "sumfnd-agent", "deployment.environment": "production"},
        )
        assert _post_traces(token, payload).status_code == 202
        assert _run_intelligence(token).status_code == 200

        resp = _client.get("/intelligence/asset-summary", headers={"Authorization": f"Bearer {token}"})
        a = resp.json()["assets"][0]
        assert a["open_findings_count"] == a["findings_count"] > 0
        assert a["high_findings_count"] >= 1                 # shell_enabled is high
        assert a["finding_categories"].get("security", 0) >= 1
        assert a["finding_categories"].get("operations", 0) >= 1  # production_runtime
        # Span timestamps use the fixed 2023 base nano — well past the 7-day
        # freshness window, so the asset must NOT be flagged active.
        assert "active" not in a["status"]
        assert "runtime_observed" in a["status"]
        assert "has_findings" in a["status"]
        assert "error_observed" not in a["status"]
    finally:
        db.close()


def test_asset_summary_includes_evidence_arrays():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "sumarr")
        payload = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="chat",
            attrs={"gen_ai.system": "openai", "gen_ai.request.model": "gpt-4o"},
            resource_attrs={"service.name": "sumarr-agent"},
        )
        assert _post_traces(token, payload).status_code == 202
        assert _run_intelligence(token).status_code == 200

        resp = _client.get("/intelligence/asset-summary", headers={"Authorization": f"Bearer {token}"})
        a = resp.json()["assets"][0]
        assert a["models"] == ["gpt-4o"]
        assert a["providers"] == ["OpenAI"]   # display-normalized from stored "Openai"
        assert a["capabilities_count"] >= 2
        assert a["trace_count"] == 1
        assert a["span_count"] == 1
    finally:
        db.close()


def test_asset_summary_no_raw_content():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "sumpriv")
        payload = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="chat",
            attrs={
                "gen_ai.system": "openai",
                "gen_ai.input.messages": '[{"role":"user","content":"top secret"}]',
            },
            resource_attrs={"service.name": "sumpriv-agent"},
        )
        assert _post_traces(token, payload).status_code == 202
        assert _run_intelligence(token).status_code == 200

        resp = _client.get("/intelligence/asset-summary", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert "attributes_json" not in resp.text
        assert "gen_ai.input.messages" not in resp.text
        assert "top secret" not in resp.text
    finally:
        db.close()


def test_org_isolation():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org_a, _, token_a = _make_org_and_token(db, "isola")
        org_b, _, token_b = _make_org_and_token(db, "isolb")

        # POST span for org A only
        payload = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="chat",
            attrs={"gen_ai.system": "openai", "gen_ai.request.model": "gpt-4o"},
            resource_attrs={"service.name": "isol-agent"},
        )
        resp = _post_traces(token_a, payload)
        assert resp.status_code == 202

        # Run intelligence for org A
        resp = _run_intelligence(token_a)
        assert resp.status_code == 200
        assert resp.json()["capabilities_created"] >= 1

        # Org B should have zero capabilities and findings
        b_caps = db.query(AssetCapability).filter(
            AssetCapability.organization_id == org_b.id
        ).count()
        b_finds = db.query(AssetFinding).filter(
            AssetFinding.organization_id == org_b.id
        ).count()
        assert b_caps == 0
        assert b_finds == 0
    finally:
        db.close()


def test_many_slow_spans_one_run_single_finding_with_count():
    """N slow spans in a single run collapse into one finding carrying
    occurrence_count — the in-run dedup that autoflush=False used to break."""
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "manyslow")
        start = 1_700_000_000_000_000_000
        for i in range(4):
            payload = _make_span(
                trace_id=uuid.uuid4().hex,
                span_id=uuid.uuid4().hex[:16],
                name=f"step-{i}",
                attrs={},
                resource_attrs={"service.name": "many-slow-agent"},
                start_nano=start,
                end_nano=start + (6 + i) * 1_000_000_000,  # 6..9 seconds
            )
            resp = _post_traces(token, payload)
            assert resp.status_code == 202

        resp = _run_intelligence(token)
        assert resp.status_code == 200

        findings = db.query(AssetFinding).filter(
            AssetFinding.organization_id == org.id,
            AssetFinding.finding_type == "slow_runtime_step",
        ).all()
        assert len(findings) == 1
        assert findings[0].occurrence_count == 4
        evidence = json.loads(findings[0].evidence_json)
        assert evidence["span_count"] == 4
        assert len(evidence["sample_span_ids"]) == 4
        assert evidence["max_duration_ms"] >= 9000

        # Idempotent: a second run keeps one row with the same count
        resp = _run_intelligence(token)
        assert resp.status_code == 200
        db.expire_all()
        findings = db.query(AssetFinding).filter(
            AssetFinding.organization_id == org.id,
            AssetFinding.finding_type == "slow_runtime_step",
        ).all()
        assert len(findings) == 1
        assert findings[0].occurrence_count == 4

        # API exposes the count
        resp = _client.get(
            "/intelligence/findings",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        row = next(f for f in resp.json() if f["finding_type"] == "slow_runtime_step")
        assert row["occurrence_count"] == 4
    finally:
        db.close()


def test_many_mcp_spans_one_run_single_capability():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "manymcp")
        for i in range(3):
            payload = _make_span(
                trace_id=uuid.uuid4().hex,
                span_id=uuid.uuid4().hex[:16],
                name=f"mcp-call-{i}",
                attrs={"mcp.method.name": "tools/call", "gen_ai.tool.name": "jira_search"},
                resource_attrs={"service.name": "many-mcp-agent"},
            )
            resp = _post_traces(token, payload)
            assert resp.status_code == 202

        resp = _run_intelligence(token)
        assert resp.status_code == 200

        caps = db.query(AssetCapability).filter(
            AssetCapability.organization_id == org.id,
            AssetCapability.capability_type == "mcp",
        ).all()
        assert len(caps) == 1
    finally:
        db.close()


def test_merge_pass_heals_existing_duplicates():
    """Rows duplicated by the pre-fix bug are merged on the next derive run:
    oldest row kept, seen-window widened, open status wins, count folded in."""
    from datetime import datetime, timedelta, timezone as _tz

    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "heal")
        t0 = datetime.now(_tz.utc) - timedelta(hours=2)
        statuses = ["resolved", "open", "open"]
        for i, status in enumerate(statuses):
            db.add(AssetFinding(
                organization_id=org.id,
                asset_key="deadbeef" * 8,
                category="performance",
                finding_type="slow_llm_call",
                severity="medium",
                title="Slow LLM Call Detected",
                summary="An LLM call for this service exceeded 10,000 ms.",
                source="otel_trace",
                status=status,
                first_seen=t0 + timedelta(minutes=i),
                last_seen=t0 + timedelta(minutes=i),
            ))
            db.add(AssetCapability(
                organization_id=org.id,
                asset_key="deadbeef" * 8,
                capability_type="mcp",
                capability_name="jira_search",
                source="otel_trace",
                first_seen=t0 + timedelta(minutes=i),
                last_seen=t0 + timedelta(minutes=i),
            ))
        db.commit()

        resp = _run_intelligence(token)
        assert resp.status_code == 200
        db.expire_all()

        findings = db.query(AssetFinding).filter(
            AssetFinding.organization_id == org.id,
            AssetFinding.finding_type == "slow_llm_call",
        ).all()
        assert len(findings) == 1
        kept = findings[0]
        assert kept.status == "open"          # any-open wins over the kept row's resolved
        assert kept.occurrence_count == 3     # duplicate count folded in
        assert kept.first_seen <= kept.last_seen
        assert (kept.last_seen - kept.first_seen) >= timedelta(minutes=2)

        caps = db.query(AssetCapability).filter(
            AssetCapability.organization_id == org.id,
            AssetCapability.capability_type == "mcp",
        ).all()
        assert len(caps) == 1
    finally:
        db.close()


def test_reopen_finding():
    """Resolved and dismissed findings can be returned to open via /reopen."""
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "reopen")
        start = 1_700_000_000_000_000_000
        payload = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="step",
            attrs={},
            resource_attrs={"service.name": "reopen-agent"},
            start_nano=start,
            end_nano=start + 6_000_000_000,
        )
        assert _post_traces(token, payload).status_code == 202
        assert _run_intelligence(token).status_code == 200

        finding = db.query(AssetFinding).filter(
            AssetFinding.organization_id == org.id,
            AssetFinding.finding_type == "slow_runtime_step",
        ).first()
        fid = finding.id
        H = {"Authorization": f"Bearer {token}"}

        # resolve → reopen
        assert _client.post(f"/intelligence/findings/{fid}/resolve", headers=H).status_code == 200
        r = _client.post(f"/intelligence/findings/{fid}/reopen", headers=H)
        assert r.status_code == 200 and r.json()["status"] == "open"
        db.expire_all()
        assert db.query(AssetFinding).get(fid).status == "open"

        # dismiss → reopen
        assert _client.post(f"/intelligence/findings/{fid}/dismiss", headers=H).status_code == 200
        assert _client.post(f"/intelligence/findings/{fid}/reopen", headers=H).status_code == 200
        db.expire_all()
        assert db.query(AssetFinding).get(fid).status == "open"

        # org isolation: another org's token cannot reopen it
        _, _, token_b = _make_org_and_token(db, "reopenb")
        r = _client.post(f"/intelligence/findings/{fid}/reopen",
                         headers={"Authorization": f"Bearer {token_b}"})
        assert r.status_code == 404
    finally:
        db.close()


# ── 16. GenAI SemConv capability + finding derivation ─────────────────────────

def test_genai_semconv_capabilities_derived():
    """gen_ai.data_source.id / workflow.name / prompt.name / mcp.resource.uri
    become normalized capabilities; mcp.resource.uri is sanitized (no query)."""
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "gcap")
        trace_id = uuid.uuid4().hex

        payload = _make_span(
            trace_id=trace_id,
            span_id=uuid.uuid4().hex[:16],
            name="chat",
            attrs={
                "gen_ai.provider.name": "openai",
                "gen_ai.request.model": "gpt-4o",
                "gen_ai.data_source.id": "kb-products",
                "gen_ai.workflow.name": "order-support-flow",
                "gen_ai.prompt.name": "support-triage",
                "gen_ai.prompt.version": "3",
                "mcp.method.name": "resources/read",
                "mcp.resource.uri": "postgres://db.internal/orders?password=hunter2#frag",
            },
            resource_attrs={"service.name": "genai-cap-agent"},
        )
        assert _post_traces(token, payload).status_code == 202
        assert _run_intelligence(token).status_code == 200

        caps = db.query(AssetCapability).filter(
            AssetCapability.organization_id == org.id,
        ).all()
        by_type = {(c.capability_type, c.capability_name): c for c in caps}

        assert ("data_source", "kb-products") in by_type
        assert ("workflow", "order-support-flow") in by_type
        assert ("prompt", "support-triage") in by_type
        prompt_ev = json.loads(by_type[("prompt", "support-triage")].evidence_json)
        assert prompt_ev["gen_ai.prompt.version"] == "3"

        mcp_res = [c for c in caps if c.capability_type == "mcp_resource"]
        assert len(mcp_res) == 1
        assert mcp_res[0].capability_name == "postgres://db.internal/orders"
        assert "hunter2" not in (mcp_res[0].capability_name or "")
        assert "hunter2" not in (mcp_res[0].evidence_json or "")

        # all otel-derived
        for c in caps:
            assert c.source == "otel_trace"

    finally:
        db.close()


def test_genai_tool_type_evidence_no_duplicate_row():
    """gen_ai.tool.type lands as evidence on the classified tool capability
    without creating a second row for the same tool."""
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "gtool")
        payload = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="execute_tool query_database",
            attrs={
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": "query_database",
                "gen_ai.tool.type": "function",
            },
            resource_attrs={"service.name": "genai-tool-agent"},
        )
        assert _post_traces(token, payload).status_code == 202
        assert _run_intelligence(token).status_code == 200

        rows = db.query(AssetCapability).filter(
            AssetCapability.organization_id == org.id,
            AssetCapability.capability_name == "query_database",
        ).all()
        assert len(rows) == 1
        assert rows[0].capability_type == "database"
        assert json.loads(rows[0].evidence_json)["gen_ai.tool.type"] == "function"

    finally:
        db.close()


def test_model_mismatch_finding():
    """Genuinely different request/response models fire the governance finding;
    a dated snapshot (prefix) does not."""
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "gmm")

        # dated snapshot — must NOT fire
        ok = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="chat",
            attrs={
                "gen_ai.request.model": "gpt-4o",
                "gen_ai.response.model": "gpt-4o-2024-08-06",
            },
            resource_attrs={"service.name": "mm-snapshot-agent"},
        )
        # different model — must fire
        bad = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="chat",
            attrs={
                "gen_ai.request.model": "gpt-4o",
                "gen_ai.response.model": "gpt-4o-mini",
            },
            resource_attrs={"service.name": "mm-mismatch-agent"},
        )
        assert _post_traces(token, ok).status_code == 202
        assert _post_traces(token, bad).status_code == 202
        assert _run_intelligence(token).status_code == 200

        findings = db.query(AssetFinding).filter(
            AssetFinding.organization_id == org.id,
            AssetFinding.finding_type == "request_response_model_mismatch",
        ).all()
        assert len(findings) == 1
        f = findings[0]
        assert f.category == "governance"
        assert f.severity == "low"
        ev = json.loads(f.evidence_json)
        assert "gpt-4o -> gpt-4o-mini" in ev["details"]

    finally:
        db.close()


def test_high_token_usage_finding_threshold():
    """Fires at 100k total tokens on one span; not at 99k."""
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "gtok")

        under = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="chat",
            attrs={
                "gen_ai.request.model": "gpt-4o",
                "gen_ai.usage.input_tokens": 98_000,
                "gen_ai.usage.output_tokens": 1_000,
            },
            resource_attrs={"service.name": "tok-under-agent"},
        )
        over = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="chat",
            attrs={
                "gen_ai.request.model": "gpt-4o",
                "gen_ai.usage.input_tokens": 95_000,
                "gen_ai.usage.output_tokens": 5_000,
                "gen_ai.usage.reasoning.output_tokens": 2_500,
            },
            resource_attrs={"service.name": "tok-over-agent"},
        )
        assert _post_traces(token, under).status_code == 202
        assert _post_traces(token, over).status_code == 202
        assert _run_intelligence(token).status_code == 200

        findings = db.query(AssetFinding).filter(
            AssetFinding.organization_id == org.id,
            AssetFinding.finding_type == "high_token_usage",
        ).all()
        assert len(findings) == 1
        f = findings[0]
        assert f.category == "performance"
        assert f.severity == "medium"
        ev = json.loads(f.evidence_json)
        assert ev["max_total_tokens"] == 100_000
        assert ev["max_reasoning_tokens"] == 2_500

    finally:
        db.close()


def test_genai_capabilities_rerun_no_duplicates():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "grerun")
        payload = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="chat",
            attrs={
                "gen_ai.workflow.name": "rerun-flow",
                "gen_ai.data_source.id": "rerun-kb",
            },
            resource_attrs={"service.name": "genai-rerun-agent"},
        )
        assert _post_traces(token, payload).status_code == 202
        assert _run_intelligence(token).status_code == 200
        assert _run_intelligence(token).status_code == 200

        for cap_type, cap_name in (("workflow", "rerun-flow"), ("data_source", "rerun-kb")):
            rows = db.query(AssetCapability).filter(
                AssetCapability.organization_id == org.id,
                AssetCapability.capability_type == cap_type,
                AssetCapability.capability_name == cap_name,
            ).all()
            assert len(rows) == 1, f"duplicate {cap_type} rows after rerun"

    finally:
        db.close()


# ── 17. runtime_usage from ProvenanceEvent scalar columns ─────────────────────

from app.models import ProvenanceEvent


def _summary_asset(token: str, name: str) -> dict | None:
    resp = _client.get(
        "/intelligence/asset-summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    return next((a for a in resp.json()["assets"] if a["asset_name"] == name), None)


def test_asset_summary_runtime_usage():
    """asset-summary exposes per-asset runtime usage aggregated from the
    provenance scalar columns (written at ingest, no /intelligence/run needed)."""
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "rusage")
        payload = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="chat",
            attrs={
                "gen_ai.system": "openai",
                "gen_ai.request.model": "gpt-4o",
                "gen_ai.usage.input_tokens": 150,
                "gen_ai.usage.output_tokens": 50,
            },
            resource_attrs={"service.name": "usage-agent"},
        )
        assert _post_traces(token, payload).status_code == 202

        asset = _summary_asset(token, "usage-agent")
        assert asset is not None
        usage = asset["runtime_usage"]
        assert usage is not None
        assert usage["llm_call_count"] == 1
        assert usage["input_tokens"] == 150
        assert usage["output_tokens"] == 50
        assert usage["last_activity"] is not None

        # Org isolation: org B's summary has no such asset
        org_b, _, token_b = _make_org_and_token(db, "rusage-b")
        assert _summary_asset(token_b, "usage-agent") is None
    finally:
        db.close()


def test_asset_summary_runtime_usage_null_scalars():
    """Pre-migration provenance rows (NULL scalars) still produce a
    runtime_usage block with zeroed tokens and no avg TTFC."""
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, user, token = _make_org_and_token(db, "rusagenull")
        payload = _make_span(
            trace_id=uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            name="chat",
            attrs={
                "gen_ai.system": "openai",
                "gen_ai.request.model": "gpt-4o",
                "gen_ai.usage.input_tokens": 99,
                "gen_ai.usage.output_tokens": 11,
            },
            resource_attrs={"service.name": "usage-null-agent"},
        )
        assert _post_traces(token, payload).status_code == 202

        for ev in db.query(ProvenanceEvent).filter(
            ProvenanceEvent.organization_id == org.id,
        ).all():
            ev.input_tokens = None
            ev.output_tokens = None
            ev.request_stream = None
            ev.time_to_first_chunk_ms = None
        db.commit()

        asset = _summary_asset(token, "usage-null-agent")
        assert asset is not None
        usage = asset["runtime_usage"]
        assert usage is not None
        assert usage["event_count"] == 1
        assert usage["input_tokens"] == 0
        assert usage["output_tokens"] == 0
        assert usage["avg_time_to_first_chunk_ms"] is None
    finally:
        db.close()
