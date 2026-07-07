# Asset Intelligence

ObserveAgents.ai is an **Enterprise AI Intelligence Platform**. Asset Intelligence is the analysis layer that reads OTel evidence collected during trace ingestion and derives structured, actionable intelligence across six dimensions:

| Layer | What it tells you |
|---|---|
| **Discovery** | Which AI systems exist in your environment |
| **Dependency** | What each AI system depends on (models, tools, APIs, databases) |
| **Capability** | What each AI system can do (tool surface, runtime access, provider reach) |
| **Security** | What capability combinations create risk |
| **Performance** | Where latency bottlenecks are occurring |
| **Operations** | Whether AI systems are managed, healthy, and observable |

---

## How it works

Asset Intelligence is a derived layer. It does not collect new data — it reads from the OTel evidence tables already populated by span ingestion:

```
otel_assets     – aggregated evidence per service/environment
otel_spans      – individual span records (structural metadata only)
asset_registry  – canonical AI inventory
```

When you call `POST /intelligence/run`, the engine:

1. Reads all `otel_assets` rows for your organization
2. Creates or updates `asset_capabilities` — one row per discovered capability type
3. Derives and upserts `asset_findings` based on the observed capability surface
4. Scans `otel_spans` for performance and error signals, writing additional findings

No raw prompt/response content is ever read or stored. The privacy guarantees of the OTel ingestion layer apply throughout.

---

## Capabilities

An `asset_capability` row records a single concrete capability of an AI system — which model it uses, which provider it calls, which tools it has access to, and what runtime environment it operates in.

### Capability types

| Type | Derived from | Examples |
|---|---|---|
| `provider` | `gen_ai.system` | openai, anthropic, google |
| `model` | `gen_ai.request.model` / `gen_ai.response.model` | gpt-4o, claude-opus-4-8 |
| `mcp` | tool names containing "mcp" | mcp_filesystem, mcp_browser |
| `database` | tool/dependency names with db keywords | postgres_query, mysql_read |
| `filesystem` | tool/dependency names with fs keywords | file_reader, s3_upload |
| `shell` | tool names with shell keywords | bash_exec, subprocess_run |
| `messaging` | tool names with messaging keywords | slack_post, email_send |
| `source_control` | tool names with git keywords | github_pr_create |
| `crm` | tool names with CRM keywords | salesforce_update |
| `retrieval` | tool names with search/vector keywords | vector_search, embed |
| `memory` | tool names with memory/cache keywords | memory_store, cache_get |
| `external_api` | tool names with http/api keywords | http_get, api_call |
| `runtime` | `deployment.environment` = production/prod | production |
| `unknown` | tool names that don't match any category | custom_tool_xyz |

Capabilities are deduplicated per `(org, asset_key, capability_type, capability_name, source)`. Running intelligence twice does not create duplicate rows — it updates `last_seen`.

---

## Findings

An `asset_finding` is a normalized signal about an AI system's observed behavior. Findings are not alerts. There is no enforcement, no blocking, no automated policy action. Findings are structured observations that help teams understand what their AI systems are doing.

### Finding lifecycle

```
open  →  dismissed   (acknowledged, no action needed)
open  →  resolved    (remediated or no longer applicable)
```

Status changes are persistent — a second intelligence run does not reopen a dismissed or resolved finding.

### Severity levels

| Severity | Meaning |
|---|---|
| `critical` | Immediate attention required (not used in MVP) |
| `high` | Significant risk or broad impact |
| `medium` | Moderate risk, worth reviewing |
| `low` | Informational with some signal value |
| `info` | Purely observational, no risk implied |

---

## MVP Finding Catalog

### Security

| finding_type | Trigger | Severity |
|---|---|---|
| `shell_enabled` | Asset has `shell` capability | high |
| `database_access` | Asset has `database` capability | medium |
| `filesystem_enabled` | Asset has `filesystem` capability | medium |
| `mcp_enabled` | Asset has `mcp` capability | medium |
| `mcp_tool_access` | MCP tool invocations (`mcp.method.name`) observed in a production environment | medium |
| `sensitive_system_access` | Asset has `provider` capability AND any of (crm, source_control, database, messaging) | high |

#### AI Agent Runtime Security Intelligence (`source: runtime_security`)

Agent-specific, environment-aware security findings derived from runtime evidence — see [ai_agent_runtime_security_intelligence.md](ai_agent_runtime_security_intelligence.md).

| finding_type | Trigger | Severity |
|---|---|---|
| `agent_has_database_access` | Agent spans reach a database (`db.system`/`db.name`) | medium · high prod |
| `agent_uses_unmanaged_external_api` | Agent calls an external API (`url.full`/`server.address`) | medium · high prod |
| `agent_uses_mcp_tool_in_production` | MCP tool/method usage in production | high |
| `agent_has_broad_tool_surface` | ≥ 5 distinct tools | medium · high if prod ∧ ≥ 8 |
| `agent_uses_unknown_model_provider` | Provider missing or outside the known catalog | low · high prod |
| `agent_missing_owner` | AssetRegistry has no owner/team | medium · high prod |
| `repeated_tool_errors` | ≥ 3 tool/MCP error spans | medium · high prod |
| `human_review_recommended` | High-risk runtime combination | medium · high if ≥ 2 reasons |

### Control (`source: observe_to_control`)

| finding_type | Trigger | Severity |
|---|---|---|
| `gateway_control_recommended` | Asset has any open high-severity finding, or an open `human_review_recommended` at any severity | high · medium |

One candidate per asset, surfaced in the **Gateway Control Center** with trigger provenance and suggested controls. Dismissal is independent of the underlying findings and sticky until a *new* trigger finding type appears; only admins can change its status. See [gateway_control_center_architecture.md](gateway_control_center_architecture.md).

### Dependency

| finding_type | Trigger | Severity |
|---|---|---|
| `broad_tool_access` | 5 or more distinct tool/dependency capabilities | medium |
| `external_api_access` | Asset has `external_api` capability | low |

### Operations

| finding_type | Trigger | Severity |
|---|---|---|
| `production_runtime` | `runtime:production` capability observed | info |
| `unmanaged_runtime` | Asset in registry has no owner and is unclaimed | medium |
| `runtime_error` | Error span (`status_code = "2"` or `error.type`) with no provider/tool/MCP context | medium |
| `provider_error` | Error span with `gen_ai.*` inference context | medium |
| `tool_error` | Error span on a tool call | medium |
| `mcp_error` | Error span on an MCP call (`error.type` or JSON-RPC error code) | medium |

### Inventory

| finding_type | Trigger | Severity |
|---|---|---|
| `new_ai_system_detected` | Asset's `discovery_status = "potential"` | info |
| `unknown_model` | No models recorded in OtelAsset | low |

### Performance

| finding_type | Trigger | Severity |
|---|---|---|
| `slow_llm_call` | Span with `gen_ai.*` attributes, duration ≥ 10,000 ms | medium |
| `slow_tool_call` | Span with `tool.*` attributes, duration ≥ 5,000 ms | medium |
| `slow_runtime_step` | Any span, duration ≥ 5,000 ms, not LLM or tool | medium |

---

## API Reference

### Run intelligence

```
POST /intelligence/run
Authorization: Bearer <jwt>
```

Derives capabilities and findings for all OTel evidence in your organization. Idempotent — safe to run repeatedly.

**Response:**
```json
{
  "capabilities_created": 4,
  "capabilities_updated": 0,
  "findings_created": 3,
  "findings_updated": 0
}
```

### Asset summary (grouped by AI system)

```
GET /intelligence/asset-summary
Authorization: Bearer <jwt>
```

Returns intelligence grouped per discovered AI system — the primary shape the dashboard renders. One object per asset with runtime evidence (`trace_count`, `span_count`, `last_seen`, `environment`), evidence arrays (`models`, `providers` — display-normalized, `tools`, `dependencies`), counts (`capabilities_count`, `findings_count`, `open_findings_count`, `high_findings_count`, `finding_categories`), status badges (`active`, `runtime_observed`, `has_findings`, `error_observed`), and the full serialized `capabilities` and `findings` lists for detail views. Built entirely from derived columns — raw span attributes are never read or returned.

```json
{
  "assets": [
    {
      "ai_asset_id": 12,
      "asset_key": "…",
      "asset_name": "support-agent",
      "environment": "production",
      "last_seen": "2026-07-03T09:00:00",
      "trace_count": 1,
      "span_count": 8,
      "models": ["gpt-4o"],
      "providers": ["OpenAI"],
      "tools": ["vector_search", "jira_issue_search"],
      "dependencies": ["https://api.acme-crm-demo.example/v1/accounts"],
      "capabilities_count": 9,
      "findings_count": 5,
      "open_findings_count": 5,
      "high_findings_count": 1,
      "finding_categories": {"security": 1, "operations": 2, "dependency": 1, "inventory": 1},
      "status": ["active", "runtime_observed", "has_findings"],
      "capabilities": ["…"],
      "findings": ["…"]
    }
  ]
}
```

### List capabilities

```
GET /intelligence/capabilities
  ?asset_id=<int>
  &capability_type=<str>
  &source=<str>
```

Returns all capabilities for the organization, ordered by `last_seen` descending.

### List findings

```
GET /intelligence/findings
  ?asset_id=<int>
  &category=<str>
  &severity=<str>
  &status=<str>
  &finding_type=<str>
```

Returns all findings for the organization, ordered by `last_seen` descending.

### Dismiss a finding

```
POST /intelligence/findings/{id}/dismiss
```

Sets `status = "dismissed"`. A subsequent intelligence run will not reopen it.

### Resolve a finding

```
POST /intelligence/findings/{id}/resolve
```

Sets `status = "resolved"`. A subsequent intelligence run will not reopen it.

---

## Data model

```
asset_capabilities
  organization_id  → organizations.id
  asset_id         → asset_registry.id  (nullable)
  asset_key        sha256(org_id:name)[:64]
  capability_type  provider|model|mcp|database|filesystem|shell|...
  capability_name  raw value (model name, tool name, etc.)
  source           otel_trace | sdk | observed
  evidence_json    optional JSON context
  first_seen / last_seen / created_at / updated_at

asset_findings
  organization_id  → organizations.id
  asset_id         → asset_registry.id  (nullable)
  asset_key        sha256(org_id:name)[:64]
  category         security|performance|operations|dependency|inventory
  finding_type     see catalog above
  severity         info|low|medium|high|critical
  title            short human-readable label
  summary          one-sentence explanation
  evidence_json    optional JSON context (span_id, duration_ms, etc.)
  source           otel_trace | sdk | observed
  status           open|dismissed|resolved
  first_seen / last_seen / created_at / updated_at
```

---

## Roadmap (not yet implemented)

- **Trust radius** — which assets have been granted access to which resources, compared against what was actually observed
- **Control recommendations** — suggested mitigations per finding type
- **Governance workflows** — owner assignment, review deadlines, policy-driven status transitions
- **Provenance UI** — timeline of what each AI system did, linked to findings
- **sdk_assets** — SDK-attested identity (agents that self-report via the ObserveAgents SDK)
- **observed_assets** — passive network observation (traffic-based discovery)
- **Content capture opt-in** — per-organization opt-in to store prompt/response content for audit (currently always redacted)
