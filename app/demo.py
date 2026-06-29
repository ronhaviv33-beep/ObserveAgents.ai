"""Demo-service helpers: synthetic org + admin seeding and identity constants.

Everything here is only ever invoked when app.config.is_demo_mode() is True (the
separate demo Render service).  It is never imported into a production code path
that runs unconditionally.
"""
import secrets

from sqlalchemy.orm import Session

DEMO_ORG_NAME = "Northwind Labs (Demo)"
DEMO_ORG_SLUG = "demo"
DEMO_ADMIN_EMAIL = "demo@observeagents.ai"
DEMO_ADMIN_NAME = "Demo User"


def get_demo_admin(db: Session):
    """Return the synthetic demo admin user, or None if not seeded yet."""
    from app.models import User
    return db.query(User).filter(User.email == DEMO_ADMIN_EMAIL).first()


def ensure_demo_seed(db: Session) -> None:
    """Idempotently create the synthetic demo org + read-only demo admin and
    populate demo data.  Safe to call on every boot."""
    from app.models import Organization, User
    from app.auth import hash_password
    from app.roles import seed_roles_for_org
    from app.routes.admin import populate_demo_org

    org = db.query(Organization).filter(Organization.slug == DEMO_ORG_SLUG).first()
    if not org:
        org = Organization(name=DEMO_ORG_NAME, slug=DEMO_ORG_SLUG)
        db.add(org)
        db.flush()
        seed_roles_for_org(db, org.id)
        db.commit()
        db.refresh(org)

    admin = get_demo_admin(db)
    if not admin:
        # Random unusable password — login happens only via the no-credential
        # /auth/demo-login endpoint, never with a password.
        db.add(User(
            email=DEMO_ADMIN_EMAIL,
            name=DEMO_ADMIN_NAME,
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            role="admin",
            team="Platform",
            organization_id=org.id,
            is_platform_admin=False,
        ))
        db.commit()

    # Populate synthetic data (idempotent) and enable demo_mode for the org so the
    # is_demo=True rows are surfaced by the dashboard read endpoints.
    populate_demo_org(db, org.id)
