# AI Agent Runtime Security Intelligence

*Security findings derived from AI agent runtime evidence — what each agent can do, what it can reach, who owns it, and where a human should review. Observe-only.*

## Positioning

This is **AI-agent-specific runtime security**, not a generic security tool. Every finding answers an agent-governance question:

- Which AI agent is running, and in what environment?
- What tools can it use, and how broad is that surface?
- What databases, external APIs, MCP servers, and providers can it reach?
- Does it have an owner and a team?
- Is it using an unknown provider or an unmanaged dependency?
- Which human review or guardrail recommendation should be created?

It is deliberately **not**:

- **AppSec** — no source scanning, dependency CVEs, or SAST/DAST.
- **SIEM** — no log correlation, threat feeds, or generic detection rules.
- **API security** in general — only the APIs an AI agent reaches at runtime.
- **eBPF / container / kernel runtime security** — no host or syscall telemetry.
- **Enforcement-first** — nothing here blocks. Observe-only: detect, explain, recommend.

**Observability discovers and recommends. Gateway controls only when explicitly configured.**

## How it works

`app/runtime_security_intelligence.py` is a pure derivation module: it reads evidence that already exists in the normalized store — `OtelAsset` summaries, privacy-scrubbed `OtelSpan` attributes, and `AssetRegistry` ownership — and returns finding *drafts*. `app/asset_intelligence.py` orchestrates: it upserts each draft through the shared dedup/occurrence machinery (`category="security"`, `source="runtime_security"`), so there is exactly one finding row per (asset, finding_type) with an `occurrence_count` and `span_count` — never dozens of identical rows. No new endpoint, no migration, no new ingestion.

## Finding types (MVP)

| finding_type | Trigger | Severity | Evidence |
|---|---|---|---|
| `agent_has_database_access` | Agent spans reach a database (`db.system`, `db.name`) | medium · **high in production** | db_systems, db_names, span_count, sample_span_ids |
| `agent_uses_unmanaged_external_api` | Agent calls an external API (`url.full`/`http.url`/`server.address`) | medium · high prod | domains, sample_paths (host+path, no query), span_count |
| `agent_uses_mcp_tool_in_production` | MCP tool/method usage **in production** | high | mcp_methods, tool_names, resource_hosts, span_count |
| `agent_has_broad_tool_surface` | ≥ 5 distinct tools | medium · **high if prod ∧ ≥ 8** | tool_count, tool_names, threshold |
| `agent_uses_unknown_model_provider` | Provider missing or outside the known provider catalog | low · **med/high in production** | providers, models |
| `agent_missing_owner` *(retired)* | No longer emitted — owner/team is optional attribution metadata, never a security finding; legacy rows are cleaned at startup | — | — |
| `repeated_tool_errors` | ≥ 3 tool/MCP spans with an error type | medium · high prod | tool_names, error_types, error_count |
| `human_review_recommended` | High-risk combination (prod + MCP / broad surface / DB / unknown provider; or repeated errors on a high-risk dependency) | medium · high if ≥ 2 reasons | reasons, related_finding_types |

Each recommended action is written into the finding's `summary`.

### Planned, not yet derived

- `production_agent_without_guardrails` — the schema has no per-asset guardrail/policy-profile marker today (guardrails evaluate client-side; guard modes are per-team gateway state). It is intentionally **not faked** — it lands when a per-asset policy-profile signal exists.

## Evidence and privacy

The module consumes only **already-scrubbed** span attributes — content-bearing keys (`gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`, `tool.arguments`, `tool.result`, prompts, responses, …) are removed at ingestion by `app/otel_privacy.py` and never reach this layer. On top of that, this module:

- **strips query strings, fragments, and userinfo from URLs** — stores scheme+host+path only, so secrets in query parameters are never persisted;
- stores **hosts only** from MCP resource URIs;
- stores identifiers and counts — span ids, tool/provider/model/db names, error types, environment, ownership status.

**Never stored:** raw prompts, responses, system instructions, tool arguments, tool results, full URLs with query strings, headers, request bodies, credentials, customer content.

## Relationship to the existing catalog

Several coarse asset-intelligence findings already exist (`source="otel_trace"`). The runtime-security findings (`source="runtime_security"`) are the AI-agent-specific, environment-aware refinement — the two sources have disjoint dedup keys, so both can coexist while the older ones are phased in or out:

| Runtime security (this MVP) | Existing coarse finding |
|---|---|
| `agent_has_database_access` | `database_access` |
| `agent_uses_mcp_tool_in_production` | `mcp_tool_access` |
| `agent_has_broad_tool_surface` | `broad_tool_access` |
| `agent_uses_unknown_model_provider` | `unknown_model` |
| `agent_missing_owner` *(both retired)* | `unmanaged_runtime` |
| `repeated_tool_errors` | `tool_error` / `mcp_error` |

## Connection to Guardrails and Observe Advisor

- **Guardrails** — these findings are the evidence a guardrail recommendation is built on. A production agent with MCP tools and a broad surface is exactly what an observe-only guardrail flags; enforcement, if ever wanted, lives in the Gateway and only when explicitly configured.
- **Observe Advisor** (roadmap O8) — the finding types map directly to skill gaps: `repeated_tool_errors` → tool-fallback skill, `agent_has_broad_tool_surface` → tool-routing skill, `human_review_recommended` → human-handoff decisioning. The Advisor turns these into per-agent "what to improve next" recommendations.
