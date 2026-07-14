# ObserveAgents.ai — System Architecture

**The runtime visibility and control layer for AI agents.** Observe helps teams understand what AI exists, what is actively running, how it is connected, and how it evolves over time.

This document describes the system as implemented today. Companion docs:
- [product_discovery_model.md](product_discovery_model.md) — the Runtime + Ecosystem discovery product model
- [otel_ingestion.md](otel_ingestion.md) — OTel trace ingestion in depth
- [asset_intelligence.md](asset_intelligence.md) — capability/finding derivation and API
- [demo_seed_data.md](demo_seed_data.md) — the demo dataset

---

## 1. System overview

```
                         EVIDENCE SOURCES
 ┌─────────────────────────────────────┐   ┌─────────────────────────────┐
 │        Runtime Discovery (today)    │   │ Ecosystem Discovery (roadmap)│
 │                                     │   │  GitHub · Jira · Slack ·     │
 │  OTel exporter        AI app / SDK  │   │  ServiceNow · n8n · MCP      │
 │       │                    │        │   └──────────────┬───────────────┘
 │       ▼                    ▼        │                  ▼
 │ POST /otel/v1/traces  POST /v1/*    │        future evidence tables
 │ (OTLP/HTTP JSON)      (gateway)     │        (github_assets, …)
 └───────┬────────────────────┬────────┘
         ▼                    ▼
   INGESTION LAYER      GATEWAY PIPELINE
   otel_parser          proxy routes: auth → guard mode →
   otel_privacy         policy/budget (advisory by default) →
   otel_normalizer      upstream call → telemetry + relationships
         │                    │
         ▼                    ▼
 ┌────────────────────────────────────────────────────────────┐
 │                     EVIDENCE STORAGE                       │
 │  otel_spans · otel_assets · provenance_events · telemetry  │
 │  agent_relationships                                       │
 └───────────────────────────┬────────────────────────────────┘
                             ▼
                  asset_registry  ← canonical AI inventory
                             │      (single source of truth)
                             ▼
                 INTELLIGENCE DERIVATION
                 derive_asset_intelligence()
                 asset_capabilities · asset_findings
                             │
                             ▼
                    READ / AGGREGATION APIs
        /runtime/* · /intelligence/* · /assets · /agents ·
        /relationships · /cost-intelligence · /security/alerts
                             │
                             ▼
                      REACT DASHBOARD
   Dashboard · Runtime · Asset Intelligence · Security · Cost ·
   Budgets · Pricing · Guardrails · Dependency Map · Discovery ·
   Ecosystem · Setup · Admin (Users/Keys/Settings/Organizations)
```

**Core invariants**

1. **`asset_registry` is the single canonical AI inventory.** Every discovery source writes source-specific *evidence* rows that link back to it (`otel_assets.ai_asset_id`); no source maintains its own inventory.
2. **Raw content is never stored.** The OTel privacy scrubber replaces `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`, `gen_ai.request.messages`, `gen_ai.response.choices`, `tool.arguments`, `tool.result` with `{redacted, sha256, size_bytes}`.
3. **Advisory by default.** Guard modes are per-team (`observe` / `alert` / `enforce`); observe and alert never block. Guardrails, budgets, and policies are signals unless a team is explicitly graduated to enforce.
4. **Everything is org-scoped.** All queries filter by `organization_id`; platform admins can switch orgs via the `X-View-Org` header, resolved inside `get_current_user`.

---

## 2. Backend

FastAPI + SQLAlchemy 2.0 (typed `Mapped[]` models) + Alembic. SQLite in dev, file-backed SQLite on a Render persistent disk in production.

### 2.1 Application composition (`app/main.py`)

Startup order: `Base.metadata.create_all` → `run_alembic_migrations()` (fresh DB: stamp head; existing DB: upgrade head) → org migration → `_seed_admin()` → role seeding per org (`app/roles.py`, insert-or-backfill so new page ids propagate on boot) → pricing seed + background sync daemon → 14 routers registered.

### 2.2 Module map

| Module | Responsibility |
|---|---|
| `app/routes/otel.py` | `POST /otel/v1/traces` — OTLP/HTTP JSON ingestion (auth: `get_proxy_caller`, JWT or `gk-` API key) |
| `app/ingestion/` | Ingestion layer — one module per integration, each exposing `parse(payload) -> list[RuntimeSpan]` (`otel.py`, `sdk.py`); isolates integration-specific parsing from Runtime |
| `app/otel_parser.py` | OTLP envelope → flat span dicts (`resourceSpans → scopeSpans → spans`) |
| `app/otel_privacy.py` | `scrub_attributes()` — the redaction layer (invariant #2) |
| `app/otel_normalizer.py` | Per-span: identity extraction (`agent.name` → declared, `service.name` → inferred), AssetRegistry upsert (`discovery_status="potential"`, `discovery_source="otel_trace"`), relationship + provenance detection, `OtelSpan` persist (dedup on org+trace+span). Per-batch: `otel_assets` evidence upsert |
| `app/asset_intelligence.py` | `derive_asset_intelligence(db, org_id)` — reads otel evidence, writes `asset_capabilities` (classified by name keywords) and `asset_findings` (capability- and span-based rules). Application-level dedup; idempotent |
| `app/routes/runtime.py` | Execution Timeline read API over `otel_spans` (trace list + span tree with offsets and step types) |
| `app/routes/asset_intelligence.py` | Intelligence reads incl. `GET /intelligence/asset-summary` (grouped per asset, 4 queries, display normalization), finding dismiss/resolve, `POST /intelligence/run` |
| `app/routes/proxy.py` | OpenAI/Anthropic-compatible gateway with SSE streaming, BYOK provider routing, guard-mode pipeline, telemetry persist |
| `app/relationships.py` / `relationship_resolver.py` | `agent_relationships` upsert (request_count/last_seen/confidence) from headers and OTel |
| `app/demo_otel_seed.py` | Org-parameterized five-system demo seeding through the real pipeline; used by `scripts/seed_demo_data.py` and admin populate |
| `app/routes/admin.py` | Org CRUD, `populate`/`clear demo-data` (gated to demo/dev env) |
| `app/auth.py` | JWT (HS256), `get_current_user` (dashboard) vs `get_proxy_caller` (gateway/ingestion), `require_admin`, `require_platform_admin`, `require_page_access(page)` |
| `app/roles.py` | `SEED_ROLES` page ACLs for admin/analyst/viewer + idempotent per-org backfill |
| Other routes | `auth`, `assets`, `agent_inventory`, `governance` (budgets/policies/alerts), `cost_intelligence`, `pricing_registry`, `relationships`, `settings`, `inventory` |

### 2.3 Ingestion pipelines

Integration-specific parsing lives in the **ingestion layer** (`app/ingestion/`): each evidence source is one module exposing `parse(payload) -> list[RuntimeSpan]`, where `RuntimeSpan` (a `TypedDict` in `app/ingestion/__init__.py`) is the flat span shape `normalize_spans()` accepts. OTel (`app/ingestion/otel.py`, wrapping `app/otel_parser.py`) and the SDK (`app/ingestion/sdk.py`, wrapping `app/runtime_events.py:to_span_dict`) both return it; the Runtime pipeline downstream is source-agnostic. Adding an integration (LangGraph, MCP, …) means adding one module with one `parse` function plus a route that authenticates, parses, and calls `normalize_spans`.

**OTel path** (primary): `POST /otel/v1/traces` → `app/ingestion/otel.py:parse_otlp` → per span: scrub → identity → registry upsert → genai/tool/db/api/workflow detection → relationship upsert → `OtelSpan` insert (skip duplicates) → `ProvenanceEvent` → per batch: `otel_assets` upsert (models/providers/tools/dependencies arrays, trace/span counts, first/last seen). Returns 202 with a creation summary.

**Gateway path**: `/v1/chat/completions` + `/v1/messages` → bearer auth → guard-mode pipeline (policy, budget — enforce-mode only for blocks) → provider routing by model prefix with BYOK credentials → streaming relay → `telemetry` row + header-derived relationships.

### 2.4 Intelligence derivation

`derive_asset_intelligence(db, org_id)`:
1. Load `otel_assets` + `asset_registry` for the org.
2. Per asset: upsert capabilities from providers/models (typed directly) and tools/dependencies (keyword-classified: mcp, database, filesystem, shell, messaging, source_control, crm, retrieval, memory, external_api, unknown) plus `runtime:production`.
3. Derive capability-based findings (security/dependency/operations/inventory categories).
4. Scan `otel_spans` for span-based findings: `slow_llm_call` (≥10s), `slow_tool_call`/`slow_runtime_step` (≥5s), `runtime_error` (status_code `"2"`).

Dedup keys: capability `(org, asset_key, type, name, source)`; finding `(org, asset_key, category, finding_type, source)`. Re-runs refresh `last_seen` and never reopen dismissed/resolved findings.

### 2.5 Auth & authorization

- **Dashboard reads/actions**: `get_current_user` — validates JWT, resolves org from DB (never the token), 401 on missing/invalid, applies `X-View-Org` for platform admins.
- **Machine ingestion**: `get_proxy_caller` — accepts dashboard JWT or `gk-` org API key.
- **Page ACLs**: role rows (`roles` table) hold JSON page lists; frontend gates nav/rendering, and `require_page_access(page)` enforces server-side on sensitive mutations (e.g. budget create/delete keyed to `settings` so viewers/analysts can *read* budgets but only admins mutate — verified viewer POST → 403, admin → 201).
- Roles: **admin** (everything), **analyst** (product pages + chat/setup), **viewer** (read-only product pages incl. Runtime, Asset Intelligence, Security, Cost, Budgets, Pricing, Guardrails).

---

## 3. Data model (24 tables)

```
organizations ─┬─ users · api_keys · roles · teams · org_config · provider_credentials
               │
               ├─ EVIDENCE            otel_spans          (raw spans, scrubbed)
               │                      otel_assets ───────┐ (per service+env summary)
               │                      provenance_events  │
               │                      telemetry          │ (gateway calls)
               │                      agent_relationships│ (dependency edges)
               │                                         │ ai_asset_id
               ├─ CANONICAL           asset_registry ◄───┘ (single source of truth,
               │                           ▲                asset_key = sha256(org:name))
               │                           │ asset_id/asset_key
               ├─ INTELLIGENCE        asset_capabilities · asset_findings
               │
               ├─ GOVERNANCE          guard_modes · policy_rules · budget_rules
               │
               ├─ COST                model_pricing · pricing_change_log ·
               │                      provider_billing · cost_reconciliation
               │
               └─ CHAT                chat_sessions · chat_session_messages
```

Notable design decisions:
- `otel_assets`, `asset_capabilities`, `asset_findings` use **application-level dedup** (no DB unique constraints) because nullable columns (environment, asset_key) make SQLite unique indexes unreliable (`NULL != NULL`).
- `model_pricing` rows are **immutable/versioned** (`effective_from/to`); cost replay uses `get_active_pricing(as_of=…)`.
- Alembic: linear chain, head `d5e6f7a8b9c0`. Fresh DBs are bootstrapped by `create_all` + stamp (legacy early migrations assume pre-existing tables); existing DBs upgrade normally on startup.

---

## 4. API surface (14 routers)

| Group | Endpoints |
|---|---|
| **Ingestion** | `POST /otel/v1/traces` · gateway `POST /v1/chat/completions`, `POST /v1/messages`, `POST /ask`, `POST /chat` |
| **Runtime** | `GET /runtime/traces` · `GET /runtime/traces/{trace_id}` |
| **Intelligence** | `GET /intelligence/asset-summary` · `/assets` · `/capabilities` · `/findings` · `POST /intelligence/run` · `POST /intelligence/findings/{id}/dismiss|resolve` |
| **Inventory** | `GET/PATCH /agents…` + claim/validate/reject/approve-suggestions/ignore · `GET /assets…` + claim/registry |
| **Dependencies** | `GET /relationships` · `GET /relationships/graph` |
| **Cost** | `GET /cost-intelligence` · `GET/POST/PUT /billing/…` · `GET /agents/{id}/cost` |
| **Pricing** | `GET /pricing-registry` (+ `/status`, `/sync`, `/sync-status`, `/{provider}/{model}/history`, `POST /override`) |
| **Governance** | `GET/POST/DELETE /budgets…` · `/policies…` · `GET /guard-modes`, `PUT /guard-modes/{team}` · `GET /security/alerts` · `GET /audit` |
| **Auth/Admin** | `/auth/login|me|users…` · `/api-keys…` · `/roles…` · `/teams` · `/settings/…` · `/provider-credentials…` · `/admin/organizations…` (+ populate / clear demo-data) · `GET /health` |
| **Telemetry** | `GET /telemetry`, `GET /telemetry/summary` |

Auth conventions: ingestion/gateway → `get_proxy_caller`; reads → `get_current_user`; admin mutations → `require_admin` / `require_page_access`. Unauthenticated requests return 401; missing resources 404; empty orgs return `[]`.

---

## 5. Frontend

React 19 + Vite 8, Recharts, inline design-token styling (`theme.js`), hash-based routing in a single `App.jsx` (no router lib — `PAGES` registry + `NAV_GROUPS` sidebar + `renderPage()` switch, history managed via `#page` hashes).

```
dashboard/src/
├── App.jsx            routing, nav groups, role gating (canAccess), layout, error boundary
├── api.js             fetch client: authFetch (JWT + X-View-Org), one function per endpoint
├── auth.jsx           UserContext/RolesContext, ROLES fallback, canAccess/canSeePage
├── config.js          BRAND strings, demo-mode detection, gateway URLs
├── theme.js           design tokens (T.*) + fonts
├── pages/             primary pages (one file each)
│   ├── ExecutiveDashboard  hero + pillar cards + KPI/risk/cost panels
│   ├── RuntimeTimeline     trace list → execution waterfall (offset/duration bars, step types)
│   ├── AssetIntelligence   AI Systems (grouped cards, default) · Capabilities · Findings tabs
│   ├── SecurityIntelligence  risky-systems table + signal feed
│   ├── CostIntelligence    usage/efficiency signals + estimate/billed/reconciliation
│   ├── Guardrails          observe-only advisory catalog (evaluated client-side from asset-summary)
│   ├── PricingRegistry · GovernanceCenter · DiscoveryCenter · AgentInventory ·
│   ├── RelationshipMap · EcosystemDiscovery · PlatformGuide · Setup · Settings
├── components/         shared ui.jsx (Card/Stat/Pill/Sortable/Search), Budgets/Security/Users/… pages
└── hooks/              useLiveData (30s polling), useBreakpoint
```

Navigation: **Dashboard / Platform Guide** → **DISCOVERY & INVENTORY** (Discovery Center, Agents, Runtime, Dependency Map, Ecosystem) → **INTELLIGENCE** (Asset, Security, Cost, Budgets, Pricing, Guardrails) → **ADMINISTRATION** (Governance Readiness, Security & Audit, Users, API Keys, Setup, Settings, Organizations).

Frontend patterns: pages fetch on mount via `api.js`, best-effort secondary fetches degrade silently (e.g. guard modes hidden for viewers), all client-side evaluation is stateless (Guardrails never persists), Pill/Card components uppercase labels by convention.

---

## 6. Key flows

**Trace → dashboard** — exporter posts OTLP JSON → scrub → spans/evidence/registry rows → Runtime page lists the trace → clicking renders the waterfall from `GET /runtime/traces/{id}` (offsets computed server-side, hierarchy client-side).

**Intelligence run** — `POST /intelligence/run` (or seed/populate) → capabilities + findings derived → Asset Intelligence "AI Systems" cards via `asset-summary` → Security/Cost/Guardrails pages reuse the same summary for their own lenses.

**Demo** — `python scripts/seed_demo_data.py` (env: `DATABASE_URL`, `JWT_SECRET`, `CREDENTIAL_ENCRYPTION_KEY`) creates the Acme org + `demo@observeagents.ai`, ingests 5 deterministic traces (30 spans, one error) through the real pipeline, derives 32 capabilities + 22 findings. Idempotent. Platform admins get the same dataset per-org via **Populate Organization** (demo/dev only).

---

## 7. Deployment (Render)

One backend, one database — the two product surfaces are separate **frontend builds** over the same spine, selected at build time by `VITE_PRODUCT_SURFACE` (`dashboard/src/productSurface.js`). Deploy targets from `render.yaml`:

- **Production backend + Observability surface** (`ai-asset-app`) — `VITE_PRODUCT_SURFACE=observability`; serves ALL APIs (OTLP ingestion + `/v1` gateway proxy) and the Observability UI. `APP_ENV=production`, `DEMO_MODE=false` (config guarantees production can never be demo). Persistent disk SQLite via `DATABASE_URL`.
- **Gateway console** (`observeagents-gateway-console`) — static build of the same dashboard with `VITE_PRODUCT_SURFACE=gateway` and `VITE_API_BASE` pointing at the backend. No second backend, no second DB. Attach a hostname + add it to the backend's `FRONTEND_ORIGIN` for CORS.
- **Demo** (`ai-asset-demo`) — the only place `APP_ENV=demo` / `DEMO_MODE=true` are set; unlocks no-login demo token, populate/clear endpoints. Intentionally builds the blended **combined** surface (`VITE_PRODUCT_SURFACE` unset) so visitors can walk both products — combined is demo/local-dev-only, never the production default.
- **Marketing website** (`observeagents-website`) — static single-page site from `website/`.

Required env (backend): `DATABASE_URL`, `JWT_SECRET`, `CREDENTIAL_ENCRYPTION_KEY`, provider keys (or BYOK per org), optional `ADMIN_SEED_PASSWORD`, `GUARD_MODE` (platform default guard mode). Build compiles the dashboard into `dashboard/dist`, which the backend serves at `/` when present. Migrations run automatically at startup.

### Production database — Managed Postgres

The storage layer is `DATABASE_URL`-driven and Postgres-ready; SQLite is the zero-config default, not a dependency:

- `app/database.py` normalizes the legacy `postgres://` scheme to `postgresql://`, applies `check_same_thread` only for SQLite, and configures a pooled engine for server databases (`pool_pre_ping`, `pool_size=5`, `max_overflow=10`, `pool_recycle=300`). Driver: `psycopg2-binary`.
- The startup chain is dialect-portable: `create_all` → `ensure_model_columns` (compiles column types per dialect) → guarded Alembic stamp/upgrade. `app/migrate_orgs.py` (SQLite-era `PRAGMA`-based self-repair) skips itself on any non-SQLite dialect — on Postgres the schema is born complete.
- Validated end-to-end against PostgreSQL 16: fresh-boot schema creation, OTLP JSON + protobuf ingestion, intelligence runs (dedup idempotent on the second run), runtime/session reads, runtime-security findings + dismiss/reopen, org isolation, timezone-aware `timestamptz` round-trip, and second-boot idempotency.
- Switch = set `DATABASE_URL` to the Postgres connection string on `ai-asset-app` and redeploy. Fresh database: schema auto-builds. Existing SQLite data: manual dump/load (documented in the README deploy section).

---

## 8. Testing

| Suite | Covers |
|---|---|
| `tests/test_otel_ingestion.py` (13) | parsing, identity, privacy scrubbing, evidence summary, org isolation |
| `tests/test_runtime_timeline.py` (11) | trace list/detail, offsets, step types, errors, auth, limits, missing timestamps, attribute non-exposure |
| `tests/test_asset_intelligence.py` (20) | derivation rules, dedup, lifecycle, asset-summary grouping/counts/privacy, org isolation, auth |
| `tests/test_seed_demo_data.py` (10) | seed success, idempotency, hierarchy, error span, linkage, privacy, admin populate/clear |

Pattern: per-file scratch SQLite + env set before app import + `TestClient` startup. Known legacy debt (untouched by current work): 13 collection errors from old hardcoded repo paths and 23 failures in legacy gateway/BYOK suites.

---

## 9. Current state vs roadmap

**Implemented**: OTel Runtime Discovery, Execution Timeline API/UI, Asset Intelligence (grouped), Security/Cost reframing, Budget Awareness, Pricing Reference, observe-only Guardrails, demo seed, role-scoped navigation, gateway pipeline.

**Next (per product model)**: Ecosystem Discovery evidence tables (GitHub/Jira/Slack/n8n/MCP) and the Active / Dormant / Runtime-only correlation states — the asset-summary `status` array and AI Systems cards are already shaped to receive them. Later: trust radius, control recommendations, governance workflows, content-capture opt-in.
