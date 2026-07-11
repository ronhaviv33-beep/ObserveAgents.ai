# OTel GenAI Trace Ingestion

ObserveAgents.ai accepts OpenTelemetry traces via OTLP/HTTP — **JSON and protobuf**. This is an additional discovery path alongside the proxy gateway — agents that emit OTel spans are automatically catalogued, their model/tool/API dependencies are mapped, and provenance events are recorded for audit.

---

## Endpoint

```
POST /otel/v1/traces
Content-Type: application/json  |  application/x-protobuf
Authorization: Bearer <token>   |  Authorization: Bearer gk-<api-key>
```

**Both OTLP/HTTP encodings are accepted at the same endpoint:**

| Content-Type | Encoding |
|---|---|
| `application/json` (charset params allowed; missing content-type treated as JSON) | OTLP/HTTP JSON |
| `application/x-protobuf`, `application/protobuf`, `application/vnd.google.protobuf` | OTLP/HTTP protobuf (`ExportTraceServiceRequest`) |

Anything else returns `415`. gRPC is not supported. **Traces only** — metrics/logs
payloads posted here return `400` with a clear message; metrics/logs ingestion is
a separate roadmap item. A valid envelope with zero spans is accepted (`202`)
with zero counts on both encodings. Privacy behavior is identical for JSON and
protobuf — both feed the same scrub pipeline. Protobuf span links are ignored.

Positioning: **direct protobuf is for fast developer onboarding** (point an SDK
straight at Observe); the **Collector remains the recommended enterprise path**
for routing, processing, retries, and multi-destination export.

---

## Authentication

Use the same credential types as the proxy gateway:

| Credential type | Header value |
|---|---|
| JWT (web login) | `Bearer <jwt>` |
| API key | `Bearer gk-<raw-key>` |

Unauthenticated requests are rejected with HTTP 401. Each span is scoped to the organization associated with the credential — cross-org data is never mixed.

---

## Request format

Standard OTLP/HTTP JSON envelope:

```json
{
  "resourceSpans": [
    {
      "resource": {
        "attributes": [
          {"key": "service.name",              "value": {"stringValue": "support-agent"}},
          {"key": "deployment.environment",    "value": {"stringValue": "production"}},
          {"key": "service.version",           "value": {"stringValue": "2.1.0"}},
          {"key": "team",                      "value": {"stringValue": "support"}}
        ]
      },
      "scopeSpans": [
        {
          "spans": [
            {
              "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
              "spanId":  "00f067aa0ba902b7",
              "name":    "chat",
              "kind":    3,
              "startTimeUnixNano": "1700000000000000000",
              "endTimeUnixNano":   "1700000001500000000",
              "attributes": [
                {"key": "gen_ai.system",              "value": {"stringValue": "openai"}},
                {"key": "gen_ai.request.model",       "value": {"stringValue": "gpt-4o"}},
                {"key": "gen_ai.usage.input_tokens",  "value": {"intValue": 512}},
                {"key": "gen_ai.usage.output_tokens", "value": {"intValue": 128}}
              ],
              "status": {}
            }
          ]
        }
      ]
    }
  ]
}
```

---

## Response

```json
{
  "accepted": true,
  "resource_spans": 1,
  "spans": 1,
  "ai_systems": 1,
  "relationships": 2,
  "provenance_events": 1,
  "otel_assets": 1,
  "content_redacted": true
}
```

Duplicate spans (same `organization_id + trace_id + span_id`) are silently skipped and not counted.

---

## Data Architecture

```
otel_spans          – raw span records (privacy-scrubbed attributes)
otel_assets         – OTel discovery evidence summary, one row per (org, service, environment)
asset_registry      – canonical AI inventory (the "ai_assets" source of truth)
agent_relationships – dependency graph edges (model / tool / provider / API / DB)
provenance_events   – execution provenance per span
```

`asset_registry` is the single source of truth for AI inventory. All OTel-discovered services/agents are reconciled against it — no separate `ai_assets` table is created.

`otel_assets` aggregates discovery evidence across ingested spans: which models, providers, tools, and dependency targets were seen per service and environment, first/last seen timestamps, and span/trace counts. Each `otel_assets` row links back to its `asset_registry` row via `ai_asset_id`.

Future planned evidence tables (not yet implemented):
- `sdk_assets` — SDK-attested identity (agents that self-report via the ObserveAgents SDK)
- `observed_assets` — passive network observation (traffic-based discovery)

Each evidence table feeds into `asset_registry` but is never the canonical record.

---

## What gets created

| Store | Created/updated when… |
|---|---|
| `otel_spans` | Every new span (privacy-scrubbed attributes) |
| `otel_assets` | First time a `service.name` + environment is seen; updated on subsequent spans |
| `asset_registry` | First time a `service.name` / `agent.name` is seen |
| `agent_relationships` | Model, provider, tool, MCP, DB, or API target detected |
| `provenance_events` | Every span with a detectable event type |

---

## AI system identity

The ingestion pipeline derives identity in priority order:

1. `gen_ai.agent.id` → **declared** identity (stable grouping key; `gen_ai.agent.name` is used as the display name)
2. `gen_ai.agent.name`, `agent.name`, or `ai.agent.name` span/resource attribute → **declared** identity
3. `service.name` resource attribute → **inferred** identity
4. Fallback: `observed-ai-system:<hash of the non-volatile resource attributes>` → **inferred**, flagged for admin review. When the span has no resource attributes at all, the fallback is scoped to the trace (`observed-ai-system:trace-<trace_id_prefix>`) — unidentified telemetry from the same source converges to one asset instead of fragmenting per span, pod, or restart.

Declared agents receive higher confidence scores; fallback identities are marked `needs_admin_review` and surface in the discovery review queue. `gen_ai.agent.description` and `gen_ai.agent.version` are recorded as asset evidence. All OTel-discovered assets start with `discovery_status="potential"` and `discovery_source="otel_trace"`. They can be promoted to `verified` by claiming them in the Assets UI.

---

## GenAI semantic conventions (recommended attributes)

Observe follows the [OpenTelemetry GenAI Semantic Conventions](https://github.com/open-telemetry/semantic-conventions-genai). Send standard GenAI telemetry — Observe consumes it as-is; there is no proprietary schema and no Observe SDK.

Three things to know up front:

- **Observe accepts OTLP/HTTP JSON and OTLP/HTTP protobuf** at the same endpoint — SDK exporters that emit protobuf (Python, OpenLLMetry, …) can point directly at Observe; the Collector path still works and is recommended for enterprise routing.
- **`gen_ai.provider.name` is the preferred provider attribute.** `gen_ai.system` (deprecated upstream) is still fully supported for backward compatibility.
- **Raw prompt/response/tool content is scrubbed at ingestion and should not be sent intentionally** — see the privacy guarantee below.

### Provider, model, and usage

| Attribute | Used for |
|---|---|
| `gen_ai.provider.name` *(preferred)* / `gen_ai.system` *(legacy)* | Provider relationship (OpenAI, Anthropic, AWS Bedrock, …) |
| `gen_ai.operation.name` | Operation classification (see table below) |
| `gen_ai.request.model` / `gen_ai.response.model` | Model relationship |
| `gen_ai.response.id` / `gen_ai.response.finish_reasons` | Response metadata |
| `gen_ai.response.time_to_first_chunk` (or `ttft_ms`) | Latency metadata |
| `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens` | Token usage |
| `gen_ai.usage.cache_creation.input_tokens` / `gen_ai.usage.cache_read.input_tokens` | Prompt-cache usage |
| `gen_ai.usage.reasoning.output_tokens` | Reasoning-token usage |
| `gen_ai.prompt.name` / `gen_ai.prompt.version` | Safe prompt metadata (names only — never content) |

### Operations (`gen_ai.operation.name`)

Recognized values and how they classify in the Runtime timeline:

| Operation | Timeline step |
|---|---|
| `invoke_agent`, `create_agent` | Agent |
| `invoke_workflow` | Workflow |
| `plan` | Plan |
| `chat`, `text_completion`, `generate_content` | LLM |
| `embeddings` | Embedding |
| `retrieval` | Retrieval |
| `execute_tool` | Tool (MCP Tool when MCP attributes are present) |
| `search_memory`, `create_memory`, `update_memory`, `delete_memory`, `upsert_memory` | Memory |

### Agent identity

| Attribute | Used for |
|---|---|
| `gen_ai.agent.id` | Stable asset identity (highest priority) |
| `gen_ai.agent.name` | Asset display name |
| `gen_ai.agent.description` / `gen_ai.agent.version` | Asset evidence |

### Tools and MCP

| Attribute | Used for |
|---|---|
| `gen_ai.tool.name` *(preferred)* / `tool.name` / `mcp.tool.name` / `mcp.tool` | Tool relationship |
| `mcp.method.name` | Marks an MCP span (e.g. `tools/call`) |
| `mcp.session.id` / `mcp.protocol.version` | MCP session evidence |
| `mcp.resource.uri` | MCP resource dependency |
| `mcp.server` / `mcp.server.name` | MCP server relationship |
| `jsonrpc.request.id` / `rpc.response.status_code` | MCP error detection |
| `error.type` | Typed error findings (provider/tool/MCP/runtime) |

### Infrastructure and everything else

| Attribute | Used for |
|---|---|
| `db.system` / `db.name` | Database relationship |
| `url.full` / `http.url` / `server.address` | External API relationship |
| `workflow.name` / `workflow.step.name` | Workflow relationship |
| `service.name` | Agent identity fallback (resource attribute) |
| `deployment.environment` | Environment tagging |
| `service.version` | Version evidence |
| `k8s.pod.name`, `cloud.region`, `container.name` | Infrastructure evidence |

### Examples

Span-attribute snippets for the common shapes (attribute lists in OTLP JSON key/value form are abbreviated to plain JSON here):

**Model call** (`chat gpt-4o`):

```json
{"gen_ai.operation.name": "chat", "gen_ai.provider.name": "openai",
 "gen_ai.request.model": "gpt-4o", "gen_ai.response.model": "gpt-4o-2024-11-20",
 "gen_ai.response.id": "chatcmpl-abc123", "gen_ai.response.finish_reasons": ["stop"],
 "gen_ai.usage.input_tokens": 812, "gen_ai.usage.output_tokens": 214,
 "gen_ai.usage.cache_read.input_tokens": 512}
```

**Agent invocation** (`invoke_agent support-agent`):

```json
{"gen_ai.operation.name": "invoke_agent", "gen_ai.provider.name": "anthropic",
 "gen_ai.agent.id": "agent-7f3a", "gen_ai.agent.name": "support-agent",
 "gen_ai.agent.version": "2.1.0"}
```

**Plan step**:

```json
{"gen_ai.operation.name": "plan", "gen_ai.provider.name": "openai",
 "gen_ai.request.model": "gpt-4o"}
```

**Retrieval**:

```json
{"gen_ai.operation.name": "retrieval", "gen_ai.tool.name": "kb_vector_search"}
```

**Tool execution** (`execute_tool crm_account_lookup`):

```json
{"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "crm_account_lookup",
 "url.full": "https://crm.internal.example.com/api/accounts/ACC-4521"}
```

**MCP tool call** (`tools/call repo_search`):

```json
{"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "repo_search",
 "mcp.method.name": "tools/call", "mcp.session.id": "sess-91be",
 "mcp.protocol.version": "2025-06-18", "mcp.server": "repo-context-mcp"}
```

**Error span** (OTLP status `ERROR` plus a typed error):

```json
{"gen_ai.operation.name": "chat", "gen_ai.provider.name": "openai",
 "gen_ai.request.model": "gpt-4o-mini", "error.type": "rate_limit_exceeded"}
```

---

## Privacy guarantee

**Raw prompt, response, and tool content is never stored.**

Do not send these attributes intentionally — if they arrive, they are redacted at ingestion time:

- `gen_ai.system_instructions`
- `gen_ai.input.messages`
- `gen_ai.output.messages`
- `gen_ai.request.messages`
- `gen_ai.response.choices`
- `gen_ai.tool.call.arguments`
- `gen_ai.tool.call.result`
- `tool.arguments`
- `tool.result`
- `prompt`, `response`, `messages` (bare content attribute names some instrumentations emit)
- `traceloop.entity.input` / `traceloop.entity.output` (legacy OpenLLMetry entity content)
- `gen_ai.prompt.<n>.*` / `gen_ai.completion.<n>.*` (legacy OpenLLMetry numbered content attributes; `gen_ai.prompt.name` / `gen_ai.prompt.version` remain safe metadata)
- `gen_ai.prompt.variable.*` (values dropped entirely; variable *names* are kept as `gen_ai.prompt.variables`)

For each redacted field, only this metadata is stored:

```json
{"redacted": true, "sha256": "<hex>", "size_bytes": 1234}
```

List values (e.g. message arrays) also record a safe count:

```json
{"redacted": true, "sha256": "<hex>", "size_bytes": 5210, "message_count": 7}
```

For tool arguments (`tool.arguments` / `gen_ai.tool.call.arguments`), argument key names (not values) are also stored when the value is a JSON object:

```json
{"redacted": true, "sha256": "...", "size_bytes": 88, "argument_keys": ["limit", "query"]}
```

Per-organization content capture opt-in is planned for a future release.

---

## Exporter configuration

### Direct OTLP protobuf quick start

SDKs whose OTLP/HTTP exporters emit protobuf (Python, OpenLLMetry/Traceloop-style
instrumentation, and most language SDKs by default) can now point **directly**
at Observe — no Collector required for a first integration:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=https://YOUR_OBSERVE_HOST/otel
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer gk-<your-api-key>
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_SERVICE_NAME=my-agent
```

Exact syntax varies by SDK — some take the full traces URL
(`https://YOUR_OBSERVE_HOST/otel/v1/traces`) in a traces-specific variable, and
framework instrumentations like OpenLLMetry accept an `api_endpoint`-style
argument at init. Traces only: metrics/logs export must stay pointed elsewhere
until Observe's metrics ingestion ships.

Use direct protobuf for fast onboarding; use the Collector below when you want
enterprise routing, batching/retries, processing, or multi-destination export.

### Environment variables (any OTel SDK)

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=https://<your-observeagents-url>/otel
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer gk-<your-api-key>
OTEL_SERVICE_NAME=my-agent
OTEL_RESOURCE_ATTRIBUTES=deployment.environment=production,team=platform
```

### Python (opentelemetry-sdk)

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

exporter = OTLPSpanExporter(
    endpoint="https://<your-observeagents-url>/otel/v1/traces",
    headers={"Authorization": "Bearer gk-<your-api-key>"},
)
provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(exporter))
trace.set_tracer_provider(provider)
```

### OpenTelemetry Collector

```yaml
exporters:
  otlphttp/observeagents:
    endpoint: "https://<your-observeagents-url>/otel"
    headers:
      Authorization: "Bearer gk-<your-api-key>"

service:
  pipelines:
    traces:
      exporters: [otlphttp/observeagents]
```

---

## curl smoke test

```bash
curl -X POST https://<your-observeagents-url>/otel/v1/traces \
  -H "Authorization: Bearer gk-<your-api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "resourceSpans": [{
      "resource": {
        "attributes": [
          {"key": "service.name", "value": {"stringValue": "my-agent"}},
          {"key": "deployment.environment", "value": {"stringValue": "production"}}
        ]
      },
      "scopeSpans": [{
        "spans": [{
          "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
          "spanId":  "00f067aa0ba902b7",
          "name":    "llm.call",
          "kind":    3,
          "startTimeUnixNano": "1700000000000000000",
          "endTimeUnixNano":   "1700000001000000000",
          "attributes": [
            {"key": "gen_ai.request.model", "value": {"stringValue": "gpt-4o"}}
          ],
          "status": {}
        }]
      }]
    }]
  }'
```

Expected response:

```json
{"accepted": true, "resource_spans": 1, "spans": 1, "ai_systems": 1, "relationships": 0, "provenance_events": 1, "otel_assets": 1, "content_redacted": true}
```
