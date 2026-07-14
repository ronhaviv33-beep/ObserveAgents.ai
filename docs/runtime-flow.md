# Runtime Processing and Intelligence Flow

**What happens to evidence after an ingestion module's `parse()` returns `RuntimeSpan[]`.** This doc walks the Runtime pipeline end to end — normalization, intelligence derivation, and the read surfaces built on top. It complements [architecture.md](architecture.md), which describes the platform-wide spine.

---

## 1. Overview: the Ingestion / Runtime boundary

The pipeline has exactly one seam. **Ingestion** answers "what happened?": each evidence integration is one module in `app/ingestion/` exposing `parse(payload) -> list[RuntimeSpan]` (`RuntimeSpan` is a `TypedDict` in `app/ingestion/__init__.py` — the flat span shape with `trace_id`, `span_id`, `attributes`, `resource_attributes`, timing, status; attribute keys use OTel GenAI SemConv). **Runtime** answers "what does it mean?": `app/otel_normalizer.py:normalize_spans(db, org_id, spans, api_key_id)` is the single entry point, and nothing downstream of it contains integration-specific parsing. Runtime never knows the source.

```
POST /otel/v1/traces ──▶ app/ingestion/otel.py:parse_otlp ──┐
(app/routes/otel.py)     (OTLP JSON + protobuf, gzip)       │
                                                            ├─▶ RuntimeSpan[]
POST /runtime-events ──▶ app/ingestion/sdk.py:parse ────────┘        │
(app/routes/runtime_events.py)                                       ▼
                                        STAGE 1  app/otel_normalizer.py:normalize_spans
                                                 otel_spans · provenance_events ·
                                                 agent_relationships · asset_registry ·
                                                 otel_assets
                                                                     │
                                        STAGE 2  POST /intelligence/run
                                                 app/asset_intelligence.py:
                                                 derive_asset_intelligence
                                                 asset_capabilities · asset_findings
                                                                     │
                                        STAGE 3  READ SURFACES
                                                 /runtime/* · /intelligence/* ·
                                                 /agents · /assets · /relationships
```

Adding an integration (LangGraph, MCP, …) means one new `app/ingestion/<name>.py` with one `parse` function, plus a route that authenticates (`get_proxy_caller`: JWT or `gk-` API key), parses, and calls `normalize_spans` — nothing in stages 1–3 changes.

---

## 2. Stage 1 — Normalization (`normalize_spans`)

Runs synchronously inside the ingest request; returns counts (`spans_ingested`, `assets_created_or_updated`, `relationships_upserted`, `provenance_events`, `otel_assets_upserted`) that the route echoes in its 202 response. Steps, in order:

**Attribute mapping.** Org-defined custom→canonical aliases (`app/otel_attribute_mapping.py`) are loaded once per request and applied to the batch in place before anything else. Native canonical keys are never overwritten; signals resolved through mapped keys are later downgraded to medium confidence.

**Identity resolution.** A pass-0 sweep (`resolve_trace_identities`) picks the best identity per trace, then `resolve_span_identity` upgrades each span to it. Three tiers, ranked declared > service > fallback:

| Tier | Source | Effect |
|---|---|---|
| `declared` | `gen_ai.agent.id` → `gen_ai.agent.name` → `agent.name` / `ai.agent.name` | full attribution; registry confidence 75 |
| `service` | `service.name` resource attribute | inferred identity |
| `fallback` | stable hash of non-volatile resource attributes (`observed-ai-system:<hash>`), else trace-scoped | `evidence.needs_admin_review=true`, confidence 30 |

Child spans inherit the trace's best identity (SemConv agent traces declare `gen_ai.agent.*` only on the root `invoke_agent` span), so one trace never fragments into multiple assets. Volatile keys (pod name, instance id, SDK version, …) are excluded from the fallback hash so unidentified replicas converge to one asset.

**Classification and confidence.** `app/telemetry_classification.py:classify_span` — a pure module, key names only, never content values — grades each span: `fully_classified` / `partially_classified` / `unclassified` (identity unresolvable) with confidence `high` (all signals from standard SemConv keys) / `medium` (fallback-variant or org-mapped keys, or missing environment) / `low` (no identity, GenAI span without a model, MCP span without a server). Missing-signal codes and candidate custom keys (names that look mappable) are recorded for the telemetry-quality surface.

**Privacy scrub.** `app/otel_privacy.py:scrub_attributes` replaces every content-bearing key (`gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`, `tool.arguments`, `tool.result`, legacy OpenLLMetry variants, …) with `{redacted, sha256, size_bytes}` before storage. A combined SHA-256 content hash is kept for provenance. Raw content never reaches disk (architecture invariant #2).

**Persist `OtelSpan` + `ProvenanceEvent`.** One `OtelSpan` row per span, deduplicated on (org, `trace_id`, `span_id`) — duplicates are silently skipped. Safe scalar GenAI metadata (`extract_genai_scalar_fields`: operation, provider, models, token usage, finish reasons, streaming, TTFC) is denormalized into indexed `gen_ai_*` columns, and the span's classification status/confidence/missing list is stored alongside. Each meaningful span also writes a `ProvenanceEvent` (`llm_call`, `tool_call`, `agent_invocation`, `workflow_step`, `db_call`, `external_api_call`, `agent_step`, …) with `content_redacted=True`.

**Relationship upsert.** Branch order matters — `execute_tool` spans carry `gen_ai.*` keys but are routed to the tool branch first:

- GenAI spans → `uses_model` / `uses_provider` edges (confidence 0.90) with token-usage metadata
- Tool/MCP spans → `uses_tool` (0.85), `connects_to` MCP server (0.85), `reads_resource` MCP resource (0.80)
- Otherwise → `reads_from` database (0.80), `calls` external API (0.75), `invokes_workflow` (0.80)

Each edge goes through `app/relationships.py:upsert_relationship` (request_count / last_seen / confidence accumulation).

**Registry + evidence upsert.** Per new identity, `_upsert_asset` writes an `AssetRegistry` row (`discovery_status="potential"`, `discovery_source="otel_trace"`, `asset_key = sha256(org:identity)[:64]`) — the canonical inventory; humans promote to verified by claiming in the UI. Per batch, `upsert_otel_asset` writes one `OtelAsset` evidence row per (org, service, environment): merged models/providers/tools/dependencies arrays, trace/span counts, first/last seen, and the classification rollup — `merge_classification_counts` weights spans (full 1.0 / partial 0.6 / unclassified 0.2) into the asset's `classification_status` and `confidence_score`. `otel_assets.ai_asset_id` links back to the registry row.

### Pipeline properties

- **Fail-open per span.** Each `OtelSpan` / `ProvenanceEvent` persist is individually committed and exception-guarded; a failure rolls back, logs a warning, and skips that span — it never fails the batch or the request.
- **Idempotent ingest.** Re-posting the same payload skips duplicate spans (org + trace + span key) and merges evidence arrays; `OtelAsset` lookups use application-level dedup with nullable-aware environment matching (SQLite treats `NULL != NULL` in unique indexes).
- **Monotonic rollups.** Classification counters and first/last-seen windows only ever grow/widen, so batch order never changes the result.
- **Retroactive repair.** `POST /intelligence/reclassify` (admin) re-runs classification and GenAI scalar extraction over stored spans via `app/otel_reprocess.py` — sharing `resolve_trace_identities` with ingestion so identity-tier tie-breaking never drifts. Stored raw attributes are never modified.

---

## 3. Stage 2 — Intelligence derivation (`derive_asset_intelligence`)

`app/asset_intelligence.py:derive_asset_intelligence(db, org_id)`, run via `POST /intelligence/run` (also by the demo seed). Deliberately **not** part of the ingest path — `/otel/v1/traces` stays accept-and-store only. Reads `otel_assets`, `otel_spans`, `asset_registry`; writes `asset_capabilities` and `asset_findings`. Idempotent.

**Capabilities.** Per `OtelAsset`: providers and models become typed capabilities directly; tools and dependencies are keyword-classified by `_classify_capability` (mcp, database, filesystem, shell, messaging, source_control, crm, retrieval, memory, external_api, unknown); production environments add `runtime:production`. A span scan adds SemConv-derived capabilities (MCP tools/resources, `gen_ai.workflow.name`, prompts, data sources) — scalar metadata only.

**Findings** — four derivation passes, all funneled through the same `_upsert_finding` machinery:

1. **Asset intelligence** (`source="otel_trace"`): capability-based rules (`shell_enabled`, `database_access`, `sensitive_system_access`, `broad_tool_access`, `production_runtime`, `new_ai_system_detected`, …) plus span-based performance/operations rules (`slow_llm_call` ≥ 10 s, `slow_tool_call`/`slow_runtime_step` ≥ 5 s, `high_token_usage` ≥ 100k tokens, `provider_error`/`tool_error`/`mcp_error`/`runtime_error`). A `telemetry_quality_incomplete` finding (`source="telemetry_quality"`) flags materially degraded assets with a fix-list. Full catalog: [asset_intelligence.md](asset_intelligence.md).
2. **Runtime security** (`app/runtime_security_intelligence.py`, `source="runtime_security"`): agent-specific, environment-aware findings (`agent_has_database_access`, `agent_uses_mcp_tool_in_production`, `agent_has_broad_tool_surface`, `human_review_recommended`, …). Spec: [ai_agent_runtime_security_intelligence.md](ai_agent_runtime_security_intelligence.md).
3. **Detection rules** (`app/detection_rules.py`, `source="detection_rules"`): built-in batch rules (`rule_mcp_tool_access_threshold`, `rule_repeated_tool_errors`, `rule_unknown_provider_in_production`) evaluated only here, never inline at ingestion. Design: [ai_agent_detection_rules_alerts_design.md](ai_agent_detection_rules_alerts_design.md).
4. **Gateway control candidates** (`app/gateway_control.py`, `category="control"`, `source="observe_to_control"`): one `gateway_control_recommended` per asset with any open high-severity finding or an open `human_review_recommended`, carrying trigger provenance and suggested controls.

Passes 2–4 are pure modules returning finding *drafts*; the orchestrator owns all upserts. Findings on assets whose identity is a fallback hash are degraded (`_degrade_low_confidence_draft`: high/critical capped at medium, confidence note added) — never suppressed.

**Dedup and occurrence semantics.** Capabilities dedup on (org, asset_key, capability_type, capability_name, source); findings on (org, asset_key, category, finding_type, source). Span-derived findings are accumulated in memory first, so each key becomes exactly one row per run with an `occurrence_count` and aggregated evidence (`replace_evidence=True` — the fresh aggregate is the truth). Re-runs refresh `last_seen` and never reopen dismissed/resolved findings; control-candidate dismissal is sticky and reopens only when a *new* trigger finding type appears. Post-commit, detection-rule webhook notifications fire fail-safe (`app/notifications.py`).

---

## 4. Stage 3 — Read surfaces

All read-only, org-scoped via `get_current_user`; no new collection, no writes to evidence.

| Surface | Endpoints | Reads |
|---|---|---|
| **Runtime timeline** (`app/routes/runtime.py`) | `GET /runtime/traces` (one row per trace, GenAI scalar-column filters), `GET /runtime/traces/{id}` (full span tree: server-computed `offset_ms`, `step_type` via `classify_step`, per-span `gen_ai` payload, session grouping on `session.id` / `gen_ai.conversation.id`), `GET /runtime/genai-usage` (SQL-only token/provider/model aggregates) | `otel_spans` |
| **Intelligence** (`app/routes/asset_intelligence.py`) | `GET /intelligence/asset-summary` (grouped per AI system — the primary dashboard shape), `/assets`, `/capabilities`, `/findings`, `POST /intelligence/run`, finding `dismiss` / `resolve` / `reopen` | `otel_assets`, `asset_capabilities`, `asset_findings` |
| **Telemetry quality** | `GET /intelligence/telemetry-quality` (per-service classification breakdown, missing signals, candidate keys, remediation hints), `POST /intelligence/reclassify` (admin: re-run classification over stored spans via `app/otel_reprocess.py`) | `otel_spans`, `otel_assets` |
| **Inventory** | `GET /agents…`, `GET /assets…` + claim/registry actions | `asset_registry` + evidence |
| **Dependencies** | `GET /relationships`, `GET /relationships/graph` | `agent_relationships` |

The Execution Timeline is purely a read view — everything it needs (`trace_id`, `parent_span_id`, timing, duration) was persisted in stage 1 (see [product_discovery_model.md](product_discovery_model.md) §6).

---

## 5. Intelligence layers → implementing modules

The product model ([product_discovery_model.md](product_discovery_model.md) §5) defines eight intelligence layers over the correlated inventory:

| Layer | What it answers | Implemented by |
|---|---|---|
| Discovery | Which AI systems exist, and how were they found? | `app/otel_normalizer.py:_upsert_asset` → `asset_registry`; `app/asset_discovery.py` |
| Runtime | What is actually executing, how often, where? | `otel_spans` / `otel_assets` via `normalize_spans`; `app/routes/runtime.py` |
| Dependency | What does each system depend on? | relationship branches in `normalize_spans` + `app/relationships.py`; `dependency` findings |
| Capability | What can each system do? | `app/asset_intelligence.py` capability derivation (`asset_capabilities`) |
| Performance | Where is time spent? | span-scan `performance` findings; timeline offsets/durations in `app/routes/runtime.py` |
| Operational | Are systems managed, healthy, behaving normally? | `operations` findings incl. error and telemetry-quality types |
| Security | Which capability combinations and behaviors create risk? | `security` findings; `app/runtime_security_intelligence.py`; `app/detection_rules.py`; `app/gateway_control.py` |
| Inventory | Is the inventory complete, current, accurate? | `inventory` findings (`new_ai_system_detected`, `unknown_model`); registry linkage |

Security is one layer among eight: a `shell_enabled` finding and a `slow_tool_call` finding are the same kind of object — a normalized signal derived from evidence — surfaced through different lenses.

---

## 6. Where to find the specs

- [architecture.md](architecture.md) — platform-wide spine: composition, data model, API surface, deployment
- [asset_intelligence.md](asset_intelligence.md) — capability/finding catalog, dedup semantics, intelligence API reference
- [ai_agent_runtime_security_intelligence.md](ai_agent_runtime_security_intelligence.md) — runtime security finding types, evidence and privacy rules
- [ai_agent_detection_rules_alerts_design.md](ai_agent_detection_rules_alerts_design.md) — detection rules design and rollout phases
- [product_discovery_model.md](product_discovery_model.md) — the Runtime + Ecosystem discovery product model, intelligence layers, execution-timeline concepts
- [otel-deployment-guide.md](otel-deployment-guide.md) — deploying OTel export into this pipeline
- [sdk-guide.md](sdk-guide.md) — the ObserveAgents SDK ingestion path
- [customer-integration-guide.md](customer-integration-guide.md) — end-to-end customer onboarding
