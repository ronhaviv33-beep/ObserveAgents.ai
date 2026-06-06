"""
W-1 (503 gate) and /security/alerts isolation tests.

W-1: when _TENANCY_HARDENED is False, the four dashboard read paths
(/telemetry, /telemetry/summary, /audit, /security/alerts) must return 503.
When True, they return 200. Tests patch the module-level flag directly.

Alerts isolation: Acme admin sees only Acme's alerts; Beta admin sees only
Beta's. A sensitive telemetry row seeded for Beta must not appear in Acme's
alert list — both directions.
"""
import os, re, sys, uuid
_db_path = f"/tmp/test_w1_alerts_{uuid.uuid4().hex[:8]}.db"
os.environ.update({
    "JWT_SECRET":                 "testsecret-w1",
    "CREDENTIAL_ENCRYPTION_KEY":  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    "DATABASE_URL":               f"sqlite:///{_db_path}",
})
sys.path.insert(0, "/home/user/aifinops-guard")
os.chdir("/home/user/aifinops-guard")

from app.main import app, _seed_roles_for_org
import app.main as app_main          # for patching _TENANCY_HARDENED
from app.database import SessionLocal
from app.models import Organization, User, Telemetry
from app.auth import hash_password, create_token
from datetime import datetime, timezone

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

# Seed a sensitive telemetry row for Beta only
beta_tel = Telemetry(
    organization_id=beta_org.id,
    team="eng", agent="bot", model="claude-sonnet-4-5",
    prompt="my password is hunter2", response="ok",
    prompt_tokens=10, completion_tokens=5, total_tokens=15,
    latency_ms=200.0, cost_usd=0.001,
    sensitive=True,
    sensitive_findings='[{"type":"credential","severity":"critical","sample":"hunter2"}]',
    blocked=False,
    timestamp=datetime.now(timezone.utc),
)
db.add(beta_tel); db.commit()

acme_token = create_token(acme_admin)
beta_token  = create_token(beta_admin)
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

# ── W-1: 503 gate ─────────────────────────────────────────────────────────────
print("\n=== W-1: 503 gate (not-hardened path) ===")

# Patch the module-level flag to simulate un-hardened schema
app_main._TENANCY_HARDENED = False

for path, label in [
    ("/telemetry",         "/telemetry"),
    ("/telemetry/summary", "/telemetry/summary"),
    ("/audit",             "/audit"),
    ("/security/alerts",   "/security/alerts"),
]:
    r = client.get(path, headers=AH)
    check(f"{label} → 503 when not hardened", r.status_code == 503,
          f"got {r.status_code}: {r.text[:60]}")

# Restore flag — now simulate hardened
app_main._TENANCY_HARDENED = True

print("\n=== W-1: endpoints pass-through when hardened ===")
for path, label in [
    ("/telemetry",         "/telemetry"),
    ("/telemetry/summary", "/telemetry/summary"),
    ("/audit",             "/audit"),
    ("/security/alerts",   "/security/alerts"),
]:
    r = client.get(path, headers=AH)
    check(f"{label} → 200 when hardened", r.status_code == 200,
          f"got {r.status_code}: {r.text[:60]}")

# ── /security/alerts isolation ────────────────────────────────────────────────
print("\n=== /security/alerts isolation ===")

# Acme: should have no alerts (no sensitive rows in Acme's org)
r = client.get("/security/alerts", headers=AH)
check("Acme alerts → 200", r.status_code == 200, f"got {r.status_code}")
if r.status_code == 200:
    alerts = r.json()
    check("Acme sees no alerts (Beta's sensitive row not visible)", alerts == [],
          f"got {len(alerts)} alerts: {alerts[:1]}")

# Beta: should have the sensitive_data_exposure alert
r = client.get("/security/alerts", headers=BH)
check("Beta alerts → 200", r.status_code == 200, f"got {r.status_code}")
if r.status_code == 200:
    alerts = r.json()
    types  = [a["type"] for a in alerts]
    check("Beta sees sensitive_data_exposure alert",
          "sensitive_data_exposure" in types, f"got types={types}")
    check("Beta alert entity is 'bot'",
          any(a.get("entity") == "bot" for a in alerts if a["type"] == "sensitive_data_exposure"),
          str(alerts))

# Confirm 503 gate still works after flag restore (sanity — re-patch to False)
app_main._TENANCY_HARDENED = False
r = client.get("/security/alerts", headers=AH)
check("503 gate fires again after re-patching to not-hardened", r.status_code == 503,
      f"got {r.status_code}")
app_main._TENANCY_HARDENED = True  # leave clean

print()
passed = sum(results)
total  = len(results)
if passed == total:
    print(f"\033[32mAll {total}/{total} checks passed.\033[0m\n")
else:
    print(f"\033[31m{total - passed}/{total} checks FAILED.\033[0m\n")
    sys.exit(1)
