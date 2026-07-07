# ObserveAgents — UI Contract & Rebuild Handoff

*The complete specification for building a new front end (Lovable, v0, a design agency, or by hand) against the existing ObserveAgents backend. Everything here is extracted from the running platform — page inventory, data contracts, real API response samples, role rules, and copy rules. The backend does not change; only the presentation does.*

---

## 1. Product story (paste this into the design tool first)

**ObserveAgents is an Enterprise AI Intelligence Platform — the system of record for enterprise AI agents.**

The operating model, which the UI must communicate everywhere:

```
OpenTelemetry / OTLP  →  Runtime  →  Asset Intelligence  →  Security Intelligence
                                            →  Detection Rules  →  Gateway Control Center
```

- Customers send **OpenTelemetry traces**; ObserveAgents turns runtime evidence into an **AI inventory**, **capabilities**, **findings**, **security intelligence**, and **Gateway control recommendations**.
- **Core line (verbatim, use it):** *Observe first. Control only what matters.*
- **Second rule (verbatim):** *Observability discovers and recommends. Gateway controls only when explicitly configured.*
- Nothing in the Observability product blocks or enforces anything. Every security/control feature is **observe-only**: detect, explain, recommend.

### Copy rules (hard constraints for all generated text)

Never write: generic APM language, SIEM-replacement claims, automatic enforcement/blocking claims, cost/budget emphasis on Observability pages, "SDK required" (OTel is the integration — no proprietary SDK).
Prefer: *runtime evidence · AI assets · ownership · findings · security intelligence · detection rules · recommended controls · observe-only until explicitly configured*.

### Design direction (current system, treat as a starting point)

- Dark enterprise console. Current tokens: bg `#0A0B0F`, panel `#0F1117`, panel-high `#141823`, border `#1E2230`, text `#E8ECF4`, dim `#7A8499`, mute `#4B5468`, accent (green) `#7CFFB2`, warn `#FFB547`, critical `#FF5C7A`, info `#6FA8FF`, purple `#B47AFF`, teal for dependency accents.
- Typography: UI font "Geist" (sans), data/labels in "JetBrains Mono". Severity is always color-coded (critical/high = red, medium = amber, low/info = blue/gray).
- Executive-first: generous whitespace, low information density on landing pages, detail behind expansion. Tables everywhere are sortable + searchable.
- Recurring primitives: stat tile (small uppercase mono label + big number), pill/badge (severity, environment, status, `×N` occurrence count), collapsible panel, horizontal bar list, empty states with one explanatory sentence.

---

## 2. Information architecture

Two workspaces in **one app** (this is the O9 product model — no env switching between them):

```
Observe (default landing)          Gateway Control
  Dashboard                          Control Center
  Overview                           Providers        (gateway surface)
  Platform Guide                     Budgets          (gateway surface)
  Runtime                            Pricing Registry (gateway surface)
  Asset Intelligence
  Security Intelligence
  Guardrails
  Dependency Map
Administration
  Governance Readiness · Security & Audit · Users · API Keys · OTel Setup · Settings
```

### Roles (RBAC — must be respected by the UI)

| Role | Sees | Can act |
|---|---|---|
| **admin** | everything | everything (only role that can act on Gateway control candidates) |
| **analyst** | all observe pages, read-only admin-lite | dismiss/resolve normal findings; **not** control candidates |
| **viewer** | all observe pages | read-only everywhere |

Page IDs are server-known (`app/roles.py`); keep these IDs for zero-backend-change routing: `dashboard, overview_hub, welcome, runtime, intelligence, security_intel, gateway_control_center, guardrails, relationship_map, governance, security, users, apikeys, integrations, settings, cost, budgets, pricing, discovery, agent_inventory`.

---

## 3. Page-by-page specification

For each page: purpose → data (endpoints) → key elements → actions → states.

### 3.1 Login
- `POST /auth/login {email, password}` → `{access_token, user}`. Store token; add `Authorization: Bearer <token>` to every call. On any 401 → clear token, return to login. Rate limit: 5 attempts/min (show the 429 message).
- Demo mode (`GET /config → demo_mode:true`): skip login entirely via `POST /auth/demo-login`.

### 3.2 Dashboard (executive landing)
- Purpose: "is my AI estate healthy" in 5 seconds.
- Data: `GET /intelligence/asset-summary`, `GET /telemetry/summary`, recent `GET /runtime/traces?limit=20`.
- Elements: KPI tiles (systems observed, open findings, high severity, error traces), a short "needs attention" list, click-through to detail pages. Low density, no charts overload.

### 3.3 Overview (`overview_hub`)
- Purpose: role-based triage. Toggle **Executive / Operator** (persisted locally).
- Data: aggregate of findings/assets/traces/alerts (`/intelligence/findings?status=open`, `/intelligence/asset-summary`, `/runtime/traces`, `/security/alerts`, `/telemetry/summary`, `/cost-intelligence` trend for executives).
- Attention strip refreshes every 30s — show a **countdown timer** ("next refresh · 27s"), never the sentence "refreshes every 30 seconds".
- Attention card: **"Agent needs owner"** — count of observed assets with open `agent_missing_owner`/`unmanaged_runtime` findings; subtitle: *"Observed AI assets without assigned ownership should be reviewed before production expansion."* Links to Governance.
- "Worst offender" hero: the asset with most high findings + error traces → Investigate → Asset Intelligence.
- Executive view: spend/requests/tokens/latency tiles, cost trend chart, estate status bars. Operator view: recent executions, open findings by category, top findings, detection rules firing. **No budget content on this page.**

### 3.4 Runtime (`runtime`)
- Purpose: what actually executed.
- Data: `GET /runtime/traces?limit=100&service_name=<agent>` (list), `GET /runtime/traces/{trace_id}` (detail: spans with offsets → waterfall).
- Elements: agent filter (server-side refetch on change), **session grouping** — one collapsed row per `session_id` (name ×N badge, totals; expand to individual traces), trace waterfall with step types (LLM call / tool / MCP / db), duration + error badges.
- Trace fields: `trace_id, root_span_name, service_name, session_id, start_time, duration_ms, span_count, error_count` (sample in appendix).

### 3.5 Asset Intelligence (`intelligence`)
- Purpose: the AI inventory — one card per discovered AI system.
- Data: `GET /intelligence/asset-summary` (primary, sample in appendix), `GET /intelligence/capabilities`, `GET /intelligence/findings`, `POST /intelligence/run` (the "Run Intelligence" button).
- Asset card: name, environment pill, status pills, models/providers/tools/dependencies chips, findings summary (`open · high · per-category`), runtime stats; expanded: capabilities pills, findings list with actions.
- Finding row: severity pill, title, `×N` occurrence badge when `occurrence_count > 1`, actions **Dismiss / Resolve / Reopen** (`POST /intelligence/findings/{id}/dismiss|resolve|reopen`).
- If the asset has an open `category="control"` finding → button **"Review in Gateway Control Center →"** (navigates pre-filtered).

### 3.6 Security Intelligence (`security_intel`)
- Purpose: *which AI systems have risky runtime-observed behavior?* Title: **AI Agent Runtime Security Intelligence**.
- Data: same asset-summary + `GET /security/alerts`.
- Elements: runtime security findings grouped in six buckets (database access, external APIs, MCP in production, tool surface, unknown providers, human review); Risky AI Systems table (risky capability pills per system, open security findings, high count, **Control** column with "Review in Control Center" when a candidate exists); alerts feed.

### 3.7 Gateway Control Center (`gateway_control_center`)
- Purpose: the action workspace — **only** agents recommended for control. Header line: *Observe first. Control only what matters.* plus "Nothing on this page blocks or reroutes traffic."
- Data: `GET /intelligence/findings?category=control` (sample in appendix) + asset-summary for names/owners.
- Candidate row: agent name, environment, owner ("no owner" if none), risk pill (high/medium), `N findings` pill, "routing required" pill when any hard control, relative last-seen; expanded: **Why this agent is here** (reason + trigger finding-type pills) and **Suggested controls** — each control labeled by kind: `soft` = "available now" (green), `routing` = "routing step" (purple), `hard` = "requires Gateway routing" (red). Footer: "Hard controls only work after this agent's traffic is routed through the Gateway. Nothing is applied automatically."
- Sections: RECOMMENDED FOR CONTROL (open, worst first) · DISMISSED / RESOLVED (dimmed).
- Actions: **admin only** — Dismiss recommendation / Reopen (server returns 403 for others; hide buttons for non-admins).

### 3.8 Guardrails (`guardrails`)
- Observe-only guardrail catalog + per-team guard modes (observe / alert / enforce — enforce belongs to Gateway). Data: `GET /guardrails` family. Copy must say: detect, explain, recommend — nothing is blocked.

### 3.9 Governance Readiness (`governance`) — admin
- Ownership assignment for observed assets (owner/team per asset), claim flow. This is where the "Agent needs owner" card lands.

### 3.10 Administration
- **Users** — CRUD (`GET/POST/PATCH/DELETE /auth/users`), role select (admin/analyst/viewer), password change requires current password.
- **API Keys** (`/apikeys` family) — issue `gk-…` keys (shown once), used for OTLP ingestion auth.
- **OTel Setup** (`integrations`) — copy-paste onboarding: exporter env vars + collector snippet pointing at `https://app.observeagents.ai/otel` (the `otlphttp` exporter appends `/v1/traces`), Bearer `gk-` key. HTTP only, traces only.
- **Settings** — org settings, provider keys (never display secrets; last-4 only).

---

## 4. API contract (the layer the new UI must implement)

- **Base URL:** `https://app.observeagents.ai` (configurable — keep it in one place, e.g. `VITE_API_BASE`).
- **Auth:** `Authorization: Bearer <jwt>` on everything except `/auth/login`, `/config`, `/health`. JWT expires after 8h → on 401, logout. `GET /auth/me` restores the session user.
- **Boot order:** fetch `GET /config` **before** first render — it decides demo mode (`demo_mode:true` → auto-login via `/auth/demo-login`, hide logout).
- Timestamps are ISO-8601; format client-side with `en-US` locale, relative time for "last seen".

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/login` · `POST /auth/demo-login` · `GET /auth/me` · `GET/POST/PATCH/DELETE /auth/users` |
| Config | `GET /config` · `GET /health` |
| Intelligence | `POST /intelligence/run` · `GET /intelligence/asset-summary` · `GET /intelligence/findings?category=&severity=&status=&asset_id=` · `GET /intelligence/capabilities` · `POST /intelligence/findings/{id}/dismiss\|resolve\|reopen` |
| Runtime | `GET /runtime/traces?limit=&service_name=` · `GET /runtime/traces/{trace_id}` |
| Security | `GET /security/alerts` |
| Cost/Budgets (gateway) | `GET /cost-intelligence?breakdown_by=&days=` · `GET/POST/DELETE /budgets` · `GET /budgets/status` |
| Telemetry | `GET /telemetry/summary` · `GET /telemetry?limit=` |
| Roles | `GET /roles` (per-org role → pages map; fall back to the §2 matrix) |
| Guardrails | `GET /guardrails` family |
| Ingestion (not called by UI; shown in Setup copy) | `POST /otel/v1/traces` |

**CORS:** the backend allows extra origins via its `FRONTEND_ORIGIN` env var — add the Lovable preview origin there to develop against the live API, or build against the mock data below first (recommended).

---

## 5. Real API response samples (build the UI against these shapes)

### `GET /config`
```json
{
  "app_env": "production",
  "demo_mode": false,
  "public_app_url": "https://app.observeagents.ai",
  "public_gateway_url": "https://gateway.observeagents.ai",
  "public_marketing_url": "https://www.observeagents.ai"
}
```

### `GET /intelligence/asset-summary` → `{ "assets": [ … ] }` (one asset, trimmed)
```json
{
  "asset_key": "ad4472d369dcb037…",
  "asset_name": "risky-agent",
  "service_name": "risky-agent",
  "environment": "production",
  "last_seen": "2026-07-07T08:28:00.324000",
  "trace_count": 4, "span_count": 4,
  "models": ["gpt-4o"], "providers": ["OpenAI"],
  "tools": ["jira_search"], "dependencies": ["postgresql"],
  "capabilities_count": 4,
  "findings_count": 12, "open_findings_count": 12, "high_findings_count": 5,
  "finding_categories": { "security": 7, "operations": 2, "inventory": 2, "control": 1 },
  "status": ["active", "runtime_observed", "has_findings"],
  "capabilities": [
    { "id": 2, "capability_type": "database", "capability_name": "postgresql",
      "source": "otel_trace", "last_seen": "2026-07-07T08:28:00.366517" }
  ],
  "findings": [
    { "id": 1, "category": "security", "finding_type": "database_access",
      "severity": "medium", "title": "Database Access Detected",
      "summary": "This AI system has direct database read/write capability.",
      "source": "otel_trace", "status": "open", "occurrence_count": 1,
      "last_seen": "2026-07-07T08:28:00.366517" }
  ]
}
```

### `GET /intelligence/findings?category=control` (a Gateway control candidate)
```json
{
  "id": 12,
  "asset_key": "ad4472d369dcb037…",
  "category": "control",
  "finding_type": "gateway_control_recommended",
  "severity": "high",
  "title": "Gateway Control Recommended",
  "summary": "Runtime evidence recommends reviewing this agent for Gateway control: 4 open high-severity findings and human review recommended (…). No control is applied automatically.",
  "status": "open",
  "occurrence_count": 4,
  "evidence": {
    "reason": "Runtime evidence recommends reviewing this agent for Gateway control: 4 open high-severity findings and human review recommended (…).",
    "environment": "production",
    "trigger_count": 4,
    "trigger_finding_ids": [8, 9, 10, 11],
    "trigger_finding_types": [
      "agent_has_database_access", "agent_missing_owner",
      "agent_uses_mcp_tool_in_production", "human_review_recommended"
    ],
    "recommended_controls": [
      { "control": "route through gateway",    "kind": "routing" },
      { "control": "human review requirement", "kind": "soft" },
      { "control": "owner assignment",         "kind": "soft" },
      { "control": "mcp/tool usage policy",    "kind": "hard" },
      { "control": "rate limit",               "kind": "hard" }
    ]
  }
}
```

### `GET /runtime/traces?limit=5`
```json
[
  {
    "trace_id": "0b7de8b8449e4f3c94a1c49fc48ca5e0",
    "root_span_name": "mcp.call",
    "service_name": "risky-agent",
    "session_id": "9c2c1a7e33f04bd2a8bd8e21f38f2f10",
    "start_time": "2026-07-07T08:28:00.324000",
    "duration_ms": 500,
    "span_count": 1,
    "error_count": 0
  }
]
```

Finding severity values: `critical | high | medium | low | info`. Finding statuses: `open | dismissed | resolved`. Finding categories: `security | performance | operations | dependency | inventory | control`. Control kinds: `soft | routing | hard`.

---

## 6. Ready-to-paste Lovable master prompt

> Build a dark, executive-grade enterprise console called **ObserveAgents — Enterprise AI Intelligence Platform**. It is the system of record for enterprise AI agents: customers send OpenTelemetry traces, and the platform turns runtime evidence into an AI inventory, security findings, and Gateway control recommendations. Tagline used in the UI: **"Observe first. Control only what matters."** The product never blocks anything — every security feature is observe-only: detect, explain, recommend.
>
> Design: dark theme (bg #0A0B0F, panels #0F1117, borders #1E2230, text #E8ECF4, green accent #7CFFB2, amber #FFB547 for warnings, red #FF5C7A for high severity, blue #6FA8FF for info). Sans-serif UI font, monospaced font for data labels and numbers. Executive-first: whitespace, restrained density, detail behind expansion. Sortable/searchable tables, severity pills, "×N" occurrence badges, empty states with one helpful sentence.
>
> App shell: left sidebar with grouped nav — **Observe** (Dashboard, Overview, Runtime, Asset Intelligence, Security Intelligence, Guardrails) then **Gateway Control** (Control Center) then **Administration** (Governance, Users, API Keys, OTel Setup, Settings). Three roles: admin (full), analyst (acts on findings, not control candidates), viewer (read-only). Login page (email+password, dark, minimal) — mock the auth for now.
>
> Start with these four pages using the mock data I'll paste next: (1) **Overview** — executive/operator toggle, an attention card "Agent needs owner", a 30-second refresh countdown "next refresh · 27s", a worst-offender hero card; (2) **Runtime** — trace table grouped by session with expandable rows and a waterfall detail; (3) **Asset Intelligence** — one expandable card per AI system with capability chips and findings with dismiss/resolve actions; (4) **Gateway Control Center** — a queue of agents recommended for control, each expandable to show "why this agent is here" (trigger findings) and "suggested controls" where each control is tagged *available now* / *routing step* / *requires Gateway routing*, plus the footer "Nothing is applied automatically."
>
> Use mock data matching the JSON shapes I provide. Put all data access behind a single `src/lib/api.ts` module with functions like `fetchAssetSummary()`, `fetchRuntimeTraces()`, `fetchControlCandidates()`, `dismissFinding(id)` so I can later point it at the real REST API with a Bearer token.

Then, in the following messages: paste the JSON samples from §5 ("use these as the mock data shapes"), iterate one page at a time, and attach screenshots of the current product for layout reference.

---

## 7. Integration path (after the design is right)

1. In Lovable, replace the mock implementations inside `src/lib/api.ts` with real `fetch` calls to `VITE_API_BASE` + Bearer token from login — the function signatures stay.
2. Set `FRONTEND_ORIGIN=<your-lovable-or-new-domain>` on the `ai-asset-app` Render service so CORS allows the new origin.
3. Boot order: call `GET /config` first; if `demo_mode`, auto-login with `POST /auth/demo-login`.
4. When ready to replace the current dashboard entirely: build the new app to static output and serve it from `dashboard/dist` (keep `VITE_API_BASE`/`VITE_PRODUCT_SURFACE` envs and the `render.yaml` build command), or deploy it as its own static site pointing at the API.
