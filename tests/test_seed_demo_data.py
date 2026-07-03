"""
Tests for the demo seed script (scripts/seed_demo_data.py).

Covers:
  1. Seed runs successfully and is idempotent (no duplicate traces/spans/
     provenance/assets/findings on second run)
  2. At least 5 demo traces exist
  3. support-agent trace contains child spans under a root
  4. research-agent includes an error span
  5. Demo assets are linked through the OTel → AssetRegistry path
  6. Capabilities are derived across multiple types
  7. Findings are derived across all five MVP categories
  8. No raw prompt/response/secret content in seeded spans
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path

# ── Env setup BEFORE any app import ───────────────────────────────────────────
_db_path = f"/tmp/test_seed_demo_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-seed-demo")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

_repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_repo_root))
os.chdir(_repo_root)

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import (
    AssetCapability, AssetFinding, AssetRegistry, Organization,
    OtelAsset, OtelSpan, ProvenanceEvent, User,
)
from app.otel_privacy import REDACTED_KEYS

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")  # trigger startup + migrations

# Load the seed script as a module (scripts/ is not a package)
_spec = importlib.util.spec_from_file_location(
    "seed_demo_data", _repo_root / "scripts" / "seed_demo_data.py"
)
_seed_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_seed_mod)

# Run the seed twice up front — idempotency is asserted against both summaries.
_SUMMARY_1 = _seed_mod.seed()
_SUMMARY_2 = _seed_mod.seed()

_SERVICES = [s["service"] for s in _seed_mod.DEMO_SYSTEMS]


def _org_id(db) -> int:
    org = db.query(Organization).filter(Organization.slug == _seed_mod.DEMO_ORG_SLUG).first()
    assert org is not None
    return org.id


def test_seed_runs_successfully():
    assert _SUMMARY_1["org_name"] == "Acme AI Operations"
    assert _SUMMARY_1["traces_seeded"] == 5
    assert _SUMMARY_1["spans_ingested"] >= 25
    assert _SUMMARY_1["user_created"] is True
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == _seed_mod.DEMO_USER_EMAIL).first()
        assert user is not None
        assert user.role == "admin"
        assert user.organization_id == _org_id(db)
    finally:
        db.close()


def test_second_run_is_idempotent():
    assert _SUMMARY_2["traces_seeded"] == 0
    assert _SUMMARY_2["traces_skipped"] == 5
    assert _SUMMARY_2["spans_ingested"] == 0
    assert _SUMMARY_2["user_created"] is False
    assert _SUMMARY_2["org_created"] is False
    # No new capability/finding rows on the second run — only refreshes
    assert _SUMMARY_2["capabilities_created"] == 0
    assert _SUMMARY_2["findings_created"] == 0
    assert _SUMMARY_2["capabilities_total"] == _SUMMARY_1["capabilities_total"]
    assert _SUMMARY_2["findings_total"] == _SUMMARY_1["findings_total"]

    db = SessionLocal()
    try:
        org_id = _org_id(db)
        # Exactly one OtelAsset row per demo service — not doubled
        for svc in _SERVICES:
            n = db.query(OtelAsset).filter(
                OtelAsset.organization_id == org_id, OtelAsset.service_name == svc
            ).count()
            assert n == 1, f"{svc}: {n} otel_asset rows"
        # Provenance not duplicated (second run skipped ingestion entirely) —
        # every ingested span produces exactly one provenance event
        prov = db.query(ProvenanceEvent).filter(ProvenanceEvent.organization_id == org_id).count()
        assert prov == _SUMMARY_1["spans_ingested"]
    finally:
        db.close()


def test_at_least_five_demo_traces():
    db = SessionLocal()
    try:
        org_id = _org_id(db)
        trace_ids = {
            r.trace_id
            for r in db.query(OtelSpan.trace_id).filter(OtelSpan.organization_id == org_id).distinct()
        }
        assert len(trace_ids) >= 5
    finally:
        db.close()


def test_support_agent_trace_has_child_spans():
    db = SessionLocal()
    try:
        org_id = _org_id(db)
        tid = _seed_mod._trace_id("support-agent")
        spans = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org_id, OtelSpan.trace_id == tid
        ).all()
        assert len(spans) == 8
        roots = [s for s in spans if s.parent_span_id is None]
        children = [s for s in spans if s.parent_span_id is not None]
        assert len(roots) == 1
        assert roots[0].duration_ms == 8400
        assert len(children) == 7
        # Nested hop: crm.http_call is a child of the CRM span, not the root
        nested = [s for s in children if s.span_name == "crm.http_call"]
        assert nested and nested[0].parent_span_id != roots[0].span_id
    finally:
        db.close()


def test_research_agent_has_error_span():
    db = SessionLocal()
    try:
        org_id = _org_id(db)
        tid = _seed_mod._trace_id("research-agent")
        errors = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org_id,
            OtelSpan.trace_id == tid,
            OtelSpan.status_code == "2",
        ).all()
        assert len(errors) == 1
        assert errors[0].span_name == "external.api_lookup"
    finally:
        db.close()


def test_assets_linked_to_registry():
    db = SessionLocal()
    try:
        org_id = _org_id(db)
        for svc in _SERVICES:
            oa = db.query(OtelAsset).filter(
                OtelAsset.organization_id == org_id, OtelAsset.service_name == svc
            ).first()
            assert oa is not None, f"missing otel_asset for {svc}"
            assert oa.ai_asset_id is not None, f"{svc} not linked to asset_registry"
            reg = db.query(AssetRegistry).get(oa.ai_asset_id)
            assert reg is not None
            assert reg.discovery_source == "otel_trace"
    finally:
        db.close()


def test_capabilities_derived():
    db = SessionLocal()
    try:
        org_id = _org_id(db)
        caps = db.query(AssetCapability).filter(AssetCapability.organization_id == org_id).all()
        types = {c.capability_type for c in caps}
        for expected in ("provider", "model", "retrieval", "crm", "messaging",
                         "mcp", "database", "external_api", "runtime"):
            assert expected in types, f"missing capability type {expected} (have {sorted(types)})"
    finally:
        db.close()


def test_findings_derived_across_categories():
    db = SessionLocal()
    try:
        org_id = _org_id(db)
        finds = db.query(AssetFinding).filter(AssetFinding.organization_id == org_id).all()
        categories = {f.category for f in finds}
        assert {"security", "performance", "operations", "dependency", "inventory"} <= categories

        types = {f.finding_type for f in finds}
        for expected in ("database_access", "mcp_enabled", "production_runtime",
                         "runtime_error", "external_api_access",
                         "new_ai_system_detected", "slow_runtime_step",
                         "broad_tool_access"):
            assert expected in types, f"missing finding type {expected} (have {sorted(types)})"
    finally:
        db.close()


def test_no_raw_content_or_secrets_in_spans():
    db = SessionLocal()
    try:
        org_id = _org_id(db)
        spans = db.query(OtelSpan).filter(OtelSpan.organization_id == org_id).all()
        assert spans
        for s in spans:
            attrs = json.loads(s.attributes_json or "{}")
            # The seed never includes prompt/response/tool-content keys at all
            for k in REDACTED_KEYS:
                assert k not in attrs, f"sensitive key {k} present in span {s.span_name}"
            blob = (s.attributes_json or "") + (s.resource_attributes_json or "")
            for needle in ("Demo123", "password", "api_key", "sk-", "Bearer "):
                assert needle not in blob, f"suspicious content {needle!r} in span {s.span_name}"
    finally:
        db.close()
