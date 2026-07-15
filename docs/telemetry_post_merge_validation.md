# Telemetry Ingestion MVP — Post-Merge Stabilization Validation (PR #143)

Status: **validated** — merged to `main` as `219c6bf` (PR
[#143](https://github.com/ronhaviv33-beep/ObserveAgents.ai/pull/143)).
This document is the post-merge checklist for operators and reviewers: what
shipped, what deployment/migration must (and must not) do, the commands that
prove the pipeline is healthy, and a manual smoke test that exercises it
end-to-end. Companion design doc: [telemetry_ingestion.md](telemetry_ingestion.md).

---

## 1. What was merged

| Piece | Where | Behavior |
|---|---|---|
| Batch ingestion API | `POST /api/v1/telemetry/batch` (`app/routes/telemetry_v1.py`) | Up to 1,000 events/request; per-event validation with partial acceptance (one bad event never fails the batch); 202 with `{accepted, duplicated, failed, errors[]}`; auth via JWT or `gk-` API key; org resolved server-side only |
| Raw event preservation | `telemetry_events_raw.raw_payload` | The submitted event JSON is stored byte-for-byte, including unknown extra fields, and never mutated — investigation evidence |
| Deduplication | unique `(organization_id, event_id)` on both new event tables | Intra-batch, cross-batch, and replay-after-processing duplicates are detected and reported in the `duplicated` count; the same `event_id` in two orgs is two distinct events |
| DB queue | `telemetry_events_raw.status` (`pending → processing → processed \| failed`) | The raw table doubles as the work queue — no external broker |
| In-process worker | `app/telemetry_ingest/worker.py` | Daemon thread (same pattern as the pricing-registry sync); wake-on-ingest + 2s poll; at-least-once with idempotent processing; 3 retries then `failed`; stale claims recovered after 5 minutes |
| Risk scoring | `app/risk_processor.py` | 11 readable rules → `risk_score` 0–100, `risk_reasons[]`, `policy_action` allow/warn/block; per-org overrides via the `risk_thresholds` OrgConfig key |
| Daily rollups | `agent_metrics_daily` (`app/telemetry_ingest/metrics.py`) | One row per (org, agent, UTC day), recomputed absolutely on write — replays can never double-count |
| Timeline APIs | `GET /agents/{agent_id}/timeline`, `GET /telemetry/metrics/daily` (`app/routes/agent_timeline.py`) | Rollup-backed summary + keyset-paginated event feed; org-wide top-risky-agents / per-team violations views |
| Agent Timeline UI | `dashboard/src/pages/AgentTimeline.jsx` | Observe → Agent Timeline nav entry; also reachable from Agent Inventory row "Timeline" actions; shows timestamp, event type, model/provider, tool/action, latency, cost, status, risk badge, and a one-line explanation |
| Role visibility backfill | `app/roles.py`, `dashboard/src/auth.jsx` | `agent_timeline` added to all seeded role page lists; the role seeder backfills existing orgs on boot (bug found during pre-merge validation, fixed in `4e775b5`) |

Existing `/otel/v1/traces` and `/runtime-events` ingestion routes are
**unchanged** (their suites pass unchanged — see §4).

## 2. Deployment checklist

- [x] **No new Render service** — `render.yaml` untouched; the web service is the only backend process.
- [x] **No new queue infrastructure** — no Kafka/Redpanda/NATS/Redis; the database is the queue.
- [x] **Worker runs in-process** — a daemon thread inside the web process, started from `app/startup.py:start_telemetry_worker()` during boot.
- [x] **Kill switch** — `TELEMETRY_WORKER_ENABLED=false` prevents the worker thread from starting (queue rows accumulate as `pending` until re-enabled).
- [x] **Test/debug mode** — `TELEMETRY_WORKER_MODE=inline` skips the thread and drains the queue synchronously inside the API request; used by the test suite, not for production.
- [x] **Existing `gk-` API keys work** — the batch endpoint authenticates exactly like `/otel/v1/traces` and `/runtime-events`; no new credential type.
- [x] **No new frontend env vars** — the dashboard needs only its normal `npm run build`.

## 3. Migration checklist

- [x] **Migration exists** — `alembic/versions/b9c0d1e2f3a4_add_telemetry_ingestion_tables.py`, `down_revision='a8b9c0d1e2f3'`, single Alembic head.
- [x] **Creates exactly three tables** — `telemetry_events_raw`, `telemetry_events`, `agent_metrics_daily`, each with `organization_id` FK and the unique constraints above.
- [x] **No existing tables modified** — the migration only creates; `ensure_model_columns()` has nothing to alter.
- [x] **Startup applies it automatically** — the standard boot flow (`create_all` → `ensure_model_columns` → `alembic upgrade head`) builds the tables on fresh DBs and migrates existing ones; the migration is guarded with `inspector.has_table()` per repo convention, so both paths are safe. Zero downtime, no manual step.
- [x] **Role seeder backfills visibility** — `seed_roles()` runs on every boot and updates any role whose page set differs from the seed, so `agent_timeline` appears for existing orgs' admin/analyst/viewer roles on the first post-deploy boot.

## 4. Validation commands

Run from the repo root. Results below are from the post-merge run on
`main @ 219c6bf` (2026-07-15).

```bash
# Telemetry ingestion suites
python -m pytest tests/test_telemetry_batch_ingestion.py -q   # 7 passed
python -m pytest tests/test_telemetry_dedup.py -q             # 4 passed
python -m pytest tests/test_telemetry_worker.py -q            # 5 passed
python -m pytest tests/test_risk_processor.py -q              # 15 passed
python -m pytest tests/test_agent_metrics_daily.py -q         # 4 passed
python -m pytest tests/test_agent_timeline_api.py -q          # 6 passed
python -m pytest tests/test_telemetry_batch_load.py -q        # 1 passed (1,000-event batch)

# Existing ingestion routes (regression guard)
python -m pytest tests/test_runtime_events.py -q              # 9 passed
python -m pytest tests/test_otel_ingestion.py -q              # 17 passed

# Isolation/structural harnesses
make verify                                                   # === All harnesses passed ===

# Frontend build
npm --prefix dashboard run build                              # ✓ built (pre-existing chunk-size warning only)
```

All 42 telemetry tests, both legacy-route suites, the `make verify`
harnesses, and the dashboard build pass.

## 5. Manual smoke test

Prerequisites: a running backend, one org with a dashboard user, and an
active `gk-` API key (Settings → API Keys). `$GK` is the key, `$HOST` the
backend origin.

**1. Post a sample batch — expect `accepted`:**

```bash
curl -s -X POST $HOST/api/v1/telemetry/batch \
  -H "Authorization: Bearer $GK" -H "Content-Type: application/json" \
  -d '{"events":[{"event_id":"smoke-1","agent_id":"smoke-agent","agent_name":"Smoke Agent",
       "team":"qa","owner":"qa@example.com","environment":"production",
       "provider":"openai","model":"gpt-4o","input_tokens":100,"output_tokens":20,
       "latency_ms":800,"status":"ok"}]}'
# → {"accepted":1,"duplicated":0,"failed":0,"errors":[],"queued":true}   HTTP 202
```

**2. Re-post the same `event_id` — expect `duplicated`:**

```bash
# (same command again)
# → {"accepted":0,"duplicated":1,"failed":0,"errors":[],"queued":false}
```

**3. Verify the raw row exists and the worker processed it** (the worker
wakes on ingest; allow a couple of seconds):

```sql
SELECT event_id, status, attempts FROM telemetry_events_raw WHERE event_id = 'smoke-1';
-- smoke-1 | processed | 1     (raw_payload holds the submitted JSON verbatim)
```

**4. Verify the normalized event row exists:**

```sql
SELECT agent_id, model, cost_usd, risk_score, policy_action
FROM telemetry_events WHERE event_id = 'smoke-1';
-- smoke-agent | gpt-4o | 0.00045 (cost_estimated=1) | 0 | allow
```

**5. Verify the daily metric rollup exists:**

```sql
SELECT events_count, total_cost_usd, models_json FROM agent_metrics_daily
WHERE agent_id = 'smoke-agent';
-- 1 | 0.00045 | {"gpt-4o": {"events": 1, ...}}
```

Or via the API: `GET /telemetry/metrics/daily?days=7&group_by=agent` (JWT
auth) should list `smoke-agent`.

**6. Verify the Agent Timeline shows the event:** log into the dashboard →
**Observe → Agent Timeline** (or Agents → row → **Timeline**), select
"Smoke Agent". The summary cards show 1 event with its cost, and the
activity rail shows the event with timestamp, `LLM` pill, `gpt-4o via
openai`, token/latency/cost chips, and an `ok` status dot.
API equivalent: `GET /agents/smoke-agent/timeline?days=7`.

This exact flow was executed during pre-merge validation against a live
server with the real worker thread (not inline mode), including the browser
steps, with zero page errors.

## 6. Known follow-ups (all non-blockers)

- **Raw-event retention** — no pruning policy yet for `processed` rows in
  `telemetry_events_raw`; add a periodic cleanup before ingest volume grows.
- **Raw-payload redaction mode** — the batch endpoint stores payloads as
  sent (documented); consider an org-level redaction option mirroring the
  OTel hash-only contract.
- **Multi-worker scaling** — single in-process worker is sufficient today;
  next step is Postgres `FOR UPDATE SKIP LOCKED` claims for multiple
  workers, then an external queue only when volume demands it.
- **Risk weight tuning** — rule weights and the warn threshold (50) are
  sensible defaults; revisit with real customer telemetry as the Detection
  Rule Zone takes shape.
- **Self-host Google Fonts** — `dashboard/index.html` loads fonts from the
  Google CDN, which fails (console error) in network-restricted
  environments; bundling the fonts removes the external dependency.
  Pre-existing, unrelated to PR #143.
