"""Default role definitions and per-org seeding logic.

Imported by both the startup seed in main.py and the admin org-creation router.
Keeping these here avoids circular imports between main.py and app/routes/admin.py.
"""
import json
from sqlalchemy.orm import Session
from app.models import Role as RoleModel

SEED_ROLES = [
    {
        "name": "admin",
        "label": "Admin",
        "color": "#FF5C7A",
        "pages": json.dumps([
            "dashboard", "overview_hub", "surfaces_demo", "welcome",
            "agent_inventory", "discovery", "governance", "relationship_map",
            "runtime", "intelligence", "gateway_control_center", "guardrails", "cost", "security_intel", "rules_alerts", "ecosystem",
            "budgets", "pricing", "security", "users", "apikeys", "settings",
            "home", "chat", "assets", "overview", "agents", "models",
            "workflows", "alerts", "integrations", "onboarding", "providers",
        ]),
        "can": json.dumps(["view_all_sessions"]),
        "team_scoped": False,
    },
    {
        "name": "analyst",
        "label": "Analyst",
        "color": "#FFB547",
        "pages": json.dumps([
            "dashboard", "overview_hub", "surfaces_demo", "welcome",
            "agent_inventory", "discovery", "governance", "relationship_map",
            "runtime", "intelligence", "gateway_control_center", "guardrails", "cost", "security_intel", "rules_alerts", "ecosystem",
            "budgets", "pricing",
            "home", "chat", "assets", "overview", "agents", "models",
            "workflows", "alerts", "integrations", "onboarding",
        ]),
        "can": json.dumps([]),
        "team_scoped": True,
    },
    {
        "name": "viewer",
        "label": "Viewer",
        "color": "#6FA8FF",
        "pages": json.dumps([
            "dashboard", "overview_hub", "surfaces_demo", "welcome",
            "agent_inventory", "discovery", "governance", "relationship_map",
            "runtime", "intelligence", "gateway_control_center", "guardrails", "cost", "security_intel", "rules_alerts", "ecosystem",
            "budgets", "pricing",
            "home", "assets", "overview", "agents", "models",
            "workflows", "alerts",
        ]),
        "can": json.dumps([]),
        "team_scoped": True,
    },
]


def seed_roles_for_org(db: Session, org_id: int) -> None:
    """Seed/migrate the 3 default roles for a single org.

    Insert-only for new rows; backfills team_scoped and pages on existing rows
    when those fields are stale. Idempotent — safe to call on every boot.
    """
    for r in SEED_ROLES:
        existing = db.query(RoleModel).filter(
            RoleModel.organization_id == org_id,
            RoleModel.name == r["name"],
        ).first()
        if not existing:
            db.add(RoleModel(organization_id=org_id, **r))
        else:
            try:
                raw = existing.pages
                pages = json.loads(raw) if isinstance(raw, str) else (raw or [])
            except Exception:
                pages = []
            seed_pages = json.loads(r["pages"])
            if r["name"] == "admin" or set(seed_pages) != set(pages):
                existing.pages = r["pages"]
            existing.team_scoped = r["team_scoped"]
    db.commit()
