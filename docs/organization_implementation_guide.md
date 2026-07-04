# Organization Implementation Guide

A practical, step-by-step guide for rolling out ObserveAgents in your organization — from first login to a fully observed AI estate.

> גרסה בעברית: [organization_implementation_guide_he.md](organization_implementation_guide_he.md)

**Who this is for:** platform engineers, security engineers, and engineering leads implementing Observe for their organization.

**What you'll have at the end:** every connected AI system automatically discovered, its runtime traces and execution timelines visible, its capabilities and findings derived, and advisory guardrails running in observe-only mode — without changing how your AI systems behave in production.

**Time estimate:** first AI system connected in under 30 minutes; organization-wide rollout is incremental after that.

---

## Phase 0 — Workspace setup (15 minutes, admin)

### 0.1 Sign in and check your organization

Log in with your admin account. Everything in Observe is scoped to your organization — users, AI systems, traces, and findings from other organizations are never visible to you.

### 0.2 Add your team

**Users → Add User.** Three roles:

| Role | Use for | Can do |
|---|---|---|
| **Admin** | Platform owners | Everything: users, API keys, settings, budget rules, guard modes |
| **Analyst** | Engineers, security analysts | All product pages, finding triage (resolve/dismiss), setup |
| **Viewer** | Leadership, stakeholders | Read-only: Runtime, Asset Intelligence, Security, Cost, Budgets, Pricing, Guardrails |

Start small: one admin, a few analysts for the teams connecting first.

### 0.3 Create API keys

**API Keys → Create.** Keys look like `gk-…` and authenticate telemetry ingestion.

Recommended convention: **one key per team or per major service**, named accordingly (`payments-team`, `support-agent-prod`). This keeps attribution clean and lets you revoke a single team's key without touching others.

### 0.4 (Gateway users only) Configure provider credentials

If you'll route AI traffic through the gateway (Path B below), add your OpenAI/Anthropic/Google keys under **Settings → Organization AI Providers** (BYOK — stored encrypted, write-only, never displayed again). Skip this if you're only sending OpenTelemetry traces.

---

## Phase 1 — Connect your first AI system

Pick **one** AI service to start with. Two paths — use whichever matches your stack. (Neither? See Phase 2.)

### Path A — You already use OpenTelemetry

If your AI service already emits OTel traces, you point your existing pipeline at Observe. **Important: the endpoint accepts OTLP/HTTP JSON only — protobuf is rejected.** What that means per stack:

**Via an OpenTelemetry Collector (recommended — works for every language):**

```yaml
exporters:
  otlphttp/observeagents:
    endpoint: "https://<your-observeagents-url>/otel"
    encoding: json          # required — Observe accepts OTLP JSON, not protobuf
    headers:
      Authorization: "Bearer gk-<your-api-key>"

service:
  pipelines:
    traces:
      exporters: [otlphttp/observeagents]
```

Add this exporter alongside your existing ones — Observe becomes an additional destination; nothing else in your pipeline changes.

**Node.js (direct — its HTTP exporter sends JSON natively):**

```js
const { OTLPTraceExporter } = require('@opentelemetry/exporter-trace-otlp-http');

const exporter = new OTLPTraceExporter({
  url: 'https://<your-observeagents-url>/otel/v1/traces',
  headers: { Authorization: 'Bearer gk-<your-api-key>' },
});
```

**Python and other languages whose OTLP/HTTP exporters send protobuf:** route through the Collector config above — it transcodes to JSON for you.

### Path B — No OTel, but you call OpenAI/Anthropic-compatible APIs

Route traffic through the Observe gateway using **your existing provider SDK** — there is no proprietary Observe SDK to install. One config change:

```python
# Python — OpenAI SDK
client = openai.OpenAI(
    base_url="https://gateway.observeagents.ai/v1",
    api_key="gk-<your-api-key>",        # your Observe key, not your provider key
)
```

```python
# Python — Anthropic SDK
client = anthropic.Anthropic(
    base_url="https://gateway.observeagents.ai",
    api_key="gk-<your-api-key>",
)
```

```bash
# Env-var only — no code change at all (any OpenAI-compatible client)
export OPENAI_API_KEY=gk-<your-api-key>
export OPENAI_BASE_URL=https://gateway.observeagents.ai/v1
```

Works with the OpenAI SDK, Anthropic SDK, LangChain, CrewAI, LiteLLM, MCP clients, Vercel AI SDK, and anything OpenAI-compatible. Your provider keys stay server-side in Observe (Phase 0.4); application code never sees them.

The gateway runs in **advisory mode by default** — it observes, attributes, and estimates cost; it never blocks unless a team is explicitly moved to enforce mode later.

### Verify (both paths)

1. Trigger one request through your AI service.
2. **Runtime** — the trace appears within seconds; click it to see the execution timeline.
3. **Asset Intelligence** — the AI system appears as a discovered card with its model and provider.

If nothing appears, see Troubleshooting at the end.

---

## Phase 2 — Starting from zero: no OTel, no compatible SDK path

This phase is for organizations where neither path fits yet — e.g. custom AI code without observability, or AI calls that don't go through OpenAI/Anthropic-style APIs. You have two options; most organizations do **Option 1** because it's ~20 lines and pays off across all observability tooling, not just Observe.

### Option 1 — Add OpenTelemetry instrumentation from scratch

OTel is the vendor-neutral standard; instrumenting once serves Observe and anything else you adopt later.

**Step 1 — Install (Python example):**

```bash
pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
```

**Step 2 — Stand up a minimal Collector** (one small container; it bridges any language to Observe's JSON endpoint):

```yaml
# otel-collector.yaml
receivers:
  otlp:
    protocols:
      http:
      grpc:
exporters:
  otlphttp/observeagents:
    endpoint: "https://<your-observeagents-url>/otel"
    encoding: json
    headers:
      Authorization: "Bearer gk-<your-api-key>"
service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [otlphttp/observeagents]
```

```bash
docker run -v $(pwd)/otel-collector.yaml:/etc/otelcol/config.yaml \
  -p 4318:4318 otel/collector-contrib:latest
```

**Step 3 — Initialize tracing once at app startup:**

```python
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

resource = Resource.create({
    "service.name": "support-agent",            # becomes the AI system's identity
    "deployment.environment": "production",     # production | staging | development
    "team": "customer-support",                 # optional attribution
})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces")  # → your Collector
))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("support-agent")
```

**Step 4 — Wrap your AI calls with spans.** The attributes below are what Observe understands — each one becomes a capability, dependency, or timeline step:

```python
# One root span per request/task — this is the Execution Timeline's spine
with tracer.start_as_current_span("handle_customer_request"):

    # LLM call → discovered model + provider
    with tracer.start_as_current_span("llm.plan") as span:
        span.set_attribute("gen_ai.system", "openai")
        span.set_attribute("gen_ai.request.model", "gpt-4o")
        span.set_attribute("gen_ai.usage.input_tokens", 512)   # optional
        span.set_attribute("gen_ai.usage.output_tokens", 128)  # optional
        response = call_your_llm(...)

    # Tool call → discovered tool capability
    with tracer.start_as_current_span("tool.search_kb") as span:
        span.set_attribute("tool.name", "kb_search")
        results = search_knowledge_base(...)

    # Database access → database capability + security finding
    with tracer.start_as_current_span("db.lookup") as span:
        span.set_attribute("db.system", "postgresql")
        span.set_attribute("db.name", "customers")
        rows = query_db(...)

    # External API call → external_api dependency
    with tracer.start_as_current_span("crm.update") as span:
        span.set_attribute("url.full", "https://api.your-crm.example/v1/update")
        update_crm(...)
```

Full attribute reference (MCP, workflows, agent identity): [otel_ingestion.md](otel_ingestion.md).

**Privacy note — you don't need to be careful about prompts:** even if instrumentation libraries attach `gen_ai.input.messages` / `gen_ai.output.messages` / `tool.arguments`, Observe scrubs them at ingestion and stores only a hash and byte size. Raw prompt/response content is never persisted.

**Shortcut — auto-instrumentation:** if your service uses common libraries (requests/httpx, FastAPI, etc.), `pip install opentelemetry-distro && opentelemetry-instrument python app.py` with `OTEL_SERVICE_NAME` and `OTEL_EXPORTER_OTLP_ENDPOINT` env vars generates spans without code changes. You'll still want the manual `gen_ai.*` / `tool.*` attributes on your AI-specific steps for the richest intelligence, but auto-instrumentation gets timelines flowing on day one.

### Option 2 — Route through the gateway without touching application code

If you can't add instrumentation at all, you can still get Runtime Discovery for any HTTP-callable AI usage by pointing it at the gateway:

```bash
curl https://gateway.observeagents.ai/v1/chat/completions \
  -H "Authorization: Bearer gk-<your-api-key>" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"demo request"}]}'
```

Anything that can change a base URL — cron jobs, low-code platforms, internal scripts — can adopt this. You get discovery, attribution, token usage, and cost signals; you won't get per-step execution timelines (those need spans), which is why Option 1 is the recommended end-state.

### Choosing

| Your situation | Do this |
|---|---|
| Existing OTel pipeline | Phase 1 Path A (add the Collector exporter) |
| OpenAI/Anthropic-style SDK calls, no observability | Phase 1 Path B today; add Option 1 spans when you want timelines |
| Custom AI code, no observability | Option 1 (Collector + ~20 lines of spans) |
| Can't change code at all | Option 2 (gateway URL swap wherever config allows) |

---

## Phase 3 — Roll out across the organization

Repeat Phase 1/2 service by service. Conventions that keep the estate legible:

- **`service.name` = one AI system.** Use stable, meaningful names (`support-agent`, `invoice-extractor`) — this is the identity everything groups under.
- **Always set `deployment.environment`** (`production` / `staging` / `development`) — it drives production-specific findings and guardrails.
- **One API key per team/service**, named to match.
- Connect production systems first (that's where the intelligence matters), then staging.

As systems connect, **Discovery Center** shows newly observed systems awaiting review; **Dependency Map** fills in what they touch.

---

## Phase 4 — Operate the intelligence (weekly rhythm)

1. **Asset Intelligence → AI Systems** — your grouped estate view: per system, its models, tools, dependencies, capability surface, findings, and runtime evidence. Run **▶ Run Intelligence** after connecting new systems to refresh derivations.
2. **Findings triage** — work the Findings tab by severity. *Resolve* what you've fixed, *dismiss* what's accepted; neither reopens on re-derivation.
3. **Guardrails** — review which advisory guardrails are triggered (database access, MCP tools, external APIs, broad tool surface, production systems with high-severity findings, runtime errors, slow paths). Observe-only: they detect, explain, and recommend — nothing is blocked.
4. **Security / Cost Intelligence** — the risky-systems table and the usage/efficiency signals ("potential cost hotspots" from slow steps and heavy trace volume).
5. **Budgets (admin)** — set expected-usage thresholds per team as planning signals.
6. **Graduating enforcement (optional, later):** guard modes are per team. Watch **Settings → Guard Modes → "Would block (30d)"** — it shows what enforce mode *would* have blocked. Only when a team's number is stable and understood, move that one team observe → alert → enforce. Most organizations run observe-only indefinitely.

**Optional governance:** in Discovery Center / Agents, claim discovered systems, assign owners, validate or reject. This builds on the inventory — it's never required for the intelligence to work.

---

## Privacy & data handling (for your security review)

- **Never stored:** prompt text, response text, system instructions, tool arguments, tool results — scrubbed at ingestion to `{redacted, sha256, size_bytes}`.
- **Stored:** service/model/provider/tool names, span timing, token counts, scrubbed attributes, synthetic identifiers.
- **Isolation:** every row is organization-scoped; cross-org access is impossible through the API.
- **Keys:** provider credentials are Fernet-encrypted, write-only; `gk-` keys are stored as SHA-256 hashes and revocable individually.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `401` on `/otel/v1/traces` | Missing/wrong `Authorization: Bearer gk-…` header on the exporter/Collector |
| `415 Content-Type must be application/json` | Your exporter sends protobuf — route through a Collector with `encoding: json` |
| Traces arrive but system is named `observed-ai-system:…` | No `service.name` resource attribute — set it |
| Runtime shows traces but Asset Intelligence is empty | Click **▶ Run Intelligence** (derivation is on-demand) |
| Gateway returns `424 provider_not_configured` | Add the provider key under Settings → Organization AI Providers (Phase 0.4) |
| Waterfall shows one flat span | Add child spans around each step (LLM / tool / DB) — the timeline mirrors your span hierarchy |
| Viewer can't create budgets | Expected — budgets are readable by all roles, managed by admins |

---

## Rollout checklist

- [ ] Admin logged in; users invited with roles
- [ ] API key created per team/service
- [ ] (Gateway) provider credentials configured
- [ ] First AI system connected (OTel Collector `encoding: json`, Node direct, gateway base_url swap, or Phase 2 from-scratch instrumentation)
- [ ] `service.name` + `deployment.environment` set on every connected service
- [ ] Trace visible in Runtime; waterfall renders
- [ ] Run Intelligence executed; system appears in Asset Intelligence with capabilities and findings
- [ ] Guardrails reviewed (observe-only)
- [ ] Weekly triage rhythm agreed (findings, security, cost)
- [ ] Remaining services scheduled for connection
