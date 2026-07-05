# Product Surface Separation Plan: OTel Observability vs Gateway Platform

*A concrete plan for separating ObserveAgents into two customer-facing products on one shared backend foundation.*

**Status: plan only.** Nothing in this document has been implemented. It is the Phase 1 deliverable of its own migration plan (§8).

---

## The two products

| | **ObserveAgents Observability** | **ObserveAgents Gateway** |
|---|---|---|
| Purpose | AI observability and intelligence through OpenTelemetry | AI gateway, traffic control, budget, and policy platform |
| Primary customer | Organizations willing to send OpenTelemetry / OTLP telemetry | Organizations that do not want or cannot implement OpenTelemetry |
| Main promise | *See what AI is actually running, what it connects to, and where it needs attention* | *Control AI traffic without instrumenting every app* |
| Primary ingestion | OTLP/HTTP JSON, Collector, GenAI SemConv, MCP telemetry, Claude Code telemetry | Gateway endpoint, existing provider SDKs, OpenAI/Anthropic-compatible base_url |
| Posture | Observe-only by default; guardrails detect and recommend | Control plane; budgets, policies, rate limits, optional enforcement |

They share backend foundations — organizations, users, auth, API keys, provider credentials, pricing registry, budgets, audit — but the customer-facing surfaces, setup flows, navigation, docs, and mental models must be separate.

---

## 1. Current mixed surfaces

Where the two products are mixed today, with file references.

### README and docs

| Doc | State |
|---|---|
| `README.md` | Mostly OTel-first; presents gateway as a secondary "getting data in" path on the same product. One product identity, two ingestion stories. |
| `docs/otel_ingestion.md` | Clean Observability doc (GenAI SemConv, Collector, privacy). |
| `docs/organization_implementation_guide.md` (+ Hebrew) | Deliberately mixes both: "Path A OTel / Path B Gateway" as options of one product. |
| `docs/organization_quick_start_non_technical.md` | Same two-paths-one-product framing. |
| `docs/fake_customer_company_simulation_guide.md` | Same: Level 1 Gateway / Level 2 OTel of one product. |
| `docs/manual_company_simulation_qa_guide.md` | QA guide covers both paths in one flow. |
| `docs/architecture.md` | Documents one platform with both pipelines. |

The docs mixing is *intentional today* (one product, two paths). After separation, each product needs its own top-level doc set, with the implementation guide split accordingly.

### Frontend navigation (`dashboard/src/App.jsx` — `NAV_GROUPS`)

Every nav group mixes the two products:

| Nav group | Observability items | Gateway items |
|---|---|---|
| (top) | Dashboard*, Platform Guide* | — (*both currently blend the two stories*) |
| DISCOVERY & INVENTORY | Runtime, Dependency Map | Discovery Center, Agents (gateway-era discovery), Ecosystem Discovery (future, shared) |
| INTELLIGENCE | Asset Intelligence, Guardrails (observe-only) | Budgets, Pricing Registry; Security/Cost Intelligence read **both** data sources |
| ADMINISTRATION | — | Guard modes (via Settings) | plus shared: Governance Readiness, Security & Audit, Users, API Keys, Setup, Settings, Organizations |

### Setup and Settings pages

- `dashboard/src/pages/Setup.jsx` — one page hosts **both** setup flows: "Connect your first AI system" + OTLP endpoint block (Observability) *and* Client Examples with gateway base_url (Gateway).
- `dashboard/src/pages/Settings.jsx` — shared org config sits beside gateway-only surfaces: **Provider Credentials (BYOK)** and **Guard Modes** (observe/alert/enforce per team, i.e. the enforcement dial).

### Intelligence pages and their data sources

| Page | Data source today | Mixing |
|---|---|---|
| `CostIntelligence.jsx` | Gateway `telemetry` table (proxy token counts, cost) | Branded as one "Cost Intelligence" although OTel usage signals now also exist (span token attrs, trace usage totals) |
| `SecurityIntelligence.jsx` | Both: gateway telemetry signals + OTel-derived findings | One page, two evidence pipelines |
| `Guardrails.jsx` | OTel asset-summary derived, observe-only | Also fetches gateway guard-modes table (admin view) — control-plane data on an observability page |
| `BudgetsPage.jsx` | Gateway budgets (`/budgets`, spend from proxy telemetry) | Sits in the "INTELLIGENCE" nav group next to OTel pages |
| `AssetIntelligence.jsx` | OTel-derived + gateway-era registry assets (recent addition) | Intentional shared inventory — this one *should* stay shared |

### Backend routes (16 modules, all mounted flat — no prefixes)

| Module | Product | Endpoints (representative) |
|---|---|---|
| `app/routes/otel.py` | Observability | `POST /otel/v1/traces` |
| `app/routes/runtime.py` | Observability | `GET /runtime/traces`, `GET /runtime/traces/{id}` |
| `app/routes/asset_intelligence.py` | Observability | `/intelligence/asset-summary`, `/intelligence/run`, capabilities/findings |
| `app/routes/relationships.py` | Observability | `/relationships/graph` (dependency map) |
| `app/routes/proxy.py` | Gateway | `POST /ask`, `/chat`, `/sessions/{id}/chat`, `/v1/chat/completions`, `/v1/messages` + rate limiter + circuit breaker |
| `app/routes/governance.py` | Gateway (mostly) | `/budgets*`, `/policies*`, `/security/scan`, `/security/alerts` |
| `app/routes/settings.py` | Mixed | Gateway: `/provider-credentials*`, `/guard-modes*` · Shared: `/settings/keys`, `/settings/config`, `/settings/demo-mode` |
| `app/routes/assets.py`, `agent_inventory.py`, `inventory.py` | Gateway-era discovery | Asset registry views fed by proxy traffic |
| `app/routes/cost_intelligence.py` | Gateway data, shared branding | Cost reads from gateway `telemetry` only |
| `app/routes/pricing_registry.py` | Shared | Model pricing reference |
| `app/routes/auth.py`, `admin.py` | Shared | Auth, users, orgs, platform admin |

### API keys, credentials, proxy code

- **One `gk-` API key authenticates both products**: the same key posts OTLP to `/otel/v1/traces` and proxies chat through `/v1/chat/completions`. Convenient, but it blurs the product boundary and audit story.
- **Provider credentials (BYOK)** exist only for the Gateway (upstream calls) but live on the shared Settings page.
- **Proxy machinery** (circuit breaker, rate limiter, PII scan, policy/budget enforcement pipeline) is Gateway-only code inside the shared app.

### Tests and seed data

- Tests already split cleanly: **Observability** = `test_otel_ingestion`, `test_runtime_timeline`, `test_asset_intelligence`, `test_genai_semconv`, `test_seed_demo_data`; **Gateway** = `test_provider_not_configured`, `test_upstream_error_telemetry`, `test_circuit_breaker`, `test_guardmode_recheck`, `test_proxy_team_register`, `test_credential_save_errors`, `test_team_scope`; **Shared** = auth/isolation/startup/pricing/schema-repair tests.
- Demo seed (`scripts/seed_demo_data.py` + `app/demo_otel_seed.py`) is OTel-focused; older demo data generation was gateway-telemetry-focused. Both feed the same demo org.

---

## 2. Proposed product boundaries

| Area | Observability | Gateway | Shared |
|---|---|---|---|
| **Ingestion** | `/otel/v1/traces` (OTLP JSON), Collector, SemConv, MCP, Claude Code telemetry | `/v1/chat/completions`, `/v1/messages`, `/ask`, `/chat` proxy endpoints | — |
| **Pages** | Dashboard (obs mode), Runtime, Execution Timeline, Asset Intelligence, Security Intelligence (OTel evidence), Cost Intelligence (OTel usage signals), Guardrails (observe-only), Dependency Map, OTel Setup, Integrations | Gateway Dashboard, Traffic, Routes, Providers, SDK/base_url Setup, Budgets, Policies, Rate Limits, Enforcement, Usage, Cost (billing-grade), Audit | Users, API Keys, Settings (org config), Organizations, Pricing Registry (reference layer) |
| **Backend routes** | `otel.py`, `runtime.py`, `asset_intelligence.py`, `relationships.py` | `proxy.py`, `governance.py` (budgets/policies), provider-credentials + guard-modes (from `settings.py`), gateway-era discovery (`assets.py`, `agent_inventory.py`, `inventory.py`), `cost_intelligence.py` (today's implementation) | `auth.py`, `admin.py`, `pricing_registry.py`, `/settings/config|keys|demo-mode` |
| **Data tables** | `otel_spans`, `otel_assets`, `asset_capabilities`, `asset_findings`, `provenance_events` | `telemetry`, `budget_rules`, `policy_rules`, `guard_modes`, `provider_credentials`, `agent_relationships` (gateway-fed rows) | `organizations`, `users`, `roles`, `api_keys`, `asset_registry` (**the shared inventory spine** — both products discover into it), `model_pricing`, audit |
| **API keys** | Same `gk-` keys, scoped per product later (key metadata: `surface: observability\|gateway`) | Same | Key issuance/revocation UI |
| **Guardrails vs Policies** | Guardrails = advisory, derived from observed behavior; never blocks | Policies/Enforcement = the control dial (observe → alert → enforce) | Budget definitions (Gateway enforces; Observability may *display* budget context) |
| **Cost** | Usage/efficiency **signals** from spans (token attrs, slow traces) — "not an invoice" | Token/cost **accounting** from proxied requests — billing-grade | Pricing Registry powering both |
| **Docs** | otel_ingestion.md, asset_intelligence.md, runtime docs | new gateway_platform.md, provider credentials, budgets/policies docs | architecture.md, org/user/auth docs |
| **Copy** | "See what AI is actually running" | "Control AI traffic without instrumenting every app" | — |

Explicit boundary decisions:

- **`asset_registry` stays shared.** It is the org's AI inventory regardless of which product observed the asset (`discovery_source` already distinguishes `otel_trace` vs `gateway_telemetry`). Asset Intelligence remains the shared inventory brain, surfaced primarily on Observability.
- **Budgets and Pricing are Gateway-primary, shared backend.** The Gateway can enforce them; Observability may reference them read-only.
- **Cost Intelligence becomes two pages** with the same name family but different data honesty: Observability shows *signals*, Gateway shows *accounting*.
- **Guardrails ≠ Policies.** The word "guardrail" belongs to Observability (observe-only). The words "policy", "rate limit", "enforcement" belong to Gateway.

---

## 3. Proposed frontend structure

### Option A — single dashboard app with a product mode (recommended)

`PRODUCT_SURFACE=observability | gateway` (build-time env, later per-org setting via the existing `get_org_config` mechanism). One codebase; `NAV_GROUPS`, page registry, Dashboard, and Setup render per surface. The existing role page-list mechanism (`app/roles.py` + `require_page_access`) already gates pages per role — the same pattern extends naturally to gating per surface.

- **Pros:** smallest diff; one build/deploy pipeline; shared theme/ui/api layers stay shared; per-org switch possible later; easiest rollback.
- **Cons:** both products ship in one bundle; discipline needed to prevent mode leakage (a Gateway link rendering in Observability mode); one deploy serves both.
- **Migration difficulty:** low. Nav + Setup + Dashboard conditionals; no routing changes.

### Option B — two frontend apps (`apps/observability`, `apps/gateway`)

- **Pros:** cleanest mental model; independent release cadence; no leakage possible.
- **Cons:** duplicates theme.js/ui.jsx/api.js or forces a shared-package refactor first; two builds, two deploy targets; every shared page (Users, Settings, API Keys) maintained twice or extracted.
- **Migration difficulty:** high. Do not do this before the boundaries are proven.

### Option C — one codebase, two route groups (`#/observability/*`, `#/gateway/*`)

- **Pros:** both surfaces reachable from one deployment; clean URLs; middle ground.
- **Cons:** the hash router (`window.location.hash` in App.jsx) needs a nested-routing rework; two navs reachable in one session weakens the "separate products" story; permission/copy leakage still possible.
- **Migration difficulty:** medium.

### Recommended path (staged)

1. **Now: Option A** — `PRODUCT_SURFACE` mode, two navs, two setup flows, one backend.
2. **When both surfaces have real users: Option C** — route groups + a product switcher for orgs licensed for both.
3. **Only if teams/release cadences truly diverge: Option B.**

---

## 4. Proposed backend structure

**Logical separation first. No file moves, no route renames, no service split.**

### Route groups (target taxonomy)

| Group | Routes | Today's home |
|---|---|---|
| **Observability** | `/otel`, `/runtime`, `/intelligence`, `/relationships` (→ future `/dependencies` alias), `/guardrails/observations` (future read API for the advisory layer, currently client-derived) | `otel.py`, `runtime.py`, `asset_intelligence.py`, `relationships.py` |
| **Gateway** | `/v1/*` + `/ask`,`/chat` (→ conceptual `/gateway`/`/proxy` group), `/provider-credentials` (→ future `/providers` alias), `/policies`, `/guard-modes` (→ conceptual `/rate-limits`/enforcement group), `/budgets` execution, usage/cost from proxy telemetry | `proxy.py`, `governance.py`, `settings.py` (BYOK + guard modes), `cost_intelligence.py` |
| **Shared** | `/auth`, `/users`, `/organizations`, `/api-keys` (`/settings/keys`), `/settings`, `/budgets` definitions, `/pricing`, audit | `auth.py`, `admin.py`, `settings.py`, `pricing_registry.py`, `governance.py` |

### Concrete near-term steps (Phase 3, still one service)

1. **Tag every router** with `tags=["observability"] | ["gateway"] | ["shared"]` so OpenAPI/docs group by product (today's tags are HTTP-verb-themed).
2. **Split `settings.py`** logically: move provider-credentials + guard-modes handlers into a `gateway_settings.py` module (same URLs — module move only, zero route renames).
3. **Add aliases, don't rename:** e.g. mount `relationships` router additionally under `/dependencies` if/when the new nav needs it; keep old paths working indefinitely.
4. **Do not split services.** One FastAPI app, one DB, one deploy — until product boundaries are proven with customers (Phase 5 is optional and last).

---

## 5. Setup flow separation

Two totally separate setup flows, never shown on the same page.

### Observability setup (page: **OTel Setup**)

1. Create an API key (`gk-…`).
2. Point telemetry at `POST /otel/v1/traces` — **OTLP/HTTP JSON only**.
3. Stand up an OpenTelemetry Collector (`otlphttp` exporter, `encoding: json`) for SDKs that emit protobuf.
4. Instrument with **GenAI Semantic Conventions** (`gen_ai.provider.name`, `gen_ai.operation.name`, agent attrs, token usage).
5. Optional: MCP telemetry (`mcp.method.name`, …) and Claude Code telemetry.
6. **Verify in Runtime:** trace appears, timeline nests, Asset Intelligence card appears.

Never mentions: SDK installation for proxying, base_url changes, provider credentials, enforcement.

### Gateway setup (page: **SDK / base_url Setup**)

1. Choose provider (OpenAI, Anthropic, …).
2. Configure provider credentials (BYOK) in Gateway settings.
3. Create a gateway API key (`gk-…`).
4. Point the **existing provider SDK / OpenAI-compatible client** at the gateway base_url (`https://<observe-url>/v1`). *Not an Observe SDK.*
5. Send a test request; expect a completion — or a clear `provider_not_configured` if step 2 was skipped.
6. Configure budgets and policies; review usage.
7. Optional, deliberate: enable enforcement per team (observe → alert → enforce).

Never mentions: Collector, OTLP, traceparent, span attributes, SemConv, MCP spans, Execution Timeline.

---

## 6. Navigation separation

### Observability nav

| Item | Maps to today |
|---|---|
| Home | `dashboard` (obs-mode variant) |
| Runtime | `runtime` (Execution Timeline lives inside) |
| Asset Intelligence | `intelligence` |
| Security Intelligence | `security_intel` (OTel-evidence view) |
| Cost Intelligence | `cost` (OTel usage-signals view — see risk §9) |
| Guardrails | `guardrails` (observe-only; drop the guard-modes table from this page) |
| Dependencies | `relationship_map` |
| OTel Setup | `integrations` (obs-mode variant of Setup.jsx) |
| Integrations | Claude Code / Collector / SemConv recipes |
| Settings | `settings` minus Provider Credentials & Guard Modes |

### Gateway nav

| Item | Maps to today |
|---|---|
| Home | new Gateway dashboard (traffic/usage summary) |
| Traffic | new page over proxy `telemetry` (today partially in Discovery/Agents) |
| Providers | Provider Credentials section extracted from Settings |
| SDK Setup | gateway-mode variant of Setup.jsx (Client Examples block) |
| Budgets | `budgets` |
| Policies | policies UI (backend `/policies` exists; UI is thin today) |
| Rate Limits | new (limiter exists in proxy; needs config surface) |
| Usage | new page over proxy telemetry aggregates |
| Cost | gateway cost accounting (today's `cost` implementation) |
| Audit | `security` (Security & Audit) |
| Settings | shared settings + Guard Modes (the enforcement dial lives here) |

Landing spots for remaining current pages: Discovery Center + Agents → Gateway (their evidence is proxy traffic); Ecosystem Discovery → future, shared; Governance Readiness / Users / API Keys / Organizations → shared administration on both.

---

## 7. Copy / positioning cleanup

### Observability says

- "See what AI is actually running, what it connects to, and where it needs attention."
- "Send OpenTelemetry traces" / "Use the Collector" / "Follow the GenAI semantic conventions."
- "Understand agents, tools, models, dependencies."
- "Guardrails are observe-only: detect, explain, recommend — nothing is blocked."

### Gateway says

- "Control AI traffic without instrumenting every app."
- "Use your existing SDKs with the Gateway base_url" (never "Observe SDK").
- "Manage providers" / "Set budgets and policies" / "Optional enforcement, one team at a time."

### Never mix

| Rule | Where it currently breaks |
|---|---|
| No SDK/base_url setup inside OTel setup | `Setup.jsx` shows Client Examples beside the OTLP block |
| No Collector/OTLP/span language in Gateway setup | `Setup.jsx` (same page), implementation guide Path A/B framing |
| No enforcement language on Observability | `Guardrails.jsx` renders the guard-modes table; Settings guard-mode cards visible to obs users |
| No deep-timeline claims on Gateway | Keep Gateway copy to requests/usage — proxy requests do not produce span timelines |
| Dashboard/PlatformGuide tell one blended story | Both need per-surface variants in Phase 2 |

---

## 8. Migration phases

### Phase 1 — Documentation and product boundary plan *(this document)*
- **Files:** `docs/product_surface_separation_plan.md`; follow-ups: split the implementation guide into per-product guides, add `docs/gateway_platform.md`.
- **Risk:** none.
- **Acceptance:** boundaries agreed; every current page/route/table has exactly one home in §2.
- **Validation:** `git diff --stat` (docs only).

### Phase 2 — Frontend nav/setup separation, no backend changes
- **Files:** `App.jsx` (NAV_GROUPS/PAGES per `PRODUCT_SURFACE`), `Setup.jsx` (split into OTelSetup/GatewaySetup variants), `Settings.jsx` (move BYOK + guard modes behind gateway surface), `Guardrails.jsx` (drop guard-modes table), `ExecutiveDashboard.jsx`/`PlatformGuide.jsx` copy variants, `app/roles.py` page lists updated in lockstep.
- **Risk:** medium — role page-lists and demo flows must keep working; default mode must preserve today's behavior.
- **Acceptance:** `PRODUCT_SURFACE=observability` shows only obs nav/setup; `gateway` only gateway nav/setup; unset = current combined behavior (safe default); demo seed and Playwright nav flows pass in all three modes.
- **Validation:** `cd dashboard && npm run build`; Playwright nav walk per mode; `pytest tests/test_seed_demo_data.py` unchanged.

### Phase 3 — Route grouping and API naming cleanup
- **Files:** router `tags=` across `app/routes/*.py`; extract BYOK/guard-modes into `gateway_settings.py` (same URLs); optional `/dependencies` alias for relationships; OpenAPI groups by product.
- **Risk:** low-medium — zero URL changes; only module moves and tags.
- **Acceptance:** OpenAPI shows three product groups; all existing tests pass unmodified; no frontend change required.
- **Validation:** full pytest core suites; `curl /openapi.json | jq '.tags'`.

### Phase 4 — Separate deployment surfaces / environment modes
- **Files:** `render.yaml` (add per-surface services using `PRODUCT_SURFACE`, mirroring the existing production/demo dual-service pattern), env docs.
- **Risk:** medium — two hostnames, one DB; auth/cookie and CORS review; keys must be clearly scoped per surface (add key metadata).
- **Acceptance:** observe.* serves Observability-only UI, gateway.* serves Gateway-only UI, both against one backend; production demo unaffected.
- **Validation:** deploy previews; smoke: OTLP post visible only on obs surface, proxy request visible only on gateway surface.

### Phase 5 — Optional split into two apps or services
- **Files:** `apps/observability`, `apps/gateway` (frontend); optionally a separate gateway service for the proxy hot path.
- **Risk:** high — shared-code extraction, double maintenance, data-consistency questions.
- **Acceptance:** only undertaken with evidence: separate customer bases, separate release cadence needs, or proxy-latency isolation requirements.
- **Validation:** full regression per app; load test on the proxy path.

---

## 9. Risks

1. **Breaking the existing demo** — demo seed and demo org walk both products today; every phase must keep `seed_demo_data` green and the demo login usable (Phase 2 acceptance includes it).
2. **Confusing users during transition** — a half-split nav is worse than no split; ship each phase whole, keep the unset-mode fallback identical to today.
3. **Duplicate concepts** — API keys and budgets exist in both stories; without clear "Gateway-primary, Observability read-only" rules (§2) users will ask which budget is real.
4. **Shared models becoming ambiguous** — `asset_registry` serves both; if each surface starts writing conflicting statuses/fields, the shared spine corrupts. Keep discovery_source semantics strict.
5. **Route permission drift** — `app/roles.py` page lists gate access; if nav splits but role lists don't update in lockstep, users lose pages silently (this exact class of bug appeared before with viewer/budgets).
6. **Over-separating too early** — two apps/services before product-market proof doubles maintenance for zero customer value; Phases 4–5 are gated on evidence.
7. **Losing current OTel product momentum** — the OTel surface just landed (Runtime, Asset Intelligence, SemConv layer); the split must be additive around it, not a rewrite of it.
8. **Cost Intelligence data honesty** *(codebase-specific)* — `app/routes/cost_intelligence.py` reads gateway `telemetry` only. If the Observability nav shows "Cost Intelligence" backed by that route, an OTel-only org sees an empty or misleading page. The obs-mode cost view must read OTel usage signals (span token attrs / trace usage totals) and say "signals, not an invoice."
9. **One key, two products** — the same `gk-` key authenticates OTLP ingestion and proxy calls. Fine for now; when surfaces get separate deployments (Phase 4), keys need a surface scope for audit clarity.

---

## 10. Recommendation

**Start with documentation + frontend/setup separation. Keep one backend. Use logical route/product boundaries. Do not split services until product boundaries are proven.**

Concretely:

1. **Adopt this plan (Phase 1)** and split the customer docs per product as the immediate follow-up.
2. **Implement Phase 2 with Option A** — `PRODUCT_SURFACE` mode in the single dashboard app: two navs, two setup flows, Settings/Guardrails cleanup, roles updated in lockstep, unset mode = today's behavior.
3. **Phase 3 backend work is tags + module hygiene only** — no renames, no URL changes, aliases where the new nav needs them.
4. **Defer Phases 4–5** until both surfaces have real, distinct users. The proxy hot path is the only component with a genuine future case for service isolation.
5. Throughout: protect the demo seed, the OTel momentum, and the two sentences that define the products — *"See what AI is actually running"* and *"Control AI traffic without instrumenting every app."*
