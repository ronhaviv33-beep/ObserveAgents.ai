"""
Tests for AI Agent Detection Rules — built-in batch evaluator (app/detection_rules.py).

R1 scope: rule_mcp_tool_access_threshold, rule_repeated_tool_errors,
rule_unknown_provider_in_production. Every finding carries
source="detection_rules". Verifies rule firing, dedup/idempotency, the
production-only boundary, the privacy boundary (no raw content), the
gateway-candidate handoff, and that rules never run at OTLP ingestion.
"""
from __future__ import annotations

import json
import os
import sys
import uuid

_db_path = f"/tmp/test_detection_rules_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-detection-rules")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Organization, User, AssetFinding
from app.auth import hash_password, create_token
import app.asset_discovery as _ad

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")


def _org(db, suffix=""):
    sfx = suffix or uuid.uuid4().hex[:6]
    org = Organization(name=f"dr-org-{sfx}", slug=f"dr-{sfx}")
    db.add(org)
    db.flush()
    user = User(email=f"dr-{sfx}@example.com", name=f"DR {sfx}",
                hashed_password=hash_password("pass"), organization_id=org.id,
                role="admin", team="eng", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(org)
    db.refresh(user)
    return org, create_token(user)


def _span(trace_id, span_id, name, attrs=None, resource_attrs=None, status=None,
          start=1_700_000_000_000_000_000, end=1_700_000_001_000_000_000):
    sattrs = [{"key": k, "value": ({"intValue": v} if isinstance(v, int)
               else {"doubleValue": v} if isinstance(v, float)
               else {"stringValue": str(v)})} for k, v in (attrs or {}).items()]
    rattrs = [{"key": k, "value": {"stringValue": str(v)}} for k, v in (resource_attrs or {}).items()]
    return {"resourceSpans": [{
        "resource": {"attributes": rattrs},
        "scopeSpans": [{"spans": [{
            "traceId": trace_id, "spanId": span_id, "name": name, "kind": 3,
            "startTimeUnixNano": start, "endTimeUnixNano": end,
            "status": status or {}, "attributes": sattrs,
        }]}],
    }]}


def _post(token, payload):
    return _client.post("/otel/v1/traces", json=payload,
                        headers={"Authorization": f"Bearer {token}"})


def _run(token):
    return _client.post("/intelligence/run", headers={"Authorization": f"Bearer {token}"})


def _dr_findings(db, org_id, finding_type=None):
    q = db.query(AssetFinding).filter(
        AssetFinding.organization_id == org_id,
        AssetFinding.source == "detection_rules",
    )
    if finding_type:
        q = q.filter(AssetFinding.finding_type == finding_type)
    return q.all()


def _post_mcp_spans(token, service, count, environment="staging"):
    trace = uuid.uuid4().hex
    for i in range(count):
        assert _post(token, _span(trace, uuid.uuid4().hex[:16], f"mcp-call-{i}",
            attrs={"mcp.method.name": "tools/call", "gen_ai.tool.name": "search_web"},
            resource_attrs={"service.name": service,
                            "deployment.environment": environment})).status_code == 202


def test_mcp_threshold_creates_one_finding_with_count_evidence():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "mcp")
        _post_mcp_spans(token, "mcp-agent", 6)  # threshold is 5, strictly above
        assert _run(token).status_code == 200
        rows = _dr_findings(db, org.id, "rule_mcp_tool_access_threshold")
        assert len(rows) == 1
        row = rows[0]
        assert row.category == "security"
        assert row.severity == "medium"  # staging, below high-count
        assert row.status == "open"
        assert row.occurrence_count == 6
        ev = json.loads(row.evidence_json)
        assert ev["span_count"] == 6 and ev["threshold"] == 5
        assert ev["mcp_methods"] == ["tools/call"]
        assert ev["tool_names"] == ["search_web"]
        assert 1 <= len(ev["sample_span_ids"]) <= 5
        assert ev["environment"] == "staging"
    finally:
        db.close()


def test_mcp_below_threshold_does_not_fire():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "mcplow")
        _post_mcp_spans(token, "quiet-agent", 5)  # exactly at threshold: no fire
        assert _run(token).status_code == 200
        assert _dr_findings(db, org.id, "rule_mcp_tool_access_threshold") == []
    finally:
        db.close()


def test_second_run_is_idempotent():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "idem")
        _post_mcp_spans(token, "idem-agent", 7)
        assert _run(token).status_code == 200
        first = _dr_findings(db, org.id, "rule_mcp_tool_access_threshold")
        assert len(first) == 1
        first_id, first_count = first[0].id, first[0].occurrence_count

        assert _run(token).status_code == 200
        db.expire_all()
        second = _dr_findings(db, org.id, "rule_mcp_tool_access_threshold")
        assert len(second) == 1
        assert second[0].id == first_id
        assert second[0].occurrence_count == first_count == 7
    finally:
        db.close()


def test_repeated_tool_errors_creates_one_finding():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "err")
        trace = uuid.uuid4().hex
        for i in range(4):
            assert _post(token, _span(trace, uuid.uuid4().hex[:16], f"crm-{i}",
                attrs={"gen_ai.tool.name": "crm_lookup", "error.type": "TimeoutError"},
                status={"code": 2, "message": "timeout"},
                resource_attrs={"service.name": "sales-agent"})).status_code == 202
        assert _run(token).status_code == 200
        rows = _dr_findings(db, org.id, "rule_repeated_tool_errors")
        assert len(rows) == 1
        row = rows[0]
        assert row.category == "operations"
        assert row.severity == "medium"  # not production
        assert row.occurrence_count == 4
        ev = json.loads(row.evidence_json)
        assert ev["error_count"] == 4 and ev["threshold"] == 3
        assert "crm_lookup" in ev["tool_names"]
        assert "TimeoutError" in ev["error_types"]
        assert len(ev["sample_span_ids"]) >= 1
    finally:
        db.close()


def test_unknown_provider_in_production_creates_high_finding():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "prov")
        assert _post(token, _span(uuid.uuid4().hex, uuid.uuid4().hex[:16], "llm",
            attrs={"gen_ai.system": "mystery-llm-co", "gen_ai.request.model": "mystery-1"},
            resource_attrs={"service.name": "support-agent",
                            "deployment.environment": "production"})).status_code == 202
        assert _run(token).status_code == 200
        rows = _dr_findings(db, org.id, "rule_unknown_provider_in_production")
        assert len(rows) == 1
        row = rows[0]
        assert row.category == "security"
        assert row.severity == "high"
        ev = json.loads(row.evidence_json)
        # Providers are display-cased by the normalizer; match case-insensitively.
        assert "mystery-llm-co" in [p.lower() for p in ev["providers"]]
        assert "mystery-1" in ev["models"]
        assert ev["environment"] == "production"
    finally:
        db.close()


def test_unknown_provider_outside_production_does_not_fire():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "nonprod")
        assert _post(token, _span(uuid.uuid4().hex, uuid.uuid4().hex[:16], "llm",
            attrs={"gen_ai.system": "mystery-llm-co", "gen_ai.request.model": "mystery-1"},
            resource_attrs={"service.name": "dev-agent",
                            "deployment.environment": "staging"})).status_code == 202
        assert _run(token).status_code == 200
        # Production-only rule by design: nothing fires outside production.
        assert _dr_findings(db, org.id, "rule_unknown_provider_in_production") == []
    finally:
        db.close()


def test_evidence_never_contains_raw_content():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "priv")
        trace = uuid.uuid4().hex
        secret_bits = ("SECRET-PROMPT-TEXT", "SECRET-RESPONSE-TEXT",
                       "SECRET-TOOL-ARG", "SECRET-TOOL-RESULT", "sk-SECRETKEY123")
        for i in range(6):
            assert _post(token, _span(trace, uuid.uuid4().hex[:16], f"mcp-{i}",
                attrs={
                    "mcp.method.name": "tools/call",
                    "gen_ai.tool.name": "search_web",
                    "error.type": "ToolError",
                    # Content-bearing keys — scrubbed at ingestion, must never
                    # surface in detection-rule evidence.
                    "gen_ai.input.messages": secret_bits[0],
                    "gen_ai.output.messages": secret_bits[1],
                    "gen_ai.tool.call.arguments": secret_bits[2],
                    "gen_ai.tool.call.result": secret_bits[3],
                    "url.full": f"https://api.vendor.com/v1?apikey={secret_bits[4]}",
                },
                status={"code": 2, "message": "boom"},
                resource_attrs={"service.name": "priv-agent",
                                "deployment.environment": "production"})).status_code == 202
        assert _run(token).status_code == 200
        rows = _dr_findings(db, org.id)
        assert rows, "expected detection rule findings to fire"
        blob = json.dumps([{
            "title": r.title, "summary": r.summary,
            "evidence": json.loads(r.evidence_json or "{}"),
        } for r in rows])
        for secret in secret_bits:
            assert secret not in blob
        assert "apikey=" not in blob
    finally:
        db.close()


def test_rules_never_run_at_otlp_ingestion():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "ingest")
        _post_mcp_spans(token, "ingest-agent", 10, environment="production")
        # Ingestion alone (no intelligence run) must not evaluate rules.
        assert _dr_findings(db, org.id) == []
        # And the ingestion route module must not import the evaluator.
        import app.routes.otel as otel_route
        source = open(otel_route.__file__).read()
        assert "detection_rules" not in source
    finally:
        db.close()


def test_high_risk_rule_finding_creates_gateway_candidate():
    _ad._known_assets.clear()
    db = SessionLocal()
    try:
        org, token = _org(db, "gcc")
        _post_mcp_spans(token, "prod-mcp-agent", 6, environment="production")
        assert _run(token).status_code == 200
        rule_rows = _dr_findings(db, org.id, "rule_mcp_tool_access_threshold")
        assert len(rule_rows) == 1 and rule_rows[0].severity == "high"  # production
        cands = db.query(AssetFinding).filter(
            AssetFinding.organization_id == org.id,
            AssetFinding.category == "control",
            AssetFinding.asset_key == rule_rows[0].asset_key,
        ).all()
        assert len(cands) == 1
        ev = json.loads(cands[0].evidence_json)
        assert "rule_mcp_tool_access_threshold" in ev["trigger_finding_types"]
        controls = {c["control"] for c in ev["recommended_controls"]}
        assert "mcp/tool usage policy" in controls
    finally:
        db.close()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
    print("all detection rules tests passed")
