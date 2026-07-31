# Privacy

## Privacy guarantee

**Raw prompt, response, and tool content is never stored.**

Runtime evidence is structural metadata only. Privacy behavior is identical for JSON and protobuf payloads — both feed the same scrub pipeline before anything persists.

## What is redacted

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

## What is stored

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

Beyond span content:

- **URLs** are stored as scheme + host + path only — query strings, fragments, and credentials never persist.
- **Findings, security intelligence, and control recommendations** carry identifiers and counts only: agent/tool/provider/model names, MCP methods, span counts, durations, error types.

## Defense in depth

The scrub is server-side and unconditional — a successful ingest response includes `"content_redacted": true`. You can additionally stop content at the source (e.g. `TRACELOOP_TRACE_CONTENT=false` for OpenLLMetry) so content attributes are never emitted at all; the platform redacts either way.

Per-organization content capture opt-in is planned for a future release.
