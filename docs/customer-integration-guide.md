# Customer Integration Guide

The single entry point for rolling out ObserveAgents in your organization — from first login to a fully observed AI estate.

**What you'll have at the end:** every connected AI system automatically discovered, its runtime traces and execution timelines visible, its capabilities and findings derived, and advisory guardrails running in observe-only mode — without changing how your AI systems behave in production.

**Time estimate:** first AI system connected in under 30 minutes; organization-wide rollout is incremental after that.

## Choose your path

| You are | Read |
|---|---|
| A business stakeholder, product leader, security leader, or manager | [Part 1 — Overview for stakeholders](#part-1--overview-for-stakeholders-non-technical) — what Observe does, what rollout involves, and what you need from your team. No technical knowledge needed. |
| A platform engineer, security engineer, or engineering lead implementing Observe | [Part 2 — Technical rollout](#part-2--technical-rollout) — org setup, evidence paths, deployment, and verification. |
| Looking for deep dives | [Further reading](#further-reading) — architecture, runtime flow, OTel deployment, and the SDK guide. |

---

# Part 1 — Overview for stakeholders (non-technical)

*A simple rollout guide for teams that want to understand their AI systems before adding controls.*

## 1.1 What Observe does

Observe helps teams see what AI exists, what is actually running, what it connects to, and where it needs attention.

In practice, Observe shows your organization:

- **Which AI systems exist** — including ones nobody registered anywhere
- **Which AI systems are actually running** — not just which ones are supposed to exist
- **What each system connects to** — the models, tools, databases, and outside services it touches
- **Which systems have risky behavior** — like direct database access or broad tool access
- **Which systems are slow, heavy, or potentially expensive**
- **Which guardrails would be triggered** — in observe-only mode, before anything is enforced

One important idea to hold onto:

> **Observe does not need to block anything on day one. It first helps you understand what is happening.**

Nothing about how your AI systems behave changes when you connect them. Observe watches, explains, and recommends.

## 1.2 Who should be involved

A rollout works best with a small group and clear roles:

| Role | Responsibility |
|---|---|
| **Admin / platform owner** | Creates user accounts, manages who can see what, creates access keys, and configures settings. Usually one person. |
| **Platform or engineering team** | Connects the first AI system to Observe. This is the only technical part of the rollout, and it is small — usually under an hour for the first system. |
| **Security team** | Reviews risky behavior once data flows: findings, sensitive access, and guardrail signals. |
| **Product or business owner** | Uses Observe to understand which AI systems exist and how they are being used. |
| **Leadership / viewer** | Gets a read-only picture of AI activity, risk, and usage — no setup, no actions required. |

## 1.3 Start with one AI system

**Do not try to connect the whole organization on day one.**

Pick one real AI system your team knows well — for example a support agent, a finance analysis agent, an engineering copilot, an onboarding bot, or a research assistant.

The goal of the first connection is simple:

- Prove that data is flowing
- See the system appear in **Runtime**
- See it appear in **Asset Intelligence**
- Understand its models, tools, dependencies, and first findings

Once one system is visible and understood, connecting the next ones is repetition, not a new project.

## 1.4 How data gets into Observe

There are two ways data flows in. Your technical team picks whichever fits — the choice does not change what you see.

### OpenTelemetry

If your organization already uses observability tools (many engineering teams do), your technical team can send AI activity to Observe through OpenTelemetry — an industry standard they will recognize.

This lets Observe show runtime traces, execution timelines, slow steps, errors, and the models, tools, and dependencies each system uses.

### Gateway

If your AI systems call common AI providers (like OpenAI or Anthropic), your team can route those calls through the Observe gateway — a small configuration change on their side.

This helps Observe see which AI systems are making requests, which providers and models they use, token and usage signals, cost signals, and advisory guardrail signals.

**Either way, Part 2 of this guide covers the exact steps.** From your perspective as a stakeholder, the outcome is the same: your AI systems start appearing in Observe.

## 1.5 What you will see after the first connection

### Runtime
Shows whether the AI system is actually running, when it ran, and where its time was spent. Each run appears as a trace you can click into.

### Execution Timeline
Shows the steps inside a single request — for example: planning, retrieval, tool calls, database calls, and the final response — each with how long it took. This is how you spot the slow or surprising parts.

### Asset Intelligence
Shows one card per AI system: its models, providers, tools, dependencies, capabilities, findings, and when it was last seen. This becomes your organization's AI inventory.

### Security Intelligence
Shows risky observed behavior per system — things like database access, MCP tools, external API calls, broad tool access, runtime errors, and high-severity findings. It answers: *which AI systems need a security conversation?*

### Cost Intelligence
Shows usage and efficiency signals — slow traces, heavy workflows, which models are used, repeated tool calls, and possible cost hotspots. These are signals based on observed behavior, not an invoice.

### Guardrails
Guardrails start in **observe-only mode**. That means Observe **detects, explains, and recommends — it does not block production AI systems.** You see which recommended guardrails would be triggered by real behavior, and what to do about it, without any risk to production.

## 1.6 What the first week should look like

**Day 1**
- Admin creates the workspace and adds the first users
- The group chooses the first AI system
- The technical team connects it

**Day 2–3**
- Confirm activity appears in Runtime
- Check the system's card in Asset Intelligence
- Review the first capabilities and findings together

**Day 4–5**
- Security team reviews Security Intelligence
- Product/business owner reviews Cost Intelligence
- Review Guardrails in observe-only mode
- Decide which systems to connect next

**End of week**
- The first AI system is fully visible
- The team understands what it connects to
- Findings are triaged (fixed, planned, or accepted)
- Guardrails have been reviewed
- A rollout plan exists for more systems

## 1.7 Weekly operating rhythm

Once systems are connected, a short weekly review keeps the picture current. Recommended checklist:

- Which AI systems were active this week?
- Did any **new** systems appear that nobody expected?
- Which findings are open, and who owns them?
- Which systems connect to sensitive tools or databases?
- Which traces are slow or heavy?
- Which guardrails were triggered in observe-only mode?
- Which systems should be connected next?

Fifteen minutes with the right people in the room is usually enough.

## 1.8 When to use enforcement

**Enforcement is optional. Many organizations stay in observe-only mode for a long time — and get full value.**

If and when you want more, there is a deliberate progression, applied one team at a time:

### Observe-only
Detect and recommend. Nothing is blocked. This is where everyone starts.

### Alert
Notify the right people when something needs attention. Still nothing is blocked.

### Enforce
Block or require action — only when the organization intentionally enables it, for a specific team, after reviewing what enforcement *would have* blocked.

> **Do not start with enforcement. Start by understanding what is happening.**

This is what makes Observe safe to adopt: nothing about your production AI changes until you decide it should.

## 1.9 What success looks like

By the end of the first rollout stage, your organization should have:

- At least one AI system connected
- Runtime traces visible
- The Execution Timeline working
- Asset Intelligence showing the system's card
- Capabilities detected
- Findings generated and triaged
- Security and Cost Intelligence populated
- Guardrails reviewed in observe-only mode
- A clear plan to connect more systems

At that point you can answer, with evidence, the questions this started with: what AI exists, what is actually running, what it connects to, and where it needs attention.

**Implementers: continue to Part 2 below for the exact setup steps.**

---

# Part 2 — Technical rollout

**Who this is for:** platform engineers, security engineers, and engineering leads implementing Observe for their organization.

The rollout follows four phases: workspace setup → connect your first AI system (choose an evidence path) → roll out service by service → operate the intelligence.

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

## Phase 1 — Connect your first AI system

Pick **one** AI service to start with. Two paths — use whichever matches your stack. (Neither? See Phase 2.)

### Path A — You already use OpenTelemetry

If your AI service already emits OTel traces, you point your existing pipeline at Observe. **The endpoint accepts both OTLP/HTTP JSON and OTLP/HTTP protobuf**, so most SDKs can post directly; the Collector remains the recommended production path. What that means per stack:

**Via an OpenTelemetry Collector (recommended — works for every language):**

```yaml
exporters:
  otlphttp/observeagents:
    endpoint: "https://<your-observeagents-url>/otel"
    encoding: json          # json shown; Observe also accepts protobuf directly
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

**Python and other languages whose OTLP/HTTP exporters send protobuf:** point them directly at Observe (`OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`), or route through the Collector above for production routing and processing.

For the full OTel deployment reference — endpoints, attribute conventions, and Collector patterns — see [otel-deployment-guide.md](otel-deployment-guide.md).

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

Prefer connecting from application code with a lightweight wrapper instead of a base-URL change? See the [SDK guide](sdk-guide.md).

### Verify (both paths)

1. Trigger one request through your AI service.
2. **Runtime** — the trace appears within seconds; click it to see the execution timeline.
3. **Asset Intelligence** — the AI system appears as a discovered card with its model and provider.

If nothing appears, see [Troubleshooting](#troubleshooting) at the end.

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

Full attribute reference (MCP, workflows, agent identity): [otel-deployment-guide.md](otel-deployment-guide.md).

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

## Phase 3 — Roll out across the organization

Repeat Phase 1/2 service by service. Conventions that keep the estate legible:

- **`service.name` = one AI system.** Use stable, meaningful names (`support-agent`, `invoice-extractor`) — this is the identity everything groups under.
- **Always set `deployment.environment`** (`production` / `staging` / `development`) — it drives production-specific findings and guardrails.
- **One API key per team/service**, named to match.
- Connect production systems first (that's where the intelligence matters), then staging.

As systems connect, **Discovery Center** shows newly observed systems awaiting review; **Dependency Map** fills in what they touch.

## Phase 4 — Operate the intelligence (weekly rhythm)

1. **Asset Intelligence → AI Systems** — your grouped estate view: per system, its models, tools, dependencies, capability surface, findings, and runtime evidence. Run **▶ Run Intelligence** after connecting new systems to refresh derivations.
2. **Findings triage** — work the Findings tab by severity. *Resolve* what you've fixed, *dismiss* what's accepted; neither reopens on re-derivation.
3. **Guardrails** — review which advisory guardrails are triggered (database access, MCP tools, external APIs, broad tool surface, production systems with high-severity findings, runtime errors, slow paths). Observe-only: they detect, explain, and recommend — nothing is blocked.
4. **Security / Cost Intelligence** — the risky-systems table and the usage/efficiency signals ("potential cost hotspots" from slow steps and heavy trace volume).
5. **Budgets (admin)** — set expected-usage thresholds per team as planning signals.
6. **Graduating enforcement (optional, later):** guard modes are per team. Watch **Settings → Guard Modes → "Would block (30d)"** — it shows what enforce mode *would* have blocked. Only when a team's number is stable and understood, move that one team observe → alert → enforce. Most organizations run observe-only indefinitely.

**Optional governance:** in Discovery Center / Agents, claim discovered systems, assign owners, validate or reject. This builds on the inventory — it's never required for the intelligence to work.

## Privacy & data handling (for your security review)

- **Never stored:** prompt text, response text, system instructions, tool arguments, tool results — scrubbed at ingestion to `{redacted, sha256, size_bytes}`.
- **Stored:** service/model/provider/tool names, span timing, token counts, scrubbed attributes, synthetic identifiers.
- **Isolation:** every row is organization-scoped; cross-org access is impossible through the API.
- **Keys:** provider credentials are Fernet-encrypted, write-only; `gk-` keys are stored as SHA-256 hashes and revocable individually.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `401` on `/otel/v1/traces` | Missing/wrong `Authorization: Bearer gk-…` header on the exporter/Collector |
| `415 Unsupported Content-Type` | Content-Type is neither JSON nor protobuf — check the exporter's protocol setting |
| Traces arrive but system is named `observed-ai-system:…` | No `service.name` resource attribute — set it |
| Runtime shows traces but Asset Intelligence is empty | Click **▶ Run Intelligence** (derivation is on-demand) |
| Gateway returns `424 provider_not_configured` | Add the provider key under Settings → Organization AI Providers (Phase 0.4) |
| Waterfall shows one flat span | Add child spans around each step (LLM / tool / DB) — the timeline mirrors your span hierarchy |
| Viewer can't create budgets | Expected — budgets are readable by all roles, managed by admins |

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

---

# Further reading

| Guide | Read it for |
|---|---|
| [architecture.md](architecture.md) | How the system is built — evidence sources, ingestion, derivation, and the product surfaces |
| [runtime-flow.md](runtime-flow.md) | What happens to a trace end to end, from ingestion to timeline and findings |
| [otel-deployment-guide.md](otel-deployment-guide.md) | OTel deployment in depth — endpoints, Collector patterns, and the full span attribute reference (MCP, workflows, agent identity) |
| [sdk-guide.md](sdk-guide.md) | Connecting agents from application code with the lightweight SDK wrapper |
