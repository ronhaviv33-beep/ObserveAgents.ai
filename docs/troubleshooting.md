# Troubleshooting

Common errors and fixes for OTel ingestion. The contract itself (status codes, limits) is specified in [otlp-api-reference.md](otlp-api-reference.md).

## Common errors

| Response | Meaning | Fix |
|---|---|---|
| **202 Accepted** | Ingested OK | Nothing — check Runtime. |
| **401** | Bad/missing key, or key has no org | Use a valid `gk-` key from the dashboard. |
| **400** | Malformed body, or non-trace payload | Send OTLP **traces** only; metrics/logs are rejected here. |
| **415** `Content-Type` | Wrong media type | Send `application/json` or `application/x-protobuf`. |
| **415** `Content-Encoding` | Unsupported compression | Use `gzip` or no compression. |
| No agent in Runtime | Spans exported to the wrong URL | Direct SDK: full path `…/otel/v1/traces`. Collector: `traces_endpoint: …/otel/v1/traces`, or `endpoint: …/otel` (it appends `/v1/traces` itself). |
| No trace visible but ingest returned 202 | Looking at the wrong Runtime view | Switch the Runtime toggle to **Traces** — OTel spans don't appear in *Agent events* (that view is fed by the batch telemetry API). |
| Service shows **unclassified** | No `service.name` / `gen_ai.agent.*` on the spans | Set the `service.name` resource attribute; the Telemetry Quality page lists the source under Unidentified. |
| Model missing on **old** spans after adding a mapping | Mapping saved with `reprocess: false` | Click **Reclassify** on the Telemetry Quality page (admin), or re-save the mapping. |

## Collector issues

| Symptom | Meaning | Fix |
|---|---|---|
| `Exporting failed … HTTP Status Code 400` | Gzipped body the platform couldn't read | Update to a build with gzip support, or set `compression: none` on the exporter. |
| Deprecation warning on `otlphttp` | Collector **v0.156+** renamed the exporter to `otlp_http` | Use `otlp_http/...` on v0.156+; `otlphttp` on older Collectors. |
| Docker: `manifest ... not found` | Wrong image name (e.g. `otel/collector-contrib` — doesn't exist) | Use `otel/opentelemetry-collector` (config at `/etc/otelcol/config.yaml`) or `otel/opentelemetry-collector-contrib` (config at `/etc/otelcol-contrib/config.yaml`). |
| Collector can't reach a localhost backend | Container `localhost` ≠ host `localhost` | Use `http://host.docker.internal:<port>/otel/v1/traces` (Linux: add `--add-host=host.docker.internal:host-gateway`, or `extra_hosts: ["host.docker.internal:host-gateway"]` in Compose). |
| `bind: address already in use` on 4318 | Another collector/process owns the port | Stop it, or publish a different host port (`-p 14318:4318`) and point the SDK exporter at it. |
| Spans reach the Collector but not the platform | Only the debug exporter is wired | Ensure the **traces** pipeline lists your `otlp_http/observeagents` exporter; keep `debug` alongside it during rollout. |

Docker Compose form of the standard Collector, for reference:

```yaml
services:
  otel-collector:
    image: otel/opentelemetry-collector:latest
    command: ["--config=/etc/otelcol/config.yaml"]
    volumes:
      - ./otel-collector-config.yaml:/etc/otelcol/config.yaml:ro
    ports:
      - "4318:4318"
    restart: unless-stopped
```

## Windows / PowerShell

- bash continues lines with `\`; PowerShell uses a **backtick** `` ` ``. Pasting a `\`-continued command into PowerShell executes each line separately — you'll see errors like *"The term '-p' is not recognized"*. Re-join onto one line or switch continuations.
- For curl tests, run in **Git Bash/WSL**, or in PowerShell use `curl.exe` (not the bare `curl` alias), and keep JSON in a file passed via `-d "@payload.json"` to avoid quoting issues.
- Docker volume mounts: use `${PWD}` with backtick continuation:

```powershell
docker run --rm -p 4318:4318 `
  -v "${PWD}\otel-collector-config.yaml:/etc/otelcol/config.yaml" `
  otel/opentelemetry-collector:latest --config=/etc/otelcol/config.yaml
```

## FAQ

**Does a JWT work for ingestion?** Yes, but it expires after 8 hours — anything long-running (Collector, deployed exporter) needs a `gk-` API key.

**Can I send metrics or logs?** Not yet — traces only. Metrics/logs pipelines must stay pointed at another backend until ObserveAgents' metrics ingestion ships.

**Why did my error spans not trigger `repeated_tool_errors`?** The rule counts spans whose attributes carry an `error.type` (or an RPC error code) **and** a tool/MCP identity — a bare OTLP `ERROR` status alone is not counted.

**Why is there no unknown-provider finding for my test agent?** Known providers (e.g. `anthropic`, `openai`, `aws.bedrock`) never raise it. Use an out-of-catalog provider name (e.g. `acme-llm`) in a `production` environment to see `agent_uses_unknown_model_provider`.

**Some generic Python OTel examples fail to import.** Copy-paste-broken imports circulate (e.g. `from opentelemetryimport trace`) — use the imports from the [deployment guide](otel-deployment-guide.md#direct-sdk-export-no-collector) exactly.

**Where do batch detection rules run?** On demand — click **Run rules** on the Rules & Alerts page. Rules never evaluate during ingestion.
