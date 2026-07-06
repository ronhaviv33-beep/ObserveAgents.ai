# ObserveAgents

**The System of Record for Enterprise AI**

> ObserveAgents helps organizations understand, govern, and improve enterprise AI agents from runtime evidence.

Every AI agent leaves evidence when it runs. ObserveAgents turns that evidence into a canonical AI inventory — what exists, who owns it, what it depends on, what needs attention — and into recommendations for what each agent should improve next.

- Website: https://www.observeagents.ai
- Dashboard: https://app.observeagents.ai
- Gateway: https://gateway.observeagents.ai

> Hosting note: the platform is also reachable at the Render fallback URL (`https://ai-asset-app.onrender.com`); the custom domains above are canonical.

---

## Product Surfaces

ObserveAgents ships as **two products on one shared spine** — both feed and read the same canonical AI inventory.

### ObserveAgents Observability

> **See what AI is actually running.**

For organizations that can send telemetry. Point any OpenTelemetry exporter at Observe and runtime evidence becomes intelligence:

- **OpenTelemetry / OTLP ingestion** — JSON and protobuf, GenAI semantic conventions understood natively
- **Runtime evidence** — execution timelines, sessions, per-step waterfalls
- **AI inventory** — every system discovered automatically, no manual registration
- **Ownership** — claim, assign, and govern each discovered system
- **Dependencies** — the models, tools, MCP servers, databases, and APIs each agent touches
- **Findings** — security, performance, operations, dependency, and inventory signals per system
- **Observe-only guardrail recommendations** — detect, explain, recommend; nothing is blocked
- **Advisor recommendations** — what each agent should learn or improve next ([roadmap](docs/roadmap.md))

### ObserveAgents Gateway

> **Control AI traffic without instrumenting every app.**

For organizations that do not want — or cannot — instrument every application. One `base_url` change puts AI traffic behind a controlled endpoint:

- **Gateway endpoint** — OpenAI-compatible and Anthropic-compatible proxies; keep your existing SDKs and clients
- **Provider credentials / BYOK** — per-org encrypted provider keys managed in one place
- **Budgets** — daily/monthly thresholds per team or agent
- **Policies** — model allowlists/blocklists per team
- **Rate limits and optional enforcement** — observe → alert → enforce, one team at a time
- **Gateway usage & cost** — token and cost accounting from proxied traffic

**The core rule: Observability discovers and recommends. Gateway controls only when explicitly configured.**

### Which product surface should I use?

- Use **Observability** if you can send telemetry and want runtime evidence — inventory, dependencies, findings, and recommendations without touching application traffic.
- Use **Gateway** if you want traffic control — credentials, budgets, policies, optional enforcement — without instrumenting every app.

Both surfaces share the same inventory, so starting with one never blocks adopting the other.

---

## 🚀 Observability Quick Start

**Your starting point:** create an API key in the dashboard (**API Keys** → New — it starts with `gk-`), then pick the fastest path for you. Every path ends the same way: **open Runtime and watch your first trace appear.**

**Direct protobuf is the fastest developer quick start; a Collector remains the recommended enterprise deployment** for routing, processing, and multi-backend export.

### Path A — Instant proof (nothing to install)

Send one trace with curl and see it in Runtime seconds later:

```bash
curl -X POST "https://<your-observeagents-url>/otel/v1/traces" \
  -H "Authorization: Bearer gk-<your-api-key>" \
  -H "Content-Type: application/json" \
  -d '{"resourceSpans":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"my-first-agent"}}]},"scopeSpans":[{"spans":[{"traceId":"aaaa1111bbbb2222cccc3333dddd4444","spanId":"1111222233334444","name":"chat gpt-4o","kind":3,"startTimeUnixNano":"'$(date +%s%N)'","endTimeUnixNano":"'$(($(date +%s%N)+1200000000))'","status":{},"attributes":[{"key":"gen_ai.operation.name","value":{"stringValue":"chat"}},{"key":"gen_ai.provider.name","value":{"stringValue":"openai"}},{"key":"gen_ai.request.model","value":{"stringValue":"gpt-4o"}}]}]}]}]}'
```

Open **Runtime** → `my-first-agent` is there, with an execution timeline. That's it.

### Path B — Already using OpenTelemetry

Point your existing exporter at Observe (OTLP/HTTP **JSON or protobuf** — protobuf SDKs can post directly; the Collector remains the recommended enterprise path — [details](docs/otel_ingestion.md)):

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=https://<your-observeagents-url>/otel
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer gk-<your-api-key>
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_SERVICE_NAME=my-agent
OTEL_RESOURCE_ATTRIBUTES=deployment.environment=production
```

### Path C — Richest auto-instrumentation (open-source, no proprietary SDK)

[OpenLLMetry](https://github.com/traceloop/openllmetry) auto-instruments OpenAI, Anthropic, Bedrock, LangChain, LlamaIndex, CrewAI, vector DBs and more — and emits **standard OpenTelemetry** that Observe consumes:

```python
pip install traceloop-sdk

from traceloop.sdk import Traceloop
Traceloop.init()   # OTLP/HTTP protobuf → straight to Observe
```

Point its exporter directly at Observe (`OTEL_EXPORTER_OTLP_ENDPOINT=https://<observe>/otel` + your `gk-` key — [details](docs/otel_ingestion.md#direct-otlp-protobuf-quick-start)), or through your Collector for enterprise routing. Two lines of code, full GenAI traces — with the open standard, not a vendor SDK.

Raw prompt/response content is **never stored** — see the [privacy guarantee](docs/otel_ingestion.md#privacy-guarantee). Full format, supported GenAI attributes, and Collector guidance: [docs/otel_ingestion.md](docs/otel_ingestion.md).

---

## 🔌 Gateway Quick Start

Three steps — no instrumentation, no telemetry setup:

**1. Point your existing client at the gateway endpoint** (one line):

```python
# Before
client = openai.OpenAI(api_key="sk-...")

# After — one line change
client = openai.OpenAI(
    base_url="https://gateway.observeagents.ai/v1",
    api_key="YOUR_GATEWAY_KEY",
)
```

**No proprietary SDK required — use your existing AI stack.** Works with OpenAI SDK, LangChain, CrewAI, LiteLLM, OpenAI Agents SDK, MCP Clients, Agno, PydanticAI, Vercel AI SDK, and any OpenAI-compatible client (Anthropic SDKs via `/v1/messages`).

**2. Configure provider credentials** — add your provider keys (BYOK) on the **Providers** page; they are stored encrypted per organization and used for your traffic.

**3. Set budgets, policies, and rate limits** — per team or agent, in the dashboard. Everything starts advisory: **observe → alert → enforce**, and nothing blocks until a team is explicitly set to enforce.

---

## Architecture

```
   Observability (OTLP)   Gateway (/v1 proxy)        Ecosystem Discovery (roadmap)
┌────────────────────────────────────────┐      ┌──────────────────────────────────┐
│ OTel exporter          Agent / SDK     │      │ GitHub · Jira · Slack · n8n · MCP│
│      │                     │           │      └──────────────────┬───────────────┘
│      ▼                     ▼           │                         │
│ POST /otel/v1/traces  POST /v1/chat/…  │                         ▼
│ (JSON + protobuf)     POST /v1/messages│               future evidence tables
│      │                     │           │
│  privacy scrub         guard modes     │
│  (prompts never        (observe/alert/ │
│   stored)               enforce)       │
└──────┬─────────────────────┬───────────┘
       ▼                     ▼
 otel_spans · otel_assets · telemetry · provenance_events
       │
       ▼
 asset_registry  (canonical AI inventory — single source of truth)
       │
       ▼
 derive_asset_intelligence()
 asset_capabilities · asset_findings
       │
       ▼
           React Dashboard
  (Dashboard · Runtime · Asset Intelligence · Security Intelligence ·
   Cost Intelligence · Budgets · Pricing Registry · Guardrails ·
   Dependency Map · Discovery · Ecosystem · Setup · Users · Settings)
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

Grouped by product surface. Shared spine (inventory, pricing reference, auth) listed once at the end.

## Observability Features

### Runtime Discovery (OpenTelemetry)
- **OTLP/HTTP ingestion (JSON + protobuf)** — `POST /otel/v1/traces` accepts standard OTel spans in both encodings; agents are discovered from `agent.name` / `service.name` and reconciled into the canonical inventory
- **GenAI semantic conventions** — models, providers, tools, MCP servers, databases, workflows, and external APIs extracted from `gen_ai.*`, `tool.*`, `mcp.*`, `db.*`, and `url.*` attributes
- **Evidence summary** — one `otel_assets` row per (service, environment) aggregating models/providers/tools/dependencies with first/last seen and trace/span counts
- **Privacy guarantee** — `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`, `tool.arguments`, and `tool.result` are never stored; only SHA-256 hash + byte size
- **Provenance** — one semantic event per span (llm_call / tool_call / db_call / external_api_call / agent_step)

### Runtime Execution Timeline
- `GET /runtime/traces` — recent executions with root span, duration, span and error counts
- `GET /runtime/traces/{trace_id}` — full span tree with per-step offsets and durations for the trace waterfall
- **Runtime Step classification** — each span typed as llm / tool / database / external_api / step
- Dashboard **Runtime** page: trace list → click into an execution timeline showing where each request spent its time

### Asset Intelligence
- **Capabilities** (`asset_capabilities`) — what each AI system can do, derived from OTel evidence: provider, model, mcp, database, filesystem, shell, messaging, source_control, crm, retrieval, external_api, runtime
- **Findings** (`asset_findings`) — normalized signals across five categories: security (shell_enabled, database_access, mcp_enabled, sensitive_system_access), performance (slow_llm_call, slow_tool_call, slow_runtime_step), operations (production_runtime, runtime_error, unmanaged_runtime), dependency (external_api_access, broad_tool_access), inventory (new_ai_system_detected, unknown_model)
- **Grouped by AI system** — `GET /intelligence/asset-summary` returns one object per asset with runtime evidence, capability surface, finding counts, and status badges (active / runtime_observed / has_findings / error_observed)
- Finding lifecycle: open → dismissed / resolved; idempotent derivation, no duplicates
- See [docs/asset_intelligence.md](docs/asset_intelligence.md) for the full catalog

### Advisory Guardrails (observe-only)
- Seven guardrails evaluated live against observed capabilities and findings — database access, MCP tools, external APIs, broad tool access, production + high-severity findings, runtime errors, slow execution paths
- **Detect, explain, recommend — nothing is blocked.** Observability never enforces; when a team wants control, enforcement lives in the Gateway and only when explicitly configured (see the core rule above)

### Security Intelligence
Answers: *which AI systems have risky runtime-observed behavior?*
- **Risky AI Systems** — per-system risky capability surface (mcp / database / shell / external_api / crm / filesystem) with open security findings and high-severity counts, derived from asset intelligence
- **Runtime security signals** — monitor unmanaged assets, high-capability agents, risky capability surfaces, and unusual runtime behavior
- 8 automated detection rules (cost spike, large prompt, workflow failure spike, premium model misuse, after-hours activity, agent loop, unapproved model, unvetted model)
- Each alert includes root cause analysis and recommended remediation
- Full audit log — expandable rows with prompt, response, block reason, and findings; load-more pagination
- Optional sensitive-content checks — can be enabled per org for customers that want additional runtime safety signals
- TLS via reverse proxy, HS256 JWT, secrets never returned via API, all data stays in your deployment

## Gateway Features

### Gateway
- **OpenAI-compatible proxy** — `POST /v1/chat/completions` accepts any OpenAI SDK call
- **Anthropic-compatible proxy** — `POST /v1/messages` accepts any Anthropic SDK call
- **Real streaming** — SSE chunks relayed as they arrive from the upstream provider; client disconnect stops the upstream call immediately (no wasted tokens)
- **Full body passthrough** — `tool_calls`, `temperature`, `response_format`, `seed`, and every other parameter forwarded unchanged
- **Opaque Bearer auth** — accepts dashboard JWT *or* any arbitrary token (`sk-...`); no agent code changes required
- **Fail mode** — `GATEWAY_FAIL_MODE=closed` (default) blocks on errors; `open` passes through. Policy/budget blocks always propagate.
- **Provider routing** by model name prefix: `claude-*` → Anthropic, `gemini-*` → Google, `llama-*` → Local/Ollama, everything else → OpenAI
- **Bring Your Own Key (BYOK)** — per-org provider credentials stored encrypted (Fernet); used in place of server-level env vars when present

### Gateway Pipeline (every proxied call — advisory by default)
Blocking only occurs for teams explicitly set to **enforce** guard mode; teams start in **observe** (nothing blocked).
1. **Safety check** — model policy evaluation; in enforce mode blocked calls return HTTP 403 and are logged. Optional sensitive-content scan (10 pattern types) can be enabled per org.
2. **Budget check** — per-team and per-agent daily/monthly thresholds; `action=alert` warns, `action=block` returns HTTP 429 in enforce mode
3. **LLM call** — forwarded to the real provider
4. **Telemetry** — tokens, cost (versioned per-model pricing), latency, team, agent, and findings all persisted
5. **Relationship capture** — non-fatal; extracts runtime dependencies from headers and upserts into `agent_relationships`

### Runtime Dependency Map
The second pillar of the system of record — maps what every AI agent touches at runtime.

- **Header-based detection** — reads `X-Agent-Name`, `X-MCP-Server`, `X-MCP-Tool`, `X-Agent-Workflow`, `X-Agent-Target`, and `X-Workflow-*` headers on every proxied call
- **Target types**: `mcp_tool`, `mcp_server`, `workflow`, `api`, `database`, `crm`, `spreadsheet`, `unknown`
- **Relationship types**: `calls`, `uses_tool`, `invokes_workflow`, `triggers`, `writes_to`, `reads_from`, `sends_event_to`
- **Upsert with telemetry**: each rediscovery increments `request_count`, updates `last_seen_at`, and takes the max `confidence_score`
- **Metadata safety**: never stores raw prompt or response content; only header-derived facts
- **SDK support**: `build_headers()` accepts `mcp_server`, `mcp_tool`, `workflow_provider`, `workflow_name`, `parent_agent`, `target`, `tool`, `relation`
- `GET /relationships` — filterable list (source agent, target type, relationship type)
- `GET /relationships/graph` — nodes + edges for graph visualisation

**Add relationship headers to any agent call:**
```python
extra_headers={
    "X-Agent-Name":   "sales-enrichment-agent",
    "X-MCP-Server":   "hubspot-mcp",
    "X-MCP-Tool":     "create_lead",
    "X-Agent-Relation": "uses_tool",
}
```

### Cost Intelligence
Runtime usage and efficiency intelligence — which AI systems are heavy, slow, or likely expensive — plus three-layer financial analysis:
1. **Runtime estimate** — token counts × versioned pricing from the Pricing Registry
2. **Provider billed** — import actual invoices (API / manual / CSV); stored in `provider_billing`
3. **Reconciliation** — variance analysis per period per provider; healthy < 2%, warning 2–5%, investigate > 5%

- **Runtime Usage & Efficiency Signals** — per-system trace/span volume and slow-step findings surfaced as potential cost hotspots (signals, not billed amounts)
- Cost breakdown by agent, team, model, environment, or provider
- Daily cost trend charts (Recharts)
- Per-agent cost detail: monthly, lifetime, models used, cost signals

## Shared Spine

### AI Agent Inventory
- **Two-tier discovery**: *Verified* agents (seen in gateway traffic, confidence 95%) vs *Potential* agents (OTel-discovered and platform signals, confidence 30–70%; promoted to verified when claimed)
- **Stable identity**: `asset_key = sha256(org_id + ":" + agent_id_raw)` — survives restarts and renames
- **Governance lifecycle**: `unassigned → managed → retired`; claim, retire, and annotate agents from the UI
- **CMDB model**: immutable `telemetry` table (runtime facts) + mutable `asset_registry` (governance layer)
- Filter by team, environment, discovery status, and confidence tier

### Auth & Users
- JWT login (`POST /auth/login`) with 8-hour expiry
- Role-based access: **admin** / **analyst** / **viewer**
- Admin user seeded automatically on first start
- User CRUD with inline role/team editing
- Settings page: live API key management (reads/writes `.env` without restart)

### Pricing Registry
Model/provider pricing **reference layer** — the assumptions that feed cost estimation (estimates, not billing).
- **Versioned, immutable rows** — prices are never updated; each change inserts a new version with `effective_from` / `effective_to` timestamps
- **Org-specific overrides** — `organization_id = NULL` = global default; non-null = org override that shadows the global row
- **Background sync daemon** — compares built-in price table against DB every 3600 s; creates new versions on drift
- **Historical cost accuracy** — `get_active_pricing(as_of=timestamp)` returns the price that was active at any past datetime, enabling cost replay
- **Admin UI** — view all prices, filter by provider, see version history per model, apply overrides with mandatory audit reason
- **Freshness warnings** — amber > 24 h, red > 48 h since last sync
- 24 models seeded on first start across OpenAI, Anthropic, Google, and Local

---

## Dashboard Pages

Visible pages also depend on the built product surface (`VITE_PRODUCT_SURFACE`) — an Observability deployment hides gateway-control pages and vice versa. The table below is the combined superset by role:

| Page | Who can see it |
|---|---|
| Dashboard, Platform Guide | Everyone |
| Discovery Center, Agents, Runtime, Dependency Map, Ecosystem Discovery | Everyone |
| Asset Intelligence, Security Intelligence, Cost Intelligence | Everyone |
| Budgets (read-only for viewer/analyst; rules managed by admin) | Everyone |
| Pricing Registry, Guardrails | Everyone |
| Governance Readiness, Security & Audit, Users, API Keys, Settings | Admin only |
| Setup (Integrations) | Admin + Analyst |
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
git clone https://github.com/ronhaviv33-beep/ObserveAgents.ai.git
cd ObserveAgents.ai

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

Seeds the **Acme AI Operations** demo org with five realistic AI systems through the real OTel ingestion pipeline — traces, execution timelines, capabilities, and findings across all five categories. Idempotent; all data synthetic. Log in with `demo@observeagents.ai` / `Demo123!`, then open **Runtime** and **Asset Intelligence**. See [docs/demo_seed_data.md](docs/demo_seed_data.md).

---

## Data Model

| Table | Purpose |
|---|---|
| `organizations` | Multi-tenant org registry |
| `users` | Auth accounts; role (admin / analyst / viewer) |
| `roles` | Custom role definitions per org; page + capability ACLs |
| `api_keys` | Machine-to-machine auth; stored as SHA-256 hash |
| `provider_credentials` | Encrypted per-org LLM keys (Fernet / BYOK) |
| `telemetry` | Immutable proxy call records — tokens, cost, latency, agent identity, policy findings |
| `asset_registry` | Canonical AI inventory — single source of truth; lifecycle, owner, criticality |
| `otel_spans` | Raw OTel span records (privacy-scrubbed attributes — prompts never stored) |
| `otel_assets` | Runtime Discovery evidence — one row per (org, service, environment) with models/providers/tools/dependencies |
| `provenance_events` | One semantic event per span (llm_call / tool_call / db_call / external_api_call) |
| `asset_capabilities` | Derived capability surface per AI system (provider, model, mcp, database, shell, …) |
| `asset_findings` | Derived findings across security / performance / operations / dependency / inventory |
| `agent_relationships` | Runtime dependency map — what each agent calls, uses, or writes to |
| `teams` | Auto-registering soft team registry |
| `guard_modes` | Per-team governance mode (observe / alert / enforce) |
| `policy_rules` | Model allowlist / blocklist per team |
| `budget_rules` | Budget thresholds (daily / monthly; advisory alerts, block only in enforce guard mode) |
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
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello"}],
    extra_headers={
        "X-Guard-Team":     "SOC",
        "X-Guard-Agent":    "my-agent",
        # Relationship mapping (optional)
        "X-MCP-Server":     "hubspot-mcp",
        "X-MCP-Tool":       "create_lead",
        "X-Agent-Relation": "uses_tool",
    },
)
print(response.choices[0].message.content)
```

### Anthropic-compatible proxy

```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:8000",
    api_key="<jwt>",
    default_headers={
        "X-Guard-Team":  "SOC",
        "X-Guard-Agent": "my-agent",
    },
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
| `X-Agent-Name` | Primary agent identity for relationship mapping |
| `X-MCP-Server` | MCP server the agent is connecting to |
| `X-MCP-Tool` | Specific MCP tool being invoked |
| `X-Agent-Workflow` | Workflow being triggered |
| `X-Agent-Target` | Generic target system (API, database, CRM, etc.) |
| `X-Agent-Relation` | Explicit relationship type override |
| `X-Workflow-Provider` | Workflow platform (zapier, n8n, etc.) |
| `X-Workflow-Name` | Workflow name within the platform |

### Key endpoints

```http
POST /auth/login                          # { email, password } → { access_token, user }
POST /otel/v1/traces                      # OTLP/HTTP span ingestion, JSON + protobuf (Runtime Discovery)
GET  /runtime/traces                      # Recent executions (root span, duration, span/error counts)
GET  /runtime/traces/{trace_id}           # Full span tree for the execution timeline / waterfall
GET  /intelligence/asset-summary          # Intelligence grouped per AI system (the dashboard's primary shape)
GET  /intelligence/assets                 # Runtime Discovery evidence rows (otel_assets)
GET  /intelligence/capabilities           # Derived capabilities (filterable)
GET  /intelligence/findings               # Derived findings (filterable by category/severity/status)
POST /intelligence/run                    # Re-derive capabilities + findings (idempotent)
POST /intelligence/findings/{id}/dismiss  # Dismiss a finding
POST /intelligence/findings/{id}/resolve  # Resolve a finding
POST /ask                                 # Single-shot LLM request with enforcement pipeline
POST /chat                                # Multi-turn with enforcement pipeline
GET  /telemetry                           # Paginated request log
GET  /telemetry/summary                   # Totals: requests, tokens, cost, latency
GET  /audit                               # Filtered audit log (team, agent, sensitive, blocked)
GET  /security/alerts                     # Live detection rule results
POST /budgets                             # Create budget rule
GET  /budgets/status                      # Live spend vs limit per rule
POST /policies                            # Create model allow/block rule
GET  /agents                              # Agent inventory (verified + potential)
GET  /agents/summary                      # Discovery stats
GET  /relationships                       # Runtime dependency map (filterable)
GET  /relationships/graph                 # Dependency graph — nodes + edges
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

The deployment story matches the product split — **each frontend build targets exactly one surface via the build-time env var `VITE_PRODUCT_SURFACE`**:

| Target | Surface | What it is |
|---|---|---|
| `ai-asset-app` | `VITE_PRODUCT_SURFACE=observability` | The single backend (all APIs: OTLP ingestion **and** the `/v1` gateway proxy) + the **Observability** UI, on a persistent disk |
| `observeagents-gateway-console` | `VITE_PRODUCT_SURFACE=gateway` | Static build of the **Gateway** console UI, pointed at the same backend API |
| `ai-asset-demo` | *(unset → combined)* | Public demo only — the blended showcase surface; not the production story |
| `observeagents-website` | — | Public marketing site (`website/`) |

Notes:
- There is **one backend and one database** — the two surfaces are separate frontend builds over the same spine, exactly as designed in [docs/product_surface_separation_plan.md](docs/product_surface_separation_plan.md).
- `combined` (the unset default) exists for local development and the demo only; production targets always set `VITE_PRODUCT_SURFACE` explicitly.
- When attaching a hostname to the gateway console, add that origin to the backend's `FRONTEND_ORIGIN` env var for CORS.

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

The phased forward roadmap — including **Observe Advisor** and Agent Skill Recommendations — lives in [docs/roadmap.md](docs/roadmap.md).

| Status | Item |
|---|---|
| ✅ | OpenAI-compatible proxy (`/v1/chat/completions`) with real streaming |
| ✅ | Anthropic-compatible proxy (`/v1/messages`) with real streaming |
| ✅ | JWT auth + RBAC (admin / analyst / viewer) |
| ✅ | Safety checks — sensitive-content scan (10 pattern types, opt-in per org) |
| ✅ | Budget enforcement (daily / monthly, alert / block) |
| ✅ | Model policy (allowlist / blocklist per team) |
| ✅ | Full audit log with expandable rows + pagination |
| ✅ | Bring Your Own Key (BYOK) — per-org encrypted provider credentials |
| ✅ | AI Agent Inventory — two-tier discovery (verified / potential), CMDB governance |
| ✅ | Runtime Dependency Map — header-based relationship capture, graph API, dashboard page |
| ✅ | Cost Intelligence — three-layer analysis (runtime / billed / reconciliation) |
| ✅ | Pricing Registry — versioned, org-scoped, background sync, history |
| ✅ | Sortable + searchable tables on every dashboard page |
| ✅ | Render deployment (`render.yaml` Blueprint) |
| ✅ | OTel Runtime Discovery — OTLP/HTTP JSON ingestion with privacy scrubbing |
| ✅ | OTLP protobuf direct ingestion — same endpoint, no Collector required (OpenLLMetry-style onboarding) |
| ✅ | Runtime Execution Timeline — trace list + waterfall API and UI |
| ✅ | Asset Intelligence — capabilities + findings derived per AI system, grouped dashboard view |
| ✅ | Advisory Guardrails — observe-only guardrail catalog + per-team guard modes |
| ✅ | Demo seed data — five-system synthetic demo through the real ingestion pipeline |
| ✅ | Product surface separation — per-surface frontend builds (`VITE_PRODUCT_SURFACE=observability` / `gateway`) with explicit deploy targets |
| 🔜 | Ecosystem Discovery — GitHub / Jira / Slack / n8n / MCP evidence sources, Active/Dormant/Runtime-only correlation |
| 🔜 | Per-tenant API key table (issue org keys, not user JWTs) |
| 🔜 | Budget alerts via webhook (Slack / Teams at 80%) |
| 🔜 | Cost forecasting (end-of-month projection from burn rate) |
| 🔜 | MCP payload parsing for richer relationship evidence |
| 🔜 | SSO (Okta / Google OAuth) |
| 🔜 | HA / fail-over story for enterprise SLA conversations |

---

## Author

**Ron Haviv**  
SOC Analyst · Security Operations · Enterprise AI Intelligence

---

*Understand what AI exists, what is running, how it is connected, and how it evolves over time.*
