# Telemetry Ingestion — Batch API, Queue, Risk Scoring, Metrics, Timeline

The telemetry ingestion layer turns AI-agent activity into **operational
evidence**: every event an agent emits becomes something a user can search,
measure, investigate, and control. This document covers the MVP ingestion
pipeline shipped alongside the existing OTLP (`POST /otel/v1/traces`) and SDK
(`POST /runtime-events`) routes — both of which are unchanged.

## Architecture

```
Client / SDK / OTEL input
        │
        ▼
POST /api/v1/telemetry/batch        ── validate, dedup, preserve raw, 202 fast
        │
        ▼
telemetry_events_raw                ── DB-backed queue + immutable raw archive
        │                              (status: pending → processing → processed|failed)
        ▼
Background worker                   ── in-process daemon thread (app/telemetry_ingest/worker.py)
        │                              normalization → risk scoring → storage → aggregation
        ▼
telemetry_events                    ── normalized product events (dashboards, search, timeline)
        │
        ├──► Risk processor         ── risk_score / risk_reasons / policy_action per event
        ├──► agent_metrics_daily    ── precomputed per-agent daily rollups
        └──► Agent Timeline UI      ── GET /agents/{id}/timeline
```

The API route does **no heavy processing** — it validates, deduplicates,
stores the raw payload, and returns. Normalization, risk evaluation, and
metrics aggregation all happen in the worker, so ingest latency stays flat as
processing grows richer.

### Components

| Piece | File |
|---|---|
| Batch endpoint | `app/routes/telemetry_v1.py` |
| Request/response schemas | `app/telemetry_ingest/schemas.py` |
| Queue worker | `app/telemetry_ingest/worker.py` |
| Normalizer | `app/telemetry_ingest/normalizer.py` |
| Risk processor | `app/risk_processor.py` |
| Metrics rollups | `app/telemetry_ingest/metrics.py` |
| Timeline + metrics read API | `app/routes/agent_timeline.py` |
| Tables | `TelemetryEventRaw`, `TelemetryEvent`, `AgentMetricsDaily` in `app/models.py` |
| UI | `dashboard/src/pages/AgentTimeline.jsx` |

## Raw vs normalized telemetry

**Raw** (`telemetry_events_raw.raw_payload`) is the submitted event JSON,
byte-for-byte, including any extra fields the product schema doesn't know
about. It is never mutated and exists for investigation — when a risk score or
a dashboard number looks wrong, the original evidence is always available.

**Normalized** (`telemetry_events`) is the product schema: typed columns the
platform can index, filter, aggregate, and rule over. Dashboards, the
timeline, risk rules, and metrics only ever read normalized data.

> Privacy note: unlike the OTel path (which stores content hashes only), this
> endpoint stores whatever you send in `raw_payload`. Don't send prompts or
> PII you don't want at rest; send metadata about the activity.

### Normalized event schema

| Field | Type | Notes |
|---|---|---|
| `event_id` | string ≤64 | **required** — client-generated idempotency key |
| `agent_id` | string ≤256 | **required** — stable agent identity |
| `timestamp` | ISO8601 | defaults to server receive time |
| `event_type` | string | `llm_call` (default), `tool_call`, `agent_step`, `retrieval`, … |
| `agent_name`, `team`, `environment`, `owner` | string | governance metadata; backfilled from the Asset Registry when omitted |
| `trace_id`, `span_id`, `parent_span_id` | string | OTEL-compatible correlation ids |
| `provider`, `model` | string | e.g. `openai` / `gpt-4o` |
| `input_tokens`, `output_tokens`, `total_tokens` | int ≥0 | `total` computed if omitted |
| `cost_usd` | float ≥0 | computed from the pricing registry if omitted (`cost_estimated=true`) |
| `latency_ms` | float ≥0 | |
| `status` | `ok` \| `error` \| `blocked` | |
| `error_message` | string ≤512 | |
| `tool_name`, `action_name` | string | |
| `attributes` | object | OTEL-style free-form attributes (kept in raw payload) |
| `risk_score`, `risk_reasons`, `policy_action` | — | **server-computed**, never client-supplied |

Agents seen by this endpoint are upserted into the existing **Asset Registry**
using the same `asset_key = sha256(org_id:agent_id)` convention as OTel
ingestion, so batch-ingested agents appear in the Agent Inventory alongside
OTel-discovered ones — one inventory, two evidence sources.

## Batch endpoint

```
POST /api/v1/telemetry/batch
Authorization: Bearer <JWT>  or  Bearer gk-<api-key>
```

Accepts `{"events": [ ... ]}` or a bare JSON array. Max **1,000 events** per
request (413 above that). `org_id` always comes from the credential — never
from the body.

```bash
curl -X POST https://<host>/api/v1/telemetry/batch \
  -H "Authorization: Bearer gk-YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "events": [
      {
        "event_id": "2f1c9a...-unique",
        "agent_id": "billing-agent",
        "agent_name": "Billing Agent",
        "team": "payments",
        "owner": "dana@acme.com",
        "environment": "production",
        "event_type": "llm_call",
        "provider": "openai",
        "model": "gpt-4o",
        "input_tokens": 1200,
        "output_tokens": 300,
        "latency_ms": 900,
        "status": "ok",
        "timestamp": "2026-07-15T10:00:00Z"
      }
    ]
  }'
```

Response (`202 Accepted`):

```json
{ "accepted": 1, "duplicated": 0, "failed": 0, "errors": [], "queued": true }
```

**Partial acceptance:** one bad event never fails the batch. Invalid events
are reported per-index in `errors` (`{index, event_id, error}`) and everything
else is accepted.

## Idempotency and deduplication

`event_id` is the deduplication key, unique per organization
(`UNIQUE (organization_id, event_id)` on both the raw and normalized tables).

- The same `event_id` sent twice — in one batch or across batches — is stored
  once and reported in the `duplicated` count.
- Retrying a whole batch after a network failure is safe: replays are pure
  dedup no-ops.
- The same `event_id` in two different orgs is two distinct events.

## Queue and worker semantics

The queue is the database itself — no Kafka, Redis, or external broker at this
stage (see the roadmap below for when that changes).

- **At-least-once processing.** Rows are claimed (`pending → processing`),
  processed, then marked `processed`. A crash mid-batch leaves rows in
  `processing`; after 5 minutes they are recovered back to `pending` and
  retried. The unique constraint on `telemetry_events` makes re-processing a
  no-op, so replays never duplicate data.
- **Retries.** A failing event is retried up to 3 times, then marked `failed`
  with the error preserved on the row.
- **Wake-on-ingest.** The API signals the worker after each accepted batch, so
  processing typically starts within milliseconds; a 2s poll interval is the
  fallback.

Env switches:

| Variable | Effect |
|---|---|
| `TELEMETRY_WORKER_ENABLED=false` | never start the worker thread |
| `TELEMETRY_WORKER_MODE=inline` | no thread; the API drains the queue synchronously after each batch (used by tests) |

## Risk processing

`app/risk_processor.py` evaluates every normalized event and produces
`risk_score` (0–100), `risk_reasons` (human-readable strings), and
`policy_action` (`allow` / `warn` / `block`). This is the seed of the future
Detection Rule Zone — rules are a flat, ordered list of small functions.

| Rule | Default | Weight |
|---|---|---|
| Event reported an error | `status == error` | +25 |
| Upstream policy block | `status == blocked` or payload `policy_action == block` | floor 80, block |
| No owner | — | +10 |
| No team | — | +10 |
| Unknown environment | not prod/staging/dev (+aliases) | +15 (missing: +10) |
| Unknown provider | not a known provider | +10 |
| Unknown model | not in the pricing registry | +15 |
| High cost | > $1.00/event | +20 |
| High latency | > 30,000 ms | +15 |
| Risky tool | `shell`, `exec`, `eval`, `code_interpreter`, … | +25 |
| Non-approved model in production | existing `PolicyRule` engine (`app/policy.py`) | +30, block |

`policy_action` is `block` when a blocking rule fired, `warn` when the score
reaches 50, otherwise `allow`.

Per-org overrides live in the `risk_thresholds` OrgConfig key (merged over the
defaults):

```json
{ "cost_usd_threshold": 5.0, "latency_ms_threshold": 60000,
  "warn_score": 40, "risky_tools": ["shell", "prod_db_write"] }
```

## Metrics aggregation

`agent_metrics_daily` holds one row per `(org, agent, UTC day)`: event/error/
blocked counts, policy violations, high-risk events, token totals, cost,
avg/max latency, avg/max risk score, and a per-model usage breakdown
(`models_json`). Dashboards read rollups instead of scanning raw events.

Rollups are **recomputed absolutely** from `telemetry_events` for every bucket
a worker batch touches — never incremented — so they stay exactly correct
under at-least-once reprocessing.

`GET /telemetry/metrics/daily?days=7&group_by=agent|team` serves org-wide
views: top risky agents (`group_by=agent`, sorted by risk) and policy
violations/spend per team (`group_by=team`).

## Agent Timeline

`GET /agents/{agent_id}/timeline?days=7&limit=50` answers: *what did this
agent do, when, with which model or tool, at what cost and latency, and was
any of it risky?* `agent_id` accepts the raw agent identity or its
`asset_key`, matching the existing inventory API. Filters: `event_type`,
`status`, `min_risk`; keyset pagination via `cursor`/`next_cursor`.

The response contains the agent's registry record, a summary computed from the
daily rollups (events, errors, cost, latency, high-risk count, model mix,
last seen), and the event feed with per-event risk level and reasons.

The UI lives in the **Runtime** page's **Agent events** view
(`dashboard/src/pages/AgentTimeline.jsx`, embedded in RuntimeTimelineV2) and
is also reachable from any Agent Inventory row via its **Timeline** action or
from any risk finding in Rules & Alerts.

## Risk Findings v1

Risk Findings turn the per-event `risk_score` / `risk_reasons` / `policy_action`
columns into a product experience: a filterable feed that answers *which
AI-agent events require attention and why*. A finding is any normalized
telemetry event the ingest-time risk processor flagged (`risk_score > 0` or
reasons present) — no new tables, no re-scoring, pure read layer
(`app/routes/risk_findings.py`):

- `GET /risk-findings` — event-level findings, newest first, keyset-paginated.
  Filters: `days`, `min_risk`, `risk_level`, `policy_action`, `agent_id`,
  `team`, `environment`, `event_type`, `status`, `model`, `provider`.
  Each finding carries the full event context, `risk_level`, `primary_reason`,
  a safely derived `rule_id`/`rule_name` (mapped from the stable reason
  phrasing via `risk_processor.RULE_CATALOG` — never guessed), and
  `timeline_agent_id`/`timeline_url` linking straight to the Agent Timeline.
- `GET /risk-findings/summary` — totals, high-risk/blocked/warning counts,
  top risky agents, most common reasons, findings by team, findings by day.
- `GET /risk-findings/rules` — the real-time rule catalog with each org's
  effective thresholds.

**Where it lives in the UI:** the **Rules & Alerts** page (deliberately — not
a new page). The page now shows both rule populations and their matches:
real-time risk rules (evaluated at ingestion by the worker) with the
**Recent findings** feed they produce, and the batch detection-rule templates
with their intelligence-run matches. Every finding explains which rule fired,
for which agent, why, at what severity, and links to that agent's timeline.

**Why this is not a SIEM:** findings are AI-agent-shaped operational evidence
— model calls, tools, cost, ownership, policy — not a generic event/log
correlation console. There is no query language, no raw log retention story,
and nothing enforces from this view; it explains risk and routes the user to
the timeline (investigate) or Gateway Control Center (control).

**Path to the Detection Rule Zone:** today's rules are fixed functions with
org-configurable thresholds (`risk_thresholds`). The rule catalog + findings
feed established here become the read surface for configurable rules: the
rule builder will write rule definitions, the worker will evaluate them at
ingestion, and matches will land in this same feed with their `rule_id`.

### Admin-managed detection rules (v1)

Admins can tune the real-time rules from the Rules & Alerts page; the
`detection_rules` table (migration `c0d1e2f3a4b5`) stores per-org state:

- **Built-in rules** exist implicitly with their defaults — no rows are
  seeded. Editing one (enable/disable, severity, threshold) creates a
  per-org override row keyed by the rule's `rule_key`. Built-ins can be
  disabled but never deleted, so defaults are always restorable.
- **Custom rules** are created only from approved templates
  (`app/detection_rule_templates.py`): cost / latency / token-usage
  thresholds, watched environments, watched providers/models, watched
  tools. Each template validates typed, bounded parameters in
  `config_json`. **Rules never carry code** — no DSL, no eval, no arbitrary
  logic — so rule management can't become an execution vector, and the
  product stays an evidence platform rather than a SIEM rule engine.
- **Severity** (low/medium/high) maps to score weight (+10/+15/+25).
- **Authorization is enforced in the backend**: `GET /detection-rules` and
  `GET /detection-rules/templates` are readable by any authenticated user;
  `POST`/`PATCH`/`DELETE` require the admin role (`require_admin`), with
  org isolation on every query. The frontend hides controls for non-admins
  ("Only admins can manage detection rules") but the API is the real gate.
- **Rule changes affect future findings only.** The worker snapshots the
  org's rules per processing batch; already-scored events are never
  retroactively re-scored, so historical findings remain stable evidence.
  Orgs that never touch rule management get exactly the default behavior.

## Risk Findings v1

Risk Findings turn the per-event `risk_score` / `risk_reasons` / `policy_action`
columns into a product experience: a filterable feed that answers *which
AI-agent events require attention and why*. A finding is any normalized
telemetry event the ingest-time risk processor flagged (`risk_score > 0` or
reasons present) — no new tables, no re-scoring, pure read layer
(`app/routes/risk_findings.py`):

- `GET /risk-findings` — event-level findings, newest first, keyset-paginated.
  Filters: `days`, `min_risk`, `risk_level`, `policy_action`, `agent_id`,
  `team`, `environment`, `event_type`, `status`, `model`, `provider`.
  Each finding carries the full event context, `risk_level`, `primary_reason`,
  a safely derived `rule_id`/`rule_name` (mapped from the stable reason
  phrasing via `risk_processor.RULE_CATALOG` — never guessed), and
  `timeline_agent_id`/`timeline_url` linking straight to the Agent Timeline.
- `GET /risk-findings/summary` — totals, high-risk/blocked/warning counts,
  top risky agents, most common reasons, findings by team, findings by day.
- `GET /risk-findings/rules` — the real-time rule catalog with each org's
  effective thresholds.

**Where it lives in the UI:** the **Rules & Alerts** page (deliberately — not
a new page). The page now shows both rule populations and their matches:
real-time risk rules (evaluated at ingestion by the worker) with the
**Recent findings** feed they produce, and the batch detection-rule templates
with their intelligence-run matches. Every finding explains which rule fired,
for which agent, why, at what severity, and links to that agent's timeline.

**Why this is not a SIEM:** findings are AI-agent-shaped operational evidence
— model calls, tools, cost, ownership, policy — not a generic event/log
correlation console. There is no query language, no raw log retention story,
and nothing enforces from this view; it explains risk and routes the user to
the timeline (investigate) or Gateway Control Center (control).

**Path to the Detection Rule Zone:** today's rules are fixed functions with
org-configurable thresholds (`risk_thresholds`). The rule catalog + findings
feed established here become the read surface for configurable rules: the
rule builder will write rule definitions, the worker will evaluate them at
ingestion, and matches will land in this same feed with their `rule_id`.

## OpenTelemetry compatibility

`trace_id` / `span_id` / `parent_span_id` and free-form `attributes` are
first-class fields, so events emitted from OTel-instrumented apps correlate
with spans ingested through `/otel/v1/traces`. OTel remains an ingestion
*source*; the normalized event schema above is the product model.

## Scaling roadmap

**Current MVP:** HTTP batch ingestion → DB queue/worker → SQLite/Postgres →
risk rules → precomputed metrics → timeline.

**Future scale path (in order, each step preserves the API contract):**

1. Postgres + `FOR UPDATE SKIP LOCKED` claims → multiple worker processes.
2. OTel collector support feeding the same normalized schema.
3. External queue (NATS / Redpanda / Kafka) replacing the DB queue when
   ingest volume outgrows it.
4. Columnar analytics store (ClickHouse / TimescaleDB) for events; Postgres
   keeps the governance layer.
5. SIEM export, customer-side collector, and the full Detection Rule Zone /
   advanced policy engine on top of the risk processor.
