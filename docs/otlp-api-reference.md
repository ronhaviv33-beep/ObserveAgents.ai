# OTLP API Reference

The ingestion contract for `POST /otel/v1/traces`. For the getting-started walkthrough see [otel-deployment-guide.md](otel-deployment-guide.md); for attribute semantics see [genai-semantic-conventions.md](genai-semantic-conventions.md); for redaction behavior see [privacy.md](privacy.md).

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

Anything else returns `415`. gRPC is not supported. **Traces only** — metrics/logs payloads posted here return `400` with a clear message; metrics/logs ingestion is a separate roadmap item.

## Authentication

| Credential type | Header value |
|---|---|
| JWT (web login) | `Bearer <jwt>` |
| API key | `Bearer gk-<raw-key>` |

Unauthenticated requests are rejected with HTTP 401. Each span is scoped to the organization associated with the credential — cross-org data is never mixed. Dashboard JWTs expire after 8 hours; use a `gk-` API key for anything long-running (a Collector, a deployed exporter).

**Preparation checklist (5 min):** log into the dashboard as admin → **API Keys** → create a key and save the `gk-…` value. *Optional but recommended:* create a separate staging/test organization first, and create the key there, so test agents don't mix into your main org's inventory.

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

## Response

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

## Status codes

| Code | Meaning |
|---|---|
| **202** | Ingested; body carries the creation summary above |
| **400** | Malformed body, or a non-trace (metrics/logs) payload |
| **401** | Missing/invalid credential, or key with no organization |
| **415** (`Content-Type`) | Media type other than the JSON/protobuf types above |
| **415** (`Content-Encoding`) | Compression other than gzip |

## Limits and behavior

- **Traces only.** Metrics/logs must stay pointed elsewhere until ObserveAgents' metrics ingestion ships.
- A valid envelope with **zero spans** is accepted (`202`) with zero counts, on both encodings.
- `Content-Encoding: gzip` is supported (the Collector exporter gzip-compresses by default).
- Privacy behavior is identical for JSON and protobuf — both feed the same scrub pipeline ([privacy.md](privacy.md)).
- Protobuf span links are ignored.

## What gets created

Each span flows through the ingestion pipeline: privacy scrub → identity extraction → asset registry upsert → model/tool/DB/API/workflow detection → relationship upsert → span persist (duplicates skipped) → provenance event; per batch, the per-service discovery evidence summary is updated.

| Store | Created/updated when… |
|---|---|
| Raw spans | Every new span (privacy-scrubbed attributes) |
| OTel discovery evidence (per service + environment) | First time a `service.name` + environment is seen; updated on subsequent spans |
| AI asset inventory | First time a `service.name` / `agent.name` is seen |
| Dependency relationships | Model, provider, tool, MCP, DB, or API target detected |
| Provenance events | Every span with a detectable event type |

The asset inventory is the single source of truth — all OTel-discovered services/agents are reconciled against it, and each discovery-evidence record links back to its inventory entry. OTel-discovered assets start with `discovery_status="potential"` and `discovery_source="otel_trace"`; they can be promoted to `verified` by claiming them in the Assets UI. See [runtime-flow.md](runtime-flow.md) for the full post-ingestion flow.

## AI system identity

The ingestion pipeline derives identity in priority order:

1. `gen_ai.agent.id` → **declared** identity (stable grouping key; `gen_ai.agent.name` is used as the display name)
2. `gen_ai.agent.name`, `agent.name`, or `ai.agent.name` span/resource attribute → **declared** identity
3. `service.name` resource attribute → **inferred** identity
4. Fallback: `observed-ai-system:<hash of the non-volatile resource attributes>` → **inferred**, flagged for admin review. When the span has no resource attributes at all, the fallback is scoped to the trace (`observed-ai-system:trace-<trace_id_prefix>`) — unidentified telemetry from the same source converges to one asset instead of fragmenting per span, pod, or restart.

Declared agents carry the strongest identity attribution; fallback identities are marked `needs_admin_review` and surface in the discovery review queue. `gen_ai.agent.description` and `gen_ai.agent.version` are recorded as asset evidence.
