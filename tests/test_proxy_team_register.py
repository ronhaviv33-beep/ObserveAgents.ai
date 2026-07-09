"""
Proxy-path team auto-registration test.

Confirms that a request through /v1/chat/completions registers the team
in the teams table — not just create_api_key.

This exercises the path that would be silently missed if _register_team
were only wired into key creation: a key with an old/unknown team could
generate telemetry under a new team (via X-Guard-Team header) that never
appears in the teams table.

Strategy: mock get_client_for_org (avoids 402 — no real credential) and
mock proxy_chat_complete (avoids real LLM call). _register_team sits
between those two in the route, so a successful pass-through proves it ran.
"""
import os, re, sys, uuid
from unittest.mock import patch, MagicMock, AsyncMock

_db_path = f"/tmp/test_proxy_register_{uuid.uuid4().hex[:8]}.db"
os.environ.update({
    "JWT_SECRET":                "testsecret-proxy",
    "CREDENTIAL_ENCRYPTION_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    "DATABASE_URL":              f"sqlite:///{_db_path}",
})
_repo_root = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, _repo_root)
os.chdir(_repo_root)

from app.main import app, _seed_roles_for_org
from app.database import SessionLocal
from app.models import Organization, User, Team as TeamModel
from app.auth import hash_password, create_token, generate_api_key, hash_api_key
from app.models import ApiKey

from fastapi.testclient import TestClient
client = TestClient(app, raise_server_exceptions=True)
client.get("/health")

db = SessionLocal()
def slug(n): return re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")

acme_org = Organization(name="ProxyAcme", slug=slug("ProxyAcme"))
db.add(acme_org); db.commit(); db.refresh(acme_org)
_seed_roles_for_org(db, acme_org.id)

acme_admin = User(email="proxy-acme@test.com", name="Proxy Acme Admin",
                  hashed_password=hash_password("x"), role="admin",
                  team="eng", organization_id=acme_org.id)
db.add(acme_admin); db.commit(); db.refresh(acme_admin)
acme_token = create_token(acme_admin)
acme_org_id = acme_org.id

# Also create an API key so we can test the key-auth path on the proxy
full_key, key_prefix, key_hash = generate_api_key()
api_key_record = ApiKey(
    name="proxy-test-key",
    key_prefix=key_prefix,
    key_hash=key_hash,
    team="keyteam",
    organization_id=acme_org_id,
)
db.add(api_key_record); db.commit()
db.close()

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results = []
def check(label, cond, extra=""):
    tag = PASS if cond else FAIL
    print(f"  [{tag}] {label}" + (f"  ({extra})" if extra else ""))
    results.append(cond)

AH = {"Authorization": f"Bearer {acme_token}"}

def get_teams():
    r = client.get("/teams", headers=AH)
    assert r.status_code == 200, f"GET /teams → {r.status_code}: {r.text}"
    return [t["name"] for t in r.json()]

# ── Fake LLM response (non-streaming) ─────────────────────────────────────────
FAKE_RESP = {
    "id": "chatcmpl-fake",
    "object": "chat.completion",
    "model": "gpt-4o-mini",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    "_latency_ms": 10.0,
}

print("\n=== proxy /v1/chat/completions registers team ===")

# Verify "analytics" not yet in teams
teams_before = get_teams()
check("'analytics' not yet in Acme teams before proxy call",
      "analytics" not in teams_before, str(teams_before))

mock_client = MagicMock()
with patch("app.routes.proxy.get_client_for_org", return_value=mock_client), \
     patch("app.routes.proxy.proxy_chat_complete", new=AsyncMock(return_value=FAKE_RESP)):
    r = client.post(
        "/v1/chat/completions",
        headers={**AH, "X-Guard-Team": "analytics", "X-Guard-Agent": "test-bot"},
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hello"}]},
    )

check("/v1/chat/completions with mocked LLM → 200", r.status_code == 200,
      f"got {r.status_code}: {r.text[:120]}")

teams_after = get_teams()
check("'analytics' registered in Acme teams after proxy call",
      "analytics" in teams_after, str(teams_after))

print("\n=== proxy /v1/messages registers team ===")

# Fake Anthropic-compat response
FAKE_MSG_RESP = {
    "id": "chatcmpl-fake2",
    "object": "chat.completion",
    "model": "claude-haiku-4-5",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "end_turn"}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    "_latency_ms": 10.0,
}

teams_before2 = get_teams()
check("'data-science' not yet in Acme teams before /v1/messages call",
      "data-science" not in teams_before2, str(teams_before2))

with patch("app.routes.proxy.get_client_for_org", return_value=mock_client), \
     patch("app.routes.proxy.proxy_chat_complete", new=AsyncMock(return_value=FAKE_MSG_RESP)):
    r = client.post(
        "/v1/messages",
        headers={**AH, "X-Guard-Team": "data-science", "X-Guard-Agent": "claude-bot"},
        json={
            "model": "claude-haiku-4-5",
            "max_tokens": 10,
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

check("/v1/messages with mocked LLM → 200", r.status_code == 200,
      f"got {r.status_code}: {r.text[:120]}")

teams_after2 = get_teams()
check("'data-science' registered in Acme teams after /v1/messages call",
      "data-science" in teams_after2, str(teams_after2))

print("\n=== proxy path: X-Guard-Team header is ignored for API-key callers ===")
# The key has team="keyteam"; the request sends X-Guard-Team: "header-team".
# API keys are low-trust callers (identity_resolver caller_trust="low"):
# X-Agent-*/X-Guard-* headers are ignored so callers cannot spoof team
# attribution — the key's registered team wins.
with patch("app.routes.proxy.get_client_for_org", return_value=mock_client), \
     patch("app.routes.proxy.proxy_chat_complete", new=AsyncMock(return_value=FAKE_RESP)):
    r = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {full_key}",
                 "X-Guard-Team": "header-team", "X-Guard-Agent": "bot"},
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
    )
check("proxy call with API key + X-Guard-Team header → 200", r.status_code == 200,
      f"got {r.status_code}: {r.text[:120]}")

all_teams = get_teams()
check("'header-team' NOT registered (low-trust header ignored)",
      "header-team" not in all_teams, str(all_teams))
check("key's team 'keyteam' registered (key team wins)",
      "keyteam" in all_teams, str(all_teams))

print()
passed = sum(results)
total  = len(results)
if passed == total:
    print(f"\033[32mAll {total}/{total} checks passed.\033[0m\n")
else:
    print(f"\033[31m{total - passed}/{total} checks FAILED.\033[0m\n")
    sys.exit(1)
