"""
Agent discovery and lifecycle tests for the synthetic enterprise environment.

Tests the complete agent lifecycle:
  Unassigned → Managed → Retired

And discovery scenarios:
  • Auto-discovery from telemetry headers
  • asset_key stability (sha256(org_id:agent_id_raw))
  • Claim flow: sets status=managed, owner, team, environment
  • Retire flow: sets status=retired, hides from default inventory
  • Multiple agents in same org share no registry rows
  • Cross-org: same agent name produces different asset_keys

ENV vars are set before any app import — do not reorder the top block.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# ── Env setup BEFORE any app import ───────────────────────────────────────────
_db_path = f"/tmp/test_agent_lifecycle_{uuid.uuid4().hex[:8]}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ.setdefault("JWT_SECRET", "testsecret-agent-lifecycle")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.chdir(str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient
from app.main import app, _seed_roles_for_org
from app.database import SessionLocal
from app.models import Organization, User, ApiKey, Telemetry, AssetRegistry
from app.auth import hash_password, generate_api_key, create_token

# ── Shared fixtures ───────────────────────────────────────────────────────────
_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")

_db = SessionLocal()


def _slug(n: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")


def _asset_key(org_id: int, agent_id_raw: str) -> str:
    return hashlib.sha256(f"{org_id}:{agent_id_raw}".encode()).hexdigest()


# ── Create two orgs (to test cross-org key isolation) ────────────────────────
_org_a = Organization(name="LifecycleOrgA", slug="lifecycle-org-a")
_org_b = Organization(name="LifecycleOrgB", slug="lifecycle-org-b")
_db.add_all([_org_a, _org_b])
_db.commit()
_db.refresh(_org_a)
_db.refresh(_org_b)

for _o in [_org_a, _org_b]:
    _seed_roles_for_org(_db, _o.id)

ORG_A_ID = _org_a.id
ORG_B_ID = _org_b.id

# ── Admin users ───────────────────────────────────────────────────────────────
_admin_a = User(email="admin-a@lifecycle.test", name="Admin A",
                hashed_password=hash_password("x"), role="admin",
                team="", organization_id=ORG_A_ID)
_admin_b = User(email="admin-b@lifecycle.test", name="Admin B",
                hashed_password=hash_password("x"), role="admin",
                team="", organization_id=ORG_B_ID)
_db.add_all([_admin_a, _admin_b])
_db.commit()
_db.refresh(_admin_a)
_db.refresh(_admin_b)

# ── API keys (used for proxy calls) ──────────────────────────────────────────
_raw_a, _pfx_a, _hash_a = generate_api_key()
_api_a = ApiKey(name="lc-key-a", key_prefix=_pfx_a, key_hash=_hash_a,
                team="developer", organization_id=ORG_A_ID,
                created_by_id=_admin_a.id)
_raw_b, _pfx_b, _hash_b = generate_api_key()
_api_b = ApiKey(name="lc-key-b", key_prefix=_pfx_b, key_hash=_hash_b,
                team="developer", organization_id=ORG_B_ID,
                created_by_id=_admin_b.id)
_db.add_all([_api_a, _api_b])
_db.commit()

# ── Refresh users so attributes survive session close ─────────────────────────
for _u in [_admin_a, _admin_b]:
    _db.refresh(_u)

# ── Auth headers (must be created while session is open) ──────────────────────
ADMIN_A_H = {"Authorization": f"Bearer {create_token(_admin_a)}"}
ADMIN_B_H = {"Authorization": f"Bearer {create_token(_admin_b)}"}
# Proxy calls authenticate with the org admins' JWTs (high trust): the identity
# resolver only honors X-Guard-Agent headers for high-trust callers — API-key
# callers are low-trust and resolve identity from the key, not from headers.
KEY_A_H   = dict(ADMIN_A_H)
KEY_B_H   = dict(ADMIN_B_H)

_db.close()


# ── Proxy call helper ─────────────────────────────────────────────────────────

def _proxy(agent: str, team: str = "developer", model: str = "gpt-4o-mini",
           key_headers: dict | None = None):
    """Send a fake proxied LLM call and return the HTTP response."""
    hdrs = {**(key_headers or KEY_A_H), "X-Guard-Agent": agent, "X-Guard-Team": team}
    fake_resp = {
        "id": "chatcmpl-lc-test", "object": "chat.completion", "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
    }
    with patch("app.routes.proxy.get_client_for_org", return_value=MagicMock()), \
         patch("app.routes.proxy.proxy_chat_complete",
               new_callable=AsyncMock, return_value=fake_resp):
        return _client.post(
            "/v1/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": "hello"}]},
            headers=hdrs,
        )


def _reg(org_id: int, agent: str) -> AssetRegistry | None:
    db = SessionLocal()
    try:
        key = _asset_key(org_id, agent)
        row = db.query(AssetRegistry).filter(
            AssetRegistry.organization_id == org_id,
            AssetRegistry.asset_key == key,
        ).first()
        # Detach from session so we can read attrs after close
        if row:
            db.expunge(row)
        return row
    finally:
        db.close()


def _tel_count(org_id: int, agent: str) -> int:
    db = SessionLocal()
    try:
        return db.query(Telemetry).filter(
            Telemetry.organization_id == org_id,
            Telemetry.agent == agent,
        ).count()
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiscovery:
    """Agents are auto-discovered on first proxy call."""

    def test_first_proxy_call_creates_unassigned_registry_row(self):
        agent = f"new-agent-{uuid.uuid4().hex[:6]}"
        r = _proxy(agent)
        assert r.status_code == 200, r.text

        reg = _reg(ORG_A_ID, agent)
        assert reg is not None, "Registry row must be created on first proxy call"
        assert reg.status == "unassigned"
        assert reg.source in ("explicit_header", "sdk_runtime", "api_key_scope", "gateway_runtime"), (
            f"Unexpected source: {reg.source!r}"
        )
        assert reg.agent_id_raw == agent

    def test_asset_key_is_sha256_of_org_colon_agent(self):
        agent = f"key-check-{uuid.uuid4().hex[:6]}"
        _proxy(agent)
        reg = _reg(ORG_A_ID, agent)
        assert reg is not None
        expected = hashlib.sha256(f"{ORG_A_ID}:{agent}".encode()).hexdigest()
        assert reg.asset_key == expected

    def test_repeated_calls_reuse_single_registry_row(self):
        agent = f"stable-{uuid.uuid4().hex[:6]}"
        _proxy(agent)
        _proxy(agent)
        _proxy(agent)

        db = SessionLocal()
        try:
            rows = db.query(AssetRegistry).filter(
                AssetRegistry.organization_id == ORG_A_ID,
                AssetRegistry.agent_id_raw == agent,
            ).all()
        finally:
            db.close()
        assert len(rows) == 1, f"Must have exactly 1 registry row; got {len(rows)}"

    def test_unassigned_agent_accumulates_telemetry(self):
        agent = f"accumulate-{uuid.uuid4().hex[:6]}"
        _proxy(agent)
        _proxy(agent)
        _proxy(agent)

        assert _tel_count(ORG_A_ID, agent) >= 3
        reg = _reg(ORG_A_ID, agent)
        assert reg is not None
        assert reg.status == "unassigned"

    def test_different_agents_get_different_asset_keys(self):
        a1 = f"distinct-a-{uuid.uuid4().hex[:6]}"
        a2 = f"distinct-b-{uuid.uuid4().hex[:6]}"
        _proxy(a1)
        _proxy(a2)
        assert _asset_key(ORG_A_ID, a1) != _asset_key(ORG_A_ID, a2)

    def test_same_agent_different_orgs_get_different_asset_keys(self):
        """Same agent name in two orgs must produce distinct asset_keys."""
        agent = "cross-org-agent"
        _proxy(agent, key_headers=KEY_A_H)
        _proxy(agent, key_headers=KEY_B_H)

        key_a = _asset_key(ORG_A_ID, agent)
        key_b = _asset_key(ORG_B_ID, agent)
        assert key_a != key_b, (
            "Same agent name in different orgs must produce different asset_keys"
        )

        reg_a = _reg(ORG_A_ID, agent)
        reg_b = _reg(ORG_B_ID, agent)
        assert reg_a is not None
        assert reg_b is not None
        assert reg_a.asset_key != reg_b.asset_key

    def test_cross_org_registry_rows_are_independent(self):
        """Claiming agent in Org A must not affect Org B's registry."""
        agent = f"cross-claim-{uuid.uuid4().hex[:6]}"
        _proxy(agent, key_headers=KEY_A_H)
        _proxy(agent, key_headers=KEY_B_H)

        # Claim in Org A
        r = _client.post(
            f"/assets/{agent}/claim",
            json={"owner": "org-a-owner@test.local", "team": "security"},
            headers=ADMIN_A_H,
        )
        assert r.status_code == 200

        # Org B's registry row must remain unassigned
        reg_b = _reg(ORG_B_ID, agent)
        assert reg_b is not None
        assert reg_b.status == "unassigned", (
            "Org B's registry entry must remain unassigned after Org A claimed theirs"
        )


class TestClaimFlow:
    """Claim transitions an unassigned agent to managed status."""

    def test_claim_sets_status_to_managed(self):
        agent = f"claim-me-{uuid.uuid4().hex[:6]}"
        _proxy(agent)

        r = _client.post(
            f"/assets/{agent}/claim",
            json={"owner": "alice@org.test",
                  "team": "security",
                  "environment": "production",
                  "criticality": "high",
                  "business_purpose": "Threat detection pipeline"},
            headers=ADMIN_A_H,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "managed"
        assert body["owner"] == "alice@org.test"
        assert body["team"] == "security"
        assert body["environment"] == "production"
        assert body["criticality"] == "high"
        assert body["claimed_at"] is not None

    def test_claim_does_not_modify_telemetry_rows(self):
        agent = f"no-tel-rewrite-{uuid.uuid4().hex[:6]}"
        _proxy(agent, team="engineering")
        _proxy(agent, team="engineering")

        # Snapshot telemetry before claim
        db = SessionLocal()
        try:
            before = [
                {c.name: getattr(r, c.name) for c in r.__table__.columns}
                for r in db.query(Telemetry).filter(
                    Telemetry.organization_id == ORG_A_ID,
                    Telemetry.agent == agent,
                ).all()
            ]
        finally:
            db.close()

        _client.post(
            f"/assets/{agent}/claim",
            json={"owner": "owner@test.local", "team": "security"},
            headers=ADMIN_A_H,
        )

        db = SessionLocal()
        try:
            after = [
                {c.name: getattr(r, c.name) for c in r.__table__.columns}
                for r in db.query(Telemetry).filter(
                    Telemetry.organization_id == ORG_A_ID,
                    Telemetry.agent == agent,
                ).all()
            ]
        finally:
            db.close()

        assert len(before) == len(after), "Claim must not add or delete telemetry rows"
        for b, a in zip(before, after):
            for col in b:
                assert b[col] == a[col], (
                    f"Column '{col}' was modified by claim: {b[col]!r} → {a[col]!r}"
                )

    def test_claim_is_idempotent(self):
        agent = f"idempotent-{uuid.uuid4().hex[:6]}"
        _proxy(agent)

        for owner in ["first@test.local", "second@test.local"]:
            r = _client.post(
                f"/assets/{agent}/claim",
                json={"owner": owner, "team": "ops"},
                headers=ADMIN_A_H,
            )
            assert r.status_code == 200
            assert r.json()["owner"] == owner

        reg = _reg(ORG_A_ID, agent)
        assert reg.status == "managed"

    def test_claim_stores_claimer_email(self):
        agent = f"claimer-{uuid.uuid4().hex[:6]}"
        _proxy(agent)
        r = _client.post(
            f"/assets/{agent}/claim",
            json={"owner": "alice@test.local"},
            headers=ADMIN_A_H,
        )
        assert r.status_code == 200
        assert r.json()["claimed_by"] == "admin-a@lifecycle.test"

    def test_canonical_team_overrides_telemetry_hint(self):
        """After claim, inventory must show registry team, not telemetry runtime hint."""
        agent = f"team-override-{uuid.uuid4().hex[:6]}"
        _proxy(agent, team="dev-hint")  # telemetry says dev-hint

        _client.post(
            f"/assets/{agent}/claim",
            json={"owner": "o@test.local", "team": "canonical-security"},
            headers=ADMIN_A_H,
        )

        r = _client.get("/assets", headers=ADMIN_A_H)
        assert r.status_code == 200
        match = next((a for a in r.json() if a.get("agent_name") == agent), None)
        assert match is not None
        assert match["team"] == "canonical-security", (
            f"Expected canonical team 'canonical-security', got {match['team']!r}"
        )

        # Telemetry must still carry the runtime hint
        db = SessionLocal()
        try:
            tel = db.query(Telemetry).filter(
                Telemetry.organization_id == ORG_A_ID,
                Telemetry.agent == agent,
            ).first()
            assert tel is not None
            assert tel.team == "dev-hint", "Telemetry team hint must remain unchanged"
        finally:
            db.close()


class TestRetireFlow:
    """Retire transitions a managed agent to retired status."""

    def _create_managed_agent(self, suffix: str) -> str:
        agent = f"retire-{suffix}"
        _proxy(agent)
        _client.post(
            f"/assets/{agent}/claim",
            json={"owner": "owner@test.local", "team": "ops"},
            headers=ADMIN_A_H,
        )
        return agent

    def test_retire_sets_status_to_retired(self):
        agent = self._create_managed_agent(uuid.uuid4().hex[:6])
        r = _client.patch(
            f"/assets/{agent}/registry",
            json={"status": "retired"},
            headers=ADMIN_A_H,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "retired"

    def test_retired_agent_excluded_from_default_inventory(self):
        agent = self._create_managed_agent(uuid.uuid4().hex[:6])
        _client.patch(f"/assets/{agent}/registry", json={"status": "retired"},
                      headers=ADMIN_A_H)

        r = _client.get("/assets", headers=ADMIN_A_H)
        assert r.status_code == 200
        names = [a.get("agent_name") for a in r.json()]
        assert agent not in names, "Retired agent must not appear in default inventory"

    def test_retired_agent_visible_with_include_retired(self):
        agent = self._create_managed_agent(uuid.uuid4().hex[:6])
        _client.patch(f"/assets/{agent}/registry", json={"status": "retired"},
                      headers=ADMIN_A_H)

        r = _client.get("/assets?include_retired=true", headers=ADMIN_A_H)
        assert r.status_code == 200
        match = next((a for a in r.json() if a.get("agent_name") == agent), None)
        assert match is not None, "Retired agent must appear when include_retired=true"
        assert match["lifecycle_status"] == "retired"

    def test_retire_preserves_all_telemetry(self):
        agent = self._create_managed_agent(uuid.uuid4().hex[:6])
        _proxy(agent)  # add a second telemetry call
        before = _tel_count(ORG_A_ID, agent)

        _client.patch(f"/assets/{agent}/registry", json={"status": "retired"},
                      headers=ADMIN_A_H)

        after = _tel_count(ORG_A_ID, agent)
        assert after == before, (
            f"Retiring must not delete telemetry. Before={before}, after={after}"
        )

    def test_retire_does_not_affect_other_org_same_agent(self):
        agent = f"retire-iso-{uuid.uuid4().hex[:6]}"
        _proxy(agent, key_headers=KEY_A_H)
        _proxy(agent, key_headers=KEY_B_H)

        # Set up managed in both orgs
        _client.post(f"/assets/{agent}/claim", json={"owner": "a@t.t", "team": "t"},
                     headers=ADMIN_A_H)
        _client.post(f"/assets/{agent}/claim", json={"owner": "b@t.t", "team": "t"},
                     headers=ADMIN_B_H)

        # Retire in Org A only
        r = _client.patch(f"/assets/{agent}/registry", json={"status": "retired"},
                          headers=ADMIN_A_H)
        assert r.status_code == 200

        # Org B's agent must remain managed
        reg_b = _reg(ORG_B_ID, agent)
        assert reg_b is not None
        assert reg_b.status == "managed", (
            "Retiring agent in Org A must not affect Org B's registry entry"
        )


class TestLifecycleTransitions:
    """Full lifecycle: unassigned → managed → retired."""

    def test_full_lifecycle_transition(self):
        agent = f"full-lc-{uuid.uuid4().hex[:6]}"

        # Step 1: Discovery — unassigned
        _proxy(agent)
        reg = _reg(ORG_A_ID, agent)
        assert reg.status == "unassigned"

        # Step 2: Claim — managed
        r = _client.post(
            f"/assets/{agent}/claim",
            json={"owner": "owner@test.local", "team": "security",
                  "environment": "production", "criticality": "critical"},
            headers=ADMIN_A_H,
        )
        assert r.status_code == 200
        reg = _reg(ORG_A_ID, agent)
        assert reg.status == "managed"
        assert reg.owner == "owner@test.local"
        assert reg.environment == "production"

        # Step 3: Retire — retired
        r = _client.patch(f"/assets/{agent}/registry", json={"status": "retired"},
                          headers=ADMIN_A_H)
        assert r.status_code == 200
        reg = _reg(ORG_A_ID, agent)
        assert reg.status == "retired"

        # Verify telemetry survived all transitions
        assert _tel_count(ORG_A_ID, agent) >= 1

    def test_managed_agent_can_be_updated(self):
        agent = f"update-lc-{uuid.uuid4().hex[:6]}"
        _proxy(agent)
        _client.post(f"/assets/{agent}/claim",
                     json={"owner": "v1@test.local", "team": "dev"},
                     headers=ADMIN_A_H)

        # Update governance metadata
        r = _client.patch(
            f"/assets/{agent}/registry",
            json={"owner": "v2@test.local", "team": "security",
                  "criticality": "critical", "environment": "production"},
            headers=ADMIN_A_H,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["owner"] == "v2@test.local"
        assert body["team"] == "security"
        assert body["criticality"] == "critical"
        assert body["status"] == "managed"  # still managed after update


class TestDiscoveryQueue:
    """Unassigned agents appear in the discovery queue."""

    def test_unassigned_agent_appears_in_discovery_queue(self):
        agent = f"queue-{uuid.uuid4().hex[:6]}"
        _proxy(agent)

        r = _client.get("/assets/registry/unassigned", headers=ADMIN_A_H)
        assert r.status_code == 200
        ids = [row.get("agent_id_raw") for row in r.json()]
        assert agent in ids, f"New agent {agent!r} must appear in unassigned queue"

    def test_claimed_agent_no_longer_in_unassigned_queue(self):
        agent = f"claimed-queue-{uuid.uuid4().hex[:6]}"
        _proxy(agent)
        _client.post(f"/assets/{agent}/claim", json={"owner": "o@t.t"},
                     headers=ADMIN_A_H)

        r = _client.get("/assets/registry/unassigned", headers=ADMIN_A_H)
        assert r.status_code == 200
        ids = [row.get("agent_id_raw") for row in r.json()]
        assert agent not in ids, "Claimed agent must not appear in unassigned queue"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
