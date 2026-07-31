# Runtime Events API Reference (legacy)

> **OpenTelemetry/OTLP is the only recommended integration path.** Instrument your
> runtime with standard OpenTelemetry and export OTLP — directly or through an
> OpenTelemetry Collector — to ObserveAgents ingestion. See
> [otel-deployment-guide.md](otel-deployment-guide.md).
>
> The `POST /runtime-events` API documented below is **legacy** and under review for
> removal — see [otlp_native_audit.md](otlp_native_audit.md). Do not build new
> integrations on it.

The proprietary `ObserveOpenAI` wrapper has been removed. ObserveAgents does not ship
provider-specific wrappers: transport belongs to OpenTelemetry; ObserveAgents focuses on
intelligence over the evidence.

Companion docs:
- [otel-deployment-guide.md](otel-deployment-guide.md) — the recommended OpenTelemetry/OTLP path
- [customer-integration-guide.md](customer-integration-guide.md) — integration rollout guide
- [runtime-flow.md](runtime-flow.md) — how events become traces, assets, and findings
- [architecture.md](architecture.md) — the full platform architecture

---

## The endpoint

`POST {OBSERVEAGENTS_URL}/runtime-events` with
`Authorization: Bearer gk-...` (a `gk-` API key; a JWT also works).
The body is `{ "events": [ ... ] }` — a single event object or a bare list are also
accepted. Limits and behavior:

- **Max 500 events per request** (larger batches are rejected with `413`).
- **Strict schema** — the event model is an allow-list (`extra="forbid"`). Any unknown
  field (`prompt`, `messages`, `headers`, …) is rejected with a `422`; there is no way
  to smuggle content in.
- **Organization scoping is server-side** — `org_id` is resolved from your credential
  and never read from the body.
- Success returns `202` with ingestion counts and `"content_redacted": true`.

Events feed the same span pipeline and intelligence engine as OTLP traces — one engine,
no separate findings pipeline.

## Event fields

Required:

| Field | Meaning |
|---|---|
| `source` | Where the event came from, e.g. `sdk` |
| `agent_name` | Your agent's name — becomes the inventory identity |
| `trace_id` / `span_id` | Correlation ids (any hex ids you generate) |
| `event_type` | `llm_call`, `tool_call`, `mcp_tool`, `db_call`, `external_api_call`, `runtime_step`, or `error` (anything else ingests as a generic runtime step) |

Optional:

| Field | Meaning |
|---|---|
| `provider`, `model` | e.g. `anthropic`, `claude-sonnet-5` |
| `status`, `error_type` | `ok` / `error`; exception **class name** only |
| `duration_ms`, `input_tokens`, `output_tokens` | Timing and usage metadata |
| `environment`, `owner_hint`, `team_hint` | Attribution hints |
| `session_id`, `parent_span_id`, `timestamp` | Grouping and ordering (ISO-8601 timestamp) |
| `tool_name`, `mcp_server`, `db_system`, `db_name`, `external_domain` | For non-LLM event types; `external_domain` is reduced server-side to a bare host — schemes, paths, and query strings are dropped |
| `metadata_json` | Small scalar identifiers/counts only — keys that look like content or secrets (`prompt`, `token`, `password`, …) and URL-like values are scrubbed |

## Minimal curl example

```bash
curl -X POST "https://api.observeagents.ai/runtime-events" \
  -H "Authorization: Bearer gk-..." \
  -H "Content-Type: application/json" \
  -d '{
    "events": [{
      "source": "sdk", "event_type": "llm_call",
      "agent_name": "research-agent", "environment": "production",
      "provider": "anthropic", "model": "claude-sonnet-5",
      "duration_ms": 850.0, "status": "ok",
      "input_tokens": 12, "output_tokens": 96,
      "trace_id": "6f3a1c2e9b4d4f0a8c7e5d2b1a0f9e8d", "span_id": "8c7e5d2b1a0f9e8d"
    }]
  }'
```

## Privacy model — what is sent, what is never sent

Events carry metadata only. **Never send:** prompts · messages · responses · system
instructions · tool arguments · tool results · headers · credentials · full URLs with
query strings.

The platform independently enforces this boundary at ingestion — payloads carrying
forbidden fields are rejected (`422`), and free-form metadata is scrubbed server-side.

## Troubleshooting

| Symptom | Check |
|---|---|
| Nothing appears in Runtime | Verify the `gk-` key belongs to the workspace you're looking at, and the URL has no trailing path |
| `401` from `/runtime-events` | Missing or invalid credential, or the key has no organization associated — check the `Authorization: Bearer gk-...` header |
| `422` from `/runtime-events` | The payload carries an unknown/forbidden field or is missing a required one — the response body names the offending event index and fields |
| `413` from `/runtime-events` | More than 500 events in one request — split the batch |
| Agent appears but no findings | Findings derive during the intelligence run — they appear shortly after evidence lands, not instantly |
