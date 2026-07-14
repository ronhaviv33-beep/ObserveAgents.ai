# ObserveAgents

**The runtime visibility and control layer for AI agents**

> ObserveAgents helps teams see, understand, and control their AI agents from runtime evidence.

**See what your AI agents are actually doing.** Connect OpenTelemetry or send normalized runtime events, discover your agents, inspect runtime behavior, detect risky patterns, and review what needs control — before it becomes a production problem. OpenTelemetry is one input path, not the whole product.

> **Observe first. Control only what matters.**

- Website: https://www.observeagents.ai
- Dashboard: https://app.observeagents.ai
- Gateway: https://gateway.observeagents.ai

> Hosting note: the platform is also reachable at the Render fallback URL (`https://ai-asset-app.onrender.com`); the custom domains above are canonical.

---

## How it works

The whole product is one evidence chain, and the UI is organized around it:

```
OTel / OTLP · Runtime Events  →  Runtime  →  Asset Intelligence  →  Security Intelligence
                                                    →  Detection Rules  →  Gateway Control Center
```

1. **AI systems send evidence** — OpenTelemetry traces from your existing OTel stack, or normalized GenAI runtime events via `POST /runtime-events`. Both converge on the same pipeline; no source gets its own findings engine.
2. **Runtime** shows what actually executed: sessions, traces, execution waterfalls.
3. **Asset Intelligence** turns evidence into inventory: assets, ownership, capabilities, dependencies, findings.
4. **Security Intelligence** explains which agents are risky and why — from runtime behavior, not scanners.
5. **Detection Rules** turn the same evidence into threshold-based alerts (built-in rules today: MCP tool-access threshold, repeated tool errors, unknown provider in production), surfaced on the **Rules & Alerts** page and deliverable to a webhook — evaluated only during the intelligence run, never at ingestion.
6. **Gateway Control Center** recommends the control path for the agents that need one — observe-only until control is explicitly configured.

**The core rule: Observability discovers and recommends. Gateway controls only when explicitly configured.** Nothing is ever blocked, rerouted, or enforced automatically.

---

## The product experience

One production app, two connected workspaces, built on the **ui2 design system** (evidence-first, risk-first, dark console — see [docs/ui_redesign_plan.md](docs/ui_redesign_plan.md)):

### Observe workspace — runtime evidence into understanding

| Page | What it answers |
|---|---|
| **Overview** | Is my AI estate healthy? Four primary metrics (assets discovered, agents with findings, agents needing owner, control candidates), an evidence-backed Zone of Attention that only shows live conditions, per-agent runtime activity, and a Gateway Control preview — with a visible 30-second refresh countdown |
| **Runtime** | What actually executed — traces grouped one row per agent session, expandable into a per-step execution waterfall; filter to one agent with a server-side refetch |
| **Asset Intelligence** | Every AI asset in master/detail: identity, runtime evidence, capabilities, dependencies, findings grouped by category, and its Gateway Control status — with worst-first sorting and evidence-backed filters (needs owner, security risk, gateway candidates, trace discovered) |
| **Security Intelligence** | Which agents are risky and why — seven investigation buckets (MCP/tool risk, database & API access, unknown providers, missing ownership, repeated tool errors, human review, and detection rule matches) over a worst-first findings list |
| **Rules & Alerts** | The detection-rule catalog (built-in rules + planned templates) and a recent-matches feed, with a webhook notification path — observe-only, no rule blocks anything |
| **Platform Guide** | The onboarding story: how data gets in, what you can see, what to do next |

### Gateway Control workspace — the action surface

| Page | What it does |
|---|---|
| **Gateway Control Center** | The review queue: agents recommended for Gateway control, each with trigger-finding provenance and suggested controls typed `soft` (available now), `routing` (route through Gateway), or `hard` (requires Gateway routing). Everyone can view; only admins act. *Observe can recommend. Gateway can enforce only when explicitly configured.* |
| **Providers / Budgets / Pricing / Cost** | Gateway configuration: BYOK credentials, budget thresholds, versioned pricing, proxied-traffic cost |

Every risky agent is one click from evidence to recommendation: **Review in Gateway Control Center →** appears on Overview, Asset Intelligence, and Security Intelligence for real candidates — no environment switch, no redeploy.

The design principles behind every screen: **evidence-first** (a number without evidence behind it doesn't ship), **risk-first hierarchy** (worst first, always), **progressive disclosure** (summaries first, waterfalls on demand), and **no enforcement confusion** (a recommendation renders as a review card, never a toggle).

---

## 🚀 Observability Quick Start

**Your starting point:** create an API key in the dashboard (**API Keys** → New — it starts with `gk-`), then pick the fastest path. Every path ends the same way: **open Runtime and watch your first trace appear.**

**Direct protobuf is the fastest developer quick start; a Collector remains the recommended production deployment** for routing, processing, and multi-backend export.

### Path A — Instant proof (nothing to install)

```bash
curl -X POST "https://<your-observeagents-url>/otel/v1/traces" \
  -H "Authorization: Bearer gk-<your-api-key>" \
  -H "Content-Type: application/json" \
  -d '{"resourceSpans":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"my-first-agent"}}]},"scopeSpans":[{"spans":[{"traceId":"aaaa1111bbbb2222cccc3333dddd4444","spanId":"1111222233334444","name":"chat gpt-4o","kind":3,"startTimeUnixNano":"'$(date +%s%N)'","endTimeUnixNano":"'$(($(date +%s%N)+1200000000))'","status":{},"attributes":[{"key":"gen_ai.operation.name","value":{"stringValue":"chat"}},{"key":"gen_ai.provider.name","value":{"stringValue":"openai"}},{"key":"gen_ai.request.model","value":{"stringValue":"gpt-4o"}}]}]}]}]}'
```

Open **Runtime** → `my-first-agent` is there, with an execution timeline. That's it.

### Path B — Already using OpenTelemetry

Point your existing exporter at Observe (OTLP/HTTP **JSON or protobuf** — protobuf SDKs can post directly; the Collector remains the recommended production path — [details](docs/otel-deployment-guide.md)):

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

Point its exporter directly at Observe (`OTEL_EXPORTER_OTLP_ENDPOINT=https://<observe>/otel` + your `gk-` key — [details](docs/otel-deployment-guide.md#direct-otlp-protobuf-quick-start)), or through your Collector for production routing. Two lines of code, full GenAI traces — with the open standard, not a vendor SDK.

---

## 🔌 Gateway Quick Start

For organizations that do not want — or cannot — instrument every application. One `base_url` change puts AI traffic behind a controlled endpoint:

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

**No proprietary SDK required.** Works with OpenAI SDK, LangChain, CrewAI, LiteLLM, OpenAI Agents SDK, MCP Clients, Agno, PydanticAI, Vercel AI SDK, and any OpenAI-compatible client (Anthropic SDKs via `/v1/messages`).

**2. Configure provider credentials** — add your provider keys (BYOK) on the **Providers** page; stored encrypted per organization.

**3. Set budgets, policies, and rate limits** — per team or agent. Everything starts advisory: **observe → alert → enforce**, and nothing blocks until a team is explicitly set to enforce.

---

## Privacy guarantee

Runtime evidence is **structural metadata only**:

- `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`, `tool.arguments`, and `tool.result` are **scrubbed at ingestion and never stored** — only a SHA-256 hash + byte size survive.
- URLs are stored as scheme + host + path only — query strings, fragments, and credentials never persist.
- Findings, security intelligence, and control recommendations carry **identifiers and counts only**: agent/tool/provider/model names, MCP methods, span counts, durations, error types.

Full details: [docs/otel-deployment-guide.md](docs/otel-deployment-guide.md#privacy-guarantee) and [docs/ai_agent_runtime_security_intelligence.md](docs/ai_agent_runtime_security_intelligence.md).

---

## Architecture

```
   Observability (OTLP)          Gateway (/v1 proxy)
┌────────────────────────┐   ┌──────────────────────────┐
│ OTel exporter /        │   │ OpenAI / Anthropic SDKs  │
│ Collector / OpenLLMetry│   │ (base_url change only)   │
│          │             │   │           │              │
│          ▼             │   │           ▼              │
│ POST /otel/v1/traces   │   │ POST /v1/chat/completions│
│ (JSON + protobuf)      │   │ POST /v1/messages        │
│          │             │   │           │              │
│   privacy scrub        │   │      guard modes         │
│   (prompts never       │   │  (observe/alert/enforce) │
│    stored)             │   │                          │
└──────────┬─────────────┘   └───────────┬──────────────┘
           ▼                             ▼
   otel_spans · otel_assets · telemetry · provenance_events
           │
           ▼
   asset_registry   (agent inventory, ownership, lifecycle, and context)
           │
           ▼
   derive_asset_intelligence()
   asset_capabilities · asset_findings
   ├─ runtime security intelligence  (source=runtime_security)
   ├─ detection rules                (source=detection_rules)
   │     └─ webhook notifications  (post-commit, cooldown-throttled)
   └─ gateway control candidates     (category=control)
           │
           ▼
        ui2 dashboard — one app, two workspaces
   Observe:  Overview · Runtime · Asset Intelligence ·
             Security Intelligence · Rules & Alerts · Platform Guide
   Gateway Control:  Control Center · Providers · Budgets · Pricing
```

One backend, one database. The intelligence layer is **derivation-only and idempotent** — running it twice never duplicates a finding; recurring evidence lands as an `occurrence_count` on one row, never as row spam.

---

## Feature summary

### Observability

- **OTLP/HTTP ingestion (JSON + protobuf)** — `POST /otel/v1/traces`; GenAI semantic conventions (`gen_ai.*`, `tool.*`, `mcp.*`, `db.*`, `url.*`) understood natively; agents discovered from `service.name`/`agent.name`, no manual registration
- **Runtime Events ingestion** — `POST /runtime-events`: normalized GenAI runtime events (`llm_call` / `tool_call` / `mcp_tool` / `db_call` / `external_api_call`) from any source, validated against an allow-list schema and privacy-scrubbed at the boundary, then converted into the same span pipeline — one intelligence engine, no separate findings pipeline. A thin Python SDK wrapper over this endpoint is available ([SDK guide](docs/sdk-guide.md))
- **Runtime execution timelines** — session-grouped traces, per-step waterfalls, step classification (llm / tool / mcp_tool / database / external_api / step)
- **Asset Intelligence** — derived capabilities (provider, model, mcp, database, shell, …) and findings across security / performance / operations / dependency / inventory; finding lifecycle open → dismissed/resolved → reopen; full catalog in [docs/asset_intelligence.md](docs/asset_intelligence.md)
- **AI Agent Runtime Security Intelligence** — agent-specific, environment-aware security findings (`source=runtime_security`): database/API reach, MCP in production, broad tool surface, unknown providers, missing ownership, repeated tool errors, human-review combinations ([docs](docs/ai_agent_runtime_security_intelligence.md))
- **Detection Rules & Alerts** — built-in threshold rules over the same evidence (`source=detection_rules`): MCP tool-access threshold, repeated tool errors, unknown provider in production; evaluated during the intelligence run (never at ingestion), surfaced in Security Intelligence and the **Rules & Alerts** page, with a **webhook notification** path (admin-managed channels, Fernet-encrypted URLs, 60-minute per-finding cooldown, fail-safe delivery) — observe-only, nothing is enforced ([design](docs/ai_agent_detection_rules_alerts_design.md))
- **Gateway Control Center** — control candidates derived on every intelligence run from open high-severity evidence or human-review recommendations; evidence-backed suggested controls; admin-only actions with sticky dismissal ([architecture](docs/gateway_control_center_architecture.md))
- **Advisory Guardrails** — observe-only: detect, explain, recommend; nothing is blocked
- **Ownership** — claim assets, assign owner/team; `agent_missing_owner` findings drive the "Agent needs owner" attention card

### Gateway

- **OpenAI-compatible** (`/v1/chat/completions`) and **Anthropic-compatible** (`/v1/messages`) proxies with real SSE streaming and full body passthrough
- **Pipeline on every proxied call** (advisory by default): policy check → budget check → provider call → telemetry (tokens, cost, latency) → relationship capture. Blocking only for teams explicitly set to **enforce**
- **BYOK** — per-org provider credentials, Fernet-encrypted; provider routing by model prefix (`claude-*` → Anthropic, `gemini-*` → Google, `llama-*` → local)
- **Budgets & policies** — daily/monthly thresholds and model allow/blocklists per team or agent
- **Runtime Dependency Map** — header-based relationship capture (`X-Agent-Name`, `X-MCP-Server`, `X-MCP-Tool`, …) into a filterable graph
- **Cost Intelligence** — three layers: runtime estimate (tokens × versioned pricing), provider billed (invoice import), reconciliation variance

### Shared spine

- **AI Agent Inventory** — two-tier discovery (verified / potential), stable `asset_key` identity, CMDB lifecycle (`unassigned → managed → retired`)
- **Auth & RBAC** — JWT login (8h expiry), roles admin / analyst / viewer, per-org role page ACLs
- **Pricing Registry** — versioned immutable pricing with org overrides, background sync, historical cost replay

---

## Dashboard pages & roles

Visible pages also depend on the built product surface (`VITE_PRODUCT_SURFACE`) — an Observability deployment hides gateway-configuration pages and vice versa; the Gateway Control Center is deliberately visible on **both**. Combined superset by role:

| Page | Who can see it |
|---|---|
| Dashboard, Overview, Platform Guide | Everyone |
| Runtime, Asset Intelligence, Security Intelligence, Rules & Alerts | Everyone |
| Gateway Control Center (view for everyone; dismiss/reopen admin-only) | Everyone |
| Discovery Center, Agents, Dependency Map | Everyone |
| Cost Signals, Budgets (read-only for viewer/analyst), Pricing Registry, Guardrails | Everyone |
| Gateway vs OTEL explainer | Demo environment only |
| Governance Readiness, Security, Users, API Keys, Settings | Admin only |
| Setup (Integrations), Chat | Admin + Analyst |

---

## Local development

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
CREDENTIAL_ENCRYPTION_KEY=                # Fernet key for BYOK credential storage
# DATABASE_URL=postgresql://...           # unset → SQLite; see Deploy section
```

### Seed demo data

```bash
python scripts/seed_demo_data.py
```

Seeds the **Acme AI Operations** demo org with five realistic AI systems through the real OTel ingestion pipeline — traces, timelines, capabilities, and findings. Idempotent; all data synthetic. Log in with `demo@observeagents.ai` / `Demo123!`, then open **Runtime** and **Asset Intelligence**. See [docs/demo_seed_data.md](docs/demo_seed_data.md).

---

## API quick reference

### Key endpoints

```http
POST /auth/login                          # { email, password } → { access_token, user }
POST /otel/v1/traces                      # OTLP/HTTP span ingestion, JSON + protobuf
POST /runtime-events                      # Normalized GenAI runtime events (any source) → same pipeline
GET  /runtime/traces                      # Recent executions (?service_name= for one agent)
GET  /runtime/traces/{trace_id}           # Full span tree for the execution waterfall
POST /intelligence/run                    # Re-derive capabilities + findings (idempotent)
GET  /intelligence/asset-summary          # Intelligence grouped per AI system (the dashboard's primary shape)
GET  /intelligence/findings               # Findings (?category=control → Gateway control candidates)
GET  /intelligence/capabilities           # Derived capabilities (filterable)
POST /intelligence/findings/{id}/dismiss  # Dismiss (control findings: admin-only)
POST /intelligence/findings/{id}/resolve  # Resolve
POST /intelligence/findings/{id}/reopen   # Return to open
GET  /notifications/channels              # Webhook notification channels (admin; URL never returned)
POST /notifications/channels              # Create a webhook channel { type, name, url, min_severity }
PATCH  /notifications/channels/{id}       # Enable/disable, rename, change min_severity (admin)
DELETE /notifications/channels/{id}       # Remove a channel (admin)
GET  /security/alerts                     # Live detection signals
GET  /agents · /agents/summary            # Agent inventory + discovery stats
GET  /relationships · /relationships/graph# Runtime dependency map
GET  /telemetry · /telemetry/summary      # Proxied-call log + totals
GET  /cost-intelligence                   # Cost overview, breakdown, trends
POST /budgets · GET /budgets/status       # Budget rules + live spend
GET  /pricing-registry                    # Versioned pricing (org overrides merged)
```

Full interactive docs at `http://localhost:8000/docs`. For a complete UI-facing contract with real response samples, see [docs/ui_contract.md](docs/ui_contract.md).

### Gateway proxy usage

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
        "X-Guard-Team":     "SOC",           # policy + budget attribution
        "X-Guard-Agent":    "my-agent",      # agent identity in telemetry
        "X-MCP-Server":     "hubspot-mcp",   # optional: dependency mapping
        "X-MCP-Tool":       "create_lead",
        "X-Agent-Relation": "uses_tool",
    },
)
```

Anthropic SDKs work the same way against `/v1/messages` (`base_url="http://localhost:8000"`). Other relationship headers: `X-Agent-Name`, `X-Agent-Workflow`, `X-Agent-Target`, `X-Workflow-Provider`, `X-Workflow-Name`.

---

## Data model

| Table | Purpose |
|---|---|
| `organizations` / `users` / `roles` / `teams` | Multi-tenant orgs, auth accounts, per-org role ACLs, soft team registry |
| `api_keys` | Machine-to-machine auth (`gk-…`); stored as SHA-256 hash |
| `provider_credentials` | Encrypted per-org LLM keys (Fernet / BYOK) |
| `otel_spans` | OTel span records (privacy-scrubbed attributes — prompts never stored) |
| `otel_assets` | Runtime evidence — one row per (org, service, environment) with models/providers/tools/dependencies |
| `provenance_events` | One semantic event per span (llm_call / tool_call / db_call / external_api_call) |
| `asset_registry` | Canonical AI inventory — lifecycle, owner, criticality |
| `asset_capabilities` | Derived capability surface per AI system |
| `asset_findings` | Derived findings — security / performance / operations / dependency / inventory / **control** (Gateway candidates) / detection-rule matches (`source=detection_rules`), with `occurrence_count` dedup |
| `notification_channels` / `notification_deliveries` | Webhook notification targets (Fernet-encrypted URL) + per-attempt delivery log (doubles as the cooldown ledger) |
| `agent_relationships` | Runtime dependency map |
| `telemetry` | Immutable proxied-call records — tokens, cost, latency, findings |
| `guard_modes` / `policy_rules` / `budget_rules` | Per-team governance mode, model allow/blocklists, budget thresholds |
| `model_pricing` / `pricing_change_log` | Versioned pricing + audit trail |
| `provider_billing` / `cost_reconciliation` | Imported invoices + variance analysis |
| `chat_sessions` / `chat_session_messages` | Multi-turn session history |

---

## Deploy

### Render Blueprint

The repo includes `render.yaml`. Connect the repo in Render → **New** → **Blueprint**. Each frontend build targets one surface via `VITE_PRODUCT_SURFACE`:

| Target | Surface | What it is |
|---|---|---|
| `ai-asset-app` | `observability` | The single backend (all APIs: OTLP ingestion **and** the `/v1` proxy) + the Observability UI |
| `observeagents-gateway-console` | `gateway` | Static Gateway console build pointed at the same backend |
| `ai-asset-demo` | *(unset → combined)* | Public demo only — the blended showcase surface |
| `observeagents-website` | — | Marketing site (`website/`) |

One backend, one database — the surfaces are frontend builds over the same spine ([architecture](docs/architecture.md)). When attaching a hostname to the gateway console, add that origin to the backend's `FRONTEND_ORIGIN` env var for CORS. After first deploy, set provider API keys in the Render dashboard or the Settings page.

### Production database — Managed Postgres

Default storage is SQLite on the service's persistent disk — right for evaluation, single-writer by nature. For production/customer data, use managed Postgres (Render Postgres, Neon, RDS, …):

1. Provision the database and copy its connection string (`postgres://` and `postgresql://` both accepted).
2. Set `DATABASE_URL` on `ai-asset-app` and redeploy — nothing else changes. A fresh database builds its full schema automatically at startup (create_all + Alembic); the engine switches to a pooled Postgres configuration automatically.
3. Migrating **existing** SQLite data is a manual dump/load step; a brand-new deployment has nothing to migrate.

A commented-out `databases:` block in `render.yaml` shows the Render-managed variant — deliberately inactive so a Blueprint sync never provisions a paid database silently.

---

## Supported models

| Provider | Models |
|---|---|
| OpenAI | `gpt-4.1`, `gpt-4.1-mini`, `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `o3`, `o4-mini` |
| Anthropic | `claude-opus-4-8`, `claude-sonnet-4-6`, `claude-haiku-4-5` |
| Google | `gemini-2.5-pro`, `gemini-2.0-flash`, `gemini-1.5-pro` |
| Local | `llama-3.1-70b-local`, `llama-3.1-8b-local` (Ollama / vLLM / LM Studio) |

Pricing for all models is seeded into the Pricing Registry on first start and kept in sync by the background daemon.

---

## Tech stack

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| ORM / DB | SQLAlchemy 2.0 + SQLite (default) / managed Postgres via `DATABASE_URL` |
| Auth | HS256 JWT (pure Python) |
| Encryption | Fernet (per-org provider credential storage) |
| Frontend | React 19 + Vite — **ui2 design system** (semantic tokens, dark/light-ready, evidence-first components) + Recharts |
| Deploy | Render (backend web service + persistent disk + static frontends) |

---

## Roadmap

The phased forward roadmap — including Detection Rules, Gateway Control GCR5+, and **Observe Advisor** — lives in [docs/roadmap.md](docs/roadmap.md).

| Status | Item |
|---|---|
| ✅ | OTel Runtime Discovery — OTLP/HTTP JSON ingestion with privacy scrubbing |
| ✅ | OTLP protobuf direct ingestion — same endpoint, no Collector required |
| ✅ | Runtime Execution Timeline — session grouping, waterfall API and UI |
| ✅ | Asset Intelligence — capabilities + findings per AI system, idempotent derivation with occurrence dedup |
| ✅ | AI Agent Runtime Security Intelligence — agent-specific, environment-aware security findings ([docs](docs/ai_agent_runtime_security_intelligence.md)) |
| ✅ | Gateway Control Center (GCR2–GCR4) — Observe-to-Control candidates, evidence-backed suggested controls, one-click navigation ([docs](docs/gateway_control_center_architecture.md)) |
| ✅ | **ui2 redesign** — new design system, six migrated pages, workspace shell ([plan](docs/ui_redesign_plan.md), [UI contract](docs/ui_contract.md)) |
| ✅ | Advisory Guardrails — observe-only guardrail catalog + per-team guard modes |
| ✅ | OpenAI-compatible + Anthropic-compatible proxies with real streaming |
| ✅ | BYOK, budgets, model policies, audit log, JWT auth + RBAC |
| ✅ | AI Agent Inventory — two-tier discovery, CMDB governance |
| ✅ | Runtime Dependency Map — header-based relationship capture + graph API |
| ✅ | Cost Intelligence — runtime / billed / reconciliation, versioned Pricing Registry |
| ✅ | Product surface separation — per-surface builds (`VITE_PRODUCT_SURFACE`) with explicit deploy targets |
| ✅ | Postgres-ready storage — `DATABASE_URL` switch, validated end-to-end on PG 16 |
| ✅ | Demo seed data — five-system synthetic demo through the real ingestion pipeline |
| ✅ | AI Agent Detection Rules (R1) — built-in threshold rules over runtime evidence (`source=detection_rules`), evaluated during the intelligence run ([design](docs/ai_agent_detection_rules_alerts_design.md)) |
| ✅ | Rules & Alerts page (ui2-native) + detection-rule matches bucket in Security Intelligence |
| ✅ | Webhook notifications (R5) — admin-managed channels, encrypted URLs, per-finding cooldown, fail-safe post-intelligence delivery |
| ✅ | Runtime Events ingestion seam (Collector R1/R2) — `POST /runtime-events`, allow-list schema + privacy scrub, span-like adapter into the existing intelligence engine |
| ✅ | Python SDK wrapper (Collector R3) — thin `ObserveOpenAI`-style client emitting runtime events ([guide](docs/sdk-guide.md)) |
| 🔜 | Detection Rules R7+ — configurable rule builder, Slack channels, alert snooze/acknowledge |
| 🔜 | Gateway Control Center GCR5+ — policy drafts, explicit approval workflow, enforcement for routed agents only |
| 🔜 | Ecosystem Discovery — GitHub / Jira / Slack / n8n / MCP evidence sources |
| 🔜 | OTel Demo Readiness — demo company, telemetry coverage matrix, ingestion health, collector examples |
| 🔜 | Per-tenant API key table · budget webhooks (Slack/Teams) · cost forecasting |
| 🔜 | SSO (Okta / Google OAuth) · HA / fail-over story |

---

## Documentation

**Core docs**

| Doc | What it covers |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Overall platform architecture, startup chain, deployment |
| [docs/customer-integration-guide.md](docs/customer-integration-guide.md) | Customer-facing integration guide (stakeholder + technical rollout) |
| [docs/otel-deployment-guide.md](docs/otel-deployment-guide.md) | Complete OpenTelemetry deployment guide — OTLP format, GenAI attributes, privacy guarantee, Collector guidance |
| [docs/sdk-guide.md](docs/sdk-guide.md) | ObserveAgents Python SDK guide |
| [docs/runtime-flow.md](docs/runtime-flow.md) | Runtime processing and intelligence flow |

**Specialized specs**

| Doc | What it covers |
|---|---|
| [docs/asset_intelligence.md](docs/asset_intelligence.md) | Full capability + finding catalog |
| [docs/ai_agent_runtime_security_intelligence.md](docs/ai_agent_runtime_security_intelligence.md) | Runtime security finding types and evidence rules |
| [docs/gateway_control_center_architecture.md](docs/gateway_control_center_architecture.md) | Observe-to-Control architecture and candidate model |
| [docs/ai_agent_detection_rules_alerts_design.md](docs/ai_agent_detection_rules_alerts_design.md) | Detection Rules & Alerts design — rule templates, evaluation model, webhook notifications, R0–R8 sequence |
| [docs/ui_redesign_plan.md](docs/ui_redesign_plan.md) | ui2 design system and page migration plan |
| [docs/ui_contract.md](docs/ui_contract.md) | The UI ↔ API contract with real response samples |
| [docs/roadmap.md](docs/roadmap.md) | Phased forward roadmap (O-phases, Observe Advisor) |

---

## Author

**Ron Haviv**
SOC Analyst · Security Operations · AI Agent Observability
