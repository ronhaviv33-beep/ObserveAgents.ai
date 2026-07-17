# Auto-Instrumentation-First Discovery Plan

## Executive summary

ObserveAgents should work after SDK installation alone.

The customer installs an auto-instrumentation SDK (OpenLLMetry-style OTel instrumentation, or the ObserveAgents SDK) once. From that moment, ObserveAgents automatically discovers AI workloads from the runtime telemetry those libraries already emit — GenAI spans, provider/model attributes, token usage, HTTP/DB spans, external API calls, errors, and resource attributes like `service.name` and `deployment.environment`.

Manual spans are optional. Explicit `gen_ai.agent.name`, hand-written workflow spans, tagged tool spans, and owner/team metadata all **improve accuracy and confidence** — but the product must never require them to produce an inventory, a timeline, findings, or detection-rule matches.

Core line:

> **Install the SDK once. We discover AI workloads from runtime behavior.**

## Product principle

**Manual annotations improve accuracy, but visibility starts without them.**

Every discovery, classification, and intelligence surface must answer: "what do we show when this signal is absent?" The answer is never "nothing" and never "an error" — it is a result scored lower internally, presented to the customer as the evidence that was observed plus a concrete, optional suggestion for how to enrich it.

## Discovery levels

### Level 0 — Basic service telemetry

Signals:
- `service.name`
- `deployment.environment`
- HTTP spans
- DB spans
- errors

Output: **Possible AI workload** only if AI signals are later observed. A service emitting only Level-0 telemetry is tracked as evidence but not surfaced as an AI asset until Level-1 signals appear on the same identity.

### Level 1 — Auto-instrumented AI workload

Signals:
- GenAI spans (`gen_ai.*` attributes)
- provider/model (`gen_ai.provider.name`, `gen_ai.request.model`)
- token usage (`gen_ai.usage.*`)
- LLM latency/errors

Output: **Inferred AI workload.** This is the default discovery outcome for a customer who installs auto-instrumentation and nothing else. It appears in the inventory, the runtime timeline, and intelligence derivation.

### Level 2 — Agent-like workload

Signals:
- LLM calls + tool activity in the same traces
- LLM calls + DB/API access
- MCP-like spans (`mcp.method.name`, MCP server/resource attributes)
- repeated tool/API activity
- external dependencies (domains, DB systems)

Output: **Inferred agent-like workload.** The combination of inference plus action is what distinguishes an agent from a plain LLM integration — and every one of these signals is auto-emittable by instrumentation libraries, with no manual tagging.

### Level 3 — Explicit agent

Signals:
- `gen_ai.agent.name` / `gen_ai.agent.id`
- optional workflow/action spans
- owner/team metadata (resource attributes or claims in the UI)

Output: **Explicit agent identity with high confidence.** This is the accuracy ceiling, not the entry bar.

## Identity resolution

Priority order:

1. `gen_ai.agent.name` (or `gen_ai.agent.id`) if present
2. `service.name` + AI signals
3. `service.name` + provider/model usage
4. process/job/container identity (stable non-volatile resource attributes)
5. generated inferred asset key (stable hash)

**Do not require `gen_ai.agent.name`.**

Implementation status: the OTel pipeline already implements this ladder. `app/otel_normalizer.py` resolves identity `declared → service → fallback` — declared reads `gen_ai.agent.id` → `gen_ai.agent.name` → `agent.name`/`ai.agent.name`; service reads `service.name`; fallback builds a stable `observed-ai-system:<hash>` from non-volatile resource attributes (pod names, instance ids, and SDK versions are excluded so replicas converge to one asset). Trace-level inheritance (`resolve_trace_identities`) lifts child spans to the trace's best identity, so a single declared root span upgrades a whole trace and its absence degrades gracefully rather than fragmenting assets. Priority 4 (process/job/container as a *named* tier rather than part of the fallback hash) is the one refinement to add later.

## Confidence model (internal only)

> **Product rule: Confidence is internal. Evidence is customer-facing.**

Customer-facing UI must look factual and evidence-based — never like the product is guessing. Confidence therefore exists **only as a backend signal**. It keeps powering identity resolution, deduplication, ranking, severity capping, Gateway candidate decisions, risk scoring, and telemetry-quality nudges — but no confidence percentage, no high/medium/low label, and no "low confidence" wording ever reaches a customer surface.

Internal backend fields may include:
- `identity_confidence_score`
- `identity_tier`
- `discovery_method`
- `observed_signals`
- `missing_context`

Customer-facing UI should show:
- "Runtime-discovered" / "Auto-discovered AI workload"
- "Discovered from auto-instrumented telemetry"
- observed LLM / provider / model / tool / API / DB signals
- optional metadata suggestions (owner/team, explicit agent name, environment)

Customer-facing UI should **not** show:
- confidence percentages
- high/medium/low confidence labels
- "low-confidence asset"
- "we are unsure" language

Conceptual confidence per discovered asset (backend-only):

- **high** — explicit agent name, or strong AI + tool evidence from standard SemConv keys
- **medium** — service identity with GenAI spans and dependencies (or signals resolved through fallback/mapped attribute keys)
- **low** — service with weak AI indicators, or unresolved identity (fallback hash)

Implementation status: span-level confidence already exists in `app/telemetry_classification.py` (`CONF_HIGH`/`CONF_MEDIUM`/`CONF_LOW` with missing-signal codes), rolls up to a weighted per-asset `confidence_score` (full = 1.0, partial = 0.6, unclassified = 0.2), and registry rows carry 75 (attributed) vs 30 (fallback identity, flagged `needs_admin_review`). This scoring stays where it is — backend-only. The frontend already follows the rule in its inventory surfaces (`dashboard/src/discoveryStatus.js` replaces raw confidence percentages with an explainable discovery-status lifecycle and keeps the score internal for sorting); roadmap A3 extends the same pattern to Asset Intelligence by surfacing **discovery evidence** — method, observed signals, missing metadata — never scores or labels.

## Evidence model

Allowed inferred evidence:
- LLM provider/model
- token counts
- HTTP domains (host only)
- DB systems/names
- tool names if auto-emitted
- MCP methods if auto-emitted
- status codes
- error types
- trace/span IDs
- environment/team if present

Forbidden (never stored, scrubbed at ingestion):
- raw prompts
- raw responses
- raw messages
- tool arguments
- tool results
- request/response bodies
- headers
- credentials
- full URLs with query strings

This matches the existing privacy pipeline (`app/otel_privacy.py:scrub_attributes` replaces content-bearing keys with `{redacted, sha256, size_bytes}` before storage; the runtime-events schema rejects unknown fields with `422`). No change needed — the evidence model is already auto-instrumentation-safe.

## UI implications

**Status: shipped (A3/A4).** Asset Intelligence shows, per asset:

- **Explicit Agent** or **Runtime-discovered AI Workload** (discovery badge, from the additive `discovery_method` field on `/intelligence/asset-summary`; gateway-era rows show **Gateway-observed**)
- subcopy: "Identified from explicit agent metadata." / "Discovered from auto-instrumented runtime telemetry."
- **Observed signals** section (LLM calls, provider/model, token usage, tool/MCP activity, database access, external API activity, errors, production environment, detection rule matches) — derived from existing summary data only, never raw content
- **Optional metadata can improve attribution** section — "Visibility starts from runtime telemetry. Optional metadata can make attribution richer." — listing owner/team, explicit agent name, environment, service name when absent
- optional setup improvements (link to attribute mapping / SemConv guidance)

No confidence score, percentage, or high/medium/low label appears anywhere on the card — confidence stays backend-only (see the product rule above).

Example card copy:

> Discovered from auto-instrumented runtime telemetry.
> Observed signals: LLM calls, provider/model, DB/API activity.
> Optional metadata: owner/team, explicit agent name.

Missing metadata is presented as an **optional improvement**, never as an error state, a security defect, or a statement of doubt.

## Detection rules implications

Detection rules must work even without explicit agent names.

They should key on:
- `asset_key` (stable identity hash — exists today)
- `service.name`
- resource attributes
- spans grouped by inferred asset

Auto-instrumentation-friendly rules (future set):

| Rule | Status today |
|---|---|
| `repeated_external_api_errors` | new |
| `db_and_external_api_same_trace` | new |
| `new_external_domain_seen` | new |
| `high_token_usage` | exists (asset-intelligence finding, ≥100k tokens) |
| `unknown_provider_in_production` | exists (`rule_unknown_provider_in_production`) |
| `ai_workload_missing_owner` | future — **informational governance nudge only**, never a high-severity security finding (see audit: the old `agent_missing_owner` finding was deliberately removed) |

Note: `rule_repeated_tool_errors` and `rule_mcp_tool_access_threshold` already run on auto-emittable evidence. Production-gated rules silently skip when `deployment.environment` is absent — acceptable, but the telemetry-quality surface should keep nudging for the environment attribute since it unlocks them.

## What to remove or de-emphasize

De-emphasize (stop implying anywhere in product or docs):
- manual spans required
- every agent must define `agent.workflow`
- every tool must be manually tagged
- workflow-level business intent as an MVP requirement

Keep as optional accuracy boosters:
- `gen_ai.agent.name`
- workflow spans
- tool/action spans
- owner/team attributes

## Roadmap

| # | Milestone | Status |
|---|---|---|
| A1 | Auto-instrumentation discovery plan (this document) | ✅ this PR |
| A2 | Code audit for explicit-agent assumptions (below) | ✅ this PR |
| A3 | Internal identity scoring and customer-facing discovery evidence — scoring stays backend-only; UI shows discovery method, observed signals, and optional metadata | ✅ shipped |
| A4 | "Runtime-discovered AI Workload" labeling alongside Explicit Agent | ✅ shipped |
| A5 | Discovery evidence beyond Asset Intelligence (Security Intelligence badges, Overview runtime-discovered count) | ✅ shipped |
| A6 | UI copy update pass | ✅ shipped |
| A7 | Optional ObserveAgents SDK wrapper for higher accuracy (exists for OpenAI; keep expanding) | ongoing |
| A8 | Configured AI vs Runtime AI reconciliation | later |

## Current explicit-agent assumptions

Audit of main @ `7fd192a`. Impact legend: **BLOCKS** = contradicts auto-first by default · **QUALITY** = works, lower fidelity · **GOOD** = already degrades correctly.

### Already correct (keep — these are the pattern to replicate)

| Where | Behavior |
|---|---|
| `app/otel_normalizer.py` (identity core) | Tiered identity declared → service → fallback hash; volatile keys excluded so unnamed replicas converge to one asset; trace-level identity inheritance. No `gen_ai.agent.name` requirement anywhere. |
| `app/telemetry_classification.py` | Missing identity → unclassified + low confidence (never dropped); owner/team explicitly informational ("never blocks status"); missing environment → partial + candidate-key hints. |
| `app/asset_intelligence.py` `_degrade_low_confidence_draft` | High/critical findings capped to medium for fallback-identity assets — degrades urgency, never hides the finding. |
| `app/asset_intelligence.py` ~455 / `app/runtime_security_intelligence.py` ~382 | Missing-owner findings **deliberately removed** — "ownership is optional metadata." |
| `app/identity_resolver.py` (gateway path) | Same philosophy: 6-tier fallback ending in stable hash + review flag. |
| `app/asset_discovery.py` / `app/agent_inventory.py` | Asset type defaults to `agent`; owner/team/environment default to Unassigned/Unknown — never error. |
| `dashboard/ui2/OverviewV2.jsx`, AssetIntelligenceV2 copy, `customer-integration-guide.md`, `runtime-flow.md` | Already evidence-first; integration guide states governance is "never required for the intelligence to work." |

### Violations / gaps (with recommendation)

| Where | Assumption | Impact | Recommendation |
|---|---|---|---|
| `app/risk_processor.py` ~207–217 | `missing_owner` +10, `missing_team` +10, `unknown_environment` +10–15 risk score, **default-on** — an auto-instrumented event with no governance metadata accrues ~30–45 baseline risk and trends toward `warn` | BLOCKS intent | **Change later** — make absence-of-governance rules default-off or zero-weight (per-rule `DetectionRule` overrides already exist); needs product decision + tests, not a copy fix |
| `app/telemetry_ingest/normalizer.py` ~73–75, ~92–96 | Batch-ingest API hard-requires `agent_id` (raises `ValueError`) and hardcodes `identity_tier="declared"` — no service/fallback tiers on this path | Scoped (explicit-ingest API, not the OTel surface) | **Change later** — add tiered fallback if auto-instrumentation ever feeds this path; keep the requirement for now, it's defensible for an explicit API |
| `dashboard/pages/RulesAlertsV2.jsx` ~63–67 | `missing_owner_in_production` planned-rule template: severity "high in production", action "Assign owner/team before expanding use" (`implemented: false`) | Frames optional metadata as high security risk | **Change later** — product decision: reframe as informational governance nudge (`ai_workload_missing_owner`) or gate behind a governance-strictness opt-in |
| `docs/otel-deployment-guide.md` ~479, ~487 | Documents `agent_missing_owner` as a **high** finding that "clears after you Claim" | **Stale** — the code no longer emits this finding | **Change now** (copy — fixed in this PR) |
| `dashboard/pages/SecurityIntelligenceV2.jsx` ~189, ~238–240 | Copy lists "ownership" / "missing ownership" as canonical security-finding triggers | Copy-only | **Change now** (fixed in this PR) |
| `dashboard/pages/PlatformGuideV2.jsx` ~30 | "Every agent making LLM calls — named, fingerprinted, attributed to a team" | Implies name/team always present | **Change now** (fixed in this PR: "…where available") |
| `dashboard/pages/Setup.jsx` ~97–103 | "Follow the GenAI semantic conventions" step lacks the "Optional:" prefix its sibling steps have | Reads as required | **Change now** (fixed in this PR: "Recommended:") |
| `dashboard/pages/AssetIntelligenceV2.jsx` ~138–142 | Stale sort comment mentions a "missing owner" ranking signal that isn't in the code | Comment-only | **Change now** (fixed in this PR) |
| `docs/create_first_agent_guide.md` ~52–54, ~77–79 | Demo sends `team`/`owner` unconditionally with no "optional" note | Minor framing | **Change now** (fixed in this PR: one-line note) |
| `docs/sdk-guide.md` ~99–107 | The ObserveAgents SDK wrapper requires an explicit `agent_name` | Intrinsic to the manual SDK path; the OTel path needs none | **Keep** — the SDK *is* the optional explicit path; guide already points at OTel as the no-name alternative |
| `app/runtime_security_intelligence.py` ~308, ~341, ~402 / `app/detection_rules.py` ~122 | Production-gated findings/rules are silent without `deployment.environment`; severity escalation drops | QUALITY | **Keep** — by design; telemetry-quality surface already nudges for the environment attribute |
| `app/gateway_control.py` (interaction with severity capping) | Fallback-identity assets rarely reach the high-severity trigger, so they seldom become Gateway control candidates | QUALITY | **Keep** — intended safety trade-off (don't recommend controls on unverified identities); document |
| `app/asset_intelligence.py` `unknown_model` (~469), `telemetry_quality_incomplete` (~482) | Low/info-severity findings fire specifically for sparse auto-telemetry | QUALITY | **Keep** — they are the "optional setup improvements" channel; keep severity at low/info |

### Bottom line

The OTel auto-instrumentation pipeline **already satisfies** auto-instrumentation-first end to end. The direction is violated in exactly two backend places — `risk_processor.py`'s default penalty weights for missing owner/team/environment, and `telemetry_ingest`'s declared-only identity — plus one planned UI rule template and a handful of copy strings. The copy is fixed in this PR; the rest is scheduled (A3–A6) and requires product decisions before code changes.
