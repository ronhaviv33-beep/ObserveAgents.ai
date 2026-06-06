"""
Teams auto-registration and isolation tests.

Acme creates a key with team 'marketing' → (acme, marketing) registered.
Beta cannot see Acme's team. Beta creates its own 'marketing' key → separate
row, no collision. Idempotency: second key with same team does not duplicate.
Both directions. Also verifies user creation registers the team.
"""
import os, re, sys, uuid

_db_path = f"/tmp/test_teams_{uuid.uuid4().hex[:8]}.db"
os.environ.update({
    "JWT_SECRET":                "testsecret-teams",
    "CREDENTIAL_ENCRYPTION_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    "DATABASE_URL":              f"sqlite:///{_db_path}",
})
sys.path.insert(0, "/home/user/aifinops-guard")
os.chdir("/home/user/aifinops-guard")

from app.main import app, _seed_roles_for_org
from app.database import SessionLocal
from app.models import Organization, User
from app.auth import hash_password, create_token

from fastapi.testclient import TestClient
client = TestClient(app, raise_server_exceptions=True)
client.get("/health")  # trigger startup

# ── Seed two orgs ─────────────────────────────────────────────────────────────
db = SessionLocal()
def slug(n): return re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")

acme_org = Organization(name="AcmeCo", slug=slug("AcmeCo"))
beta_org = Organization(name="BetaCo", slug=slug("BetaCo"))
db.add_all([acme_org, beta_org]); db.commit()
db.refresh(acme_org); db.refresh(beta_org)
_seed_roles_for_org(db, acme_org.id)
_seed_roles_for_org(db, beta_org.id)

acme_admin = User(email="acme@test.com", name="Acme Admin",
                  hashed_password=hash_password("x"), role="admin",
                  team="eng", organization_id=acme_org.id)
beta_admin = User(email="beta@test.com", name="Beta Admin",
                  hashed_password=hash_password("x"), role="admin",
                  team="eng", organization_id=beta_org.id)
db.add_all([acme_admin, beta_admin]); db.commit()
db.refresh(acme_admin); db.refresh(beta_admin)

acme_token = create_token(acme_admin)
beta_token  = create_token(beta_admin)
acme_org_id = acme_org.id
beta_org_id  = beta_org.id
db.close()

# ── Helpers ───────────────────────────────────────────────────────────────────
PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results = []

def check(label, cond, extra=""):
    tag = PASS if cond else FAIL
    print(f"  [{tag}] {label}" + (f"  ({extra})" if extra else ""))
    results.append(cond)

AH = {"Authorization": f"Bearer {acme_token}"}
BH = {"Authorization": f"Bearer {beta_token}"}

# ── Helper: GET /teams ────────────────────────────────────────────────────────
def get_teams(headers):
    r = client.get("/teams", headers=headers)
    assert r.status_code == 200, f"GET /teams failed: {r.status_code} {r.text}"
    return r.json()

# ── Test 1: create_user registers team ────────────────────────────────────────
print("\n=== create_user registers team ===")

r = client.post("/auth/users", headers=AH, json={
    "email": "dev@acme.com", "name": "Dev User",
    "password": "pass1234", "role": "analyst", "team": "dev",
})
check("create user with team 'dev' → 201", r.status_code == 201, f"got {r.status_code}: {r.text[:80]}")

teams = get_teams(AH)
names = [t["name"] for t in teams]
check("'dev' team registered for Acme after user creation", "dev" in names, str(names))

# ── Test 2: create_api_key registers team (Acme 'marketing') ─────────────────
print("\n=== create_api_key registers team ===")

r = client.post("/api-keys", headers=AH, json={"name": "mkt-key-1", "team": "marketing"})
check("Acme create key 'marketing' → 201", r.status_code == 201, f"got {r.status_code}: {r.text[:80]}")

teams = get_teams(AH)
names = [t["name"] for t in teams]
check("'marketing' appears in Acme teams", "marketing" in names, str(names))

# ── Test 3: Beta creates its own 'marketing' key — separate row ───────────────
print("\n=== Beta creates 'marketing' key — separate row, no collision ===")

r = client.post("/api-keys", headers=BH, json={"name": "beta-mkt-key", "team": "marketing"})
check("Beta create key 'marketing' → 201", r.status_code == 201, f"got {r.status_code}: {r.text[:80]}")

beta_teams = get_teams(BH)
beta_names = [t["name"] for t in beta_teams]
check("'marketing' appears in Beta teams", "marketing" in beta_names, str(beta_names))

# ── Test 4: Isolation — Acme cannot see Beta's teams and vice versa ───────────
print("\n=== /teams isolation ===")

acme_teams = get_teams(AH)
acme_orgs  = {t["organization_id"] for t in acme_teams}
check("Acme teams all belong to Acme org", acme_orgs == {acme_org_id},
      f"org ids seen: {acme_orgs}")

beta_teams2 = get_teams(BH)
beta_orgs   = {t["organization_id"] for t in beta_teams2}
check("Beta teams all belong to Beta org", beta_orgs == {beta_org_id},
      f"org ids seen: {beta_orgs}")

# Confirm no cross-contamination
acme_names = [t["name"] for t in acme_teams]
# Both have 'marketing' but in different org rows
check("Acme does not see Beta's team rows", all(
    t["organization_id"] == acme_org.id for t in acme_teams
), str(acme_teams))
check("Beta does not see Acme's team rows", all(
    t["organization_id"] == beta_org.id for t in beta_teams2
), str(beta_teams2))

# ── Test 5: Idempotency — second key with same team does not duplicate ─────────
print("\n=== Idempotency: duplicate team not inserted ===")

r = client.post("/api-keys", headers=AH, json={"name": "mkt-key-2", "team": "marketing"})
check("Acme create second key with 'marketing' → 201", r.status_code == 201,
      f"got {r.status_code}: {r.text[:80]}")

teams_after = get_teams(AH)
marketing_count = sum(1 for t in teams_after if t["name"] == "marketing")
check("'marketing' row count stays at 1 for Acme (idempotent)", marketing_count == 1,
      f"count={marketing_count}")

# Beta idempotency
r = client.post("/api-keys", headers=BH, json={"name": "beta-mkt-key-2", "team": "marketing"})
check("Beta create second 'marketing' key → 201", r.status_code == 201,
      f"got {r.status_code}: {r.text[:80]}")

beta_teams3 = get_teams(BH)
beta_mkt_count = sum(1 for t in beta_teams3 if t["name"] == "marketing")
check("'marketing' row count stays at 1 for Beta (idempotent)", beta_mkt_count == 1,
      f"count={beta_mkt_count}")

# ── Test 6: blank/unknown team not registered ─────────────────────────────────
print("\n=== blank/unknown team not registered ===")

count_before = len(get_teams(AH))
r = client.post("/api-keys", headers=AH, json={"name": "unknown-key", "team": "unknown"})
check("create key with team='unknown' → 201", r.status_code == 201, f"got {r.status_code}")
count_after = len(get_teams(AH))
check("'unknown' not added to teams table", count_after == count_before,
      f"before={count_before} after={count_after}")

print()
passed = sum(results)
total  = len(results)
if passed == total:
    print(f"\033[32mAll {total}/{total} checks passed.\033[0m\n")
else:
    print(f"\033[31m{total - passed}/{total} checks FAILED.\033[0m\n")
    import sys; sys.exit(1)
