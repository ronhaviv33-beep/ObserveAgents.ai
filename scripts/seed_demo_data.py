#!/usr/bin/env python3
"""
Demo seed data for the Enterprise AI Intelligence platform.

Seeds one demo organization ("Acme AI Operations") with a demo admin user and
five realistic AI systems observed via the real OTel ingestion path. The
system definitions and seeding logic live in app/demo_otel_seed.py — the same
module the platform-admin populate endpoint uses — so the CLI and the
dashboard's "Populate Organization" button produce identical demo data.

All data is synthetic. No real prompts, responses, secrets, or PII.
Idempotent: safe to run any number of times.

Usage (from the repo root):
    python scripts/seed_demo_data.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import engine, SessionLocal          # noqa: E402
from app.models import (                                # noqa: E402
    AssetCapability, AssetFinding, AssetRegistry, Base,
    Organization, OtelAsset, User,
)
from app.demo_otel_seed import (                        # noqa: E402
    DEMO_SERVICE_NAMES, DEMO_SYSTEMS, demo_trace_id, seed_otel_demo,
)

# Back-compat aliases (tests reference these names)
_trace_id = demo_trace_id

DEMO_ORG_NAME = "Acme AI Operations"
DEMO_ORG_SLUG = "acme-ai-ops"
DEMO_USER_EMAIL = "demo@observeagents.ai"
DEMO_USER_PASSWORD = "Demo123!"


def _get_or_create_org(db) -> tuple[Organization, bool]:
    org = db.query(Organization).filter(Organization.slug == DEMO_ORG_SLUG).first()
    if org:
        return org, False
    org = Organization(name=DEMO_ORG_NAME, slug=DEMO_ORG_SLUG)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org, True


def _get_or_create_user(db, org_id: int) -> tuple[User, bool]:
    from app.auth import hash_password

    user = db.query(User).filter(User.email == DEMO_USER_EMAIL).first()
    if user:
        return user, False
    user = User(
        email=DEMO_USER_EMAIL,
        name="Acme Demo Admin",
        hashed_password=hash_password(DEMO_USER_PASSWORD),
        organization_id=org_id,
        role="admin",
        team="platform",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, True


def seed() -> dict:
    """Run the demo seed. Returns a summary dict (also used by tests)."""
    from app.roles import seed_roles_for_org

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        org, org_created = _get_or_create_org(db)
        seed_roles_for_org(db, org.id)
        user, user_created = _get_or_create_user(db, org.id)

        otel = seed_otel_demo(db, org.id)

        registry_count = (
            db.query(AssetRegistry)
            .filter(
                AssetRegistry.organization_id == org.id,
                AssetRegistry.agent_id_raw.in_(DEMO_SERVICE_NAMES),
            )
            .count()
        )
        otel_asset_rows = (
            db.query(OtelAsset)
            .filter(
                OtelAsset.organization_id == org.id,
                OtelAsset.service_name.in_(DEMO_SERVICE_NAMES),
            )
            .all()
        )
        linked = sum(1 for a in otel_asset_rows if a.ai_asset_id is not None)
        cap_total = db.query(AssetCapability).filter(AssetCapability.organization_id == org.id).count()
        find_total = db.query(AssetFinding).filter(AssetFinding.organization_id == org.id).count()

        return {
            "org_id": org.id,
            "org_name": org.name,
            "org_created": org_created,
            "user_email": user.email,
            "user_created": user_created,
            "traces_seeded": otel["otel_traces_seeded"],
            "traces_skipped": otel["otel_traces_skipped"],
            "spans_ingested": otel["otel_spans_ingested"],
            "otel_assets": len(otel_asset_rows),
            "otel_assets_linked": linked,
            "registry_assets": registry_count,
            "capabilities_created": otel["capabilities_created"],
            "capabilities_updated": otel["capabilities_updated"],
            "capabilities_total": cap_total,
            "findings_created": otel["findings_created"],
            "findings_updated": otel["findings_updated"],
            "findings_total": find_total,
        }
    finally:
        db.close()


def main() -> None:
    s = seed()
    print(f"""
Acme AI Operations demo seed
────────────────────────────
organization : {s['org_name']} (id={s['org_id']}, {'created' if s['org_created'] else 'reused'})
demo user    : {s['user_email']} ({'created' if s['user_created'] else 'reused'}) — password: {DEMO_USER_PASSWORD}
traces       : {s['traces_seeded']} seeded, {s['traces_skipped']} already present
spans        : {s['spans_ingested']} ingested
otel assets  : {s['otel_assets']} ({s['otel_assets_linked']} linked to asset_registry)
registry     : {s['registry_assets']} canonical inventory rows
capabilities : {s['capabilities_created']} new, {s['capabilities_updated']} refreshed ({s['capabilities_total']} total)
findings     : {s['findings_created']} new, {s['findings_updated']} refreshed ({s['findings_total']} total)

Open the dashboard and log in as {DEMO_USER_EMAIL} / {DEMO_USER_PASSWORD}:
  • Runtime            — 5 traces incl. one with an error span
  • Asset Intelligence — discovered assets, capabilities, findings
  • Agents / Inventory — the 5 discovered AI systems
All data is synthetic; no real prompts, responses, secrets, or PII.
""")


if __name__ == "__main__":
    main()
