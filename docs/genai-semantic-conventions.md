# GenAI Semantic Conventions

ObserveAgents follows the [OpenTelemetry GenAI Semantic Conventions](https://github.com/open-telemetry/semantic-conventions-genai). Send standard GenAI telemetry — the platform consumes it as-is. This doc is the attribute reference; the transport contract lives in [otlp-api-reference.md](otlp-api-reference.md).

Three things to know up front:

- **`gen_ai.provider.name` is the preferred provider attribute.** `gen_ai.system` (deprecated upstream) is still fully supported for backward compatibility.
- **Raw prompt/response/tool content is scrubbed at ingestion and should not be sent intentionally** — see [privacy.md](privacy.md).
- Custom attribute keys don't require code changes — see [Attribute mapping](#attribute-mapping) below.

## Supported attributes

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

## Examples

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

## Attribute mapping

If your instrumentation emits custom attribute keys (`mycompany.llm.model`, `tool_used`, …) instead of the semantic conventions above, you don't have to change code. In **Settings → OTel Attribute Mapping**, an admin maps up to 50 custom keys to canonical attributes (e.g. `mycompany.llm.model → gen_ai.request.model`). A canonical key emitted natively is **never overwritten** by a mapping. Saving applies to new telemetry immediately **and re-classifies stored spans** so history reflects the mapping too; admins can also trigger this any time with the **Reclassify** button on the Telemetry Quality page.

## Telemetry Quality

OpenTelemetry is the **pipeline**. The GenAI semantic conventions are the **meaning**. ObserveAgents is the **intelligence layer** that turns that meaning into AI inventory, dependencies, capabilities, and findings. Real-world telemetry is rarely perfectly clean, so every ingested span is classified: **fully classified** (everything the intelligence layer expects arrived), **partially classified** (some signals missing), or **unclassified** (no service identity at all). Nothing is dropped — raw spans are always stored — but the platform tells you exactly what's missing instead of silently guessing.

### The three telemetry states

| State | What happens | Action |
|---|---|---|
| **Full SemConv** — standard `gen_ai.*`, `service.name`, `deployment.environment` | Everything is automatic; services show **fully classified** | None. This is the best-supported path. |
| **Partial auto-instrumentation** — only HTTP/DB/latency signals | **Partially classified**; the Telemetry Quality page lists the exact missing attributes | Add the listed SemConv attributes at the source (usually 1–2 resource attributes). |
| **Custom attributes** — `mycompany.llm.model`, `tool_used`, … | Stored but invisible to intelligence until mapped; surfaced as **candidate keys** | Map them in **Settings → OTel Attribute Mapping** — ~2 minutes, no code change. |

### Reading the Telemetry Quality page

**Observe → Telemetry Quality** shows, per service: the classification status and quality score (0–100), a span-status breakdown, which signals are missing and on how many spans (with the exact attribute to add), custom keys detected (click one to map it), and an **Unidentified sources** table for telemetry arriving without any `service.name`. *Unscored* means spans ingested before the classification upgrade — they are backfilled automatically at startup.
