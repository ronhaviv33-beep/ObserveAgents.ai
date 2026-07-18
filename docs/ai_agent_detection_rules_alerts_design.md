# AI Agent Detection Rules & Alerts Design

*Design document only — nothing in this file is implemented. No code, no migrations, no new endpoints, no Slack integration, no webhook delivery, no behavior change. This document supersedes and expands [ai_agent_detection_rules_plan.md](archive/legacy/ai_agent_detection_rules_plan.md) as the canonical design for roadmap phase **O4 — Monitors & notifications**.*

**Positioning:** this is **AI Agent Detection Rules** (also: *AI Agent Runtime Rules & Alerts*, *Detection Rules for AI Agents*). It is deliberately **not a SIEM replacement** — no log ingestion, no cross-system correlation language, no threat-intel feeds. Every rule is about an AI agent: what it runs, what it can reach, how it behaves, who owns it.

> **Detection Rules convert AI-agent runtime evidence into alerts when behavior crosses a threshold or matches a risky pattern.**

The two lines that govern the whole feature:

> **Rules observe and alert. Gateway can optionally enforce later.**
>
> **Observe can recommend. Gateway can enforce only when explicitly configured.**

---

## Executive summary

AI agents behave differently from normal software. They choose their own tools at runtime, call MCP servers, retry workflows on their own judgment, reach APIs and databases, switch between providers and models, and generate unexpected token cost. A deployed agent's behavior is an emergent property of its prompt, tools, and inputs — not something a code review fully predicts.

Runtime traces capture all of this, and ObserveAgents already ingests them (OTLP → `otel_spans` → Asset Intelligence → findings). But teams do not want to inspect traces all day. They want to say once: *"tell me when this crosses a line"* — and then get on with their work.

**Detection Rules turn runtime evidence into actionable alerts.** A rule is a condition over evidence the platform already stores ("MCP calls > 5 in 10 minutes", "unknown provider in production"). When the condition matches, the platform records a rule match, raises an alert, and — when the risk is high enough — recommends the agent for review in Gateway Control Center.

The first version is **observe-only**:

- create rule matches
- create alerts/findings
- notify Slack/webhook **later** (designed here, built in a later phase)
- recommend Gateway Control when risk is high

**No automatic blocking. No automatic enforcement. No hidden rerouting.** A rule match is information for a human, never an action against traffic.

---

## Architecture placement

Detection Rules are an **intelligence layer** — not an ingestion layer and not an enforcement layer:

```
OpenTelemetry / OTLP                      (ingestion)
  → Runtime Evidence                      (immutable, scrubbed)
    → Asset Intelligence                  (intelligence)
    → Security Intelligence               (intelligence)
    → Detection Rules  ◄── this design    (intelligence)
      → Gateway Control Candidates        (control recommendations)
        → Gateway Control Center          (human review; optional enforcement, explicitly configured)
```

Rules **consume** normalized runtime evidence (`otel_spans`, `otel_assets`, gateway `telemetry`) and existing asset/security context (`asset_registry`, `asset_findings`).

Rules **may create**:

- rule matches
- alerts
- findings
- Gateway Control Candidate recommendations

Rules **must not**:

- block traffic
- change gateway configuration
- reroute traffic
- mutate raw telemetry
- inspect raw prompts or responses

The same boundary the rest of the platform keeps: intelligence modules are read-only over evidence and write only their own derived records; enforcement lives exclusively in the proxy's explicitly configured guard modes.

---

## Key concepts

### Runtime evidence

The immutable, privacy-scrubbed record of what agents actually did. Sources:

- **OTLP traces** ingested at `POST /otel/v1/traces` (JSON + protobuf)
- **spans** (`otel_spans`) with scrubbed attributes
- **GenAI semantic convention attributes** (`gen_ai.*` — provider, model, agent identity, token usage) via `app/genai_semconv.py`
- **MCP attributes** (`mcp.method.name`, MCP span markers)
- **tool calls** (`gen_ai.tool.name`, tool spans)
- **provider/model metadata** (`gen_ai.provider.name`, `gen_ai.system`, `gen_ai.request.model`, `gen_ai.response.model`)
- **errors** (`error.type`, OTLP status codes, JSON-RPC error codes)
- **durations** (span start/end)
- **token usage where available** (`gen_ai.usage.input_tokens` / `output_tokens`; gateway `telemetry` token columns)

Evidence is read-only to this feature. Rules never add ingestion, never inspect content, and never mutate spans.

### Detection rule

A configurable condition evaluated against runtime evidence: a template (rule type) plus parameters — threshold, time window, scope (environment, asset), severity.

Example: *MCP calls > 5 in 10 minutes.*

### Rule match

A specific time when a rule condition matched, recorded once per (rule, agent, window) with an occurrence count.

Example: *web-research-agent matched `mcp_tool_access_threshold` at 13:42 (×12).*

### Alert

A user-facing record created from a rule match: severity, agent, why it triggered, evidence summary, recommended action, status lifecycle (open → acknowledged → resolved/dismissed).

### Notification

Delivery of an alert to an external channel — Slack, webhook, later email. Notifications are a view over alerts; suppressing a notification never deletes the underlying match.

### Gateway Control Candidate

An agent whose risky rule matches/findings warrant human review in Gateway Control Center. Candidates are review-queue entries produced by `app/gateway_control.py` — recommendations only, never enforcement.

---

## MVP rule templates

All templates read evidence that already exists in the normalized store (`otel_spans` scrubbed attributes, `otel_assets`, `asset_registry`, gateway `telemetry`). Severities are defaults, configurable per rule instance. "Gateway candidate" means the match can create or contribute to a Gateway Control Candidate via the existing `category="control"` finding path.

### 1. `mcp_tool_access_threshold`

- **Description:** An agent calls MCP tools more than N times in a time window.
- **Evidence source:** `otel_spans` — `mcp.method.name`, `gen_ai.tool.name`, MCP span markers (`app/genai_semconv.py:is_mcp_span`), span ids, span count, environment.
- **Default threshold/window:** > 5 MCP calls in 10 minutes.
- **Severity:** medium (high in production).
- **Alert text:** `web-research-agent called MCP tools 12 times in 10 minutes.`
- **Recommended action:** Review whether this agent should have this MCP/tool access level.
- **Gateway candidate:** yes — if production or high count.

### 2. `repeated_tool_errors`

- **Description:** The same agent/tool combination fails repeatedly.
- **Evidence source:** `otel_spans` — tool name, `mcp.method.name`, `error.type` (via `extract_error_type`), sample span ids, error count.
- **Default threshold/window:** ≥ 3 errors in 10 minutes.
- **Severity:** medium (high in production).
- **Alert text:** `sales-agent failed crm_lookup 6 times in 10 minutes.`
- **Recommended action:** Check the dependency, add fallback behavior, or route to human review.
- **Gateway candidate:** yes — if repeated in production.

### 3. `unknown_provider_in_production`

- **Description:** A production agent uses an unknown or unapproved provider/model.
- **Evidence source:** `gen_ai.provider.name`, `gen_ai.system`, `gen_ai.request.model`, `gen_ai.response.model` vs. the known-provider catalog (`runtime_security_intelligence.KNOWN_PROVIDERS`); environment; sample span ids.
- **Default threshold/window:** presence-based, per evaluation run.
- **Severity:** high.
- **Alert text:** `support-agent used unknown provider in production.`
- **Recommended action:** Confirm provider approval and ownership.
- **Gateway candidate:** yes.

### 4. `database_access_in_production`

- **Description:** An agent accesses a database in production.
- **Evidence source:** `otel_spans` — `db.system`, `db.name`, span ids, environment.
- **Default threshold/window:** presence-based (≥ 1 db span) per window; threshold configurable upward for expected-DB agents.
- **Severity:** medium (high when combined with missing owner).
- **Alert text:** `finance-agent accessed postgres in production.`
- **Recommended action:** Review whether this agent should access this database.
- **Gateway candidate:** maybe — depending on severity and combination with other matches.

### 5. `db_to_external_api_same_trace`

- **Description:** The same trace contains database access **and** an external API call — a data-egress-shaped pattern.
- **Evidence source:** `otel_spans` grouped by `trace_id` — `db.system`/`db.name` on one span, sanitized external domain (host+path only) on another; trace id; span ids.
- **Default threshold/window:** ≥ 1 matching trace per window.
- **Severity:** high.
- **Alert text:** `finance-agent accessed postgres and api.vendor.com in the same workflow.`
- **Recommended action:** Review whether sensitive data could leave internal systems. Consider human review.
- **Gateway candidate:** yes.
- **Note:** the only template requiring per-trace correlation — existing intelligence modules aggregate per asset, not per trace. The evaluator adds a trace-grouping pass for this rule.

### 6. `broad_tool_surface`

- **Description:** An agent uses too many distinct tools.
- **Evidence source:** union of tool names and MCP methods (`otel_assets.tools_json` + span-level names — the same union `runtime_security_intelligence._AssetAcc.tool_names` computes); tool count; environment.
- **Default threshold/window:** ≥ 5 distinct tools (aligned with the existing `agent_has_broad_tool_surface` finding thresholds: 5, high at 8 in production).
- **Severity:** medium (high if production and ≥ 8).
- **Alert text:** `research-agent used 9 distinct tools.`
- **Recommended action:** Reduce tool scope or add a tool-routing policy.
- **Gateway candidate:** yes — if production and high count.

### 7. `ai_workload_missing_owner` *(governance/attribution nudge — renamed from `missing_owner_in_production`)*

- **Description:** An AI workload has no owner/team metadata yet. Under auto-instrumentation-first discovery, owner/team is **optional attribution metadata** — its absence is a nudge, never a security defect.
- **Evidence source:** `asset_registry.owner`/`team`; asset key; service name; the absent fields.
- **Default threshold/window:** presence-based, per evaluation run.
- **Severity:** **info** by default (low at most). Missing owner may raise the *priority of other findings* only when combined with risky runtime evidence on the same asset — unknown provider in production, high MCP/tool usage, repeated errors, DB + external API in the same trace, a flagged dependency, or (future) payment activity — never on its own.
- **Alert text:** `research-agent has no owner/team metadata yet — optional owner/team metadata improves attribution and routing.`
- **Recommended action:** Optional owner/team metadata improves attribution and routing.
- **Gateway candidate:** **no — never on its own.** Ownership gaps may add context to candidates created by risky runtime evidence, but absence of optional metadata never creates one.

### 8. `high_token_usage_threshold`

- **Description:** An agent exceeds a token threshold in a time window. This is an **Observability Cost Signal** — do not claim billing accuracy; provider invoices are the billing source of truth.
- **Evidence source:** `gen_ai.usage.input_tokens` / `output_tokens` (reasoning/cache tokens where available) from scrubbed span attributes; gateway `telemetry` token columns; model/provider; span ids; count.
- **Default threshold/window:** configurable (suggested starting point: 100k tokens / 1 hour for interactive agents; teams tune per workload).
- **Severity:** medium.
- **Alert text:** `coding-agent used more than 100k tokens in one hour.`
- **Recommended action:** Review workflow efficiency, model choice, and retry behavior.
- **Gateway candidate:** maybe — as a cost/control recommendation (budget/rate-limit suggestion if the agent is ever routed through Gateway).

### 9. `flagged_dependency_touched`

- **Description:** An agent touches a domain, GitHub repo, MCP server, package, or tool that appears on a customer-configured watchlist.
- **Evidence source:** indicator type (domain / repo / mcp_server / package / tool), sanitized indicator value (host+path only — never query strings), source/watchlist name, sample span ids, count.
- **Default threshold/window:** presence-based — any touch of a watchlisted indicator per window.
- **Severity:** per-watchlist-entry (default high).
- **Alert text:** `research-agent touched flagged MCP server unknown-tools.example.`
- **Recommended action:** Review dependency trust before allowing production use.
- **Gateway candidate:** yes — if severity high.
- **Boundary:** watchlists are **customer-configured lists only**. No external threat feed integration in any planned phase (see "What not to build now").

---

## Rule evaluation model

**Hard MVP constraint: rule evaluation never runs inside the OTLP ingestion request path.** `POST /otel/v1/traces` stays lightweight, reliable, and focused on accepting evidence — it parses, scrubs, stores, and returns 202. Detection Rules belong to the intelligence layer and run after ingestion, preferably during or after the intelligence run.

### Phase 1 — Batch evaluation (MVP)

Rules are evaluated after:

- an intelligence run (`POST /intelligence/run` — as a post-pass, exactly where `derive_runtime_security_findings` and `derive_gateway_control_candidates` are orchestrated today in `app/asset_intelligence.py`)
- a scheduled job (when a scheduler exists)
- a manual run

The evaluator: loads the org's enabled rules → builds per-asset evidence accumulators (generalizing the `_AssetAcc` pattern from `app/runtime_security_intelligence.py`, extended with per-trace grouping for rule 5 and token sums for rule 8) → evaluates each condition against its window → upserts matches through shared dedup machinery.

Batch is easier, idempotent, and sufficient for MVP: the evidence is already stored, and the alert latency of "next evaluation run" matches the product's review-queue posture.

### Phase 2 — Near-real-time evaluation (later, explicitly scoped)

Rules are evaluated shortly **after** ingestion completes — never inside the ingestion request itself — for the small subset that are presence-based and cheap (e.g. `unknown_provider_in_production`). Threshold/window rules stay batch: the ingest path must never grow O(rules × spans) work. If added, the post-ingest hook only enqueues candidate (rule, asset) pairs for the next batch pass; it does not evaluate conditions or write matches inline.

**Do not implement Phase 2 in MVP unless explicitly scoped later.**

---

## Alert deduplication and spam prevention

An alert system that spams gets muted, and a muted alert system is worse than none. Rules:

- **Dedup key:** `org_id + rule_id + asset_key + time window` — one match row per window bucket, never one per span.
- **No repeated Slack alerts per span:** notifications fire per match, subject to cooldown, never per underlying event.
- **`occurrence_count`:** the match row carries how many times the condition's underlying events occurred in the window (same `×N` mechanic as `asset_findings.occurrence_count`).
- **Cooldown window:** per (rule, asset), suppress *notifications* (not match rows) for a configurable cooldown (default 60 minutes) after the first delivery.
- **Status lifecycle:** `open`, `acknowledged`, `resolved`, `dismissed`. Dismissal is sticky per window; matches are never hard-deleted.
- **Future:** `snoozed` — suppress notifications until a timestamp while keeping the row visible.

Example: if the MCP threshold is exceeded 20 times in 10 minutes, create **one** alert — *"MCP threshold exceeded ×20"* — not 20 Slack messages.

Idempotency contract (inherited from the findings engine): re-running the evaluator over unchanged data creates **zero** new matches; it recomputes `occurrence_count` absolutely for the same bucket.

---

## Future data model proposal

**Proposal only — no migration, no models change now.** All tables follow `app/models.py` conventions: integer PK, non-null indexed `organization_id` FK, timezone-aware timestamps, JSON columns as `*_json` text, org isolation on every query (denormalized `org_id` on child rows so list queries never join across orgs — the `asset_findings` pattern).

### `agent_detection_rules`

| Field | Notes |
|---|---|
| `id` | PK |
| `org_id` | FK, indexed, non-null |
| `name` | display name |
| `description` | optional free text |
| `rule_type` | one of the §MVP templates, validated |
| `enabled` | bool |
| `severity` | default severity override |
| `threshold` | numeric threshold |
| `window_minutes` | evaluation window |
| `scope_json` | environment filter, asset keys, teams |
| `condition_json` | template-specific parameters (e.g. watchlist ref for rule 9) |
| `notification_target_ids_json` | channel ids to notify |
| `created_by` / `created_at` / `updated_at` | audit |

### `agent_rule_matches`

| Field | Notes |
|---|---|
| `id` | PK |
| `org_id` | denormalized, indexed |
| `rule_id` | FK |
| `asset_key` / `asset_id` | agent identity (same keys as `asset_findings`) |
| `severity` | resolved severity at match time |
| `status` | open / acknowledged / resolved / dismissed (later: snoozed) |
| `occurrence_count` | events in window |
| `window_start` / `window_end` | tumbling bucket bounds — part of the dedup key |
| `evidence_json` | identifiers + counts only (see Privacy boundaries) |
| `created_at` / `updated_at` | audit |
| `acknowledged_by` / `acknowledged_at` | actor audit |
| `dismissed_by` / `dismissed_at` | actor audit |

### `notification_channels`

| Field | Notes |
|---|---|
| `id` | PK |
| `org_id` | FK |
| `type` | `slack` / `webhook` (email later) |
| `name` | display name |
| `config_json` | target config; secrets (webhook URLs) encrypted with the existing `CREDENTIAL_ENCRYPTION_KEY` Fernet pattern, never returned by any API |
| `enabled` | bool |
| `created_at` / `updated_at` | audit |

### `notification_deliveries`

| Field | Notes |
|---|---|
| `id` | PK |
| `org_id` | denormalized |
| `rule_match_id` | FK |
| `channel_id` | FK |
| `status` | pending / sent / failed / dead / suppressed-cooldown / suppressed-ratelimit |
| `attempt_count` | retries |
| `last_error` | exception class + HTTP status only — never response bodies |
| `delivered_at` / `created_at` | audit |

---

## R5 implementation note (shipped)

The **webhook** slice of this design is implemented (`app/notifications.py`,
`app/routes/notifications.py`, tables `notification_channels` /
`notification_deliveries`):

- **Webhooks first; Slack remains future.** Only `type="webhook"` is supported.
- **Post-intelligence, not ingestion-path.** Delivery runs from
  `derive_asset_intelligence` after it commits — never from `/otel/v1/traces`
  or any span-ingest path.
- **`detection_rules` findings only**, open, severity ≥ the channel's
  `min_severity` (default medium).
- **Cooldown prevents spam.** One webhook per (org, channel, finding) per 60
  minutes; a suppressed attempt records a `skipped_cooldown` delivery row.
- **Fail-safe.** A webhook error is recorded on the delivery row (exception
  class + HTTP status only) and never breaks the intelligence run.
- **No enforcement.** A notification is a POST to a customer endpoint; nothing
  is blocked, rerouted, or configured.
- **Secrets encrypted.** The webhook URL (which may embed a token) is
  Fernet-encrypted at rest with the existing `CREDENTIAL_ENCRYPTION_KEY`
  pattern and never returned by any API or written to any log — only the host
  is exposed.
- **Admin-only API:** `POST/GET/PATCH/DELETE /notifications/channels`.

Still future (design below): Slack channels, async delivery workers with
retry/backoff, per-channel rate caps beyond the cooldown, and a management UI.

## Slack and webhook notification design

**Slack and async delivery are still design-only** (the webhook slice above is shipped). Full delivery runs async (never blocks the evaluator or any request path), with exponential-backoff retries and per-channel rate caps.

A Slack alert includes:

- rule name
- agent name
- severity
- why it triggered (threshold vs. observed)
- evidence summary (names and counts only)
- recommended action
- link to Security Intelligence
- link to Gateway Control Center if the agent is a candidate

Example Slack message:

```
🚨 AI Agent Alert: High MCP usage

Agent: web-research-agent
Severity: Medium
Matched: 12 MCP calls in 10 minutes
Evidence: search_web, fetch_url, summarize_page
Recommended action: Review MCP/tool access.
Open: Security Intelligence / Gateway Control Center
```

Webhook payload fields:

- `org_id`
- `alert_id`
- `rule_type`
- `asset_key`
- `severity`
- `evidence` (allowed fields only)
- `recommended_action`
- `links` (Security Intelligence; Gateway Control Center when candidate)

**Privacy:** notifications never include raw prompts, responses, tool arguments, or tool results. The payload builder consumes only `evidence_json`, which is already restricted to the allowed list below — there is no code path from raw span attributes to a notification body. Webhook URLs (secrets) never appear in payloads, logs, or API responses.

---

## Security Intelligence integration

Security Intelligence (SecurityIntelligenceV2, reading `GET /intelligence/findings`) shows:

- rule matches (as an investigation surface, alongside derived findings)
- alert status (open / acknowledged / resolved / dismissed)
- affected agents
- evidence (allowed fields, with span/trace ids for drill-down into Runtime)
- recommended action

Suggested presentation: a dedicated **Detection Rule Matches** bucket in the existing bucket model — or fold matches into the existing investigation buckets where they naturally belong:

- MCP/tool risk (rules 1, 6)
- Unknown providers (rule 3)
- Repeated errors (rule 2)
- Threat Intelligence Matches (rule 9 — customer watchlists, not external feeds)

MVP recommendation: start with the single **Detection Rule Matches** bucket (cheapest, clearest provenance), evolve into per-family placement when volume justifies it.

---

## Gateway Control Center integration

A rule match can create or contribute to a Gateway Control Candidate — through the same `category="control"` finding path `app/gateway_control.py` uses today, with the rule's trigger type mapped to suggested controls in `_CONTROL_MAP` style:

- `unknown_provider_in_production` → provider allowlist recommendation
- `mcp_tool_access_threshold` → MCP/tool usage policy recommendation
- `db_to_external_api_same_trace` → human review recommendation
- `high_token_usage_threshold` → budget/rate-limit recommendation **if routed through Gateway**
- `flagged_dependency_touched` → restrict tool/domain/package **if routed through Gateway**

**Important: Gateway Control Center shows recommendations only. No enforcement unless traffic is explicitly routed through Gateway and controls are explicitly configured.** Sticky dismissal applies: a dismissed candidate reopens only when a new trigger type appears.

---

## UI proposal

Future page: **Rules & Alerts** (Observability surface; hidden on the Gateway-only build via the existing `productSurface` gating; registered through the standard `PAGES` / `NAV_GROUPS` / `renderPage` pattern in `dashboard/src/App.jsx` plus role page-lists).

Sections:

1. **Rule templates** — the catalog above, with descriptions and defaults; "Enable" instantiates a rule.
2. **Active rules** — configured rules: type, scope, threshold/window, severity, enabled toggle, last evaluation.
3. **Recent matches** — the alert feed: severity, agent, rule, window, `×N` badge, status actions.
4. **Notification channels** — Slack/webhook channels with masked targets and a "Send test" action.
5. **Delivery history** — what was sent where, retries, failures, suppressions.
6. **Alert cooldown/snooze settings** — per-rule cooldowns, channel caps.

**MVP UI can start as read-only: templates + recent matches.** No enforcement controls anywhere — the only actions are informational (acknowledge / resolve / dismiss / test).

---

## Privacy boundaries

**Allowed** in rule evidence, match rows, and alert payloads:

- agent name · asset key · environment
- rule name · counts · span ids · trace ids
- tool names · MCP method names · provider/model names
- sanitized domain/path (scheme+host+path only, as `runtime_security_intelligence._safe_url_parts` stores them)
- error types · token counts · durations

**Forbidden** — never stored on a match, never sent in an alert:

- prompts · responses · system instructions · raw messages
- tool arguments · tool results
- request bodies · headers · credentials
- full URLs with query strings

These are the boundaries already enforced at ingestion by `app/otel_privacy.py` (content-bearing keys are scrubbed before storage). Because the evaluator reads only the scrubbed store, forbidden items are structurally unavailable to it — the boundary holds even if a rule is misconfigured.

---

## Relationship to findings

- **Findings** are evidence-backed observations the platform derives with fixed logic ("this agent has database access").
- **Rules** are configurable conditions the customer sets over the same evidence ("tell me when db access happens in production more than N times").
- **Rule matches** may create alerts, and may also create/update findings so they flow through the existing investigation and control-candidate machinery.

Potential mapping when a match materializes as a finding:

- `category` = security / operations / cost / governance (per rule family)
- `source` = `detection_rules`
- `finding_type` = `rule_<rule_type>`, or an existing finding type where one already expresses the same fact

**Do not duplicate existing findings unnecessarily.** Where a rule template overlaps an existing derived finding (`broad_tool_surface` ↔ `agent_has_broad_tool_surface`, `repeated_tool_errors` ↔ the existing type, `unknown_provider_in_production` ↔ `agent_uses_unknown_model_provider`, `ai_workload_missing_owner` ↔ the retired `agent_missing_owner`), the rule adds the customer's threshold/window/notification on top — it should update the existing finding's occurrence/severity rather than mint a parallel type.

---

## MVP implementation sequence

| Phase | Deliverable |
|---|---|
| **R0** | This design document |
| **R1** | Fixed built-in rule evaluator — the templates above with hardcoded defaults, evaluated after `/intelligence/run`; no UI config yet |
| **R2** | Persist rule matches (dedup, occurrence_count, status lifecycle) |
| **R3** | SecurityIntelligenceV2 rule-match bucket |
| **R4** | Gateway Control candidate mapping from rule matches |
| **R5** | Webhook notification channels + deliveries ✅ (Slack still future) |
| **R6** | Rules & Alerts UI (read-only first) |
| **R7** | Configurable rule builder (thresholds, windows, scopes, watchlists) |
| **R8** | Alert cooldown, snooze, acknowledgement workflow |

---

## Open questions

- Should MVP rules be built-in first (R1) or user-configurable immediately (R7 pulled forward)?
- Should rule matches be stored separately (`agent_rule_matches`) or as `AssetFindings` first (no migration, faster to ship, less precise lifecycle)?
- Should Slack channels be org-level or team-level?
- Should rules evaluate on ingestion or on intelligence run? (This design says: intelligence run for MVP; ingestion only for cheap presence rules later.)
- Which roles can create/edit rules — admin only, or analyst too?
- How exactly to handle rate limits/cooldowns — per rule, per asset, per channel, or all three?
- How to link alerts to Gateway Control candidates — direct FK, shared `asset_key` + trigger type, or via the control finding row?

---

## What not to build now

- **SIEM replacement** — no log ingestion, no generic correlation, no detection content marketplace
- **automatic blocking**
- **automatic Gateway enforcement**
- **hidden traffic rerouting**
- **real-time prevention** (in-flight request interception from rules)
- **full rule builder** (custom condition language / arbitrary queries)
- **external threat feeds** (watchlists are customer-configured only)
- **billing-grade cost alerts** (token rules are Observability Cost Signals, not invoices)
- **prompt/content inspection** (structurally excluded by the privacy boundary)
