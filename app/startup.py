"""
Startup lifecycle functions for ObserveAgents.ai.

DB initialization contract — these must be called in order from app/main.py:

  1. Base.metadata.create_all(bind=engine)   [in main.py at module level]
     On a fresh DB: creates all tables from ORM models.
     On an existing DB: no-op — SQLAlchemy never drops or alters existing tables.

  2. run_alembic_migrations()
     On a fresh DB: stamps the DB as 'head' (skips the initial no-op baseline
     migration that matches the schema create_all() just built), then runs
     upgrade to head.
     On an existing DB: skips the stamp, runs any pending migrations only.
     This guarantees: fresh DB gets schema via ORM (fast), existing DB gets
     incremental migrations via Alembic (safe).

  3. run_org_migration() → seed_roles() → backfill_asset_keys() →
     backfill_discovery_source() → seed_pricing_registry()
     All are idempotent data backfills safe to re-run on every boot.
"""
import os
import hashlib
import logging

_log = logging.getLogger("ai_asset_mgmt")


def run_alembic_migrations() -> None:
    """Run any pending Alembic migrations on startup."""
    from alembic.config import Config as AlembicConfig
    from alembic import command as alembic_command
    import pathlib
    from app.database import engine
    from sqlalchemy import inspect as _sqlainspect, text as _sqlatext

    cfg = AlembicConfig(str(pathlib.Path(__file__).parent.parent / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL", "sqlite:////data/ai_asset_mgmt.db"))
    cfg.set_main_option("script_location", str(pathlib.Path(__file__).parent.parent / "alembic"))

    # On a fresh DB (no alembic_version table, or empty alembic_version table),
    # stamp head so Alembic doesn't re-run the initial migration on a schema
    # that create_all() already built.
    with engine.connect() as _conn:
        _tables = _sqlainspect(_conn).get_table_names()
        _needs_stamp = "alembic_version" not in _tables or not _conn.execute(
            _sqlatext("SELECT version_num FROM alembic_version")
        ).fetchall()
    if _needs_stamp:
        alembic_command.stamp(cfg, "head")
    alembic_command.upgrade(cfg, "head")


def ensure_model_columns(engine=None) -> None:
    """
    Schema self-repair for long-lived databases.

    create_all() creates missing *tables* but never alters existing ones, and a
    failed/stuck Alembic history can leave ORM-model columns absent from tables
    created in an older code era (observed in production: asset_registry was
    missing the discovery_* columns, so any full-row query 500'd). For every
    model table that already exists, add any missing columns via
    ALTER TABLE ... ADD COLUMN and backfill scalar defaults so NOT NULL model
    semantics keep holding at the ORM layer. Purely additive and idempotent.
    """
    from datetime import datetime, timezone
    from sqlalchemy import inspect as _sqlainspect, text as _sqlatext
    from app.database import engine as _app_engine, Base
    import app.models  # noqa: F401 — registers all model tables on Base.metadata

    engine = engine if engine is not None else _app_engine
    added: list[str] = []
    with engine.connect() as conn:
        inspector = _sqlainspect(conn)
        existing_tables = set(inspector.get_table_names())
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # brand-new table — create_all already built it in full
            existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing_cols:
                    continue
                ddl_type = col.type.compile(dialect=engine.dialect)
                conn.execute(_sqlatext(
                    f'ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl_type}'
                ))

                # Backfill the model default so existing rows read like new ones.
                default = None
                if col.default is not None:
                    if col.default.is_scalar:
                        default = col.default.arg
                    elif col.default.is_callable:
                        try:
                            default = col.default.arg.__wrapped__()  # plain callable
                        except AttributeError:
                            try:
                                default = col.default.arg()
                            except TypeError:
                                default = col.default.arg(None)  # context-style callable
                        except Exception:
                            default = None
                        if isinstance(default, datetime) and default.tzinfo is None:
                            default = default.replace(tzinfo=timezone.utc)
                if default is not None:
                    conn.execute(
                        _sqlatext(
                            f'UPDATE {table.name} SET {col.name} = :dflt '
                            f'WHERE {col.name} IS NULL'
                        ),
                        {"dflt": default},
                    )
                added.append(f"{table.name}.{col.name}")
        conn.commit()

    if added:
        _log.warning(
            "Schema repair: added %d missing column(s): %s",
            len(added), ", ".join(added),
        )


def run_org_migration() -> None:
    """One-time org migration backfill. Idempotent — safe to call every boot."""
    from app.migrate_orgs import run as _run
    _run()


def seed_roles() -> None:
    """Seed default roles for every existing org. Idempotent — safe to re-run."""
    from app.database import SessionLocal
    from app.models import Organization
    from app.roles import seed_roles_for_org

    db = SessionLocal()
    try:
        for org in db.query(Organization).all():
            seed_roles_for_org(db, org.id)
    finally:
        db.close()


def backfill_asset_keys() -> None:
    """
    For existing telemetry rows that predate Phase 2, generate a stable asset_key
    from sha256(org_id + ':' + agent_name) and insert the corresponding
    asset_registry row as 'discovered' if it doesn't already exist.
    """
    from app.database import SessionLocal
    from app.models import Telemetry as _Telemetry, AssetRegistry as _AssetRegistry

    db = SessionLocal()
    try:
        combos = (
            db.query(_Telemetry.organization_id, _Telemetry.agent)
            .filter(
                _Telemetry.asset_key.is_(None),
                _Telemetry.organization_id.isnot(None),
            )
            .distinct()
            .all()
        )
        if not combos:
            return

        for org_id, agent_name in combos:
            if not agent_name or not org_id:
                continue
            asset_key = hashlib.sha256(f"{org_id}:{agent_name}".encode()).hexdigest()

            db.query(_Telemetry).filter(
                _Telemetry.organization_id == org_id,
                _Telemetry.agent == agent_name,
                _Telemetry.asset_key.is_(None),
            ).update(
                {"asset_key": asset_key, "agent_id_raw": agent_name},
                synchronize_session=False,
            )

            if not db.query(_AssetRegistry).filter(
                _AssetRegistry.organization_id == org_id,
                _AssetRegistry.asset_key == asset_key,
            ).first():
                db.add(_AssetRegistry(
                    organization_id=org_id,
                    asset_key=asset_key,
                    agent_id_raw=agent_name,
                    agent_name=agent_name,
                    status="unassigned",
                    source="discovered",
                ))

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def backfill_discovery_source() -> None:
    """
    Data backfill: correct discovery_source for agents that were seen before SDK
    headers were attached. Runs at every startup — idempotent, touches only rows
    that need it.
      source='sdk_runtime'     → discovery_source='sdk_runtime'
      source in (explicit_header, api_key_scope) with gateway_runtime → gateway_telemetry
    """
    from sqlalchemy import text as _text
    from app.database import engine

    with engine.connect() as conn:
        try:
            conn.execute(_text(
                "UPDATE asset_registry SET discovery_source='sdk_runtime' "
                "WHERE source='sdk_runtime' AND discovery_source!='sdk_runtime'"
            ))
            conn.execute(_text(
                "UPDATE asset_registry SET discovery_source='gateway_telemetry' "
                "WHERE source IN ('explicit_header','api_key_scope') AND discovery_source='gateway_runtime'"
            ))
            conn.commit()
        except Exception:
            pass  # table may not exist yet on first boot — create_all handles it


def seed_pricing_registry() -> None:
    """Seed ModelPricing table from built-in COST_PER_1M on first boot, then start
    the background sync thread. Both are idempotent."""
    from app.database import SessionLocal
    from app import pricing_registry as _pr

    db = SessionLocal()
    try:
        created = _pr.seed_defaults(db)
        if created:
            _log.info("Pricing registry: %d models seeded", created)
    except Exception as exc:
        _log.warning("Pricing registry seed warning (non-fatal): %s", exc)
    finally:
        db.close()

    try:
        _pr.start_background_sync()
    except Exception as exc:
        _log.warning("Pricing sync thread non-fatal: %s", exc)


def check_secrets() -> list[str]:
    """
    Validate required secrets at startup. Returns a list of warning strings
    for any that are missing or invalid. Exposed in /health so monitoring can
    catch misconfigured deployments before users hit cryptic errors.
    """
    warnings: list[str] = []

    raw = os.getenv("CREDENTIAL_ENCRYPTION_KEY", "")
    if not raw:
        msg = (
            "CREDENTIAL_ENCRYPTION_KEY is not set. "
            "Organization AI Providers (BYOK credential storage) will not work. "
            "Generate a key with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
        _log.error("STARTUP SECRET MISSING: %s", msg)
        warnings.append(msg)
    else:
        try:
            from cryptography.fernet import Fernet as _Fernet
            _Fernet(raw.encode())
        except Exception as exc:
            msg = (
                f"CREDENTIAL_ENCRYPTION_KEY is set but is not a valid Fernet key: {exc}. "
                "Organization AI Providers will not work. "
                "Regenerate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
            _log.error("STARTUP SECRET INVALID: %s", msg)
            warnings.append(msg)

    if warnings and os.getenv("FAIL_FAST_ON_MISSING_SECRETS", "").lower() == "true":
        _log.critical(
            "FAIL_FAST_ON_MISSING_SECRETS=true — aborting startup due to missing secrets."
        )
        import sys as _sys
        _sys.exit(1)

    return warnings
