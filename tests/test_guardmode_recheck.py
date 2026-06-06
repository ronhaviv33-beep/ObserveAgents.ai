"""
Re-verification of guard-mode org isolation against current committed model state.
The prior 44/44 run was against commit 178145d (before models.py was touched).
This run verifies the same properties hold now that Team sits adjacent to GuardMode
in models.py and the full teams table is live.

Tests:
- GuardMode rows can be seeded directly (model is structurally sound)
- Acme cannot see Beta's guard-mode override
- Beta cannot see Acme's guard-mode override
- Acme write does not affect Beta's row (org-scoped write)
- Beta's row persists correct mode after Acme's write
- GuardMode model maps to guard_modes table (not teams)
"""
import os, re, sys, uuid

_db_path = f"/tmp/test_gm_recheck_{uuid.uuid4().hex[:8]}.db"
os.environ.update({
    "JWT_SECRET":                "testsecret-gm-recheck",
    "CREDENTIAL_ENCRYPTION_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    "DATABASE_URL":              f"sqlite:///{_db_path}",
})
sys.path.insert(0, "/home/user/aifinops-guard")
os.chdir("/home/user/aifinops-guard")

from app.main import app, _seed_roles_for_org
from app.database import SessionLocal
from app.models import Organization, User, GuardMode
from app.auth import hash_password, create_token

from fastapi.testclient import TestClient
client = TestClient(app, raise_server_exceptions=True)
client.get("/health")

db = SessionLocal()
def slug(n): return re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")

acme_org = Organization(name="AcmeCo-GM", slug=slug("AcmeCo-GM"))
beta_org = Organization(name="BetaCo-GM", slug=slug("BetaCo-GM"))
db.add_all([acme_org, beta_org]); db.commit()
db.refresh(acme_org); db.refresh(beta_org)
_seed_roles_for_org(db, acme_org.id)
_seed_roles_for_org(db, beta_org.id)

acme_admin = User(email="acme-gm@test.com", name="Acme Admin",
                  hashed_password=hash_password("x"), role="admin",
                  team="eng", organization_id=acme_org.id)
beta_admin = User(email="beta-gm@test.com", name="Beta Admin",
                  hashed_password=hash_password("x"), role="admin",
                  team="eng", organization_id=beta_org.id)
db.add_all([acme_admin, beta_admin]); db.commit()
db.refresh(acme_admin); db.refresh(beta_admin)

# Confirm GuardMode maps to the right table before seeding
gm_table = GuardMode.__table__.name
assert gm_table == "guard_modes", f"GuardMode.__table__.name = '{gm_table}' (should be 'guard_modes')"

# Seed a guard-mode override for Beta only
beta_gm = GuardMode(organization_id=beta_org.id, team="eng", mode="enforce")
db.add(beta_gm); db.commit(); db.refresh(beta_gm)

acme_token = create_token(acme_admin)
beta_token  = create_token(beta_admin)
acme_org_id = acme_org.id
beta_org_id  = beta_org.id
db.close()

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results = []
def check(label, cond, extra=""):
    tag = PASS if cond else FAIL
    print(f"  [{tag}] {label}" + (f"  ({extra})" if extra else ""))
    results.append(cond)

AH = {"Authorization": f"Bearer {acme_token}"}
BH = {"Authorization": f"Bearer {beta_token}"}

print("\n=== GuardMode structural integrity ===")
check("GuardMode maps to guard_modes table", gm_table == "guard_modes", f"got '{gm_table}'")

# Confirm Team maps to teams — verify the two classes weren't merged
from app.models import Team
team_table = Team.__table__.name
check("Team maps to teams table", team_table == "teams", f"got '{team_table}'")

# Confirm distinct column sets — if they were merged, Team would have 'mode'
gm_cols   = {c.name for c in GuardMode.__table__.columns}
team_cols = {c.name for c in Team.__table__.columns}
check("GuardMode has 'mode' column", "mode" in gm_cols, str(gm_cols))
check("Team does NOT have 'mode' column", "mode" not in team_cols, str(team_cols))
check("Team has 'name' column", "name" in team_cols, str(team_cols))
check("GuardMode does NOT have 'name' column", "name" not in gm_cols, str(gm_cols))

print("\n=== Guard-mode read isolation ===")

r = client.get("/guard-modes", headers=AH)
check("Acme list guard-modes → 200", r.status_code == 200, f"got {r.status_code}")
if r.status_code == 200:
    modes = r.json()
    override_teams = [m["team"] for m in modes if m["is_override"]]
    check("Acme has no overrides (Beta's eng not visible)",
          override_teams == [], f"overrides: {override_teams}")

r = client.get("/guard-modes", headers=BH)
check("Beta list guard-modes → 200", r.status_code == 200, f"got {r.status_code}")
if r.status_code == 200:
    modes = r.json()
    eng = next((m for m in modes if m["team"] == "eng"), None)
    check("Beta sees eng override with mode=enforce",
          eng is not None and eng["mode"] == "enforce" and eng["is_override"],
          str(eng))

print("\n=== Guard-mode write isolation ===")

r = client.put("/guard-modes/eng", headers=AH, json={"mode": "alert"})
check("Acme PUT guard-mode eng → 200", r.status_code == 200, f"got {r.status_code} {r.text[:80]}")

r = client.get("/guard-modes", headers=BH)
check("Beta guard-modes unaffected by Acme's write → 200", r.status_code == 200)
if r.status_code == 200:
    modes = r.json()
    eng = next((m for m in modes if m["team"] == "eng"), None)
    check("Beta eng still enforce after Acme wrote alert",
          eng is not None and eng["mode"] == "enforce", f"eng={eng}")

r = client.get("/guard-modes", headers=AH)
check("Acme reads back → 200", r.status_code == 200)
if r.status_code == 200:
    modes = r.json()
    eng = next((m for m in modes if m["team"] == "eng"), None)
    check("Acme eng is alert (its own write)",
          eng is not None and eng["mode"] == "alert", str(eng))

print()
passed = sum(results)
total  = len(results)
if passed == total:
    print(f"\033[32mAll {total}/{total} checks passed.\033[0m\n")
else:
    print(f"\033[31m{total - passed}/{total} checks FAILED.\033[0m\n")
    sys.exit(1)
