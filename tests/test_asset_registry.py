"""
Phase 2 asset registry tests — verifies the 10 architectural constraints.

Constraint list:
 1. New unseen agent creates an `unassigned` asset automatically.
 2. Claiming the asset changes its status to `managed`.
 3. Claiming does not update historical telemetry rows.
 4. Inventory shows canonical team/environment from asset_registry.
 5. If telemetry says team_raw=Dev but registry says team=Security, inventory displays Security.
 6. Retired assets are hidden by default.
 7. Retired assets appear only when include_retired=true.
 8. Single asset lookup uses registry metadata, not telemetry-only data.
 9. RBAC checks use canonical registry team.
10. Unassigned assets still appear in the discovery queue and continue accumulating telemetry.

Each test is labelled with its constraint number.
ENV must be set before any app import — do not reorder the top block.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
import uuid
from datetime import datetime, timezone, timedelta

# ── Env setup BEFORE any app import ───────────────────────────────────────────
_db_path = f"/tmp/test_asset_reg_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-asset-registry")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
sys.path.insert(0, "/home/user/ai-asset-management")
os.chdir("/home/user/ai-asset-management")

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

# ── App imports ────────────────────────────────────────────────────────────────
from fastapi.testclient import TestClient
from app.main import app, _seed_roles_for_org, _discover_asset
from app.database import SessionLocal
from app.models import Organization, User, ApiKey, Telemetry, AssetRegistry
from app.auth import hash_password, create_token, generate_api_key
from app.assets import get_all_assets_derived, get_asset_by_name, _asset_key

# ── Module-level fixtures (shared DB) ─────────────────────────────────────────
_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")   # trigger startup migrations

_db = SessionLocal()

def _slug(n): return re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")

_org = Organization(name="AssetRegTestOrg", slug=_slug("AssetRegTestOrg"))
_db.add(_org); _db.commit(); _db.refresh(_org)
_seed_roles_for_org(_db, _org.id)
ORG_ID = _org.id

# Admin user (org-wide)
_admin = User(
    email="asset-admin@test.local", name="Asset Admin",
    hashed_password=hash_password("x"), role="admin",
    team="platform", organization_id=ORG_ID,
)
_db.add(_admin); _db.commit(); _db.refresh(_admin)
_admin_hdrs = {"Authorization": f"Bearer {create_token(_admin)}"}

# API key used for proxy calls
_raw_key, _key_prefix, _hashed = generate_api_key()
_api_key_row = ApiKey(
    name="asset-test-key", key_hash=_hashed, key_prefix=_key_prefix,
    team="platform", organization_id=ORG_ID, created_by_id=_admin.id,
)
_db.add(_api_key_row); _db.commit()

# Proxy headers — generic; individual tests override X-Guard-Agent
_PROXY_BASE = {"Authorization": f"Bearer {_raw_key}"}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fake_llm_resp(model="gpt-4o-mini"):
    return {
        "id": "chatcmpl-fake", "object": "chat.completion", "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _proxy_call(agent: str, team: str = "platform", model: str = "gpt-4o-mini"):
    """Send a fake proxied LLM call and return the HTTP response."""
    hdrs = {**_PROXY_BASE, "X-Guard-Agent": agent, "X-Guard-Team": team}
    with patch("app.main.get_client_for_org", return_value=MagicMock()), \
         patch("app.main.proxy_chat_complete", new_callable=AsyncMock,
               return_value=_fake_llm_resp(model)):
        return _client.post(
            "/v1/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": "hi"}]},
            headers=hdrs,
        )


def _reg_row(agent_id_raw: str) -> AssetRegistry | None:
    key = _asset_key(ORG_ID, agent_id_raw)
    return _db.query(AssetRegistry).filter(
        AssetRegistry.organization_id == ORG_ID,
        AssetRegistry.asset_key == key,
    ).first()


def _tel_rows(agent_id_raw: str) -> list[Telemetry]:
    return _db.query(Telemetry).filter(
        Telemetry.organization_id == ORG_ID,
        Telemetry.agent == agent_id_raw,
    ).all()


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestConstraint1_DiscoverUnassigned:
    """Rule 1: proxy call for an unknown agent creates an unassigned registry row."""

    def test_unseen_agent_creates_unassigned_row(self):
        agent = f"unseen-agent-{uuid.uuid4().hex[:6]}"
        r = _proxy_call(agent)
        assert r.status_code == 200, r.text

        _db.expire_all()
        reg = _reg_row(agent)
        assert reg is not None, "asset_registry row must be created on first proxy call"
        assert reg.status == "unassigned", f"Expected 'unassigned', got {reg.status!r}"
        assert reg.agent_id_raw == agent
        assert reg.source in ("explicit_header", "sdk_runtime", "api_key_scope", "gateway_runtime"), (
            f"Unexpected source: {reg.source!r}"
        )

    def test_asset_key_derived_from_org_and_agent_id_raw(self):
        agent = f"key-check-agent-{uuid.uuid4().hex[:6]}"
        _proxy_call(agent)
        _db.expire_all()
        reg = _reg_row(agent)
        assert reg is not None

        expected_key = hashlib.sha256(f"{ORG_ID}:{agent}".encode()).hexdigest()
        assert reg.asset_key == expected_key, (
            f"asset_key must be sha256(org_id:agent_id_raw). "
            f"Got {reg.asset_key!r}, expected {expected_key!r}"
        )


class TestConstraint2_Claim:
    """Rule 2: claiming an asset promotes its lifecycle_status to 'managed'."""

    def test_claim_sets_status_managed(self):
        agent = f"claim-me-{uuid.uuid4().hex[:6]}"
        _proxy_call(agent, team="engineering")

        r = _client.post(
            f"/assets/{agent}/claim",
            json={"owner": "alice@example.com", "team": "security",
                  "environment": "prod", "criticality": "high",
                  "business_purpose": "Threat classification"},
            headers=_admin_hdrs,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "managed"
        assert body["owner"] == "alice@example.com"
        assert body["team"] == "security"
        assert body["environment"] == "prod"
        assert body["claimed_by"] == "asset-admin@test.local"
        assert body["claimed_at"] is not None

    def test_claim_is_idempotent_second_call_still_managed(self):
        agent = f"claim-again-{uuid.uuid4().hex[:6]}"
        _proxy_call(agent)
        _client.post(f"/assets/{agent}/claim",
                     json={"owner": "bob@example.com"}, headers=_admin_hdrs)
        r = _client.post(f"/assets/{agent}/claim",
                         json={"owner": "carol@example.com"}, headers=_admin_hdrs)
        assert r.status_code == 200
        assert r.json()["status"] == "managed"
        assert r.json()["owner"] == "carol@example.com"


class TestConstraint3_ClaimNoTelemetryRewrite:
    """Rule 3: claiming must not touch historical telemetry rows."""

    def test_claim_does_not_rewrite_telemetry(self):
        agent = f"no-rewrite-{uuid.uuid4().hex[:6]}"
        # Two calls before claiming
        _proxy_call(agent, team="dev-team")
        _proxy_call(agent, team="dev-team")

        before_rows = _tel_rows(agent)
        assert len(before_rows) >= 2

        # Snapshot all telemetry values
        before_snapshots = [
            {c.name: getattr(r, c.name) for c in r.__table__.columns}
            for r in before_rows
        ]

        _client.post(
            f"/assets/{agent}/claim",
            json={"owner": "alice@example.com", "team": "security",
                  "environment": "prod"},
            headers=_admin_hdrs,
        )

        _db.expire_all()
        after_rows = _tel_rows(agent)
        assert len(after_rows) == len(before_rows), "Claiming must not add or delete telemetry rows"

        # Every field of every telemetry row must be unchanged
        for before, row in zip(before_snapshots, after_rows):
            for col, val in before.items():
                current = getattr(row, col)
                assert current == val, (
                    f"Telemetry column '{col}' was mutated by claim: "
                    f"before={val!r}, after={current!r}"
                )


class TestConstraint4And5_CanonicalTeamFromRegistry:
    """Rules 4 & 5: inventory shows canonical team/environment from asset_registry,
    overriding the telemetry runtime hint."""

    def test_inventory_uses_registry_team_not_telemetry(self):
        agent = f"team-override-{uuid.uuid4().hex[:6]}"
        # Telemetry team = "dev-hint"
        _proxy_call(agent, team="dev-hint")

        # Claim with canonical team = "security-ops"
        _client.post(
            f"/assets/{agent}/claim",
            json={"owner": "owner@x.com", "team": "security-ops",
                  "environment": "prod"},
            headers=_admin_hdrs,
        )

        # Verify telemetry still has the runtime hint
        _db.expire_all()
        tel = _tel_rows(agent)
        assert all(r.team == "dev-hint" for r in tel), (
            "Telemetry team must remain 'dev-hint' (runtime hint, not rewritten)"
        )

        # Verify inventory shows canonical team from registry
        assets = get_all_assets_derived(_db, ORG_ID)
        match = next((a for a in assets if a["agent_name"] == agent), None)
        assert match is not None, f"Agent {agent!r} not found in inventory"
        assert match["team"] == "security-ops", (
            f"Expected canonical team 'security-ops', got {match['team']!r}"
        )

    def test_inventory_uses_registry_environment_not_telemetry(self):
        agent = f"env-override-{uuid.uuid4().hex[:6]}"
        _proxy_call(agent)

        _client.post(
            f"/assets/{agent}/claim",
            json={"owner": "o@x.com", "team": "ops", "environment": "prod"},
            headers=_admin_hdrs,
        )

        assets = get_all_assets_derived(_db, ORG_ID)
        match = next((a for a in assets if a["agent_name"] == agent), None)
        assert match is not None
        assert match["environment"] == "prod", (
            f"Expected canonical environment 'prod', got {match['environment']!r}"
        )

    def test_telemetry_team_used_as_fallback_when_registry_unset(self):
        agent = f"team-fallback-{uuid.uuid4().hex[:6]}"
        _proxy_call(agent, team="fallback-team")
        # Do NOT claim — registry.team is None

        assets = get_all_assets_derived(_db, ORG_ID)
        match = next((a for a in assets if a["agent_name"] == agent), None)
        assert match is not None
        assert match["team"] == "fallback-team", (
            "Before claiming, inventory should fall back to telemetry team hint"
        )


class TestConstraint6And7_RetiredAssets:
    """Rules 6 & 7: retired assets hidden by default, visible with include_retired=true."""

    def _retire(self, agent: str):
        _proxy_call(agent)
        _client.post(f"/assets/{agent}/claim",
                     json={"owner": "x@x.com", "team": "ops"},
                     headers=_admin_hdrs)
        r = _client.patch(
            f"/assets/{agent}/registry",
            json={"status": "retired"},
            headers=_admin_hdrs,
        )
        assert r.status_code == 200, r.text

    def test_retired_excluded_from_default_inventory(self):
        agent = f"retired-hidden-{uuid.uuid4().hex[:6]}"
        self._retire(agent)

        assets = get_all_assets_derived(_db, ORG_ID, include_retired=False)
        names = [a["agent_name"] for a in assets]
        assert agent not in names, f"Retired asset {agent!r} must not appear in default inventory"

    def test_retired_visible_with_include_retired(self):
        agent = f"retired-shown-{uuid.uuid4().hex[:6]}"
        self._retire(agent)

        assets = get_all_assets_derived(_db, ORG_ID, include_retired=True)
        match = next((a for a in assets if a["agent_name"] == agent), None)
        assert match is not None, "Retired asset must appear when include_retired=True"
        assert match["lifecycle_status"] == "retired"

    def test_retired_excluded_via_api_by_default(self):
        agent = f"api-retired-{uuid.uuid4().hex[:6]}"
        self._retire(agent)

        r = _client.get("/assets", headers=_admin_hdrs)
        assert r.status_code == 200
        names = [a["agent_name"] for a in r.json()]
        assert agent not in names, "Retired asset must not appear in GET /assets default response"

    def test_retired_included_via_api_with_flag(self):
        agent = f"api-retired-incl-{uuid.uuid4().hex[:6]}"
        self._retire(agent)

        r = _client.get("/assets?include_retired=true", headers=_admin_hdrs)
        assert r.status_code == 200
        names = [a["agent_name"] for a in r.json()]
        assert agent in names, "Retired asset must appear when include_retired=true"

    def test_retired_telemetry_rows_preserved(self):
        """Retiring an asset must not delete or alter its telemetry."""
        agent = f"retired-tel-{uuid.uuid4().hex[:6]}"
        # Make two proxy calls and claim first so we can retire
        _proxy_call(agent)
        _proxy_call(agent)
        _client.post(f"/assets/{agent}/claim",
                     json={"owner": "x@x.com", "team": "ops"},
                     headers=_admin_hdrs)

        # Snapshot count AFTER all setup proxy calls, before the retire PATCH
        _db.expire_all()
        before_count = len(_tel_rows(agent))

        # Retire via PATCH only — no further proxy calls
        r = _client.patch(
            f"/assets/{agent}/registry",
            json={"status": "retired"},
            headers=_admin_hdrs,
        )
        assert r.status_code == 200

        _db.expire_all()
        after_count = len(_tel_rows(agent))
        assert after_count == before_count, (
            f"Retiring must not delete telemetry rows. Before={before_count}, after={after_count}"
        )


class TestConstraint8_SingleAssetRegistryMerge:
    """Rule 8: GET /assets/{agent} returns registry metadata, not telemetry-only data."""

    def test_get_asset_returns_governance_fields(self):
        agent = f"single-lookup-{uuid.uuid4().hex[:6]}"
        _proxy_call(agent, team="dev-hint")

        _client.post(
            f"/assets/{agent}/claim",
            json={"owner": "admin@org.com", "team": "security",
                  "environment": "staging", "criticality": "critical",
                  "business_purpose": "Fraud detection pipeline"},
            headers=_admin_hdrs,
        )

        r = _client.get(f"/assets/{agent}", headers=_admin_hdrs)
        assert r.status_code == 200, r.text
        body = r.json()

        assert body["owner"] == "admin@org.com", f"owner from registry expected, got {body['owner']!r}"
        assert body["team"] == "security", f"canonical team expected, got {body['team']!r}"
        assert body["environment"] == "staging"
        assert body["criticality"] == "critical"
        assert body["business_purpose"] == "Fraud detection pipeline"
        assert body["lifecycle_status"] == "managed"
        assert body["asset_key"] is not None

    def test_get_asset_governance_fields_are_none_before_claim(self):
        agent = f"unclaimed-single-{uuid.uuid4().hex[:6]}"
        _proxy_call(agent, team="some-team")

        r = _client.get(f"/assets/{agent}", headers=_admin_hdrs)
        assert r.status_code == 200
        body = r.json()

        assert body["lifecycle_status"] == "unassigned"
        assert body["owner"] is None
        assert body["environment"] is None
        assert body["criticality"] is None
        # team falls back to telemetry hint when registry.team is null
        assert body["team"] == "some-team"


class TestConstraint9_RBACUsesCanonicalTeam:
    """Rule 9: RBAC checks use the canonical registry team, not the telemetry hint."""

    def _make_analyst(self, team: str) -> dict:
        user = User(
            email=f"analyst-{uuid.uuid4().hex[:6]}@test.local",
            name="Analyst",
            hashed_password=hash_password("x"),
            role="analyst",
            team=team,
            organization_id=ORG_ID,
        )
        _db.add(user); _db.commit(); _db.refresh(user)
        return {"Authorization": f"Bearer {create_token(user)}"}

    def test_analyst_can_access_asset_when_canonical_team_matches(self):
        agent = f"rbac-match-{uuid.uuid4().hex[:6]}"
        # Telemetry team = "dev" (runtime hint)
        _proxy_call(agent, team="dev")

        # Canonical team = "security" (from registry after claim)
        _client.post(
            f"/assets/{agent}/claim",
            json={"owner": "o@x.com", "team": "security"},
            headers=_admin_hdrs,
        )

        # Analyst whose team = "security" should access this asset
        analyst_hdrs = self._make_analyst("security")
        r = _client.get(f"/assets/{agent}", headers=analyst_hdrs)
        assert r.status_code == 200, (
            f"Analyst with canonical team should access asset. Got {r.status_code}: {r.text}"
        )

    def test_analyst_denied_when_canonical_team_differs(self):
        agent = f"rbac-deny-{uuid.uuid4().hex[:6]}"
        _proxy_call(agent, team="engineering")
        _client.post(
            f"/assets/{agent}/claim",
            json={"owner": "o@x.com", "team": "security"},
            headers=_admin_hdrs,
        )

        # Analyst whose team = "finance" must be denied
        analyst_hdrs = self._make_analyst("finance")
        r = _client.get(f"/assets/{agent}", headers=analyst_hdrs)
        assert r.status_code == 403, (
            f"Analyst from different team must be denied. Got {r.status_code}"
        )


class TestConstraint10_UnassignedAccumulatesTelemetry:
    """Rule 10: unassigned assets appear in discovery queue and keep accumulating telemetry."""

    def test_unassigned_appears_in_discovery_queue(self):
        agent = f"queue-check-{uuid.uuid4().hex[:6]}"
        _proxy_call(agent)

        r = _client.get("/assets/registry/unassigned", headers=_admin_hdrs)
        assert r.status_code == 200, r.text
        ids = [row["agent_id_raw"] for row in r.json()]
        assert agent in ids, f"{agent!r} must appear in unassigned discovery queue"

    def test_unassigned_asset_continues_accumulating_telemetry(self):
        agent = f"accumulate-{uuid.uuid4().hex[:6]}"
        # Three calls while asset remains unassigned
        _proxy_call(agent)
        _proxy_call(agent)
        _proxy_call(agent)

        _db.expire_all()
        tel = _tel_rows(agent)
        assert len(tel) >= 3, (
            f"Unassigned asset must accumulate telemetry rows. Got {len(tel)}"
        )

        # Registry row must still be unassigned
        reg = _reg_row(agent)
        assert reg is not None
        assert reg.status == "unassigned"

    def test_unassigned_appears_in_inventory_with_cost(self):
        agent = f"unassigned-cost-{uuid.uuid4().hex[:6]}"
        _proxy_call(agent)
        _proxy_call(agent)

        r = _client.get("/assets", headers=_admin_hdrs)
        assert r.status_code == 200
        match = next((a for a in r.json() if a["agent_name"] == agent), None)
        assert match is not None, "Unassigned asset must appear in inventory"
        assert match["lifecycle_status"] == "unassigned"
        assert match["total_calls"] >= 2
        # cost is derived from telemetry — even unassigned assets accumulate it
        assert match["total_cost_usd"] >= 0


# ── Additional edge cases ──────────────────────────────────────────────────────

class TestAssetKeyStability:
    """asset_key must be stable — same org+agent always yields same key."""

    def test_repeated_calls_reuse_same_registry_row(self):
        agent = f"stable-key-{uuid.uuid4().hex[:6]}"
        _proxy_call(agent)
        _proxy_call(agent)
        _proxy_call(agent)

        _db.expire_all()
        rows = _db.query(AssetRegistry).filter(
            AssetRegistry.organization_id == ORG_ID,
            AssetRegistry.agent_id_raw == agent,
        ).all()
        assert len(rows) == 1, (
            f"Multiple proxy calls for the same agent must create exactly 1 registry row, got {len(rows)}"
        )

    def test_asset_key_is_sha256_of_org_colon_agent(self):
        agent = f"key-formula-{uuid.uuid4().hex[:6]}"
        _proxy_call(agent)
        _db.expire_all()

        reg = _reg_row(agent)
        assert reg is not None
        expected = hashlib.sha256(f"{ORG_ID}:{agent}".encode()).hexdigest()
        assert reg.asset_key == expected

    def test_different_agents_get_different_keys(self):
        agent_a = f"agent-a-{uuid.uuid4().hex[:6]}"
        agent_b = f"agent-b-{uuid.uuid4().hex[:6]}"
        _proxy_call(agent_a)
        _proxy_call(agent_b)
        _db.expire_all()

        key_a = _asset_key(ORG_ID, agent_a)
        key_b = _asset_key(ORG_ID, agent_b)
        assert key_a != key_b


class TestLifecycleFilter:
    """lifecycle_status filter on GET /assets works correctly."""

    def test_filter_lifecycle_unassigned(self):
        agent = f"lc-unassigned-{uuid.uuid4().hex[:6]}"
        _proxy_call(agent)

        r = _client.get("/assets?lifecycle_status=unassigned", headers=_admin_hdrs)
        assert r.status_code == 200
        for a in r.json():
            assert a["lifecycle_status"] in ("unassigned", None), (
                f"Unexpected lifecycle_status {a['lifecycle_status']!r} when filtered to unassigned"
            )

    def test_filter_lifecycle_managed(self):
        agent = f"lc-managed-{uuid.uuid4().hex[:6]}"
        _proxy_call(agent)
        _client.post(f"/assets/{agent}/claim",
                     json={"owner": "x@x.com", "team": "t"},
                     headers=_admin_hdrs)

        r = _client.get("/assets?lifecycle_status=managed", headers=_admin_hdrs)
        assert r.status_code == 200
        names = [a["agent_name"] for a in r.json()]
        assert agent in names, "Managed asset must appear in lifecycle_status=managed filter"
        for a in r.json():
            assert a["lifecycle_status"] == "managed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
