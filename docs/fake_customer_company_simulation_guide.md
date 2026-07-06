# Fake Customer Company Simulation Guide

*How to build and run a simulated company with real AI agents to test Observe end-to-end.*

This is an internal dogfooding guide. You (the founder / product tester) run everything in it manually. Nothing in this guide runs automatically, nothing here was executed when the guide was written, and no example files exist in the repository — every file below is something **you create locally** by copying the code blocks.

The fake company is not only data. It is a small, real customer environment: **real agents, real roles, fake tools, real runs — and Observe watching them.**

Companion documents:

- [Manual company simulation QA guide](manual_company_simulation_qa_guide.md) — the in-app, page-by-page QA walkthrough. Use it *after* this guide has data flowing.
- [Organization implementation guide](organization_implementation_guide.md) — the customer-facing technical setup reference.

---

## 1. What this simulation is

This guide creates a **fake company outside Observe**.

That distinction matters twice over:

- Creating an organization record *inside* Observe gives you an empty workspace. That is not the simulation.
- Writing Python scripts that fabricate spans gives you test data. That is useful, but it is not the simulation either.

The simulation is this: you personally create **real agents** using real agent tools, frameworks, or platforms. Each agent belongs to a department of the fake company. You run the agents; they perform tasks, call models, and use (fake) tools. Observe receives their telemetry or gateway activity and should discover, on its own:

- AI systems (one per agent)
- Runtime traces and execution timelines
- Models and providers
- Tools and dependencies
- Capabilities
- Findings
- Cost / usage signals
- Guardrail signals

This is how a real customer adopts Observe: they don't type their AI inventory into a form — their systems run, and Observe builds the picture from observed behavior.

**Safety framing:** the agents are real, but everything they touch is fake. Fake customers, fake tickets, fake CRM records, fake handbook pages. No real customer data, no paid external services required, no real Jira/Slack/CRM accounts needed. You run everything yourself, by hand, when you choose to.

---

## 2. Fake company profile

| | |
|---|---|
| **Company** | Acme AI Operations |
| **Industry** | B2B SaaS / Customer Support Automation |
| **Teams** | Platform, Customer Support, Finance, Engineering, HR, Security |

**Business story:** Acme uses AI agents across the company. Leadership does not fully know which agents are running, what they connect to, or where there are risks. Some agents were built by central Platform, some by individual teams in whatever tool that team liked. Acme wants Observe to show the real AI footprint — what exists, what is actually running, what it connects to, and where it needs attention.

---

## 3. Three levels of simulation

The rest of this guide keeps returning to this distinction. Know which level you are working at.

### Level 1 — Real agents connected through the Gateway

You build real agents in real tools and route their model calls through the Observe Gateway using their **existing provider SDK or OpenAI-compatible client** (this is *not* an Observe SDK — see §7).

Good for: testing existing SDK/client compatibility, provider/model usage, and usage signals — especially for tools where you can change a base URL but can't easily add instrumentation.

### Level 2 — Real agents instrumented with OpenTelemetry

You build real agents and instrument them with OpenTelemetry so each run produces a full trace: root span, child steps, models, tools, dependencies, errors.

**This is the best level.** It exercises the full Runtime Timeline and Asset Intelligence pipeline and proves what real customer onboarding looks like.

### Level 3 — Pure Python trace simulation (fallback)

Small Python scripts that fabricate realistic spans without any real agent behind them. Fast and useful for testing OTel ingestion and filling dashboards — but it is **not enough to prove real customer onboarding**, because no real agent framework, prompt loop, or tool execution is involved.

Use Level 3 to smoke-test the pipes. Use Levels 1–2 to simulate the customer. The main body of this guide (§4–§5) is about Levels 1 and 2; Level 3 is kept as a fallback in §8.

---

## 4. Creating real agents for the fake company

This is the heart of the simulation. Work through it step by step.

### 4.1 Create the company story

- **Company:** Acme AI Operations
- **Business:** B2B SaaS company using AI across support, finance, engineering, HR, and research.
- **Goal:** Acme wants to understand which AI agents exist, which ones are actually running, what they connect to, and where risk / cost / guardrail signals appear.

Keep the story in mind as you build: every agent below is something a real Acme team plausibly built for itself.

### 4.2 Create the agents

Create these five agents manually, each in a real tool or framework:

| Agent | Suggested tool/framework | Department | Environment | What it does |
|---|---|---|---|---|
| `support-agent` | LangChain or OpenAI-compatible app | Customer Support | production | Answers customer escalation questions, searches docs, checks CRM/Jira, drafts Slack update |
| `finance-analyst-agent` | CrewAI or local agent app | Finance | staging/production | Reviews finance question, queries fake database, uses calculation tool |
| `engineering-copilot` | LiteLLM / local app / CrewAI | Engineering | staging | Searches repo context, uses MCP-like tool, suggests code change |
| `hr-onboarding-bot` | n8n AI workflow or local app | HR | production | Answers onboarding question, searches handbook, creates workflow task, sends Slack-like update |
| `research-agent` | OpenAI-compatible app / local agent | Platform | development | Searches web-like source, calls external API, produces one controlled error |

Notes on the tool column:

- These are **suggestions and examples only**. Use whatever real tool you're comfortable with — the point is that a real agent runs, not which logo built it.
- No connector is claimed to exist for any of these tools. The connection always happens through one of the two generic paths in §4.4 (OpenTelemetry) or §4.5 (Gateway).
- No paid external services are required. Every tool the agents use can be fake: a JSON file as the "CRM", a text file as the "handbook", a function that pretends to search Jira.
- **These agents can use fake tools and fake data. They should not use real customer data.**

### 4.3 Give each agent identity metadata

Every agent needs a stable identity, however it is built. Use:

- `service.name` — the agent's canonical name
- `deployment.environment` — production / staging / development
- `team` — owning team
- `owner` — owning sub-team or person (where supported)
- an agent name consistent with all of the above

Examples:

```
support-agent:
  service.name           = support-agent
  deployment.environment = production
  team                   = customer-support
  owner                  = support-platform

finance-analyst-agent:
  service.name           = finance-analyst-agent
  deployment.environment = staging
  team                   = finance
  owner                  = finance-ops
```

**Why this matters:** this identity is how Observe groups runtime traces into AI systems. `service.name` becomes the AI system's name in Asset Intelligence; if it is missing, the agent shows up as an anonymous `observed-ai-system:…` entry. Environment and team drive the ownership and risk context you'll verify later. Decide these names *before* you build, and use them identically everywhere (instrumentation, API key names, gateway attribution).

### 4.4 Connect real agents through OpenTelemetry (Level 2)

The exact code depends on the tool or framework, but **the telemetry shape must be consistent**. Whatever the agent is built in, each run should produce:

1. **One root span for the agent run** — e.g. `handle_customer_escalation`, `analyze_finance_question`.
2. **Child spans for each step** the agent takes:
   - LLM call
   - retrieval
   - tool call
   - database call
   - external API call
   - workflow action
3. **Attributes** on those spans (these are the names Observe reads):
   - `gen_ai.system` (provider, e.g. `openai`) and `gen_ai.request.model` on LLM spans
   - `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens`
   - `tool.name` on tool spans (`mcp.server` + `mcp.tool.name` for MCP-style tools)
   - `db.system` on database spans
   - `url.full` on external API spans
   - error status (`StatusCode.ERROR`) where a step fails
4. **Send spans to the local OpenTelemetry Collector** (setup in §6).
5. **The Collector forwards OTLP/HTTP JSON to Observe.** (Observe's OTLP endpoint is JSON-only; the Collector handles the conversion.)

Privacy rule, verbatim, regardless of framework: never send `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`, `gen_ai.request.messages`, `gen_ai.response.choices`, `tool.arguments`, or `tool.result`. Metadata only — no prompt or response text on spans.

How the pattern maps to specific tools:

- **LangChain** — add spans around chain/agent steps via callbacks, or use a community OpenTelemetry instrumentation for LangChain if you prefer. If you use third-party auto-instrumentation, **verify the attribute names it emits**: some libraries use their own conventions, and the attributes listed above are what Observe reads. Where names differ, add them yourself on a wrapping span.
- **CrewAI** — wrap each crew/task execution in a root span and each agent/tool step in child spans (step callbacks or a thin wrapper around task execution both work).
- **n8n** — n8n workflows don't natively emit these spans; either add an HTTP node at workflow start/end that reports to a tiny local shim which emits the spans, or wrap the workflow invocation in a small script that creates the root span and calls the workflow. Treat this as the most manual of the options.
- **Plain apps / local agent services** — instrument directly with the OpenTelemetry SDK for the app's language; the Python `shared/telemetry.py` helper in §8 is a reusable starting point even for real agents.

Whichever route you take, the check is the same: run the agent once, open Runtime, and confirm the trace has a root span with nested children carrying the attributes above.

### 4.5 Connect real agents through the Gateway (Level 1)

For agents that already use an OpenAI-compatible or Anthropic-compatible client, you can skip instrumentation and route their model calls through the Observe Gateway.

**Important: this is not an Observe SDK.** The agent keeps its existing provider SDK/client; only the base URL changes.

The pattern, for any tool:

1. Use the agent's **existing provider SDK/client**.
2. Change the base URL to the Observe Gateway (`https://<your-observe-url>/v1`).
3. Use the Observe API key (`gk-…`) as the client's API key.
4. Configure provider credentials in Observe (Settings → Provider Credentials) if you want live calls to complete.
5. Run the agent.
6. Check whether activity appears in Observe.

**Use this path when the tool supports changing the model provider base URL.** Do not assume every tool does — verify in the tool's settings first. Examples:

- **OpenAI SDK agent** — set `base_url` + `api_key` on the client (working example in §7.2).
- **LangChain** — most OpenAI-compatible chat model classes accept a `base_url` (or `openai_api_base`) parameter; point it at the gateway.
- **LiteLLM** — LiteLLM-based apps let you set a custom `api_base` per model or route through its proxy config; point either at the gateway.
- **n8n** — if your n8n version's OpenAI credential supports a custom base URL, point it at the gateway; if it doesn't, use the OpenTelemetry path for that workflow instead.

Expected behavior without provider credentials in Observe: a clear `provider_not_configured` error. That is the correct, designed response — verifying that the error is clean is itself part of the QA (details in §7.3).

### 4.6 Link the agents to the fake company

"Linking" an agent to Acme AI Operations does **not** mean manually registering a static agent record. It means making the agent's real runtime behavior attributable:

- Use the **same Observe organization** (and its API keys) for all five agents.
- **Name keys by team or service** — `support-agent-prod`, `finance-analyst-staging` — so activity is attributable per key.
- Set **`service.name` consistently** with the identity table in §4.3.
- Set **`deployment.environment`** on every agent.
- Use **team / owner metadata** where the connection path supports it (resource attributes on OTel; attribution headers on the gateway).
- **Run the agents.** Discovery comes from observed runtime behavior — an agent that never runs is invisible, and that's the product working as designed.

### 4.7 Manual run plan (one week)

A day-by-day plan you can follow. Each day: build one real agent, connect it, run it, verify one part of the product.

**Day 1 — support-agent**
- Create `support-agent` using a real framework (LangChain, an OpenAI-compatible app, or a simple local agent — see the §5 checklist).
- Connect it through OTel (§4.4/§6) or the Gateway (§4.5/§7).
- Run 3–5 escalation tasks with fake customers and fake tickets.
- Verify: **Runtime** shows the runs; **Asset Intelligence** shows a `support-agent` system card.

**Day 2 — finance-analyst-agent**
- Create it (CrewAI or a local agent app), staging or production.
- Include a database-like tool (`db.system=postgresql` on the span, or a fake SQL tool).
- Run a few finance questions.
- Verify: **Security Intelligence** shows database access on a finance agent.

**Day 3 — engineering-copilot**
- Create it (LiteLLM-based app, local app, or CrewAI), staging.
- Include a repo-search tool and an MCP-like tool (`mcp.server` / `mcp.tool.name`).
- Run a few repo-context requests.
- Verify: the agent's **tools and dependencies** appear on its Asset Intelligence card, including the MCP dependency.

**Day 4 — hr-onboarding-bot**
- Create it (n8n AI workflow or a local app), production.
- Include handbook retrieval, a workflow-task action, and a Slack-like notification.
- Run a few onboarding questions.
- Verify: **dependencies** (KB, workflow tool, Slack-like endpoint) appear on the card.

**Day 5 — research-agent**
- Create it (OpenAI-compatible app or local agent), development.
- Include a web-like search source, an external API call, and **one controlled error** (a step that deliberately fails and sets error status).
- Run it a few times.
- Verify: **Runtime** shows the error; **Security Intelligence** picks up external APIs and runtime errors; **Guardrails** shows relevant observe-only signals.

**End of week**
- All five agents appear in Observe.
- Asset Intelligence groups them into five AI systems with models, tools, and dependencies.
- Security, Cost, and Guardrails have meaningful signals.
- You have personally done what a real customer's platform team would do — that's the point.

### 4.8 Verification after each real agent runs

After each agent's first runs, check exactly this:

**Runtime**
- [ ] Did the agent run appear?
- [ ] Are traces grouped under the right service name?
- [ ] Is there a useful timeline (nested steps with durations), not a flat list?

**Asset Intelligence**
- [ ] Did the agent become an AI system (one grouped card)?
- [ ] Are models / tools / dependencies visible?
- [ ] Are capabilities and findings generated?

**Security Intelligence**
- [ ] Did database / external API / MCP / broad-tool-access risks appear where the agent has them?

**Cost Intelligence**
- [ ] Did slow or heavy workflows appear? Token-heavy agents surfacing as potential hotspots?

**Guardrails**
- [ ] Did observe-only guardrails trigger on the observed behavior?
- [ ] Is it clear nothing was blocked?

**Setup / Integrations**
- [ ] Does the UI explain how this connection works, in the terms you actually used (OpenTelemetry or Gateway with existing clients)?

---

## 5. Recommended first real agent: support-agent

Start with `support-agent`. It is easy to understand and produces the richest spread of signals in one agent: LLM planning, retrieval, CRM lookup, Jira lookup, Slack notification, a production environment, and external API dependencies.

Concrete checklist:

1. [ ] **Choose a framework:** LangChain, an OpenAI-compatible app, or a simple local agent — whichever you can stand up fastest.
2. [ ] **Give it the name `support-agent`** (as `service.name`, and in the API key name).
3. [ ] **Give it four fake tools:**
   - `search_knowledge_base` — searches a local folder of fake help articles
   - `lookup_customer` — reads a fake CRM (a local JSON file of invented accounts)
   - `search_jira` — returns fake ticket matches
   - `notify_slack` — pretends to post an update (logs it, or POSTs to a fake local endpoint)
4. [ ] **Connect it** using OTel (§4.4 + §6) or the Gateway (§4.5 + §7).
5. [ ] **Run 3 test prompts** — e.g. "Customer DataFlow Ltd. reports sync failures since yesterday, escalate and summarize," with fake customer names and fake tickets throughout.
6. [ ] **Verify it appears in Observe** using the §4.8 checklist.

Do not include real sensitive data anywhere — fake customers, fake tickets, fake URLs only.

---

## 6. Connection reference A: OpenTelemetry / OTLP

Shared plumbing for every OTel-connected agent (Level 2, and the Level 3 fallback). Set this up once.

### 6.1 Create an API key in Observe

1. Open Observe in your browser and make sure you are in the right organization.
2. Go to **API Keys**.
3. Create a key named `support-agent-prod` (create more per team/service as you add agents).
4. Copy the key **immediately** — it is shown once.
5. Store it in your local `.env` as `OBSERVE_API_KEY`.

**Expected:** the key starts with `gk-`. If you lose it, revoke it and create a new one.

### 6.2 Environment variables

Create a local `.env` (never commit it):

```bash
# ── Observe target ────────────────────────────────────────────────
OBSERVE_URL=https://<your-observeagents-url>
OBSERVE_API_KEY=gk-<your-api-key>

# ── Where local agents send spans (the local Collector) ──────────
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces

# ── Fake company identity ────────────────────────────────────────
FAKE_COMPANY_NAME=Acme AI Operations
FAKE_ENVIRONMENT=local

# ── Gateway path (§7) ────────────────────────────────────────────
# For a self-hosted instance this is your Observe URL + /v1
OBSERVE_GATEWAY_URL=https://<your-observeagents-url>/v1
OBSERVE_GATEWAY_API_KEY=gk-<your-api-key>

# ── Optional: only if you test live gateway calls with real providers ──
# OPENAI_API_KEY=<provider-key-if-needed>
# ANTHROPIC_API_KEY=<provider-key-if-needed>
```

### 6.3 Start an OpenTelemetry Collector

**Why the Collector (recommended, no longer required):** Observe now accepts **both OTLP/HTTP JSON and protobuf**, so agents can post directly. The Collector remains the recommended path for this simulation because it mirrors an enterprise rollout: local buffering, retries, and one place to route every agent's telemetry.

Create `otel-collector.yaml`:

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
      grpc:
        endpoint: 0.0.0.0:4317

exporters:
  otlphttp/observeagents:
    # The exporter appends /v1/traces automatically,
    # so this must end with /otel (NOT /otel/v1/traces).
    endpoint: ${env:OBSERVE_URL}/otel
    encoding: json          # json shown; Observe also accepts protobuf directly
    headers:
      Authorization: "Bearer ${env:OBSERVE_API_KEY}"

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [otlphttp/observeagents]
```

Run it with Docker (with `.env` values exported into your shell):

```bash
set -a; source .env; set +a   # export OBSERVE_URL and OBSERVE_API_KEY

docker run --rm \
  -p 4318:4318 -p 4317:4317 \
  -e OBSERVE_URL -e OBSERVE_API_KEY \
  -v "$(pwd)/otel-collector.yaml":/etc/otelcol-contrib/config.yaml \
  otel/opentelemetry-collector-contrib:latest
```

Leave this running. Every OTel-connected agent — whatever framework it's built in — sends spans to `http://localhost:4318/v1/traces`, and the Collector forwards them to Observe.

### 6.4 Troubleshooting table

| Symptom | Meaning | Fix |
|---|---|---|
| `401` in Collector export logs | API key / auth problem | Re-check `OBSERVE_API_KEY` and the `Authorization: Bearer` header in `otel-collector.yaml` |
| `415` | Protobuf sent directly to Observe | You bypassed the Collector, or `encoding: json` is missing from the exporter |
| Trace missing entirely | Wrong URL or Collector not forwarding | Check `OBSERVE_URL` has no trailing slash, exporter endpoint ends in `/otel`, Collector logs show exports |
| Timeline is flat (no nesting) | Parent/child relationship lost | Ensure child spans are created inside the root span's context |
| Asset named `observed-ai-system:…` | `service.name` missing | Set `service.name` in the agent's OTel Resource |

---

## 7. Connection reference B: Gateway / existing provider SDK path

For Level 1 agents. Once more, because wording matters in every demo: **do not call this an Observe SDK.** It is the *Gateway / existing provider SDK path* — the agent keeps using the OpenAI SDK (or Anthropic SDK, LangChain, LiteLLM, any OpenAI-compatible client) and only changes the base URL.

### 7.1 Configure provider credentials (optional)

1. Open **Settings** in Observe.
2. Find the **Provider Credentials** section.
3. Add a provider credential (e.g. an OpenAI key) **only if** you want live gateway calls to complete.
4. If you do not add credentials, that's a valid test too: expect a clear `provider_not_configured` error from the gateway. Confirming that error is clean and explanatory is part of the QA.

### 7.2 OpenAI-compatible example

The minimal working shape, standard OpenAI client, different base URL:

```python
"""Gateway path: OpenAI SDK pointed at the Observe Gateway.

This is NOT an Observe SDK — it is the standard OpenAI client
with a different base_url. If no provider credential is configured
in Observe, expect a provider_not_configured error (that is the
correct, expected behavior).
"""
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url=os.environ["OBSERVE_GATEWAY_URL"],       # e.g. https://<observe-url>/v1
    api_key=os.environ["OBSERVE_GATEWAY_API_KEY"],    # your gk-... key
    default_headers={                                 # optional attribution
        "X-Guard-Team": "customer-support",
        "X-Guard-Agent": "support-agent",
    },
)

resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Say hello from Acme's gateway test."}],
    max_tokens=20,
)
print(resp.choices[0].message.content)
```

The same shape applies inside real frameworks: give LangChain's OpenAI-compatible chat model the gateway `base_url`, or set LiteLLM's `api_base` to the gateway. The message content here is throwaway test text; the gateway proxies it to the provider, and Observe does not persist raw prompt/response content.

### 7.3 cURL gateway smoke test

The gateway exposes an OpenAI-compatible `POST /v1/chat/completions`, so a cURL smoke test works without any SDK:

```bash
set -a; source .env; set +a

curl -sS -X POST "$OBSERVE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $OBSERVE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Gateway smoke test from Acme."}],
    "max_tokens": 20
  }'
```

**Expected:**

- Provider credential configured → a normal chat completion response.
- No provider credential → an error whose type is `provider_not_configured`, telling you clearly what to configure. **Pass** means the error is clear, not that the call succeeds.
- In either case: no unexpected blocking. Teams are in observe mode by default; requests must not be rejected by policy unless you intentionally enabled enforcement.

### 7.4 What to verify in Observe

- [ ] Request activity appears where gateway telemetry is shown
- [ ] Model / provider usage appears, if the call completed
- [ ] Cost Intelligence may show usage signals from the gateway calls
- [ ] Guardrails remain advisory — nothing was blocked
- [ ] Nowhere in the flow did the product describe this as an "Observe SDK"

---

## 8. Level 3 fallback: pure Python trace simulation

> **Fallback only.** These scripts fabricate realistic spans without any real agent behind them. They are the fastest way to test OTel ingestion and fill dashboards, but they do **not** prove real customer onboarding — no real framework, prompt loop, or tool execution is involved. Prefer §4's real agents; reach for this when you just need pipes tested or data on screen quickly.

Create this folder **on your machine** (intentionally not committed to the Observe repository):

```
examples/fake_customer_company/
  requirements.txt                       # Python dependencies
  .env                                   # from §6.2 (never commit)
  otel-collector.yaml                    # from §6.3
  run_all_agents.py                      # runs all five simulated agents
  agents/
    __init__.py                          # empty file
    support_agent.py
    finance_analyst_agent.py
    engineering_copilot.py
    hr_onboarding_bot.py
    research_agent.py
  shared/
    __init__.py                          # empty file
    telemetry.py                         # tracer/provider factory
    fake_tools.py                        # fake latency + fake identifiers
    config.py                            # loads .env
```

`requirements.txt`:

```
opentelemetry-api
opentelemetry-sdk
opentelemetry-exporter-otlp-proto-http
requests
python-dotenv

# Optional — only for the gateway example in §7.2:
openai
```

Setup: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` (Windows: `.venv\Scripts\activate`).

### 8.1 Shared helpers

`shared/config.py`:

```python
"""Loads .env and exposes simulation settings."""
import os
from dotenv import load_dotenv

load_dotenv()

COMPANY_NAME = os.getenv("FAKE_COMPANY_NAME", "Acme AI Operations")
OTLP_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318/v1/traces"
)
```

`shared/telemetry.py` — also a reusable starting point for instrumenting *real* Python agents (§4.4):

```python
"""Tracer factory for the fake Acme agents.

Each agent gets its OWN TracerProvider so that five different
service.name values can coexist in one process (run_all_agents.py).
"""
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

from shared.config import COMPANY_NAME, OTLP_ENDPOINT


def build_tracer(service_name: str, environment: str, team: str):
    """Return (tracer, provider) for one agent.

    The caller MUST call provider.shutdown() when done so buffered
    spans are flushed to the Collector before the process exits.
    """
    resource = Resource.create({
        "service.name": service_name,             # becomes the AI system name
        "deployment.environment": environment,    # production / staging / development
        "team": team,                             # ownership signal
        "company.name": COMPANY_NAME,
    })
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT))
    )
    return provider.get_tracer(service_name), provider
```

`shared/fake_tools.py`:

```python
"""Fake latency and fake identifiers. Nothing here touches a real system."""
import random
import time


def fake_call(min_ms: int, max_ms: int) -> None:
    """Sleep like a real downstream call would."""
    time.sleep(random.uniform(min_ms, max_ms) / 1000.0)


def fake_id(prefix: str) -> str:
    return f"{prefix}-{random.randint(1000, 9999)}"
```

### 8.2 Simulated support-agent (reference script)

`agents/support_agent.py`. Note what it **never** does: no prompt or response text on any span — no `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`, `gen_ai.request.messages`, `gen_ai.response.choices`, `tool.arguments`, `tool.result`.

```python
"""support-agent — Customer Support / production.

Simulates handling one customer escalation:
plan (LLM) → search KB → look up CRM → search Jira → notify Slack.
"""
from shared.telemetry import build_tracer
from shared.fake_tools import fake_call, fake_id

SERVICE = "support-agent"
ENVIRONMENT = "production"
TEAM = "customer-support"


def run() -> None:
    tracer, provider = build_tracer(SERVICE, ENVIRONMENT, TEAM)

    with tracer.start_as_current_span("handle_customer_escalation") as root:
        root.set_attribute("agent.name", SERVICE)
        root.set_attribute("escalation.id", fake_id("ESC"))

        with tracer.start_as_current_span("llm.plan") as span:
            span.set_attribute("gen_ai.system", "openai")
            span.set_attribute("gen_ai.operation.name", "chat")
            span.set_attribute("gen_ai.request.model", "gpt-4o")
            span.set_attribute("gen_ai.usage.input_tokens", 812)
            span.set_attribute("gen_ai.usage.output_tokens", 214)
            fake_call(900, 1600)

        with tracer.start_as_current_span("retrieval.search_knowledge_base") as span:
            span.set_attribute("tool.name", "vector_search")
            span.set_attribute("retrieval.top_k", 5)
            fake_call(200, 500)

        with tracer.start_as_current_span("crm.lookup_customer") as span:
            span.set_attribute("tool.name", "crm_account_lookup")
            span.set_attribute(
                "url.full",
                f"https://crm.acme-internal.example.com/api/accounts/{fake_id('ACC')}",
            )
            fake_call(300, 700)

        with tracer.start_as_current_span("jira.search_tickets") as span:
            span.set_attribute("tool.name", "jira_issue_search")
            span.set_attribute(
                "url.full", "https://acme.atlassian.example.net/rest/api/3/search"
            )
            fake_call(250, 600)

        with tracer.start_as_current_span("slack.notify_channel") as span:
            span.set_attribute("tool.name", "slack_channel_update")
            span.set_attribute(
                "url.full", "https://slack.example.com/api/chat.postMessage"
            )
            fake_call(100, 300)

    provider.shutdown()  # flush spans to the Collector
    print(f"[{SERVICE}] escalation trace sent.")


if __name__ == "__main__":
    run()
```

### 8.3 The other four simulated agents

Copies of `support_agent.py` with different `SERVICE` / `ENVIRONMENT` / `TEAM` constants and a different span body (same imports, `run()` skeleton, `provider.shutdown()`, `__main__` guard).

**`agents/finance_analyst_agent.py`** — `finance-analyst-agent` / `production` / `finance`. Root span `analyze_finance_question`:

```python
        with tracer.start_as_current_span("llm.analyze") as span:
            span.set_attribute("gen_ai.system", "openai")
            span.set_attribute("gen_ai.request.model", "gpt-4o")
            span.set_attribute("gen_ai.usage.input_tokens", 1430)
            span.set_attribute("gen_ai.usage.output_tokens", 388)
            fake_call(1200, 2000)

        with tracer.start_as_current_span("documents.load_reports") as span:
            span.set_attribute("tool.name", "document_loader")
            fake_call(300, 600)

        with tracer.start_as_current_span("db.query_finance_warehouse") as span:
            span.set_attribute("db.system", "postgresql")   # database-access signal
            span.set_attribute("db.name", "finance_dw")
            fake_call(400, 900)

        with tracer.start_as_current_span("tool.run_variance_calculation") as span:
            span.set_attribute("tool.name", "variance_calculator")
            fake_call(150, 350)
```

**`agents/engineering_copilot.py`** — `engineering-copilot` / `staging` / `engineering`. Root span `assist_engineer_request`:

```python
        with tracer.start_as_current_span("llm.suggest_code") as span:
            span.set_attribute("gen_ai.system", "anthropic")
            span.set_attribute("gen_ai.request.model", "claude-sonnet-5")
            span.set_attribute("gen_ai.usage.input_tokens", 2210)
            span.set_attribute("gen_ai.usage.output_tokens", 640)
            fake_call(1000, 1800)

        with tracer.start_as_current_span("mcp.repo_context") as span:
            span.set_attribute("mcp.server", "repo-context-mcp")   # MCP signal
            span.set_attribute("mcp.tool.name", "repo_search")
            fake_call(250, 500)

        with tracer.start_as_current_span("tool.search_codebase") as span:
            span.set_attribute("tool.name", "code_search")
            fake_call(200, 400)
```

**`agents/hr_onboarding_bot.py`** — `hr-onboarding-bot` / `production` / `hr`. Root span `onboard_new_employee`:

```python
        with tracer.start_as_current_span("llm.answer_question") as span:
            span.set_attribute("gen_ai.system", "openai")
            span.set_attribute("gen_ai.request.model", "gpt-4o-mini")
            span.set_attribute("gen_ai.usage.input_tokens", 540)
            span.set_attribute("gen_ai.usage.output_tokens", 180)
            fake_call(600, 1100)

        with tracer.start_as_current_span("retrieval.hr_knowledge_base") as span:
            span.set_attribute("tool.name", "kb_retrieval")
            fake_call(200, 450)

        with tracer.start_as_current_span("workflow.start_onboarding_checklist") as span:
            span.set_attribute("tool.name", "onboarding_workflow")
            fake_call(150, 350)

        with tracer.start_as_current_span("slack.welcome_message") as span:
            span.set_attribute("tool.name", "slack_channel_update")
            span.set_attribute("url.full", "https://slack.example.com/api/chat.postMessage")
            fake_call(100, 250)
```

**`agents/research_agent.py`** — `research-agent` / `development` / `platform`. Root span `research_topic`, with the **error span** — add one import at the top:

```python
from opentelemetry.trace import Status, StatusCode
```

```python
        with tracer.start_as_current_span("llm.summarize_findings") as span:
            span.set_attribute("gen_ai.system", "openai")
            span.set_attribute("gen_ai.request.model", "gpt-4o-mini")
            span.set_attribute("gen_ai.usage.input_tokens", 960)
            span.set_attribute("gen_ai.usage.output_tokens", 410)
            fake_call(800, 1400)

        with tracer.start_as_current_span("search.web_query") as span:
            span.set_attribute("tool.name", "web_search")
            span.set_attribute(
                "url.full", "https://api.search-provider.example.com/v1/search"
            )
            fake_call(300, 700)

        with tracer.start_as_current_span("external.api_lookup") as span:
            span.set_attribute(
                "url.full", "https://api.data-enrichment.example.org/v2/lookup"
            )
            fake_call(200, 400)
            span.set_status(Status(StatusCode.ERROR, "Upstream API returned 503"))
```

### 8.4 Run the simulation

`run_all_agents.py`:

```python
"""Run every simulated Acme agent, optionally in a loop.

Usage:
    python run_all_agents.py            # one pass
    python run_all_agents.py --loops 5  # five passes (more traces)
"""
import argparse

from agents import (
    support_agent,
    finance_analyst_agent,
    engineering_copilot,
    hr_onboarding_bot,
    research_agent,
)

AGENTS = [
    support_agent,
    finance_analyst_agent,
    engineering_copilot,
    hr_onboarding_bot,
    research_agent,
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loops", type=int, default=1)
    args = parser.parse_args()

    total = 0
    for i in range(args.loops):
        for agent in AGENTS:
            agent.run()
            total += 1
    print(f"Done: {total} agent runs across {len(AGENTS)} agents "
          f"({args.loops} loop(s)). Open Observe → Runtime.")


if __name__ == "__main__":
    main()
```

Start with one agent (`python -m agents.support_agent`), verify with §6.4's troubleshooting table, then run the fleet. Each run produces new trace IDs, so `--loops 3` builds enough volume to populate the dashboards. But remember what this level is for: pipes and screens, not proof of onboarding.

---

## 9. Manual Observe verification after agents run

After running Acme's agents — real ones from §4, or the fallback fleet from §8 — open Observe and walk the pages. For the deeper page-by-page checklist, use the [manual company simulation QA guide](manual_company_simulation_qa_guide.md); this section is the summary version.

### Dashboard
Should answer at a glance: *what is happening across Acme AI Operations?* Activity, systems, and attention items should reflect the runs you just did.

### Runtime
- [ ] Traces from multiple agents (all five by end of week)
- [ ] Realistic durations
- [ ] `research-agent` traces show an error
- [ ] Clicking a trace opens a nested execution timeline

### Asset Intelligence
- [ ] One grouped card per agent — five AI systems
- [ ] Models and providers per agent
- [ ] Tools per agent (KB search, CRM lookup, Jira search, Slack update, calculators, repo search, workflow tools…)
- [ ] Dependencies (CRM / Jira / Slack hosts, databases, the MCP server, external APIs)
- [ ] Capabilities and findings per system

### Security Intelligence
- [ ] Database access (finance-analyst-agent)
- [ ] External API calls (research-agent, support-agent)
- [ ] MCP tool usage (engineering-copilot)
- [ ] Broad tool access where an agent uses many tools
- [ ] Runtime errors (research-agent)
- [ ] Production + sensitive-context signals (finance in production)

### Cost Intelligence
- [ ] Slow traces and heavy workflows surface
- [ ] Usage / cost signals from token counts
- [ ] Potential cost hotspots (the highest-token agents)

### Guardrails
- [ ] Observe-only / advisory framing is explicit
- [ ] Shows which guardrails *would* trigger on the observed behavior
- [ ] Nothing is blocked by default

### Budgets
- [ ] Remains a planning / advisory surface unless enforcement is intentionally enabled

### Pricing Registry
- [ ] Remains a pricing reference layer

### Setup / Integrations
- [ ] Explains the two real connection paths (OpenTelemetry; Gateway with existing clients)
- [ ] No mention of a custom Observe SDK
- [ ] No "SDK Metadata" section
- [ ] No manual X-Agent-* header guidance
- [ ] No demo seed commands in customer-facing copy

---

## 10. End-to-end fake company demo script (5–7 minutes)

| # | Page to open | What to point at | What to say |
|---|---|---|---|
| 1 | — (context) | — | "Acme has AI agents across support, finance, engineering, HR, and platform. Leadership doesn't fully know what's running or what it touches." |
| 2 | — (context) | — | "We built real agents for those teams — in the tools each team would actually use — and connected them to Observe: OpenTelemetry for the instrumented ones, the gateway path for the rest. Everything you're about to see was discovered from their real runs." |
| 3 | **Runtime** | Trace list: five services, three environments, one erroring | "Here's what's actually running — not what someone registered. Note the research agent failing in development." |
| 4 | A `support-agent` trace | The nested timeline: plan → KB → CRM → Jira → Slack | "This is one customer escalation, step by step, with timings. The LLM call, the retrieval, and every system it touched." |
| 5 | **Asset Intelligence** | The five grouped cards | "One card per AI system: models, providers, tools, dependencies, capabilities, findings. This is the AI inventory Acme didn't have." |
| 6 | **Security Intelligence** | Finance agent's database access; the MCP tool; runtime errors | "Which systems need a security conversation: a production finance agent with direct database access, an MCP tool in engineering, an agent that's erroring." |
| 7 | **Cost Intelligence** | Slow/heavy traces, token-heavy agents | "Where time and tokens are going — the signals you'd use to find cost hotspots before the invoice does." |
| 8 | **Guardrails** | The observe-only banner; which guardrails would trigger | "Guardrails are observe-only: Observe detects, explains, and recommends. Nothing is blocked until Acme decides it should be." |
| 9 | — (close) | — | "Next step: connect more agents the same way, and later, ecosystem discovery to find AI systems we didn't instrument at all." |

---

## 11. Final pass/fail checklist

### Fake company
- [ ] Company story and five agent identities defined (§4.1–§4.3)
- [ ] `.env` configured; Collector runs and exports without errors
- [ ] At least one **real** agent created in a real tool/framework and connected
- [ ] The week plan (§4.7) can be followed to all five agents

### Real agents (Levels 1–2)
- [ ] Each agent has stable identity metadata (`service.name`, environment, team, owner)
- [ ] OTel-connected agents produce root + child spans with the §4.4 attributes
- [ ] Gateway-connected agents work through their existing SDK/client with only a base-URL change
- [ ] Frameworks are treated as optional examples — nothing depended on a connector that doesn't exist

### OTel
- [ ] Spans reach Observe through the Collector as OTLP/HTTP JSON
- [ ] Traces visible in Runtime with parent/child nesting
- [ ] Assets discovered with correct names
- [ ] No raw prompt/response text in any span

### Gateway
- [ ] Gateway request works, **or** returns a clear `provider_not_configured` setup error
- [ ] No unexpected blocking in observe mode
- [ ] Never described as an Observe SDK anywhere

### Product
- [ ] Dashboard is clear
- [ ] Runtime is useful
- [ ] Asset Intelligence is grouped per system
- [ ] Security Intelligence is useful
- [ ] Cost Intelligence is useful
- [ ] Guardrails observe-only framing is clear
- [ ] Setup copy is clean (no SDK Metadata / X-Agent headers / seed commands)

### Privacy
- [ ] Fake data only — fake customers, fake tickets, no real records or secrets
- [ ] No prompt or response text sent in spans
- [ ] Raw prompt/response content is not stored by Observe

---

## 12. Known limitations

- **This is a simulation, not a real customer environment** — but with Levels 1–2 it is a *faithful* one: real agents, real runs, fake data.
- **Framework examples are suggestions, not integrations.** No LangChain/CrewAI/n8n/LiteLLM connector is claimed; the connection is always generic OTel or the gateway base-URL change, and some tools won't support the latter.
- **Third-party auto-instrumentation may emit different attribute names** than the `gen_ai.*` / `tool.*` set Observe reads — verify and supplement where needed.
- **Fake tools by design.** CRM/Jira/Slack/handbook are local fakes; no real vendor accounts are contacted or required.
- **Exact cost depends on token and pricing data.** Cost Intelligence shows signals derived from what was observed, not an invoice.
- **The gateway path may require provider credentials** for live calls; without them, the deliverable is the clear `provider_not_configured` behavior.
- **Level 3 proves pipes, not onboarding.** Don't demo Python-simulated traces as evidence of real-customer readiness.
- **Ecosystem Discovery connectors are still future** — this simulation covers runtime and gateway observation only.
- **Observe Advisor / ML recommendations may still be roadmap** — don't expect them in this pass.
- **Do not test enforcement unless you intentionally enable it** for a specific team. The simulation is designed for observe-only mode, which is the default and the recommended starting point.
