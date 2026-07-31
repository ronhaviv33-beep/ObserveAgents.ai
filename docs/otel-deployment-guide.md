# OpenTelemetry Deployment Guide

Get your first span into ObserveAgents in minutes, then harden with a Collector. That's this whole guide — the deep material lives in focused companion docs:

| Need | Doc |
|---|---|
| Endpoint, request/response, auth, status codes, limits | [otlp-api-reference.md](otlp-api-reference.md) |
| Supported `gen_ai.*` attributes, examples, mapping, Telemetry Quality | [genai-semantic-conventions.md](genai-semantic-conventions.md) |
| What is stored, what is redacted, privacy guarantees | [privacy.md](privacy.md) |
| Common errors, Collector issues, FAQ | [troubleshooting.md](troubleshooting.md) |
| A tiny first test agent (no Collector, plain Python) | [create_first_agent_guide.md](create_first_agent_guide.md) |

## What ObserveAgents supports

- **OTLP over HTTP, traces only**, at `POST /otel/v1/traces` — **JSON and protobuf** on the same endpoint. No gRPC (4317) listener, no metrics/logs endpoints yet; point only the **`traces`** pipeline at ObserveAgents.
- **Standard telemetry, no vendor SDK.** ObserveAgents consumes [OpenTelemetry GenAI Semantic Conventions](https://github.com/open-telemetry/semantic-conventions-genai) as-is. OpenTelemetry/OTLP is the only recommended integration path.
- **Auth is a long-lived API key** (`gk-…`, created on the dashboard's **API Keys** page). Dashboard JWTs also work but expire after 8 hours — never use one in a Collector.
- **Endpoint paths differ by sender.** The Collector's `otlphttp` exporter appends `/v1/traces` itself → configure `endpoint: https://<host>/otel`. A raw SDK exporter does not → give it the full `https://<host>/otel/v1/traces`.

## Quick start — curl smoke test

The fastest way to confirm connectivity and your API key:

```bash
curl -X POST https://<your-observeagents-url>/otel/v1/traces \
  -H "Authorization: Bearer gk-<your-api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "resourceSpans": [{
      "resource": {"attributes": [
        {"key": "service.name", "value": {"stringValue": "my-agent"}},
        {"key": "deployment.environment", "value": {"stringValue": "production"}}
      ]},
      "scopeSpans": [{"spans": [{
        "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
        "spanId":  "00f067aa0ba902b7",
        "name":    "llm.call",
        "kind":    3,
        "startTimeUnixNano": "1700000000000000000",
        "endTimeUnixNano":   "1700000001000000000",
        "attributes": [{"key": "gen_ai.request.model", "value": {"stringValue": "gpt-4o"}}],
        "status": {}
      }]}]
    }]
  }'
```

Expected: HTTP `202` with `{"accepted": true, "spans": 1, …}`. Full request/response shapes: [otlp-api-reference.md](otlp-api-reference.md). (Windows: run in Git Bash/WSL, or see the [PowerShell notes](troubleshooting.md#windows--powershell).)

## Direct SDK export (no Collector)

Most SDK exporters emit OTLP/HTTP protobuf by default and can point **directly** at ObserveAgents — the fastest developer onboarding:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=https://<your-observeagents-url>/otel
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer gk-<your-api-key>
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_SERVICE_NAME=my-agent
OTEL_RESOURCE_ATTRIBUTES=deployment.environment=production,team=platform
```

Or explicitly in code (Python):

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

exporter = OTLPSpanExporter(
    endpoint="https://<your-observeagents-url>/otel/v1/traces",   # full path — SDK exporters don't append
    headers={"Authorization": "Bearer gk-<your-api-key>"},
)
provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(exporter))
trace.set_tracer_provider(provider)
```

**Auto-instrumentation:** [OpenLLMetry](https://github.com/traceloop/openllmetry) (Traceloop SDK) auto-instruments OpenAI, Anthropic, AWS Bedrock (boto3), LangChain, LlamaIndex, CrewAI and more, emitting standard GenAI spans ObserveAgents consumes as-is — `pip install traceloop-sdk`, `Traceloop.init()`, plus the same env vars above (optionally `TRACELOOP_TRACE_CONTENT=false` as client-side privacy hardening; the platform [redacts content at ingestion](privacy.md) regardless).

## Collector (recommended for production)

Use the Collector when you want central routing, batching/retries, filtering, and fan-out to other backends alongside ObserveAgents.

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

  otlp_http/observeagents:            # Collector < v0.156: use otlphttp/observeagents
    traces_endpoint: https://app.observeagents.ai/otel/v1/traces
    headers:
      authorization: "Bearer gk-<your-api-key>"

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug, otlp_http/observeagents]
```

Run it:

```bash
docker run --rm -p 4318:4318 \
  -v $(pwd)/otel-collector-config.yaml:/etc/otelcol/config.yaml \
  otel/opentelemetry-collector:latest --config=/etc/otelcol/config.yaml
```

Then point your app's exporter at the Collector (`http://localhost:4318`). Keep the `debug` exporter during rollout so you can watch spans arrive locally; only the **traces** pipeline goes to ObserveAgents. Gzip (the exporter default) is supported. Docker images, Compose, networking, and exporter-naming pitfalls: [troubleshooting.md](troubleshooting.md#collector-issues).

## Verify it works

1. **Runtime** — select the **Traces** view: your trace appears as one collapsed session row; expand it into the per-step execution waterfall.
2. **Asset Intelligence** — the agent exists with model/provider evidence, team, and environment (identity from `service.name` or `gen_ai.agent.name` — [details](otlp-api-reference.md#ai-system-identity)).
3. **Security Intelligence** — derived capabilities and findings appear after evidence lands (e.g. a `db.system` span in production raises `agent_has_database_access`).
4. Nothing showing? Head straight to [troubleshooting.md](troubleshooting.md).

Done. For what the platform does with your spans after ingestion — timeline assembly, asset intelligence, findings — see [runtime-flow.md](runtime-flow.md).
