"""
One-time migration: create the organizations table, seed the platform org,
and backfill every existing ApiKey and User to it.

Run once after deploying the new models:
    python -m app.migrate_orgs

Safe to run multiple times — idempotent.
"""
import logging
from app.database import engine, SessionLocal
from app.models import Base, Organization, ApiKey, User, ProviderCredential, Telemetry, encrypt_credential
import os

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


def run():
    # Create all new tables (organizations, provider_credentials, new columns)
    Base.metadata.create_all(bind=engine)
    log.info("Tables created / verified.")

    db = SessionLocal()
    try:
        # ── 1. Seed platform org ──────────────────────────────────────────────
        platform_org = db.query(Organization).filter(Organization.is_internal == True).first()  # noqa: E712
        if not platform_org:
            platform_org = Organization(
                name="Platform (internal)",
                slug="platform",
                is_internal=True,
            )
            db.add(platform_org)
            db.flush()
            log.info(f"Created platform org: id={platform_org.id} slug=platform")
        else:
            log.info(f"Platform org already exists: id={platform_org.id}")

        # ── 2. Seed platform org's provider credentials from env vars ────────
        #    Only seeded if the env vars exist and no credential is stored yet.
        for provider, env_var, base_url in [
            ("openai",    "OPENAI_API_KEY",    None),
            ("anthropic", "ANTHROPIC_API_KEY", None),
            ("google",    "GOOGLE_API_KEY",    None),
            ("local",     "LOCAL_LLM_URL",     None),
        ]:
            raw = os.getenv(env_var, "")
            if not raw or raw == "your-openai-api-key-here":
                continue
            existing = db.query(ProviderCredential).filter(
                ProviderCredential.organization_id == platform_org.id,
                ProviderCredential.provider == provider,
            ).first()
            if existing:
                log.info(f"  Provider credential already exists: org=platform provider={provider}")
                continue
            try:
                enc = encrypt_credential(raw)
                last4 = raw[-4:] if len(raw) >= 4 else raw
                cred = ProviderCredential(
                    organization_id=platform_org.id,
                    provider=provider,
                    encrypted_key=enc,
                    last4=last4,
                    base_url=base_url,
                )
                db.add(cred)
                log.info(f"  Seeded provider credential: org=platform provider={provider} last4=...{last4}")
            except RuntimeError as e:
                log.warning(f"  Cannot seed {provider} credential: {e}")

        # ── 3. Backfill existing ApiKeys → platform org ───────────────────────
        unset_keys = db.query(ApiKey).filter(ApiKey.organization_id == None).all()  # noqa: E711
        if unset_keys:
            for key in unset_keys:
                key.organization_id = platform_org.id
            log.info(f"Backfilled {len(unset_keys)} api_keys → platform org")
        else:
            log.info("All api_keys already have organization_id.")

        # ── 4. Backfill existing Users → platform org ─────────────────────────
        unset_users = db.query(User).filter(User.organization_id == None).all()  # noqa: E711
        if unset_users:
            for user in unset_users:
                user.organization_id = platform_org.id
            log.info(f"Backfilled {len(unset_users)} users → platform org")
        else:
            log.info("All users already have organization_id.")

        # ── 5. Backfill existing Telemetry rows → platform org ────────────────
        unset_tel = db.query(Telemetry).filter(Telemetry.organization_id == None).all()  # noqa: E711
        if unset_tel:
            for row in unset_tel:
                row.organization_id = platform_org.id
            log.info(f"Backfilled {len(unset_tel)} telemetry rows → platform org")
        else:
            log.info("All telemetry rows already have organization_id.")

        db.commit()
        log.info("Migration complete.")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
