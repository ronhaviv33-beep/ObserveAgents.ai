"""
RBAC regression: state-changing asset/agent/billing endpoints must require an
admin. A team-scoped analyst assigned to the agent's own team passes the
team-scope check, so only a role guard can stop it — that guard is what this
test locks in. Admins must still succeed.

ENV vars are set before any app import — do not reorder the top block.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

_db_path = f"/tmp/test_mutation_rbac_{uuid.uuid4().hex[:8]}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ.setdefault("JWT_SECRET", "testsecret-mutation-rbac")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.chdir(str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from app.main import app, _seed_roles_for_org
from app.database import SessionLocal
from app.models import Organization, User, Telemetry
from app.auth import hash_password, create_token
from app.org_config import set_org_config

_client = TestClient(app, raise_server_exceptions=False)
_client.get("/health")

_db = SessionLocal()
_org = Organization(name="RbacTestOrg", slug="rbac-test-org")
_db.add(_org)
_db.commit()
_db.refresh(_org)
_seed_roles_for_org(_db, _org.id)
ORG_ID = _org.id
set_org_config(_db, ORG_ID, "demo_mode", False)

_admin = User(email="admin@rbac.test", name="Admin", hashed_password=hash_password("x"),
              role="admin", team="", organization_id=ORG_ID)
# analyst is team_scoped and lives on the SAME team as the seeded agent, so the
# team-scope gate does NOT block it — only require_admin does.
_analyst = User(email="analyst@rbac.test", name="Analyst", hashed_password=hash_password("x"),
                role="analyst", team="engineering", organization_id=ORG_ID)
_db.add_all([_admin, _analyst])
_db.commit()
_db.refresh(_admin)
_db.refresh(_analyst)

ADMIN_H = {"Authorization": f"Bearer {create_token(_admin)}"}
ANALYST_H = {"Authorization": f"Bearer {create_token(_analyst)}"}

_now = datetime.now(timezone.utc)


def _seed_agent(agent: str) -> None:
    db = SessionLocal()
    try:
        db.add(Telemetry(
            organization_id=ORG_ID, team="engineering", agent=agent, model="gpt-4o",
            prompt="p", response="r", prompt_tokens=10, completion_tokens=5, total_tokens=15,
            latency_ms=100.0, cost_usd=0.001, pricing_estimated=False, sensitive=False,
            blocked=False, timestamp=_now - timedelta(minutes=2),
        ))
        db.commit()
    finally:
        db.close()


# Representative mutation endpoints across the three routers we hardened.
# Each is (method, path, json_body).
_MUTATIONS = [
    ("post", "/agents/{a}/claim", {"owner": "x"}),
    ("post", "/agents/{a}/approve-suggestions", {}),
    ("post", "/agents/{a}/ignore", {}),
    ("post", "/agents/{a}/reject", {}),
    ("post", "/assets/{a}/claim", {"owner": "x"}),
    ("patch", "/assets/{a}/registry", {"criticality": "high"}),
    ("post", "/billing/openai/import",
     {"billing_period_start": "2026-06-01", "billing_period_end": "2026-06-30",
      "actual_billed_cost_usd": 100}),
]


def _call(method: str, path: str, body: dict, headers: dict):
    return getattr(_client, method)(path, json=body, headers=headers)


def test_analyst_is_forbidden_on_mutations():
    """A non-admin (team-scoped analyst on the agent's team) gets 403 on every mutation."""
    for i, (method, tmpl, body) in enumerate(_MUTATIONS):
        agent = f"rbac-analyst-{i}"
        _seed_agent(agent)
        r = _call(method, tmpl.format(a=agent), body, ANALYST_H)
        assert r.status_code == 403, f"{method.upper()} {tmpl}: expected 403, got {r.status_code} ({r.text[:160]})"


def test_admin_is_not_forbidden_on_mutations():
    """Admin must pass the role guard — never a 403 (2xx, or a domain 4xx like 400/404/422 is fine)."""
    for i, (method, tmpl, body) in enumerate(_MUTATIONS):
        agent = f"rbac-admin-{i}"
        _seed_agent(agent)
        r = _call(method, tmpl.format(a=agent), body, ADMIN_H)
        assert r.status_code != 403, f"{method.upper()} {tmpl}: admin unexpectedly got 403 ({r.text[:160]})"


if __name__ == "__main__":
    test_analyst_is_forbidden_on_mutations()
    test_admin_is_not_forbidden_on_mutations()
    print("test_mutation_rbac: OK")
