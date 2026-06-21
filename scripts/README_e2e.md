# Full Synthetic Customer E2E Test Suite

Validates **every major product feature** through a single synthetic customer
scenario (Acme AI Inc.), from first login through billing reconciliation.
96+ checks across 23 sections — all in one pass.

---

## What the test does

| § | Section | What it validates |
|---|---------|------------------|
| 01 | Health / startup | `/health` and `/` return 200 |
| 02 | Platform admin login | JWT login + `/auth/me` context |
| 03 | Organization management | `POST /admin/organizations` (graceful 404 if not implemented) |
| 04 | User management | Create admin/analyst/viewer, list, `/auth/me` |
| 05 | Role / team management | List, create custom role, patch, delete |
| 06 | API key management | Create 3 keys, list, patch |
| 07 | Provider credentials | List credentials, settings/keys, fake key submission |
| 08 | Guard mode / settings | List guard modes, set to observe, read/write config |
| 09 | OpenAI proxy | 5 agents × `POST /v1/chat/completions` with SDK headers |
| 10 | Anthropic proxy | `POST /v1/messages` with Claude model |
| 11 | Agent inventory | `/assets`, `/assets/summary`, `/agents`, `/agents/summary`, unassigned |
| 12 | Relationship mapping | `/relationships`, `/relationships/graph` (graceful 404) |
| 13 | PII detection | 4 scan payloads (email, SSN, credit card, API key) |
| 14 | Budget enforcement | Create budget, list, status, cleanup |
| 15 | Policy enforcement | Enforce mode → block rule → expect 403 → cleanup |
| 16 | Telemetry | `/telemetry` and `/telemetry/summary` |
| 17 | Audit | `/audit` with and without filters |
| 18 | Security alerts | `/security/alerts` |
| 19 | Cost intelligence | Overview, billing import, period list/detail |
| 20 | Pricing registry | List, status, sync-status, pricing override |
| 21 | Dashboard read APIs | All 24 major read endpoints return 200 |
| 22 | Rate limiting | 10 rapid login attempts trigger 429 (opt-in) |
| 23 | Sessions / chat | Create, list, chat, messages, delete |

---

## Required environment variables

| Variable | Default | Notes |
|----------|---------|-------|
| `PLATFORM_ADMIN_PASSWORD` | *(none — required)* | Password for the platform admin |
| `BASE_URL` | `http://localhost:8000` | Backend URL, no trailing slash |
| `PLATFORM_ADMIN_EMAIL` | `admin@ai-asset-mgmt.local` | Platform admin email |
| `ACME_ADMIN_EMAIL` | `admin@acme.ai` | Synthetic Acme admin email |
| `ACME_ADMIN_PASSWORD` | `AcmeAdmin1!` | Synthetic Acme admin password |

---

## CLI flags

| Flag | Description |
|------|-------------|
| `--strict` | Treat skips as failures (use in CI) |
| `--dry-run` | Print the test plan without sending requests |
| `--skip-live-llm` | Skip §09, §10, §23 chat (no provider credential needed) |
| `--include-rate-limit` | Enable §22 (hammers the login endpoint 10×) |
| `--base-url URL` | Override `BASE_URL` |
| `--admin-email EMAIL` | Override `PLATFORM_ADMIN_EMAIL` |
| `--admin-password PWD` | Override `PLATFORM_ADMIN_PASSWORD` |

---

## How to run

### Dry-run (no requests sent)

```bash
python scripts/synthetic_customer_e2e.py --dry-run
```

### Default run (local backend, skip live LLM)

```bash
BASE_URL=http://localhost:8000 \
PLATFORM_ADMIN_PASSWORD=Admin123! \
python scripts/synthetic_customer_e2e.py --skip-live-llm
```

### Full run with live LLM

```bash
BASE_URL=http://localhost:8000 \
PLATFORM_ADMIN_PASSWORD=Admin123! \
python scripts/synthetic_customer_e2e.py
```

### CI / strict mode

```bash
BASE_URL=http://localhost:8000 \
PLATFORM_ADMIN_PASSWORD=Admin123! \
python scripts/synthetic_customer_e2e.py --strict --skip-live-llm
```

### Against Render deployment

```bash
BASE_URL=https://ai-asset-backend.onrender.com \
PLATFORM_ADMIN_PASSWORD=<render-password> \
python scripts/synthetic_customer_e2e.py --skip-live-llm
```

With strict mode for a pre-release check:

```bash
BASE_URL=https://ai-asset-backend.onrender.com \
PLATFORM_ADMIN_PASSWORD=<password> \
python scripts/synthetic_customer_e2e.py --strict --skip-live-llm
```

> **Note:** First Render request can take 30–60 s if the instance has spun down.

### With rate limiting

```bash
PLATFORM_ADMIN_PASSWORD=Admin123! \
python scripts/synthetic_customer_e2e.py --include-rate-limit
```

---

## Understanding skips vs failures

| Default mode | `--strict` mode |
|---|---|
| `⏭ SKIPPED` — optional feature or missing credentials | `❌ FAILED` — any skip is a failure |

Sections that are *always* skippable (never strict-failed):
- **§03 Organization management** — `POST /admin/organizations` is not yet implemented
- **§12 Relationship mapping** — `/relationships` is not yet implemented
- **§22 Rate limiting** — opt-in only; never strict-failed

---

## What failures usually mean

### §01 Health check
Backend is not running at `BASE_URL`.

### §02 Platform admin login
`PLATFORM_ADMIN_PASSWORD` is wrong or not set. The backend may also be unreachable.

### §04 User creation (409)
Treated as a pass — the user already exists from a previous run.

### §06 API key creation
Requires a valid admin JWT. Check §02 / §04 first.

### §09–§10 Proxy calls (400 / 503)
No LLM provider credential is configured. Use `--skip-live-llm` to skip these,
or add a provider via `POST /provider-credentials` (Settings → Keys in the UI).

### §13 PII detection (0 findings)
The security scanner did not flag the test text. Check `/security/scan`
independently and verify the scanner is enabled.

### §15 Policy block (not 403)
Guard mode may not have switched to `enforce`, or the policy rule was not picked
up. Check `/guard-modes` and `/policies` via the API.

### §19 Billing import (4xx)
Verify the request body has `billing_period_start`, `billing_period_end`, and
`actual_billed_cost_usd`. Provider must be one of:
`openai`, `anthropic`, `gemini`, `google`, `bedrock`, `azure`.

### §20 Pricing override (4xx)
Admin role required. Verify the Acme admin token has admin privileges.

### §22 Rate limiting (no 429)
The rate limiter may have a higher threshold than 10 requests, or may be
disabled in local dev mode.

---

## Security invariants

This script strictly follows these rules:

- **No real PII** — all test data uses obviously fake values
  (`test-user@example-domain.com`, `123-45-6789`, `4111-1111-1111-1111`,
  `sk-TESTFAKEAPIKEY0123456789ABCDE`)
- **API keys never printed raw** — only the masked form (`gk-****…xxxx`) appears
  in output
- **JWT tokens never printed** — tokens are stored in `State` but never logged

---

## Idempotency

The script is safe to re-run:

- **Users** — 409 "already exists" is treated as a pass
- **API keys** — new keys created on each run (delete old ones via
  `DELETE /api-keys/{id}` or the UI)
- **Budget / policy** created in §14–§15 are always deleted in the same section,
  even on partial failure
- **Guard mode** always reset to `observe` at the end of §15
- **Custom role** in §05 is always deleted if created

---

## Differences from `synthetic_customer.py`

| Feature | `synthetic_customer.py` | `synthetic_customer_e2e.py` |
|---|---|---|
| HTTP client | `requests` | `httpx` |
| Sections | 8 flows | 23 sections |
| Checks | ~38 | ~96+ |
| Anthropic proxy | — | §10 |
| Cost intelligence | — | §19 |
| Pricing registry | — | §20 |
| Dashboard sweep | — | §21 (24 endpoints) |
| Rate limiting | — | §22 (opt-in) |
| Sessions / chat | — | §23 |
| `--skip-live-llm` | — | Yes |
| `--include-rate-limit` | — | Yes |
