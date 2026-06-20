# AI Asset Management

**AI Runtime Intelligence Platform — inline governance, cost control, and security for every LLM call in your organisation.**

> Closer to Cloudflare or Okta for AI traffic than to a dashboard tool. Every agent call flows *through* it — PII scanned, budget enforced, policy checked, fully audited — before it reaches the model.

---

## The Integration

```python
# Before
client = openai.OpenAI(api_key="sk-...")

# After — one line change, full governance
client = openai.OpenAI(
    base_url="https://your-guard-instance/v1",
    api_key="<jwt>",
)
```

Works with OpenAI SDK, Anthropic SDK, LangChain, Node.js, and any HTTP client. No agent code changes beyond `base_url`.

---

## Architecture

```
Agent / SDK  (OpenAI · Anthropic · LangChain · curl)
      │  base_url = https://your-guard/v1
      ▼
POST /v1/chat/completions  (OpenAI-compatible)
POST /v1/messages          (Anthropic-compatible)
      │
      ├─ JWT or opaque Bearer auth
      ├─ PII / sensitive data scan  (10 pattern types)
      ├─ Model policy check         (allowlist / blocklist per team)
      ├─ Budget enforcement         (daily / monthly per team + agent)
      ├─ Real upstream SSE streaming + disconnect detection
      └─ Telemetry saved to SQLite
                   │
           React Dashboard
  (Overview · Cost Intelligence · Agent Inventory ·
   Pricing Registry · Models · Workflows · Alerts ·
   Budgets · Security · Audit · Users · Settings ·
   Integrations · Chat)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| ORM / DB | SQLAlchemy + SQLite |
| Auth | HS256 JWT (pure Python) |
| LLM clients | OpenAI SDK (multi-provider via compatible endpoints) |
| Encryption | Fernet (per-org provider credential storage) |
| Frontend | React 19 + Vite 8 + Tailwind CSS 4 + Recharts |
| Deploy | Render (backend web service + persistent disk + static frontend) |

---

## Features

### Gateway
- **OpenAI-compatible proxy** — `POST /v1/chat/completions` accepts any OpenAI SDK call
- **Anthropic-compatible proxy** — `POST /v1/messages` accepts any Anthropic SDK call
- **Real streaming** — SSE chunks relayed as they arrive from the upstream provider; client disconnect stops the upstream call immediately (no wasted tokens)
- **Full body passthrough** — `tool_calls`, `temperature`, `response_format`, `seed`, and every other parameter forwarded unchanged
- **Opaque Bearer auth** — accepts dashboard JWT *or* any arbitrary token (`sk-...`); no agent code changes required
- **Fail mode** — `GATEWAY_FAIL_MODE=closed` (default) blocks on errors; `open` passes through. Policy/budget blocks always propagate.
- **Provider routing** by model name prefix: `claude-*` → Anthropic, `gemini-*` → Google, `llama-*` → Local/Ollama, everything else → OpenAI
- **Bring Your Own Key (BYOK)** — per-org provider credentials stored encrypted (Fernet); used in place of server-level env vars when present

### Enforcement Pipeline (every call)
1. **PII scan** — emails, phone numbers, credit cards, SSNs, API keys, passwords, AWS keys, private keys, JWT tokens, IP addresses
2. **Model policy** — per-team allowlist / blocklist; blocked calls return HTTP 403 and are logged
3. **Budget check** — per-team and per-agent daily/monthly limits; `action=alert` warns, `action=block` returns HTTP 429
4. **LLM call** — forwarded to the real provider
5. **Telemetry** — tokens, cost (versioned per-model pricing), latency, team, agent, PII findings all persisted

### Auth & Users
- JWT login (`POST /auth/login`) with 8-hour expiry
- Role-based access: **admin** / **analyst** / **viewer**
- Admin user seeded automatically on first start
- User CRUD with inline role/team editing
- Settings page: live API key management (reads/writes `.env` without restart)

### AI Agent Inventory
- **Two-tier discovery**: *Verified* agents (seen in gateway traffic, confidence 95%) vs *Potential* agents (platform signals, confidence 30-70%)
- **Stable identity**: `asset_key = sha256(org_id + ":" + agent_id_raw)` — survives restarts and renames
- **Governance lifecycle**: `unassigned → managed → retired`; claim, retire, and annotate agents from the UI
- **CMDB model**: immutable `telemetry` table (runtime facts) + mutable `asset_registry` (governance layer)
- Filter by team, environment, discovery status, and confidence tier

### Cost Intelligence
Three-layer financial analysis:
1. **Runtime estimate** — token counts × versioned pricing from the Pricing Registry
2. **Provider billed** — import actual invoices (API / manual / CSV); stored in `provider_billing`
3. **Reconciliation** — variance analysis per period per provider; healthy < 2%, warning 2-5%, investigate > 5%

- Cost breakdown by agent, team, model, environment, or provider
- Daily cost trend charts (Recharts)
- Per-agent cost detail: monthly, lifetime, models used, cost signals

### Pricing Registry
- **Versioned, immutable rows** — prices are never updated; each change inserts a new version with `effective_from` / `effective_to` timestamps
- **Org-specific overrides** — `organization_id = NULL` = global default; non-null = org override that shadows the global row
- **Background sync daemon** — compares built-in price table against DB every 3600 s; creates new versions on drift
- **Historical cost accuracy** — `get_active_pricing(as_of=timestamp)` returns the price that was active at any past datetime, enabling cost replay
- **Admin UI** — view all prices, filter by provider, see version history per model, apply overrides with mandatory audit reason
- **Freshness warnings** — amber > 24 h, red > 48 h since last sync
- 24 models seeded on first start across OpenAI, Anthropic, Google, and Local

### Security & Compliance
- 8 automated detection rules (cost spike, large prompt, workflow failure spike, premium model misuse, after-hours activity, agent loop, unapproved model, sensitive data)
- Each alert includes root cause analysis and recommended remediation
- Full audit log — expandable rows with prompt, response, block reason, PII findings; load-more pagination
- TLS via reverse proxy, HS256 JWT, secrets never returned via API, all data stays in your deployment

---

## Dashboard Pages

| Page | Who can see it |
|---|---|
| Home | Everyone |
| Overview, Agents, Models, Workflows, Alerts | Everyone |
| Agent Inventory | Everyone |
| Cost Intelligence | Everyone |
| Security (alerts + PII scanner) | Everyone |
| Security (policy rules + audit log) | Admin only |
| Pricing Registry | Admin only |
| Budgets, Users, Settings | Admin only |
| Integrations | Admin + Analyst |
| Chat | Admin + Analyst |

- **Sortable columns** on every table — click any header to toggle asc/desc
- **Free-text search** on every table — instant filter across all columns, shows match count
- **Live mode** (real API data) / **Demo mode** (synthetic events) — switches automatically

---

## Quick Start

### Prerequisites
- Python 3.12+
- Node.js 18+

### Backend

```bash
git clone https://github.com/ronhaviv33-beep/ai-asset-management.git
cd ai-asset-management

python -m venv venv
source venv/bin/activate          # Mac/Linux
venv\Scripts\Activate.ps1         # Windows PowerShell

pip install -r requirements.txt

cp .env.example .env              # then fill in your API keys

uvicorn app.main:app
# API + Swagger UI → http://localhost:8000/docs
```

### Frontend

```bash
cd dashboard
npm install
npm run dev
# Dashboard → http://localhost:5173
```

### `.env` reference

```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
LOCAL_LLM_URL=http://localhost:11434/v1   # Ollama / vLLM / LM Studio
JWT_SECRET=change-me-in-production        # long random string
GATEWAY_FAIL_MODE=closed                  # closed | open
CREDENTIAL_ENCRYPTION_KEY=               # Fernet key for BYOK credential storage
```

### Seed demo data

```bash
python scripts/seed_demo_data.py
```

Populates the database with demo organizations, users, agents, and telemetry records.

---

## Data Model

| Table | Purpose |
|---|---|
| `organizations` | Multi-tenant org registry |
| `users` | Auth accounts; role (admin / analyst / viewer) |
| `roles` | Custom role definitions per org; page + capability ACLs |
| `api_keys` | Machine-to-machine auth; stored as SHA-256 hash |
| `provider_credentials` | Encrypted per-org LLM keys (Fernet / BYOK) |
| `telemetry` | Immutable proxy call records — tokens, cost, latency, PII findings |
| `asset_registry` | Governance layer for AI agents; lifecycle, owner, criticality |
| `teams` | Auto-registering soft team registry |
| `guard_modes` | Per-team governance mode (observe / alert / enforce) |
| `policy_rules` | Model allowlist / blocklist per team |
| `budget_rules` | Spend limits (daily / monthly, alert / block) |
| `chat_sessions` | Multi-turn session metadata |
| `chat_session_messages` | Session message history with security findings |
| `model_pricing` | Versioned pricing registry; immutable rows, org overrides |
| `pricing_change_log` | Audit trail for all pricing changes |
| `provider_billing` | Actual provider invoices imported for reconciliation |
| `cost_reconciliation` | Variance analysis between runtime estimates and billed amounts |

---

## API Reference

### OpenAI-compatible proxy

```python
import openai

client = openai.OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="<jwt from POST /auth/login>",
)

response = client.chat.completions.create(
    model="gpt-4o-mini",   # or "claude-sonnet-4-6", "gemini-2.0-flash", etc.
    messages=[{"role": "user", "content": "Hello"}],
    extra_headers={"X-Guard-Team": "SOC", "X-Guard-Agent": "my-agent"},
)
print(response.choices[0].message.content)

# Streaming
stream = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello"}],
    stream=True,
    extra_headers={"X-Guard-Team": "SOC", "X-Guard-Agent": "my-agent"},
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")
```

### Anthropic-compatible proxy

```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:8000",
    api_key="<jwt>",
    default_headers={"X-Guard-Team": "SOC", "X-Guard-Agent": "my-agent"},
)

message = client.messages.create(
    model="claude-haiku-4-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}],
)
print(message.content[0].text)
```

### Attribution headers

| Header | Purpose |
|---|---|
| `X-Guard-Team` | Maps the call to a team for policy + budget enforcement |
| `X-Guard-Agent` | Identifies the agent/workflow in telemetry and audit log |

### Key endpoints

```http
POST /auth/login                          # { email, password } → { access_token, user }
POST /ask                                 # Single-shot LLM request with enforcement pipeline
POST /chat                                # Multi-turn with enforcement pipeline
GET  /telemetry                           # Paginated request log
GET  /telemetry/summary                   # Totals: requests, tokens, cost, latency
GET  /audit                               # Filtered audit log (team, agent, sensitive, blocked)
GET  /security/alerts                     # Live detection rule results
POST /budgets                             # Create budget rule
GET  /budgets/status                      # Live spend vs limit per rule
POST /policies                            # Create model allow/block rule
GET  /agents                             # Agent inventory (verified + potential)
GET  /agents/summary                      # Discovery stats
GET  /cost-intelligence                   # Cost overview, breakdown, trends
POST /billing/{provider}/import           # Import provider invoice
GET  /pricing-registry                    # All pricing records (org overrides merged)
POST /pricing-registry/override           # Apply org-specific price override (admin)
POST /pricing-registry/sync              # Trigger immediate pricing sync (admin)
GET  /settings/keys                       # API key status (never exposes values)
```

Full interactive docs at `http://localhost:8000/docs`.

---

## Deploy to Render

The repo includes a `render.yaml` Blueprint. Connect your GitHub repo in Render → **New** → **Blueprint** → select the repo.

Render will:
1. Create the backend web service with a 1 GB persistent disk for SQLite
2. Build the frontend, injecting the backend URL at build time via `VITE_API_URL`
3. Deploy both services with security headers and SPA routing configured

After first deploy, set `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and/or `GOOGLE_API_KEY` in the Render dashboard (or via the Settings page in the UI).

---

## Supported Models

| Provider | Models |
|---|---|
| OpenAI | `gpt-4.1`, `gpt-4.1-mini`, `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `o3`, `o4-mini` |
| Anthropic | `claude-opus-4-8`, `claude-sonnet-4-6`, `claude-haiku-4-5` |
| Google | `gemini-2.5-pro`, `gemini-2.0-flash`, `gemini-1.5-pro` |
| Local | `llama-3.1-70b-local`, `llama-3.1-8b-local` (Ollama / vLLM / LM Studio) |

Pricing for all models is seeded into the Pricing Registry on first start and kept in sync by the background daemon.

---

## Roadmap

| Status | Item |
|---|---|
| ✅ | OpenAI-compatible proxy (`/v1/chat/completions`) with real streaming |
| ✅ | Anthropic-compatible proxy (`/v1/messages`) with real streaming |
| ✅ | JWT auth + RBAC (admin / analyst / viewer) |
| ✅ | PII scanning (10 pattern types) |
| ✅ | Budget enforcement (daily / monthly, alert / block) |
| ✅ | Model policy (allowlist / blocklist per team) |
| ✅ | Full audit log with expandable rows + pagination |
| ✅ | Bring Your Own Key (BYOK) — per-org encrypted provider credentials |
| ✅ | AI Agent Inventory — two-tier discovery (verified / potential), CMDB governance |
| ✅ | Cost Intelligence — three-layer analysis (runtime / billed / reconciliation) |
| ✅ | Pricing Registry — versioned, org-scoped, background sync, history |
| ✅ | Sortable + searchable tables on every dashboard page |
| ✅ | Render deployment (`render.yaml` Blueprint) |
| 🔜 | Per-tenant API key table (issue org keys, not user JWTs) |
| 🔜 | Budget alerts via webhook (Slack / Teams at 80%) |
| 🔜 | Cost forecasting (end-of-month projection from burn rate) |
| 🔜 | SSO (Okta / Google OAuth) |
| 🔜 | HA / fail-over story for enterprise SLA conversations |

---

## Author

**Ron Haviv**  
SOC Analyst · Security Operations · AI Runtime Intelligence
