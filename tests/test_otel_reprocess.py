"""
Retroactive reclassification tests (app/otel_reprocess.py):

  1. Startup backfill classifies pre-migration (NULL-classification) spans,
     asset counters exact, second run no-op.
  2. Mapping change reprocesses stored spans end-to-end: gen_ai columns
     populated, classification upgraded, ProvenanceEvent updated in place
     (no duplicates), stored attributes_json byte-identical.
  3. Idempotency: second full reclassify reports zero changes.
  4. Org isolation.
  5. PUT auto-reprocess default + reprocess:false opt-out.
  6. Relationships created once, request_count stable across runs.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid

# ── Env setup BEFORE any app import ───────────────────────────────────────────
_db_path = f"/tmp/test_otel_reprocess_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-otel-reprocess")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import (
    AgentRelationship, Organization, OtelAsset, OtelSpan, ProvenanceEvent, User,
)
from app.auth import hash_password, create_token
from app.otel_reprocess import reclassify_org_spans
from app.startup import backfill_span_classification

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_org(db, suffix=""):
    sfx = suffix or uuid.uuid4().hex[:6]
    org = Organization(name=f"reproc-org-{sfx}", slug=f"reproc-{sfx}")
    db.add(org)
    db.flush()
    admin = User(
        email=f"reproc-admin-{sfx}@example.com", name="Reproc Admin",
        hashed_password=hash_password("pass"), organization_id=org.id,
        role="admin", team="eng", is_active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(org)
    db.refresh(admin)
    return org, create_token(admin)


def _attr(k, v):
    if isinstance(v, bool):
        return {"key": k, "value": {"boolValue": v}}
    if isinstance(v, int):
        return {"key": k, "value": {"intValue": v}}
    return {"key": k, "value": {"stringValue": str(v)}}


def _post_span(token, attrs, resource_attrs, trace_id=None, span_id=None):
    now = int(time.time() * 1e9)
    payload = {
        "resourceSpans": [{
            "resource": {"attributes": [_attr(k, v) for k, v in resource_attrs.items()]},
            "scopeSpans": [{"spans": [{
                "traceId": trace_id or uuid.uuid4().hex,
                "spanId": span_id or uuid.uuid4().hex[:16],
                "name": "op",
                "kind": 3,
                "startTimeUnixNano": now,
                "endTimeUnixNano": now + 10**9,
                "status": {},
                "attributes": [_attr(k, v) for k, v in attrs.items()],
            }]}],
        }]
    }
    r = _client.post("/otel/v1/traces", json=payload,
                     headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 202, r.text
    return r


def _put_mapping(token, mapping, reprocess=None):
    body = {"mapping": mapping}
    if reprocess is not None:
        body["reprocess"] = reprocess
    return _client.put("/settings/otel-attribute-mapping", json=body,
                       headers={"Authorization": f"Bearer {token}"})


_CLEAN_ATTRS = {
    "gen_ai.operation.name": "chat",
    "gen_ai.provider.name": "anthropic",
    "gen_ai.request.model": "claude-sonnet-5",
}
_PROD_RES = {"service.name": "backfill-agent", "deployment.environment": "production"}


# ── 1. Startup backfill of NULL-classification (legacy) spans ─────────────────

def test_backfill_classifies_legacy_null_spans_exactly_once():
    db = SessionLocal()
    try:
        org, token = _make_org(db)
        for _ in range(3):
            _post_span(token, _CLEAN_ATTRS, _PROD_RES)

        # Simulate pre-migration rows: NULL the span classification and the
        # asset counters (raw UPDATE — the ingest path always classifies).
        db.query(OtelSpan).filter(OtelSpan.organization_id == org.id).update({
            "classification_status": None,
            "classification_confidence": None,
            "classification_missing": None,
        }, synchronize_session=False)
        db.query(OtelAsset).filter(OtelAsset.organization_id == org.id).update({
            "classification_status": None,
            "classification_counts_json": None,
            "confidence_score": None,
        }, synchronize_session=False)
        db.commit()

        backfill_span_classification()
        db.expire_all()

        spans = db.query(OtelSpan).filter(OtelSpan.organization_id == org.id).all()
        assert len(spans) == 3
        for s in spans:
            assert s.classification_status == "fully_classified"
            assert s.classification_confidence == "high"

        oa = db.query(OtelAsset).filter(
            OtelAsset.organization_id == org.id,
            OtelAsset.service_name == "backfill-agent",
        ).one()
        assert json.loads(oa.classification_counts_json) == {
            "full": 3, "partial": 0, "unclassified": 0}
        assert oa.confidence_score == 100.0
        # span/trace counts untouched by the backfill (counted at ingest)
        assert oa.span_count == 3

        # Second run is a no-op — no NULL rows remain, counters stable.
        backfill_span_classification()
        db.expire_all()
        oa2 = db.query(OtelAsset).filter(OtelAsset.id == oa.id).one()
        assert json.loads(oa2.classification_counts_json) == {
            "full": 3, "partial": 0, "unclassified": 0}
    finally:
        db.close()


# ── 2. Mapping change reprocesses stored spans end-to-end ─────────────────────

def test_mapping_put_reprocesses_stored_spans():
    db = SessionLocal()
    try:
        org, token = _make_org(db)
        trace_id = uuid.uuid4().hex
        span_id = uuid.uuid4().hex[:16]
        _post_span(token, {
            "gen_ai.operation.name": "chat",
            "mycompany.model": "acme-x",
            "mycompany.provider": "acme",
        }, {"service.name": "acme-agent", "deployment.environment": "staging"},
            trace_id=trace_id, span_id=span_id)

        before = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org.id, OtelSpan.trace_id == trace_id).one()
        assert before.gen_ai_request_model is None
        assert before.classification_status == "partially_classified"
        attrs_before = before.attributes_json
        prov_count_before = db.query(ProvenanceEvent).filter(
            ProvenanceEvent.organization_id == org.id).count()

        resp = _put_mapping(token, {
            "mycompany.model": "gen_ai.request.model",
            "mycompany.provider": "gen_ai.provider.name",
        })
        assert resp.status_code == 200, resp.text
        rep = resp.json()["reprocess"]
        assert rep["spans_rescored"] == 1
        assert rep["spans_reclassified"] == 1

        db.expire_all()
        after = db.query(OtelSpan).filter(OtelSpan.id == before.id).one()
        assert after.gen_ai_request_model == "acme-x"
        assert after.gen_ai_provider_name == "acme"
        assert after.classification_status == "fully_classified"
        assert after.classification_confidence == "medium"  # mapped tier
        # stored raw attributes are never rewritten
        assert after.attributes_json == attrs_before

        # ProvenanceEvent updated in place — no new rows
        assert db.query(ProvenanceEvent).filter(
            ProvenanceEvent.organization_id == org.id).count() == prov_count_before
        ev = db.query(ProvenanceEvent).filter(
            ProvenanceEvent.organization_id == org.id,
            ProvenanceEvent.span_id == span_id,
        ).one()
        assert ev.gen_ai_request_model == "acme-x"

        # Asset rollup rebuilt, and the now-mapped keys left the candidates
        oa = db.query(OtelAsset).filter(
            OtelAsset.organization_id == org.id,
            OtelAsset.service_name == "acme-agent",
        ).one()
        assert oa.classification_status == "fully_classified"
        assert "acme-x" in json.loads(oa.models_json or "[]")
        cands = json.loads(oa.candidate_attr_keys_json or "[]")
        assert "mycompany.model" not in cands
    finally:
        db.close()


# ── 3. Idempotency of the full pass ───────────────────────────────────────────

def test_full_reclassify_is_idempotent():
    db = SessionLocal()
    try:
        org, token = _make_org(db)
        _post_span(token, _CLEAN_ATTRS, {"service.name": "idem-agent",
                                         "deployment.environment": "production"})
        first = reclassify_org_spans(db, org.id)
        second = reclassify_org_spans(db, org.id)
        assert second["spans_reclassified"] == 0
        assert second["spans_rescored"] == 0
        assert second["relationships_created"] == 0

        oa = db.query(OtelAsset).filter(
            OtelAsset.organization_id == org.id,
            OtelAsset.service_name == "idem-agent",
        ).one()
        assert oa.span_count == 1
        assert oa.trace_count == 1
        assert json.loads(oa.classification_counts_json) == {
            "full": 1, "partial": 0, "unclassified": 0}
        assert first["spans_seen"] == second["spans_seen"] == 1
    finally:
        db.close()


# ── 4. Org isolation ──────────────────────────────────────────────────────────

def test_reclassify_scoped_to_one_org():
    db = SessionLocal()
    try:
        org_a, token_a = _make_org(db, "isoA")
        org_b, token_b = _make_org(db, "isoB")
        _post_span(token_a, {"gen_ai.operation.name": "chat", "mycompany.model": "m-a"},
                   {"service.name": "iso-a-agent"})
        _post_span(token_b, {"gen_ai.operation.name": "chat", "mycompany.model": "m-b"},
                   {"service.name": "iso-b-agent"})

        # Org A maps the key and reprocesses; org B must be untouched.
        resp = _put_mapping(token_a, {"mycompany.model": "gen_ai.request.model"})
        assert resp.status_code == 200

        db.expire_all()
        a_span = db.query(OtelSpan).filter(OtelSpan.organization_id == org_a.id).one()
        b_span = db.query(OtelSpan).filter(OtelSpan.organization_id == org_b.id).one()
        assert a_span.gen_ai_request_model == "m-a"
        assert b_span.gen_ai_request_model is None
    finally:
        db.close()


# ── 5. reprocess:false opt-out ────────────────────────────────────────────────

def test_mapping_put_reprocess_false_skips():
    db = SessionLocal()
    try:
        org, token = _make_org(db)
        trace_id = uuid.uuid4().hex
        _post_span(token, {"gen_ai.operation.name": "chat", "mycompany.model": "m1"},
                   {"service.name": "optout-agent"}, trace_id=trace_id)

        resp = _put_mapping(token, {"mycompany.model": "gen_ai.request.model"},
                            reprocess=False)
        assert resp.status_code == 200
        assert "reprocess" not in resp.json()

        db.expire_all()
        row = db.query(OtelSpan).filter(
            OtelSpan.organization_id == org.id, OtelSpan.trace_id == trace_id).one()
        assert row.gen_ai_request_model is None  # untouched

        # The admin endpoint finishes the job later.
        resp = _client.post("/intelligence/reclassify",
                            headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["spans_rescored"] == 1
        db.expire_all()
        row = db.query(OtelSpan).filter(OtelSpan.id == row.id).one()
        assert row.gen_ai_request_model == "m1"
    finally:
        db.close()


# ── 6. Relationships: created once, no counter inflation ─────────────────────

def test_reclassify_creates_missing_model_edge_once():
    db = SessionLocal()
    try:
        org, token = _make_org(db)
        _post_span(token, {"gen_ai.operation.name": "chat", "mycompany.model": "edge-m"},
                   {"service.name": "edge-agent", "deployment.environment": "production"})
        # No uses_model edge at ingest (model key unrecognized then).
        assert db.query(AgentRelationship).filter(
            AgentRelationship.organization_id == org.id,
            AgentRelationship.target_name == "edge-m",
        ).count() == 0

        resp = _put_mapping(token, {"mycompany.model": "gen_ai.request.model"})
        assert resp.status_code == 200
        assert resp.json()["reprocess"]["relationships_created"] == 1

        db.expire_all()
        edge = db.query(AgentRelationship).filter(
            AgentRelationship.organization_id == org.id,
            AgentRelationship.target_name == "edge-m",
            AgentRelationship.relationship_type == "uses_model",
        ).one()
        count_before = edge.request_count

        # Second run: same edge, untouched counter.
        second = reclassify_org_spans(db, org.id)
        assert second["relationships_created"] == 0
        db.expire_all()
        edge2 = db.query(AgentRelationship).filter(AgentRelationship.id == edge.id).one()
        assert edge2.request_count == count_before
    finally:
        db.close()
