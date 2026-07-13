# Synthetic Customer E2E Test Suite

Tests the AI Asset Management platform **as a system** — not individual
endpoints in isolation. It simulates a real company (Acme AI Inc.) going
from first login through day-to-day operations across 8 flows.

---

## What the test does

| Flow | Name | What it proves |
|------|------|----------------|
| 1 | Platform admin onboarding | Admin can log in, create an org, create an Acme admin, and verify org context |
| 2 | Org setup | Acme admin can create users, API keys, configure guard modes and PII settings |
| 3 | Normal AI runtime traffic | 5 agents across 4 teams can send gateway calls with proper SDK headers |
| 4 | PII / security detection | Fake PII in prompts is flagged as sensitive in telemetry |
| 5 | Budget + policy enforcement | Budget rules can be created; policy block returns 403; telemetry records blocked=True |
| 6 | Agent inventory | Discovered agents appear in /assets with metadata (first_seen, team, status) |
| 7 | Relationship mapping | /relationships routes are probed; skipped gracefully if not implemented |
| 8 | Dashboard read APIs | All major read endpoints return 200 with valid data |

---

## Required environment variables

| Variable | Default | Notes |
|----------|---------|-------|
| `PLATFORM_ADMIN_PASSWORD` | *(none — required)* | Password for the platform admin account |
| `BASE_URL` | `http://localhost:8000` | Backend URL, no trailing slash |
| `PLATFORM_ADMIN_EMAIL` | `admin@ai-asset-mgmt.local` | Platform admin email |
| `ACME_ADMIN_EMAIL` | `admin@acme.ai` | Email for the synthetic Acme admin |
| `ACME_ADMIN_PASSWORD` | `AcmeAdmin1!` | Password for the synthetic Acme admin |

---

## How to run locally

### Prerequisites

```bash
# Install dependencies (only requests is needed)
pip install requests

# Start the backend
PLATFORM_ADMIN_PASSWORD=Admin123! python scripts/synthetic_customer.py
```

### Full run (live traffic)

```bash
BASE_URL=http://localhost:8000 \
PLATFORM_ADMIN_PASSWORD=Admin123! \
python scripts/synthetic_customer.py
```

### Dry-run (no requests sent — prints the plan)

```bash
python scripts/synthetic_customer.py --dry-run
```

### Strict mode (skips count as failures — useful for CI)

```bash
PLATFORM_ADMIN_PASSWORD=Admin123! \
python scripts/synthetic_customer.py --strict
```

### Fast mode (halves LLM call count — quicker smoke-test)

```bash
PLATFORM_ADMIN_PASSWORD=Admin123! \
python scripts/synthetic_customer.py --fast
```

---

## How to run against the Render deployment

```bash
BASE_URL=https://ai-asset-backend.onrender.com \
PLATFORM_ADMIN_PASSWORD=<your-render-admin-password> \
python scripts/synthetic_customer.py
```

With strict mode (for a pre-release readiness check):

```bash
BASE_URL=https://ai-asset-backend.onrender.com \
PLATFORM_ADMIN_PASSWORD=<password> \
python scripts/synthetic_customer.py --strict
```

> **Note:** The first request to Render may take 30–60 seconds if the
> instance has spun down. Subsequent requests are fast.

---

## What failures usually mean

### ❌ Platform admin login
- `PLATFORM_ADMIN_PASSWORD` is wrong or not set.
- The backend is not running / not reachable at `BASE_URL`.

### ⏭ Organization creation — Acme AI Inc.
- `POST /admin/organizations` returned 404 — the endpoint has not been
  implemented yet. The script continues using the platform admin's org.
  Full multi-tenant isolation requires this endpoint.

### ❌ Acme admin user creation
- The role `admin` does not exist in the org (roles are seeded on org
  creation; if org creation was skipped this may fail).
- Try: `POST /auth/login` as platform admin first to confirm connectivity.

### ❌ API key: support-runtime-key (or similar)
- `POST /api-keys` failed — check the platform admin token is valid.

### ⏭ Runtime traffic — LLM calls
- No LLM provider credentials are configured. Add a provider credential
  via **Settings → Keys** in the UI, or via `POST /provider-credentials`.
  All gateway calls route through the provider, so this is required for
  real traffic.

### ❌ Policy enforcement — request blocked (403)
- Guard mode may not be in `enforce` mode, or the policy rule was not
  picked up. Check `/guard-modes` and `/policies` via the API.

### ⏭ GET /relationships
- The relationship mapping feature is not yet implemented in the backend.
  This is expected — the skip is intentional.

### ❌ Health check (/health)
- The backend is unreachable. Check `BASE_URL` and that the service is up.

---

## Understanding skips vs failures

| Default mode | `--strict` mode |
|---|---|
| `⏭ SKIPPED` — optional feature not yet implemented, or requires credentials | `❌ FAILED` — any skip is treated as a failure |

Use **default mode** during development when some features are still being built.

Use **`--strict`** mode in CI or before a customer demo to ensure everything
that can work does work.

---

## How this validates customer readiness

Running this script against a fresh deployment answers:

1. **Can a new customer onboard?** (Flows 1–2)
2. **Does the gateway correctly route traffic?** (Flow 3)
3. **Does the security scanner detect sensitive data?** (Flow 4)
4. **Does policy enforcement actually block requests?** (Flow 5)
5. **Does the inventory discover all active agents?** (Flow 6)
6. **Are all monitoring/dashboard endpoints healthy?** (Flow 8)

A full green run (no ❌) with `--strict` means the platform is ready for a
real customer onboarding.

---

## Notes on idempotency

The script is designed to be safe to run multiple times:

- **Users** — 409 "already exists" is treated as a pass (skip with note).
- **API keys** — new keys are created on each run (old ones are not deleted
  automatically; use the UI or `DELETE /api-keys/{id}` to clean up).
- **Budget and policy rules** created in Flow 5 are deleted at the end of
  that flow, even if a test fails.
- **Guard modes** set to `enforce` during Flow 5 are reset to `observe`
  during cleanup.
- **Org and admin user** — skipped gracefully if they already exist.

---

## Example output

```
══════════════════════════════════════════════════════════════
  AI Asset Management — Synthetic Customer Test Suite
  Backend : http://localhost:8000
  Org     : Acme AI Inc.
  Mode    : live
══════════════════════════════════════════════════════════════

──────────────────────────────────────────────────────────────
  Flow 1 — Platform admin onboarding
──────────────────────────────────────────────────────────────
  ✅ Platform admin login
  ⏭  Organization creation — Acme AI Inc.
       POST /admin/organizations returned 404 — endpoint not yet implemented.
  ✅ Acme admin user creation
  ✅ Acme admin login
  ✅ Auth /me — org context present

──────────────────────────────────────────────────────────────
  Flow 2 — Org setup
──────────────────────────────────────────────────────────────
  ✅ Create analyst user (analyst@acme.ai)
  ✅ Create viewer user (viewer@acme.ai)
  ✅ API key: support-runtime-key
  ✅ API key: sales-runtime-key
  ✅ API key: security-runtime-key
  ✅ Guard mode: Support → observe
  ✅ Guard mode: Sales → observe
  ✅ Guard mode: Operations → observe
  ✅ Guard mode: Security → observe
  ✅ Org config: pii_redaction_mode = findings_only

...

══════════════════════════════════════════════════════════════
  Synthetic Customer Test Report
  Backend : http://localhost:8000
  Org     : Acme AI Inc.
══════════════════════════════════════════════════════════════
  ✅ Platform admin login
  ⏭  Organization creation — Acme AI Inc.
  ✅ Acme admin user creation
  ...
──────────────────────────────────────────────────────────────
  24 passed · 3 skipped · 0 failed
══════════════════════════════════════════════════════════════
```
