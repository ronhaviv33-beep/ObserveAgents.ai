"""
Management isolation test: verifies org-scoping on /auth/users, /api-keys,
/guard-modes, and /budgets after the tenancy fix.
"""
import os, re, sys, uuid
_db_path = f"/tmp/test_mgmt_iso_{uuid.uuid4().hex[:8]}.db"
os.environ.update({
    "JWT_SECRET": "testsecret-isolation",
    "CREDENTIAL_ENCRYPTION_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    "DATABASE_URL": f"sqlite:///{_db_path}",
})
_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

from app.main import app, _seed_roles_for_org
from app.database import SessionLocal
from app.models import Organization, User, ApiKey, GuardMode, BudgetRule
from app.auth import hash_password, generate_api_key, create_token

from fastapi.testclient import TestClient
client = TestClient(app, raise_server_exceptions=True)
client.get("/health")  # trigger startup

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
beta_user  = User(email="betauser@test.com", name="Beta User",
                  hashed_password=hash_password("x"), role="analyst",
                  team="eng", organization_id=beta_org.id)
db.add_all([acme_admin, beta_admin, beta_user]); db.commit()
db.refresh(acme_admin); db.refresh(beta_admin); db.refresh(beta_user)

_, kp, kh   = generate_api_key()
acme_key = ApiKey(name="acme-key", key_prefix=kp,  key_hash=kh,
                  team="eng", organization_id=acme_org.id)
_, kp2, kh2 = generate_api_key()
beta_key = ApiKey(name="beta-key", key_prefix=kp2, key_hash=kh2,
                  team="eng", organization_id=beta_org.id)
db.add_all([acme_key, beta_key]); db.commit()
db.refresh(acme_key); db.refresh(beta_key)

# Seed one guard-mode override per org for the same team name ("eng")
beta_gm = GuardMode(organization_id=beta_org.id, team="eng", mode="enforce")
db.add(beta_gm); db.commit(); db.refresh(beta_gm)

# Seed one budget rule per org for the same team name ("eng")
beta_budget = BudgetRule(organization_id=beta_org.id, team="eng",
                         limit_usd=10.0, period="daily", action="alert")
db.add(beta_budget); db.commit(); db.refresh(beta_budget)

acme_token   = create_token(acme_admin)
beta_token   = create_token(beta_admin)
beta_user_id = beta_user.id
beta_key_id  = beta_key.id
beta_gm_team = beta_gm.team
beta_budget_id = beta_budget.id
db.close()

# ── Checks ─────────────────────────────────────────────────────────────────────
PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results = []

def check(label, cond, extra=""):
    tag = PASS if cond else FAIL
    print(f"  [{tag}] {label}" + (f"  ({extra})" if extra else ""))
    results.append(cond)

AH = {"Authorization": f"Bearer {acme_token}"}
BH = {"Authorization": f"Bearer {beta_token}"}

print("\n=== /auth/users ===")
r = client.get("/auth/users", headers=AH)
check("Acme list → 200", r.status_code == 200, f"got {r.status_code}")
if r.status_code == 200:
    emails = [u["email"] for u in r.json()]
    check("Acme sees acme@test.com",            "acme@test.com"     in emails, str(emails))
    check("Acme does NOT see beta@test.com",    "beta@test.com"     not in emails, str(emails))
    check("Acme does NOT see betauser@test.com","betauser@test.com" not in emails, str(emails))

r = client.get("/auth/users", headers=BH)
check("Beta list → 200", r.status_code == 200, f"got {r.status_code}")
if r.status_code == 200:
    emails = [u["email"] for u in r.json()]
    check("Beta sees beta@test.com",        "beta@test.com"     in emails, str(emails))
    check("Beta sees betauser@test.com",    "betauser@test.com" in emails, str(emails))
    check("Beta does NOT see acme@test.com","acme@test.com"     not in emails, str(emails))

r = client.patch(f"/auth/users/{beta_user_id}", headers=AH, json={"name": "Hacked"})
check(f"Acme PATCH beta user → 404", r.status_code == 404,
      f"got {r.status_code} {r.text[:60]}")
r = client.delete(f"/auth/users/{beta_user_id}", headers=AH)
check(f"Acme DELETE beta user → 404", r.status_code == 404,
      f"got {r.status_code} {r.text[:60]}")

print("\n=== /api-keys ===")
r = client.get("/api-keys", headers=AH)
check("Acme list keys → 200", r.status_code == 200, f"got {r.status_code}")
if r.status_code == 200:
    names = [k["name"] for k in r.json()]
    check("Acme sees acme-key",         "acme-key" in names, str(names))
    check("Acme does NOT see beta-key", "beta-key" not in names, str(names))

r = client.get("/api-keys", headers=BH)
check("Beta list keys → 200", r.status_code == 200, f"got {r.status_code}")
if r.status_code == 200:
    names = [k["name"] for k in r.json()]
    check("Beta sees beta-key",         "beta-key" in names, str(names))
    check("Beta does NOT see acme-key", "acme-key" not in names, str(names))

r = client.patch(f"/api-keys/{beta_key_id}", headers=AH, json={"is_active": False})
check(f"Acme PATCH beta key → 404", r.status_code == 404,
      f"got {r.status_code} {r.text[:60]}")
r = client.delete(f"/api-keys/{beta_key_id}", headers=AH)
check(f"Acme DELETE beta key → 404", r.status_code == 404,
      f"got {r.status_code} {r.text[:60]}")

print("\n=== /guard-modes ===")
# Acme list — should be empty (no overrides seeded for Acme's "eng" team)
r = client.get("/guard-modes", headers=AH)
check("Acme list guard-modes → 200", r.status_code == 200, f"got {r.status_code}")
if r.status_code == 200:
    modes = r.json()
    override_teams = [m["team"] for m in modes if m["is_override"]]
    check("Acme has no overrides (Beta's eng not visible)", override_teams == [],
          f"overrides: {override_teams}")

# Beta list — should show the "eng" enforce override
r = client.get("/guard-modes", headers=BH)
check("Beta list guard-modes → 200", r.status_code == 200, f"got {r.status_code}")
if r.status_code == 200:
    modes = r.json()
    eng = next((m for m in modes if m["team"] == "eng"), None)
    check("Beta sees eng override with mode=enforce",
          eng is not None and eng["mode"] == "enforce" and eng["is_override"],
          str(eng))

# Acme sets enforce on "eng" — should NOT affect Beta's "eng"
r = client.put("/guard-modes/eng", headers=AH, json={"mode": "alert"})
check("Acme PUT guard-mode eng → 200", r.status_code == 200, f"got {r.status_code} {r.text[:80]}")

# Beta re-reads — must still see "enforce", not Acme's "alert"
r = client.get("/guard-modes", headers=BH)
check("Beta guard-modes unaffected by Acme's write", r.status_code == 200)
if r.status_code == 200:
    modes = r.json()
    eng = next((m for m in modes if m["team"] == "eng"), None)
    check("Beta eng still enforce after Acme wrote alert",
          eng is not None and eng["mode"] == "enforce",
          f"eng={eng}")

# Acme reads back — must see "alert"
r = client.get("/guard-modes", headers=AH)
if r.status_code == 200:
    modes = r.json()
    eng = next((m for m in modes if m["team"] == "eng"), None)
    check("Acme eng is alert (its own write)", eng is not None and eng["mode"] == "alert", str(eng))

print("\n=== /budgets ===")
# Acme list — should be empty (no budgets seeded for Acme)
r = client.get("/budgets", headers=AH)
check("Acme list budgets → 200", r.status_code == 200, f"got {r.status_code}")
if r.status_code == 200:
    rules = r.json()
    check("Acme sees no budgets (Beta's not visible)", rules == [], f"got {rules}")

# Beta list — should see the seeded rule
r = client.get("/budgets", headers=BH)
check("Beta list budgets → 200", r.status_code == 200, f"got {r.status_code}")
if r.status_code == 200:
    rules = r.json()
    check("Beta sees its eng budget", any(b["team"] == "eng" for b in rules), str(rules))

# Acme DELETE Beta's budget rule id → 404
r = client.delete(f"/budgets/{beta_budget_id}", headers=AH)
check(f"Acme DELETE beta budget {beta_budget_id} → 404", r.status_code == 404,
      f"got {r.status_code} {r.text[:60]}")

# Beta can still see it after Acme's failed delete
r = client.get("/budgets", headers=BH)
if r.status_code == 200:
    rules = r.json()
    check("Beta budget survives Acme's delete attempt",
          any(b["id"] == beta_budget_id for b in rules), str([b["id"] for b in rules]))

print("\n=== /roles ===")
# Both orgs get 3 seeded roles; they must not see each other's
r = client.get("/roles", headers=AH)
check("Acme list roles → 200", r.status_code == 200, f"got {r.status_code}")
if r.status_code == 200:
    acme_role_names = [x["name"] for x in r.json()]
    check("Acme has 3 seeded roles", len(acme_role_names) == 3,
          f"got {acme_role_names}")

r = client.get("/roles", headers=BH)
check("Beta list roles → 200", r.status_code == 200, f"got {r.status_code}")
if r.status_code == 200:
    beta_role_names = [x["name"] for x in r.json()]
    check("Beta has 3 seeded roles", len(beta_role_names) == 3,
          f"got {beta_role_names}")

# Acme creates a custom role
r = client.post("/roles", headers=AH,
                json={"name": "ops", "label": "Ops", "color": "#aabbcc",
                      "pages": ["home"], "can": []})
check("Acme create role 'ops' → 201", r.status_code == 201,
      f"got {r.status_code} {r.text[:80]}")

# Beta cannot see Acme's 'ops' role
r = client.get("/roles", headers=BH)
if r.status_code == 200:
    beta_names = [x["name"] for x in r.json()]
    check("Beta does NOT see Acme's ops role", "ops" not in beta_names, str(beta_names))

# Acme can see its own 'ops' role
r = client.get("/roles", headers=AH)
if r.status_code == 200:
    acme_names = [x["name"] for x in r.json()]
    check("Acme sees its own ops role", "ops" in acme_names, str(acme_names))

# Beta PATCH Acme's role 'ops' → 404 (Beta has no such role)
r = client.patch("/roles/ops", headers=BH, json={"label": "Hacked"})
check("Beta PATCH Acme's ops → 404", r.status_code == 404,
      f"got {r.status_code} {r.text[:60]}")

# Beta DELETE Acme's role 'ops' → 404
r = client.delete("/roles/ops", headers=BH)
check("Beta DELETE Acme's ops → 404", r.status_code == 404,
      f"got {r.status_code} {r.text[:60]}")

# Acme can still see ops unchanged
r = client.get("/roles", headers=AH)
if r.status_code == 200:
    ops = next((x for x in r.json() if x["name"] == "ops"), None)
    check("Acme ops survives Beta's attempts", ops is not None and ops["label"] == "Ops",
          str(ops))

# Admin self-lockout guard: Acme cannot strip 'users'+'settings' from its own admin role
r = client.patch("/roles/admin", headers=AH, json={"pages": ["home"]})
check("Admin self-lockout guard: stripping users+settings → 400", r.status_code == 400,
      f"got {r.status_code} {r.text[:80]}")

# Cannot delete the admin role
r = client.delete("/roles/admin", headers=AH)
check("Cannot delete admin role → 400", r.status_code == 400,
      f"got {r.status_code} {r.text[:60]}")

print()
passed = sum(results)
total  = len(results)
if passed == total:
    print(f"\033[32mAll {total}/{total} checks passed.\033[0m\n")
else:
    print(f"\033[31m{total - passed}/{total} checks FAILED.\033[0m\n")
    sys.exit(1)
