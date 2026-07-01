# OTel GenAI Trace Ingestion

ObserveAgents.ai accepts OpenTelemetry traces via OTLP/HTTP JSON. This is an additional discovery path alongside the proxy gateway — agents that emit OTel spans are automatically catalogued, their model/tool/API dependencies are mapped, and provenance events are recorded for audit.

---

## Endpoint

```
POST /otel/v1/traces
Content-Type: application/json
Authorization: Bearer <token>  |  Authorization: Bearer gk-<api-key>
```

Protobuf is not supported. gRPC is not supported.

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
  "content_redacted": true
}
```

Duplicate spans (same `organization_id + trace_id + span_id`) are silently skipped and not counted.

---

## What gets created

| Store | Created/updated when… |
|---|---|
| `otel_spans` | Every new span (privacy-scrubbed attributes) |
| `asset_registry` | First time a `service.name` / `agent.name` is seen |
| `agent_relationships` | Model, provider, tool, MCP, DB, or API target detected |
| `provenance_events` | Every span with a detectable event type |

---

## AI system identity

The ingestion pipeline derives identity in priority order:

1. `agent.name` or `ai.agent.name` span/resource attribute → **declared** identity
2. `service.name` resource attribute → **inferred** identity
3. Fallback: `observed-ai-system:<span_id_prefix>` → **inferred**

Declared agents receive higher confidence scores. All OTel-discovered assets start with `discovery_status="potential"` and `discovery_source="otel_trace"`. They can be promoted to `verified` by claiming them in the Assets UI.

---

## Supported OTel GenAI attributes

| Attribute | Used for |
|---|---|
| `gen_ai.system` | Provider relationship (OpenAI, Anthropic, etc.) |
| `gen_ai.request.model` / `gen_ai.response.model` | Model relationship |
| `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens` | Token metadata |
| `gen_ai.operation.name` | LLM call detection |
| `tool.name` / `mcp.tool.name` / `mcp.tool` | Tool relationship |
| `mcp.server` / `mcp.server.name` | MCP server relationship |
| `db.system` / `db.name` | Database relationship |
| `url.full` / `http.url` / `server.address` | External API relationship |
| `workflow.name` / `workflow.step.name` | Workflow relationship |
| `service.name` | Agent identity (resource attribute) |
| `deployment.environment` | Environment tagging |
| `service.version` | Version evidence |
| `k8s.pod.name`, `cloud.region`, `container.name` | Infrastructure evidence |

---

## Privacy guarantee

**Raw prompt, response, and tool content is never stored.**

The following attributes are redacted at ingestion time:

- `gen_ai.system_instructions`
- `gen_ai.input.messages`
- `gen_ai.output.messages`
- `gen_ai.request.messages`
- `gen_ai.response.choices`
- `tool.arguments`
- `tool.result`

For each redacted field, only this metadata is stored:

```json
{"redacted": true, "sha256": "<hex>", "size_bytes": 1234}
```

For `tool.arguments`, argument key names (not values) are also stored when the value is a JSON object:

```json
{"redacted": true, "sha256": "...", "size_bytes": 88, "argument_keys": ["limit", "query"]}
```

Per-organization content capture opt-in is planned for a future release.

---

## Exporter configuration

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
{"accepted": true, "resource_spans": 1, "spans": 1, "ai_systems": 1, "relationships": 0, "provenance_events": 1, "content_redacted": true}
```
