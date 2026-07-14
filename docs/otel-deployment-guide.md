# OpenTelemetry Deployment Guide

ObserveAgents.ai accepts OpenTelemetry traces via OTLP/HTTP — **JSON and protobuf**. This guide takes a platform or DevOps engineer from a first curl smoke test to a production Collector deployment: agents that emit OTel spans are automatically catalogued, their model/tool/API dependencies are mapped, and provenance events are recorded for audit.

There is no proprietary schema and no required vendor SDK — ObserveAgents consumes standard [OpenTelemetry GenAI Semantic Conventions](https://github.com/open-telemetry/semantic-conventions-genai) telemetry as-is. (If you prefer an SDK-attested integration instead of raw OTel export, see the [SDK guide](sdk-guide.md).)

For what the platform does with your spans after ingestion — timeline assembly, asset intelligence, findings — see [runtime-flow.md](runtime-flow.md).

---

## Before you start: three things to know

These correct the assumptions baked into generic OpenTelemetry guides. They are verified against the ObserveAgents backend.

1. **HTTP + traces only.** ObserveAgents ingests **OTLP over HTTP**, **traces only**, at `POST /otel/v1/traces` (JSON or protobuf). There is **no gRPC (4317) listener** and **no metrics/logs endpoints**. The Collector must use the **`otlphttp`** exporter, and only the **`traces`** pipeline points at ObserveAgents. Metrics/logs export must stay pointed elsewhere until ObserveAgents' metrics ingestion ships.

2. **Auth = API key (`gk-…`), not a JWT.** The endpoint accepts both, but dashboard JWTs expire after 8 hours. A Collector (or any long-running exporter) needs the **long-lived `gk-` key** you create in the dashboard (**API Keys** page, admin login).

3. **Watch the endpoint path.** The Collector's `otlphttp` exporter **appends `/v1/traces` itself** — configure its `endpoint` as `https://app.observeagents.ai/otel` (no `/v1/traces` suffix), or set the full path explicitly via `traces_endpoint`. When posting **directly from an SDK exporter**, the opposite applies: give the **full** path `…/otel/v1/traces` — the raw SDK exporter does not auto-append.

---

## Quick start

### curl smoke test

The fastest way to confirm connectivity and your API key:

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

### Direct OTLP protobuf quick start

SDKs whose OTLP/HTTP exporters emit protobuf (Python, OpenLLMetry/Traceloop-style
instrumentation, and most language SDKs by default) can point **directly**
at ObserveAgents — no Collector required for a first integration:

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
until ObserveAgents' metrics ingestion ships.

Use direct protobuf for fast onboarding; use the [Collector](#deploying-with-an-opentelemetry-collector) when you want
production routing, batching/retries, processing, or multi-destination export.

Generic environment-variable form for any OTel SDK:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=https://<your-observeagents-url>/otel
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer gk-<your-api-key>
OTEL_SERVICE_NAME=my-agent
OTEL_RESOURCE_ATTRIBUTES=deployment.environment=production,team=platform
```

---

## Endpoint & authentication

### Endpoint

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
with zero counts on both encodings. `Content-Encoding: gzip` is supported
(the Collector exporter gzip-compresses by default). Privacy behavior is
identical for JSON and protobuf — both feed the same scrub pipeline. Protobuf
span links are ignored.

Positioning: **direct protobuf is for fast developer onboarding** (point an SDK
straight at ObserveAgents); the **Collector remains the recommended production path**
for routing, processing, retries, and multi-destination export.

### Authentication

Use the same credential types as the proxy gateway:

| Credential type | Header value |
|---|---|
| JWT (web login) | `Bearer <jwt>` |
| API key | `Bearer gk-<raw-key>` |

Unauthenticated requests are rejected with HTTP 401. Each span is scoped to the organization associated with the credential — cross-org data is never mixed. Remember that dashboard JWTs expire after 8 hours; use a `gk-` API key for anything long-running.

**Preparation checklist (5 min):** log into [app.observeagents.ai](https://app.observeagents.ai) as admin → open the **API Keys** page → create a key and save the `gk-…` value. *Optional but recommended:* create a separate staging/test **organization** first (Admin → Organizations) and create the key there, so test agents don't mix into your main org's inventory.

---

## Request formats & responses

### Request format

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

### Response

A successful ingest returns **HTTP 202** with a creation summary:

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

### What gets created

Each span flows through the ingestion pipeline: privacy scrub → identity extraction → asset registry upsert → model/tool/DB/API/workflow detection → relationship upsert → span persist (duplicates skipped) → provenance event; per batch, the per-service discovery evidence summary is updated. The result:

| Store | Created/updated when… |
|---|---|
| Raw spans | Every new span (privacy-scrubbed attributes) |
| OTel discovery evidence (per service + environment) | First time a `service.name` + environment is seen; updated on subsequent spans |
| AI asset inventory | First time a `service.name` / `agent.name` is seen |
| Dependency relationships | Model, provider, tool, MCP, DB, or API target detected |
| Provenance events | Every span with a detectable event type |

The asset inventory is the single source of truth — all OTel-discovered services/agents are reconciled against it, and each discovery-evidence record links back to its inventory entry. All OTel-discovered assets start with `discovery_status="potential"` and `discovery_source="otel_trace"`; they can be promoted to `verified` by claiming them in the Assets UI. See [runtime-flow.md](runtime-flow.md) for the full post-ingestion flow.

### AI system identity

The ingestion pipeline derives identity in priority order:

1. `gen_ai.agent.id` → **declared** identity (stable grouping key; `gen_ai.agent.name` is used as the display name)
2. `gen_ai.agent.name`, `agent.name`, or `ai.agent.name` span/resource attribute → **declared** identity
3. `service.name` resource attribute → **inferred** identity
4. Fallback: `observed-ai-system:<hash of the non-volatile resource attributes>` → **inferred**, flagged for admin review. When the span has no resource attributes at all, the fallback is scoped to the trace (`observed-ai-system:trace-<trace_id_prefix>`) — unidentified telemetry from the same source converges to one asset instead of fragmenting per span, pod, or restart.

Declared agents receive higher confidence scores; fallback identities are marked `needs_admin_review` and surface in the discovery review queue. `gen_ai.agent.description` and `gen_ai.agent.version` are recorded as asset evidence.

---

## Deploying with an OpenTelemetry Collector

The Collector is the recommended production path: central routing, batching/retries, filtering, and fan-out to Datadog/Grafana alongside ObserveAgents. Roll it out in phases so each step has a checkpoint.

### Phase 1 — Collector with a debug exporter (prove telemetry flows)

Start with debug output only, to confirm spans arrive before you touch the platform.

`otel-collector-config.yaml`:

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
processors:
  batch: {}
exporters:
  debug:
    verbosity: normal
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
```

Run it:

```bash
docker run --rm -p 4318:4318 \
  -v $(pwd)/otel-collector-config.yaml:/etc/otelcol/config.yaml \
  otel/opentelemetry-collector:latest --config=/etc/otelcol/config.yaml
```

### Phase 2 — A test agent that emits realistic spans

If your real agents aren't instrumented yet, this script stands in for one. The attributes are chosen so the platform lights up: session grouping (`session.id`), a GenAI call, a database dependency, and an MCP tool call.

```bash
pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
```

`lab_agent.py`:

```python
# lab_agent.py — pretend customer-support-agent
import time
import uuid
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.trace import Status, StatusCode

resource = Resource.create({
    "service.name": "customer-support-agent",
    "deployment.environment": "production",   # -> findings become "high" severity
    "team": "support-ai",
})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces")))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("lab")

session = uuid.uuid4().hex
with tracer.start_as_current_span("agent.workflow") as root:
    root.set_attribute("session.id", session)

    with tracer.start_as_current_span("gen_ai.request") as s:
        s.set_attribute("session.id", session)
        s.set_attribute("gen_ai.provider.name", "anthropic")
        s.set_attribute("gen_ai.request.model", "claude-sonnet-5")
        s.set_attribute("gen_ai.usage.input_tokens", 850)
        s.set_attribute("gen_ai.usage.output_tokens", 300)
        time.sleep(0.2)

    with tracer.start_as_current_span("db.query") as s:
        s.set_attribute("session.id", session)
        s.set_attribute("db.system", "postgresql")
        s.set_attribute("db.name", "tickets")

    with tracer.start_as_current_span("mcp.call") as s:
        s.set_attribute("session.id", session)
        s.set_attribute("mcp.method.name", "tools/call")
        s.set_attribute("gen_ai.tool.name", "jira_search")

# ── Extra operations that trigger the three built-in Detection Rules ──
# Same production agent. After sending, click "Run rules" on Rules & Alerts
# (rules are observe-only — they evaluate on demand, never during ingestion).
rules_session = uuid.uuid4().hex
with tracer.start_as_current_span("agent.workflow") as root:
    root.set_attribute("session.id", rules_session)

    # Rule 1 — MCP Tool Access Above Threshold: fires on > 5 MCP calls.
    # Rule 2 — Repeated Tool Errors: fires on >= 3 tool/MCP spans that carry an
    #          error.type attribute (a bare ERROR status is NOT enough).
    for i in range(6):
        with tracer.start_as_current_span("mcp.call") as s:
            s.set_attribute("session.id", rules_session)
            s.set_attribute("mcp.method.name", "tools/call")
            s.set_attribute("gen_ai.tool.name", f"jira_search_{i}")
            if i < 3:                                   # 3 failures -> Repeated Tool Errors
                s.set_attribute("error.type", "tool_timeout")
                s.set_status(Status(StatusCode.ERROR, "tool timeout"))

    # Rule 3 — Unknown Provider in Production: a provider outside the known catalog.
    with tracer.start_as_current_span("gen_ai.request") as s:
        s.set_attribute("session.id", rules_session)
        s.set_attribute("gen_ai.provider.name", "acme-llm")
        s.set_attribute("gen_ai.request.model", "acme-model-v1")

provider.shutdown()
print("sent — sessions", session, rules_session)
```

Run `python lab_agent.py` and confirm the spans print in the Collector's debug output. That's your checkpoint before pointing at the platform.

> **Note:** some generic Python examples floating around have copy-paste-broken imports (e.g. `from opentelemetryimport trace`). Use the imports above exactly.

### Phase 3 — Point the Collector at ObserveAgents

Add the `otlp_http` exporter on the **traces** pipeline. Keep `debug` too, so you still see local output. Use an explicit `traces_endpoint` with the full path — no path-append guessing.

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch: {}

exporters:
  debug:
    verbosity: normal

  otlp_http/observeagents:
    traces_endpoint: https://app.observeagents.ai/otel/v1/traces
    headers:
      authorization: "Bearer YOUR_API_KEY_HERE"
    # gzip (the exporter default) is supported. If your platform build predates
    # gzip ingestion support, set: compression: none

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug, otlp_http/observeagents]
```

> **`otlp_http` vs `otlphttp`:** Collector **v0.156+** renamed the exporter to `otlp_http` (the old `otlphttp` alias still works but logs a deprecation warning). On older Collectors use `otlphttp`.

> **Compression:** the Collector exporter **gzip-compresses by default**, and ObserveAgents accepts `Content-Encoding: gzip`. `YOUR_API_KEY_HERE` is the `gk-…` key from your API Keys page.

If you configure the shorthand `endpoint` form instead of `traces_endpoint`, remember the exporter appends `/v1/traces` itself:

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

Restart the Collector and run `python lab_agent.py` again. A successful ingest returns **HTTP 202** to the Collector.

### Phase 4 — Verify in the dashboard

1. **Runtime** — the trace appears as **one collapsed session row**; expand it into a per-step execution waterfall.
2. **Asset Intelligence / Inventory** — `customer-support-agent` now exists, with model/provider evidence.
3. **Security Intelligence** — capabilities (provider, model, database, MCP) plus the runtime-security findings below.
4. **Close the governance loop** — **Claim** the asset and assign an **owner** (admin action). The `agent_missing_owner` finding clears.

Findings the test agent raises:

| Finding | Severity | Why it fires |
|---|---|---|
| `agent_has_database_access` | **high** | A DB span is present (`db.system=postgresql`); high because `deployment.environment=production`. |
| `agent_uses_mcp_tool_in_production` | **high** | An MCP call is present (`mcp.method.name=tools/call`) in a production environment (production-only finding). |
| `agent_missing_owner` | **high** | No owner/team assigned yet — clears after you Claim the asset. |
| `human_review_recommended` | **high** | High-risk combination: a production agent with both DB access and MCP use (2 reasons → high). |

> `anthropic` / `claude-sonnet-5` is a **known** provider, so the test agent deliberately raises **no** unknown-provider finding. Swap the provider to something like `"acme-llm"` to see `agent_uses_unknown_model_provider`.

Optionally, emit **3+ failing tool spans** from a *different* team/service to trigger `repeated_tool_errors` (and, combined with a DB/API dependency, escalate `human_review_recommended`) — this exercises the multi-asset inventory and the error-findings path:

```python
# add to a second script with service.name="billing-agent", team="billing-ai"
from opentelemetry.trace import Status, StatusCode
for i in range(3):
    with tracer.start_as_current_span("mcp.call") as s:
        s.set_attribute("session.id", session)
        s.set_attribute("mcp.method.name", "tools/call")
        s.set_attribute("gen_ai.tool.name", "stripe_charge")
        s.set_attribute("error.type", "tool_timeout")   # required — the rule keys on error.type
        s.set_status(Status(StatusCode.ERROR, "tool timeout"))
```

> **Why `error.type`?** The `repeated_tool_errors` rule counts spans whose attributes carry an `error.type` (or an RPC error code) **and** a tool/MCP identity — a bare OTLP `ERROR` status alone is not counted.

---

## Instrumenting with the OpenTelemetry SDK

When you can't provision a Collector on day one, the OTel SDK can post straight to ObserveAgents. Python example (opentelemetry-sdk):

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

> When posting **directly from the SDK**, give the **full** path `…/otel/v1/traces`. The `/v1/traces` suffix is only auto-appended by the **Collector's** `otlphttp` exporter, not by the raw SDK exporter.

The Collector then becomes the **production-hardening step** — central routing, filtering, and fan-out to other backends alongside ObserveAgents.

If you'd rather use ObserveAgents' own SDK integration (attested agent identity rather than raw OTel export), see the [SDK guide](sdk-guide.md).

---

## GenAI semantic conventions reference

ObserveAgents follows the [OpenTelemetry GenAI Semantic Conventions](https://github.com/open-telemetry/semantic-conventions-genai). Send standard GenAI telemetry — the platform consumes it as-is.

Three things to know up front:

- **ObserveAgents accepts OTLP/HTTP JSON and OTLP/HTTP protobuf** at the same endpoint — SDK exporters that emit protobuf (Python, OpenLLMetry, …) can point directly at ObserveAgents; the Collector path still works and is recommended for production routing.
- **`gen_ai.provider.name` is the preferred provider attribute.** `gen_ai.system` (deprecated upstream) is still fully supported for backward compatibility.
- **Raw prompt/response/tool content is scrubbed at ingestion and should not be sent intentionally** — see the [Privacy guarantee](#privacy-guarantee) below.

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

## Attribute mapping

If your instrumentation emits custom attribute keys (`mycompany.llm.model`, `tool_used`, …) instead of the semantic conventions above, you don't have to change code. In **Settings → OTel Attribute Mapping**, an admin maps up to 50 custom keys to canonical attributes (e.g. `mycompany.llm.model → gen_ai.request.model`). A canonical key emitted natively is **never overwritten** by a mapping. Saving applies to new telemetry immediately **and re-classifies stored spans** so history reflects the mapping too; admins can also trigger this any time with the **Reclassify** button on the Telemetry Quality page.

---

## Telemetry Quality

OpenTelemetry is the **pipeline**. The GenAI semantic conventions are the **meaning**. ObserveAgents is the **intelligence layer** that turns that meaning into AI inventory, dependencies, capabilities, and findings — Discovery, Runtime, Dependency, Capability, Performance, Operational, and Security Intelligence. Real-world telemetry is rarely perfectly clean, so every ingested span is classified: **fully classified** (everything the intelligence layer expects arrived), **partially classified** (some signals missing), or **unclassified** (no service identity at all). Nothing is dropped — raw spans are always stored — but the platform tells you exactly what's missing instead of silently guessing.

### The three telemetry states

| State | What happens | Action |
|---|---|---|
| **Full SemConv** — standard `gen_ai.*`, `service.name`, `deployment.environment` | Everything is automatic; services show **fully classified** | None. This is the best-supported path. |
| **Partial auto-instrumentation** — only HTTP/DB/latency signals | **Partially classified**; the Telemetry Quality page lists the exact missing attributes | Add the listed SemConv attributes at the source (usually 1–2 resource attributes). |
| **Custom attributes** — `mycompany.llm.model`, `tool_used`, … | Stored but invisible to intelligence until mapped; surfaced as **candidate keys** | Map them in **Settings → OTel Attribute Mapping** — ~2 minutes, no code change. |

### Reading the Telemetry Quality page

**Observe → Telemetry Quality** shows, per service: the classification status and quality score (0–100), a span-status breakdown, which signals are missing and on how many spans (with the exact attribute to add), custom keys detected (click one to map it), and an **Unidentified sources** table for telemetry arriving without any `service.name`. *Unscored* means spans ingested before the classification upgrade — they are backfilled automatically at startup.

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

Per-organization content capture opt-in is planned for a future release. Privacy behavior is identical for JSON and protobuf payloads.

---

## Troubleshooting

| Response | Meaning | Fix |
|---|---|---|
| **202 Accepted** | Ingested OK | Nothing — check Runtime. |
| **401** | Bad/missing key, or key has no org | Use a valid `gk-` key from the dashboard. |
| **400** | Malformed body, or non-trace payload | Send OTLP **traces** only; metrics/logs are rejected here. |
| **415** `Content-Type` | Wrong media type | Send `application/json` or `application/x-protobuf`. |
| **415** `Content-Encoding` | Unsupported compression | Use `gzip` or no compression. |
| Collector: `Exporting failed … HTTP Status Code 400` | Gzipped body the platform couldn't read | Update to a build with gzip support, or set `compression: none` on the exporter. |
| No agent in Runtime | Spans exported to the wrong URL | Use `traces_endpoint: …/otel/v1/traces` (full path). |
| Service shows **unclassified** | No `service.name` / `gen_ai.agent.*` on the spans | Set the `service.name` resource attribute; the Telemetry Quality page lists the source under Unidentified. |
| Model missing on **old** spans after adding a mapping | Mapping saved with `reprocess: false` | Click **Reclassify** on the Telemetry Quality page (admin), or re-save the mapping. |

---

*Every endpoint, attribute, status code and finding in this guide is verified against the ObserveAgents backend.*
