"""
Tests for legacy-database schema repair and migration idempotency.

Reproduces the production failure where a long-lived DB (created by an older
code era) was missing ORM-model columns on asset_registry, wedging Alembic and
500-ing /intelligence/asset-summary:

  1. ensure_model_columns() adds missing columns and backfills model defaults
     (runs automatically at app import — the legacy table is built first).
  2. /intelligence/asset-summary returns 200 on the repaired DB and includes
     the gateway-era asset with `gateway_observed` status.
  3. alembic upgrade(head) completes on a create_all()-built DB stamped at the
     oldest revision (guarded migrations must skip what already exists).
  4. Registry-only (gateway-discovered) assets appear in asset-summary with
     empty runtime evidence on a modern DB too.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import uuid

# ── Env setup BEFORE any app import ───────────────────────────────────────────
_db_path = f"/tmp/test_schema_repair_{uuid.uuid4().hex[:8]}.db"
os.environ.setdefault("JWT_SECRET",                "testsecret-schema-repair")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"

_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

# ── Build a LEGACY-era asset_registry BEFORE the app imports ─────────────────
# (mimics production: table created by an old code version, so it lacks the
# discovery_*, confidence_score, asset_type, capabilities, first_seen_at and
# is_demo columns that current models expect)
_conn = sqlite3.connect(_db_path)
_conn.executescript("""
CREATE TABLE asset_registry (
  id INTEGER PRIMARY KEY,
  organization_id INTEGER NOT NULL,
  asset_key VARCHAR(64),
  agent_id_raw VARCHAR(256),
  agent_name VARCHAR(256),
  owner VARCHAR(256),
  team VARCHAR(128),
  environment VARCHAR(64),
  criticality VARCHAR(32),
  business_purpose TEXT,
  status VARCHAR(32),
  source VARCHAR(32),
  claimed_by VARCHAR(256),
  claimed_at DATETIME,
  created_at DATETIME,
  updated_at DATETIME
);
INSERT INTO asset_registry
  (organization_id, asset_key, agent_id_raw, agent_name, environment, status, source, created_at, updated_at)
VALUES
  (1, 'legacygatewaykey0000000000000000000000000000000000000000000000ab',
   'billing-agent', 'billing-agent', 'production', 'unassigned', 'discovered',
   '2026-01-15 10:00:00', '2026-06-01 12:00:00');
""")
_conn.commit()
_conn.close()

from fastapi.testclient import TestClient          # noqa: E402
from app.main import app                            # noqa: E402  (import runs repair)
from app.database import SessionLocal, engine, Base # noqa: E402
from app.models import Organization, User, AssetRegistry  # noqa: E402
from app.auth import hash_password, create_token    # noqa: E402

_client = TestClient(app, raise_server_exceptions=True)
_client.get("/health")


def _auth_headers(db, org_id):
    sfx = uuid.uuid4().hex[:6]
    user = User(
        email=f"schema-repair-{sfx}@example.com",
        name=f"Schema Repair {sfx}",
        hashed_password=hash_password("pass"),
        organization_id=org_id,
        role="admin",
        team="eng",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_token(user)
    return {"Authorization": f"Bearer {token}"}


def test_repair_added_missing_columns_and_backfilled_defaults():
    """Order-independent repair check: build a legacy-shaped asset_registry on a
    dedicated side DB and run ensure_model_columns against that engine."""
    import sqlalchemy as sa
    from app.startup import ensure_model_columns

    side_db = f"/tmp/test_schema_repair_side_{uuid.uuid4().hex[:8]}.db"
    conn = sqlite3.connect(side_db)
    conn.executescript("""
    CREATE TABLE asset_registry (
      id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL, asset_key VARCHAR(64),
      agent_id_raw VARCHAR(256), agent_name VARCHAR(256), owner VARCHAR(256), team VARCHAR(128),
      environment VARCHAR(64), criticality VARCHAR(32), business_purpose TEXT, status VARCHAR(32),
      source VARCHAR(32), claimed_by VARCHAR(256), claimed_at DATETIME, created_at DATETIME, updated_at DATETIME
    );
    INSERT INTO asset_registry (organization_id, asset_key, agent_id_raw, agent_name, status, source)
    VALUES (1, 'sidekey', 'side-billing-agent', 'side-billing-agent', 'unassigned', 'discovered');
    """)
    conn.commit()
    conn.close()

    side_engine = sa.create_engine(f"sqlite:///{side_db}")
    ensure_model_columns(engine=side_engine)
    ensure_model_columns(engine=side_engine)  # idempotent

    conn = sqlite3.connect(side_db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(asset_registry)")}
    expected = {
        "discovery_status", "discovery_source", "discovery_reason", "evidence",
        "confidence_score", "asset_type", "capabilities", "first_seen_at", "is_demo",
    }
    assert expected <= cols, f"missing after repair: {expected - cols}"

    row = conn.execute(
        "SELECT discovery_status, discovery_source, confidence_score, is_demo, asset_type "
        "FROM asset_registry WHERE agent_id_raw='side-billing-agent'"
    ).fetchone()
    conn.close()
    assert row == ("verified", "gateway_telemetry", 95.0, 0, "agent")
    side_engine.dispose()
    os.unlink(side_db)


def test_asset_summary_returns_200_on_repaired_legacy_db():
    """The exact production regression: full-row AssetRegistry query must not 500.

    When this module imports first, the app DB was born with the legacy-shaped
    asset_registry built above and repaired at startup. When another test module
    imported the app first (shared pytest process), the pre-import legacy table
    lives in an unused DB file — recreate the gateway-era row via ORM so the
    endpoint assertions still run against a real row.
    """
    db = SessionLocal()
    try:
        # run_org_migration seeded a default org at startup; attach the legacy
        # row to a real org so it is visible through the org-scoped endpoint.
        org = db.query(Organization).first()
        assert org is not None
        legacy = db.query(AssetRegistry).filter(
            AssetRegistry.agent_id_raw == "billing-agent"
        ).first()
        if legacy is not None:
            legacy.organization_id = org.id
        else:
            db.add(AssetRegistry(
                organization_id=org.id,
                asset_key="legacygatewaykey0000000000000000000000000000000000000000000000ab",
                agent_id_raw="billing-agent",
                agent_name="billing-agent",
                environment="production",
                status="unassigned",
                source="discovered",
                discovery_source="gateway_telemetry",
                is_demo=False,
            ))
        db.commit()
        headers = _auth_headers(db, org.id)
    finally:
        db.close()

    r = _client.get("/intelligence/asset-summary", headers=headers)
    assert r.status_code == 200, r.text
    assets = r.json()["assets"]
    billing = [a for a in assets if a["asset_name"] == "billing-agent"]
    assert billing, f"gateway-era asset missing from summary: {assets}"
    a = billing[0]
    assert "gateway_observed" in a["status"]
    assert a["trace_count"] == 0 and a["span_count"] == 0
    assert a["models"] == [] and a["tools"] == []
    assert a["last_seen"]  # backfilled/legacy timestamp serializes


def test_alembic_upgrade_completes_on_create_all_db():
    """Guarded migrations: upgrade to head on a DB where create_all() already
    built every table (stamped at the oldest revision, like a wedged prod)."""
    import pathlib
    import sqlalchemy as sa
    from alembic.config import Config as AlembicConfig
    from alembic import command as alembic_command

    side_db = f"/tmp/test_schema_repair_mig_{uuid.uuid4().hex[:8]}.db"
    url = f"sqlite:///{side_db}"
    side_engine = sa.create_engine(url)
    Base.metadata.create_all(bind=side_engine)

    cfg = AlembicConfig(str(pathlib.Path(_repo_root) / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", str(pathlib.Path(_repo_root) / "alembic"))
    # alembic/env.py overrides sqlalchemy.url from DATABASE_URL, so point the
    # env var at the side DB for the duration of the migration commands.
    prev_url = os.environ["DATABASE_URL"]
    os.environ["DATABASE_URL"] = url
    try:
        alembic_command.stamp(cfg, "99d18c0f5741")
        alembic_command.upgrade(cfg, "head")  # must not raise
    finally:
        os.environ["DATABASE_URL"] = prev_url

    with side_engine.connect() as c:
        version = c.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
    # Compare against the actual script head so new migrations don't stale this test.
    from alembic.script import ScriptDirectory
    assert version == ScriptDirectory.from_config(cfg).get_current_head()
    side_engine.dispose()
    os.unlink(side_db)


def test_gateway_only_registry_asset_appears_in_summary_on_modern_db():
    db = SessionLocal()
    try:
        sfx = uuid.uuid4().hex[:6]
        org = Organization(name=f"gw-org-{sfx}", slug=f"gw-org-{sfx}")
        db.add(org)
        db.flush()
        db.add(AssetRegistry(
            organization_id=org.id,
            asset_key="a" * 64,
            agent_id_raw="proxy-only-agent",
            agent_name="proxy-only-agent",
            environment="production",
            status="unassigned",
            source="discovered",
            discovery_source="gateway_telemetry",
            is_demo=False,
        ))
        db.commit()
        headers = _auth_headers(db, org.id)
    finally:
        db.close()

    r = _client.get("/intelligence/asset-summary", headers=headers)
    assert r.status_code == 200, r.text
    assets = r.json()["assets"]
    assert len(assets) == 1
    a = assets[0]
    assert a["asset_name"] == "proxy-only-agent"
    assert a["status"] == ["gateway_observed"]
    assert a["span_count"] == 0 and a["providers"] == []
