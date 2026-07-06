# AI Agent Detection Rules & Alerts — Implementation Plan

*Design document only. Nothing in this plan is implemented yet: no code, no migrations, no frontend, no Slack integration. This is the concrete design for roadmap phase **O4 — Monitors & notifications** (the roadmap's "server-side guardrail monitors with thresholds; alert rules on finding families"), and its rule matches are a planned input to **O8 — Observe Advisor**.*

---

## 1. Product definition

**AI Agent Detection Rules are configurable rules that evaluate runtime AI-agent evidence and create alerts/findings when behavior crosses a threshold or matches a risky pattern.**

Examples of what a team can express:

- alert when an agent calls MCP tools more than 5 times in 10 minutes
- alert when a production agent uses an unknown model provider
- alert when an agent repeatedly fails the same tool
- alert when an agent touches a database and an external API in the same trace
- alert when an agent has too broad a tool surface

**Positioning:** this is *AI Agent Detection Rules* (or *AI Agent Runtime Rules & Alerts*) — SIEM-inspired, but deliberately **not a SIEM**. Every rule is about an AI agent: what it runs, what it can reach, how it behaves, who owns it.

The one line that governs the whole feature:

> **Rules observe and alert. Gateway can optionally enforce later.**

No rule ever blocks anything. Detection Rules extend the platform's observe-first posture: they turn the evidence ObserveAgents already derives into *configurable*, *notifiable* signals.

---

## 2. Difference from existing concepts

| Concept | What it is | Who defines it | When it fires | Does it act? |
|---|---|---|---|---|
| **Finding** | A derived fact about an asset ("this agent has database access"), produced by the intelligence engine with fixed logic | The platform (`app/asset_intelligence.py`, `app/runtime_security_intelligence.py`) | On every `/intelligence/run` | No — it's a statement of observed state |
| **Guardrail** | A policy evaluation on gateway traffic (PII, budget, policy checks) with per-team guard modes | Admins via guard mode + policies | Inline on `/v1` proxy requests | Only in `enforce` mode, and only on Gateway traffic |
| **Rule** (this plan) | A *user-configured condition over runtime evidence* — a template plus thresholds, window, scope | Customer teams, from templates | When the evaluator runs and the condition crosses its threshold | No — it records a match |
| **Alert** | The notification produced by a rule match (in-app row, later Slack/webhook message) | Follows from rules | When a match is created (subject to dedup/rate limits) | No — it informs a human |
| **Gateway enforcement** | Actually blocking/altering traffic | Admins, explicitly, per team | Inline | Yes — and it is a separate, opt-in product surface |
| **SIEM** | Generic log correlation, threat feeds, detection content across the whole IT estate | Security vendors | Continuously | Varies |

Boundary statements:

- **Findings vs. rules:** findings are the platform's fixed derivations; rules are the customer's thresholds over the same evidence. A finding says *"this agent invokes MCP tools in production"*; a rule says *"tell me when it does so more than N times in M minutes"*.
- **Rules vs. guardrails:** guardrails see gateway request content in flight; rules see stored, privacy-scrubbed runtime evidence after the fact. They never inspect prompts or responses.
- **Not a SIEM:** no log ingestion, no cross-system correlation, no threat-intel feeds, no generic detection language. The rule vocabulary is AI-agent-shaped: agents, models, providers, tools, MCP, databases, ownership, environments.
- **Observability discovers and recommends. Gateway controls only when explicitly configured.** Rule matches may *recommend* a gateway policy (roadmap R7) — they never create one.

---

## 3. MVP rule templates

All templates read evidence that already exists in the normalized store (`otel_assets`, `otel_spans` scrubbed attributes, `asset_registry`, gateway `telemetry`). Severity below is the default; configurable per rule instance.

### 3.1 `mcp_tool_access_threshold`

- **Description:** An agent's MCP tool usage exceeds a configured rate.
- **Evidence source:** `otel_spans` attributes `mcp.method.name` / MCP SemConv markers (`app/genai_semconv.py:is_mcp_span`), per asset.
- **Condition:** count(MCP spans for asset) > threshold within window.
- **Threshold/window:** default 5 calls / 10 minutes.
- **Severity:** medium · high in production.
- **Recommended action:** Review which MCP servers/tools this agent reaches; confirm the usage pattern is expected; assign an owner if missing.
- **Example alert:** `support-agent (production) invoked MCP tools 12 times in the last 10 minutes (threshold: 5). Methods: tools/call. Tools: jira_search.`

### 3.2 `repeated_tool_errors`

- **Description:** The same agent keeps failing tool or MCP calls.
- **Evidence source:** `otel_spans` error evidence (`error.type`, OTLP status, JSON-RPC error codes via `extract_error_type`) on tool/MCP spans.
- **Condition:** count(tool-error spans for asset) ≥ threshold within window.
- **Threshold/window:** default 3 errors / 15 minutes.
- **Severity:** medium · high in production.
- **Recommended action:** Inspect the failing tool's integration; add fallback behavior (maps to Advisor "tool fallback handling skill").
- **Example alert:** `ticket-triage-agent recorded 7 tool errors in 15 minutes on jira_search. Error types: TimeoutError.`

### 3.3 `unknown_provider_in_production`

- **Description:** A production agent uses a model provider outside the known catalog.
- **Evidence source:** `otel_assets.providers_json` vs. the known-provider catalog; environment from `otel_assets.environment`.
- **Condition:** environment is production AND any provider not in catalog (or missing entirely).
- **Threshold/window:** none — presence-based; evaluated per run.
- **Severity:** high.
- **Recommended action:** Verify the provider is approved; if it is, add it to the catalog; if not, migrate the agent to an approved provider.
- **Example alert:** `research-agent (production) is using unknown model provider "mystery-llm-co" (model: mystery-1).`

### 3.4 `database_access_in_production`

- **Description:** A production agent reaches a database at runtime.
- **Evidence source:** `otel_spans` attributes `db.system` / `db.name`.
- **Condition:** environment is production AND count(db spans) ≥ threshold within window.
- **Threshold/window:** default 1 (presence) / evaluation window; configurable up for chatty agents.
- **Severity:** medium · high when combined with missing owner.
- **Recommended action:** Confirm the database scope is least-privilege; document the dependency; consider a read-only credential.
- **Example alert:** `support-agent (production) accessed database "orders" (postgresql) — 14 spans in the last hour.`

### 3.5 `broad_tool_surface`

- **Description:** An agent's distinct tool count exceeds a threshold.
- **Evidence source:** union of `otel_assets.tools_json` and span-level tool names (the same union `runtime_security_intelligence._AssetAcc.tool_names` computes).
- **Condition:** distinct tool count ≥ threshold.
- **Threshold/window:** default ≥ 5 · high if production and ≥ 8 (matches the existing finding's thresholds).
- **Severity:** medium · high (prod ∧ ≥ 8).
- **Recommended action:** Split the agent or scope its toolset; require review for high-risk tools (maps to Advisor "tool routing skill").
- **Example alert:** `ops-agent has 9 distinct tools (threshold: 5), including shell_exec and github_pr_create, in production.`

### 3.6 `db_to_external_api_same_trace`

- **Description:** One trace shows the agent reading a database *and* calling an external API — a data-egress-shaped pattern.
- **Evidence source:** `otel_spans` grouped by `trace_id`: `db.*` attrs on one span, `url.full`/`http.url`/`server.address` on another (host+path only; query strings are never stored).
- **Condition:** within a single trace_id, at least one db span AND at least one external-API span.
- **Threshold/window:** per-trace pattern; alert on ≥ 1 matching trace per window (default window: since last evaluation).
- **Severity:** high.
- **Recommended action:** Review the trace to confirm the flow is intended; check which domains receive data after database reads.
- **Example alert:** `billing-agent trace 4f9c… read database "customers" and called api.external-vendor.com/v1/upload in the same workflow.`
- **Note:** this is the one template that requires new per-trace correlation in the evaluator — existing modules aggregate per asset, not per trace.

### 3.7 `missing_owner_in_production`

- **Description:** A production agent has no owner/team in the registry.
- **Evidence source:** `asset_registry.owner` / `team` joined to `otel_assets.environment`.
- **Condition:** environment is production AND owner and team are both empty.
- **Threshold/window:** presence-based; per run.
- **Severity:** high (medium outside production).
- **Recommended action:** Claim the asset and assign an owner/team in the Inventory page.
- **Example alert:** `knowledge-bot runs in production with no owner or team assigned.`

### 3.8 `high_token_usage_threshold`

- **Description:** An agent's token consumption exceeds a configured budget-like threshold.
- **Evidence source:** OTel path — `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens` from scrubbed span attributes; Gateway path — `telemetry.prompt_tokens` / `completion_tokens` rows.
- **Condition:** sum(tokens for asset) > threshold within window.
- **Threshold/window:** default 1,000,000 tokens / 24 hours (customer-tuned).
- **Severity:** medium.
- **Recommended action:** Review context size and caching; consider a smaller model for low-risk steps (maps to Advisor "context compression skill"); set a budget rule if cost-driven.
- **Example alert:** `research-agent consumed 2.4M tokens in 24h (threshold: 1M). Top model: claude-sonnet-5.`

---

## 4. Data model proposal (future — no migration now)

All tables follow the existing `app/models.py` conventions: integer PK, `organization_id` FK → `organizations.id` (indexed, non-null), timezone-aware `created_at`/`updated_at`, JSON columns as `*_json` text.

### 4.1 `agent_detection_rules`

- **Purpose:** one row per configured rule instance (template + parameters + scope).
- **Key fields:** `organization_id` · `template` (one of §3, validated) · `name` · `enabled` · `params_json` (threshold, window_minutes, environment filter, asset scope) · `severity_override` · `created_by_user_id` · `updated_by_user_id` · timestamps.
- **Org isolation:** every query filters `organization_id`; template list is global, rule rows are strictly per-org. Follows the BudgetRule pattern (`app/routes/governance.py` — org-scoped create/list/delete, team-scope checks via `resolve_team_scope`).
- **Audit:** `created_by`/`updated_by` are mandatory; changes to `enabled`/params logged to the security logger (same pattern as role-change logging in `app/routes/auth.py`).

### 4.2 `agent_detection_rule_matches`

- **Purpose:** one row per (rule, asset, window bucket) that crossed its condition — the alert record.
- **Key fields:** `organization_id` · `rule_id` FK · `asset_id`/`asset_key` · `window_start`/`window_end` · `occurrence_count` · `severity` · `title` · `summary` · `evidence_json` (identifiers + counts only, §7) · `status` (`open`/`acknowledged`/`snoozed`/`resolved`) · `first_seen`/`last_seen`.
- **Org isolation:** `organization_id` denormalized onto the match row (not only via rule FK) so list queries never join across orgs — same defensive denormalization as `asset_findings`.
- **Audit:** status transitions record actor + timestamp; matches are never hard-deleted while their rule exists (dismiss ≠ delete), mirroring the finding lifecycle.
- **Dedup:** unique application-level key `(organization_id, rule_id, asset_key, window_start)` maintained by the same aggregate-then-upsert approach as `_upsert_finding` (application-level, not a DB constraint, for parity with existing dedup behavior on nullable columns).

### 4.3 `notification_channels`

- **Purpose:** where alerts go — Slack webhook, generic webhook (extensible to Teams/email later).
- **Key fields:** `organization_id` · `channel_type` (`slack_webhook`/`webhook`) · `name` · `encrypted_target` (webhook URL encrypted with the existing `CREDENTIAL_ENCRYPTION_KEY` Fernet pattern from provider credentials — webhook URLs embed secrets) · `enabled` · `min_severity` · `created_by_user_id` · timestamps.
- **Org isolation:** strictly per-org; the decrypted target is never returned by any API (same never-return-secrets rule as provider keys — only a last-4/host hint).
- **Audit:** create/update/delete logged with actor; a `last_test_at`/`last_test_status` pair records test notifications.

### 4.4 `notification_deliveries`

- **Purpose:** delivery log — one row per attempt to send one match to one channel.
- **Key fields:** `organization_id` · `match_id` FK · `channel_id` FK · `status` (`pending`/`sent`/`failed`/`dead`) · `attempt_count` · `last_attempt_at` · `response_code` · `error_summary` (exception class + HTTP status only — never response bodies).
- **Org isolation:** denormalized `organization_id`; delivery history API filters by it.
- **Audit:** immutable append-style rows; retries update `attempt_count`/`status` but the row itself is the audit trail for "was this alert delivered".

---

## 5. Rule evaluator design

### Batch evaluation (MVP)

The evaluator runs as a post-pass of `POST /intelligence/run` — after capabilities and findings are upserted, exactly where `derive_runtime_security_findings` is orchestrated today (`app/asset_intelligence.py`). It:

1. Loads the org's enabled `agent_detection_rules`.
2. Builds per-asset evidence accumulators — reusing/generalizing the `_AssetAcc` pattern from `app/runtime_security_intelligence.py` (MCP counts, tool errors, tool surface, db/API reach, providers, environment), extended with per-trace grouping (for `db_to_external_api_same_trace`) and token sums.
3. Evaluates each rule's condition against its window.
4. Upserts matches through the shared dedup/occurrence machinery.

### Near-real-time evaluation (future)

A later phase hooks a lightweight evaluator after span ingestion (`/otel/v1/traces`) for the small subset of rules that are presence-based and cheap (e.g. unknown provider in production). Threshold/window rules stay batch — the ingest path must never grow O(rules × spans) work. If ingest-time evaluation is added, it enqueues candidate (rule, asset) pairs for the next batch pass rather than writing matches inline.

### Aggregation windows

Windows are tumbling buckets aligned to the rule's `window_minutes` (e.g. a 10-minute rule buckets spans into `floor(start_time / 10min)`). A match belongs to the bucket where the threshold was crossed. Buckets make idempotency trivial: re-evaluating the same data lands in the same bucket.

### Deduplication, occurrence_count, idempotency

- Dedup key: `(organization_id, rule_id, asset_key, window_start)`.
- Re-running the evaluator over unchanged data creates **zero** new matches — it recomputes `occurrence_count` absolutely (count of qualifying spans/traces in the bucket), the same idempotency contract the findings engine has ("second run creates 0").
- A match's `last_seen` advances when later evaluations still satisfy the condition in a newer bucket only if the rule is configured to *merge consecutive windows*; default is one match per bucket with `occurrence_count`, never one match per span.

### Avoiding alert spam

- **One match per (rule, asset, window)** — the primary anti-spam mechanism, inherited from the findings dedup design that already collapsed "33 duplicate findings" into one row with `×N`.
- **Cooldown:** per (rule, asset), suppress *notifications* (not match rows) for a configurable cooldown (default 60 min) after the first delivery.
- **Max notifications per window:** per channel cap (default 20/hour); overflow recorded as `notification_deliveries.status='suppressed-ratelimit'` variants so nothing is silently dropped without a trace.
- **Snooze:** a match status that suppresses notifications until a timestamp while keeping the row visible.
- Alerts are additive views over matches: suppressing a notification never loses the underlying evidence.

---

## 6. Slack/webhook notification design (future — not in this MVP)

- **Channel config:** `notification_channels` rows (§4.3); Slack incoming-webhook URL or generic HTTPS webhook, encrypted at rest, admin-managed.
- **Delivery:** async worker drains pending deliveries; retry with exponential backoff (e.g. 1m → 5m → 30m, max 5 attempts), then `dead`. Delivery never blocks the evaluator or any request path.
- **Payload (metadata only):**

  ```json
  {
    "rule": "mcp_tool_access_threshold",
    "severity": "high",
    "agent": "support-agent",
    "environment": "production",
    "window": "2026-07-06T10:00Z/10:10Z",
    "occurrence_count": 12,
    "summary": "support-agent invoked MCP tools 12 times in 10 minutes (threshold: 5).",
    "evidence": {"mcp_methods": ["tools/call"], "tool_names": ["jira_search"], "span_count": 12},
    "link": "https://app.observeagents.ai/#rules_alerts"
  }
  ```

- **Redaction/privacy boundary:** the payload builder consumes only `evidence_json`, which is already restricted to §7's allowed list — there is no code path from raw span attributes to a notification body. Webhook URLs (secrets) never appear in payloads, logs, or API responses.
- **Rate limiting:** per-channel cap + per-(rule, asset) cooldown from §5; a channel-level `min_severity` filter.
- **Test notification:** `POST /notification-channels/{id}/test` sends a synthetic payload (clearly marked `"test": true`) and records the result on the channel row — so customers validate the pipe before relying on it.

---

## 7. Privacy boundaries

**Allowed in rule evidence, match rows, and alert payloads:**

- agent name · asset key · environment
- span count · occurrence counts · durations · token counts
- tool names · MCP method names · provider/model names
- sanitized domain + path (scheme+host+path only, exactly as `runtime_security_intelligence._safe_url_parts` stores them)
- error types

**Forbidden — never stored on a match, never sent in an alert:**

- prompts · responses · raw messages
- tool arguments · tool results
- credentials, API keys, tokens
- full URLs with query strings · headers · request bodies

These are the same boundaries enforced at ingestion by `app/otel_privacy.py` (content-bearing keys are scrubbed before storage) and restated in `docs/ai_agent_runtime_security_intelligence.md`. Because the evaluator reads only the already-scrubbed store, the forbidden items are structurally unavailable to it — the boundary holds even if a rule template is misconfigured.

---

## 8. UI proposal (future)

New **Observability-surface** page: **Rules & Alerts** (hidden on the Gateway build via the existing `productSurface` gating; registered through the standard 7-point pattern — `PAGES`/`NAV_GROUPS`/`renderPage` in `dashboard/src/App.jsx`, `app/roles.py` SEED_ROLES, `dashboard/src/auth.jsx` ROLES).

Sections:

1. **Rule templates** — the §3 catalog with descriptions and defaults; "Enable" instantiates a rule.
2. **Active rules** — the org's configured rules: template, scope, threshold/window, severity, enabled toggle, last evaluation.
3. **Recent matches** — the alert feed: severity, agent, rule, window, `×N` occurrence badge (same visual as findings), status actions (acknowledge / snooze / resolve).
4. **Notification channels** — Slack/webhook channels with masked targets, min-severity, and a "Send test" button.
5. **Alert delivery history** — `notification_deliveries` view: what was sent where, retries, failures.

**No enforcement controls anywhere in this MVP** — no block toggles, no policy editors. The only actions are informational (acknowledge/snooze/resolve/test).

---

## 9. Roadmap

| Phase | Deliverable |
|---|---|
| **R1** | This design document |
| **R2** | Backend **fixed** rule evaluator — the §3 templates with hardcoded defaults, evaluated after `/intelligence/run`, matches stored + visible via API. No config UI yet |
| **R3** | Configurable rules — `agent_detection_rules` CRUD (thresholds, windows, scopes), template validation |
| **R4** | Slack/webhook notifications — channels, deliveries, retries, test endpoint |
| **R5** | Alert hygiene — dedup hardening, per-channel rate limits, cooldowns, snooze |
| **R6** | Advisor integration — rule matches feed O8 skill-gap recommendations (`repeated_tool_errors` → tool-fallback skill, etc.) |
| **R7** | Optional Gateway policy **export** — a match can generate a *recommended* gateway policy a human may apply; rules themselves never enforce |

Roadmap placement: R1–R5 realize roadmap phase **O4 (Monitors & notifications)**; R6 connects into **O8 (Observe Advisor)**; R7 respects the product split — *Observability discovers and recommends; Gateway controls only when explicitly configured.*

---

## 10. Acceptance criteria for the future MVP

- **Org-scoped:** every rule, match, channel, and delivery row carries `organization_id`; no cross-org read path exists.
- **No raw content:** alert payloads and `evidence_json` contain only §7-allowed fields; a privacy test asserts forbidden keys never appear (same negative-test pattern as `tests/test_runtime_security_intelligence.py::test_evidence_never_contains_raw_content`).
- **No enforcement:** no code path from a rule match to blocking, policy mutation, or gateway behavior change.
- **No alert spam:** one match per (rule, asset, window); notification cooldowns and channel caps enforced.
- **Deduped matches:** re-running the evaluator on unchanged data creates zero new matches (idempotency test).
- **Testable evaluator:** the evaluator is a pure function of (rules, evidence, window) → matches, unit-testable without HTTP.
- **Slack/webhook optional:** the feature is fully usable in-app with zero channels configured.
- **Existing evidence only:** the MVP requires no new ingestion, no new span attributes, and no schema change to evidence tables — it reads what the platform already stores.
