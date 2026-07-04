# Fake Customer Company Simulation Guide

*How to build and run a simulated company with AI agents to test Observe end-to-end.*

This is an internal dogfooding guide. You (the founder / product tester) run everything in it manually. Nothing in this guide runs automatically, nothing here was executed when the guide was written, and no example files exist in the repository yet — every file below is something **you create locally** by copying the code blocks.

Companion documents:

- [Manual company simulation QA guide](manual_company_simulation_qa_guide.md) — the in-app, page-by-page QA walkthrough. Use it *after* this guide has data flowing.
- [Organization implementation guide](organization_implementation_guide.md) — the customer-facing technical setup reference.

---

## 1. What this simulation is

This guide creates a **fake company outside Observe**.

That distinction matters. Creating an organization record *inside* Observe gives you an empty workspace. This guide instead builds the thing Observe exists to observe: a small local company simulation with teams and AI agents that actually run, produce spans, call fake tools, touch fake databases, hit fake external APIs, and occasionally fail.

The company has teams. The teams run AI agents. The agents execute realistic local workflows and generate telemetry. Observe receives that telemetry and should discover, on its own:

- AI systems (one per agent)
- Runtime traces and execution timelines
- Models and providers
- Tools and dependencies
- Capabilities
- Findings
- Cost / usage signals
- Guardrail signals

This simulates how a real customer adopts Observe: they don't type their AI inventory into a form — their systems run, and Observe builds the picture from observed behavior.

**Safety framing:** every agent is a local simulation. No real OpenAI, Jira, Slack, or CRM is called. All identifiers, URLs, tokens counts, and customer references are fake. You will run everything yourself, by hand, when you choose to.

---

## 2. Fake company profile

| | |
|---|---|
| **Company** | Acme AI Operations |
| **Industry** | B2B SaaS / Customer Support Automation |
| **Teams** | Platform, Customer Support, Finance, Engineering, HR, Security |

**Business story:** Acme uses AI agents across the company. Leadership does not fully know which agents are running, what they connect to, or where there are risks. Some agents were built by central Platform, some by individual teams. Acme wants Observe to show the real AI footprint — what exists, what is actually running, what it connects to, and where it needs attention.

---

## 3. Agents to simulate

| Agent | Team | Environment | Purpose | Signals to generate |
|---|---|---|---|---|
| `support-agent` | Customer Support | production | Handles customer escalations | LLM planning, retrieval, CRM, Jira, Slack |
| `finance-analyst-agent` | Finance | production | Analyzes finance questions | LLM, documents, database, calculation tool |
| `engineering-copilot` | Engineering | staging | Helps engineers with repo context | LLM, repo search, MCP-like tool, code suggestions |
| `hr-onboarding-bot` | HR | production | Helps with employee onboarding | LLM, knowledge base, workflow tool, Slack |
| `research-agent` | Platform | development | Researches topics | LLM, web/search API, external API, **one error span** |

Each agent is a small local Python script. It does not call real OpenAI, Jira, Slack, or CRM — it *sleeps* where a real call would take time and *sets span attributes* describing what a real call would look like. The goal is to produce realistic spans and metadata, safely.

---

## 4. Two ways the fake company sends data to Observe

The simulation covers both ingestion paths, because real customers arrive with both profiles.

### Path A — OpenTelemetry / OTLP

The fake agents create OpenTelemetry spans and send them to Observe. **This is the preferred path** — it produces the richest picture.

It should produce:

- Parent/child span hierarchy (the execution timeline)
- `service.name` per agent (this becomes the AI system's name)
- `deployment.environment` (production / staging / development)
- `team` (resource attribute for ownership)
- `gen_ai.system` and `gen_ai.request.model` (provider + model discovery)
- Token counts (`gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens`)
- `tool.name` on tool spans
- `db.system` on database spans
- `url.full` on external API spans
- Error spans (status `ERROR`)

### Path B — Gateway using existing provider SDKs

The fake company routes AI requests through the Observe Gateway using an **existing SDK or OpenAI-compatible client** — the OpenAI SDK, the Anthropic SDK, LangChain, LiteLLM, or plain cURL — pointed at the gateway's base URL.

**Important: this is not a custom Observe SDK.** There is no Observe SDK. The correct wording is *"Gateway / existing provider SDK path"* — e.g. "OpenAI SDK with Observe Gateway base_url."

This path validates the teams that do not yet have OpenTelemetry. It should produce:

- Gateway-observed requests
- Model / provider usage
- Token / cost signals where supported
- Advisory (observe-only) behavior by default — nothing blocked
- A clear `provider_not_configured` error if provider keys are missing (this is correct behavior, not a bug)

---

## 5. Recommended local project structure

Create this folder **on your machine** (it is intentionally *not* committed to the Observe repository — it plays the role of the customer's codebase):

```
examples/fake_customer_company/
  README.md                              # one paragraph: what this is, how to run it
  requirements.txt                       # Python dependencies
  .env.example                           # environment variable template (copy to .env)
  otel-collector.yaml                    # OpenTelemetry Collector config (Path A)
  run_all_agents.py                      # runs all five agents in sequence
  agents/
    __init__.py                          # empty file (makes agents/ importable)
    support_agent.py                     # Customer Support / production
    finance_analyst_agent.py             # Finance / production, DB + calc tool
    engineering_copilot.py               # Engineering / staging, MCP-like tool
    hr_onboarding_bot.py                 # HR / production, KB + workflow + Slack
    research_agent.py                    # Platform / development, error span
  shared/
    __init__.py                          # empty file (makes shared/ importable)
    telemetry.py                         # tracer/provider factory (Resource + exporter)
    fake_tools.py                        # fake latency + fake identifier helpers
    config.py                            # loads .env, exposes settings
  gateway/
    openai_compatible_gateway_test.py    # Path B: OpenAI SDK → Observe Gateway
```

All file contents are given below as copy-paste blocks. Create the two empty `__init__.py` files yourself (`touch agents/__init__.py shared/__init__.py`).

---

## 6. Environment variables

Create `.env.example` (and copy it to `.env` with real values):

```bash
# ── Observe target ────────────────────────────────────────────────
OBSERVE_URL=https://<your-observeagents-url>
OBSERVE_API_KEY=gk-<your-api-key>

# ── Where the local agents send spans (the local Collector) ──────
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces

# ── Fake company identity ────────────────────────────────────────
FAKE_COMPANY_NAME=Acme AI Operations
FAKE_ENVIRONMENT=local

# ── Gateway path (Path B) ────────────────────────────────────────
# For a self-hosted instance this is your Observe URL + /v1
OBSERVE_GATEWAY_URL=https://<your-observeagents-url>/v1
OBSERVE_GATEWAY_API_KEY=gk-<your-api-key>

# ── Optional: only if you test live gateway calls with real providers ──
# OPENAI_API_KEY=<provider-key-if-needed>
# ANTHROPIC_API_KEY=<provider-key-if-needed>
```

Rules:

- **Use fake data everywhere.** No real customer names, records, or prompt content.
- Provider keys are optional — they matter only if you want Path B to complete a *live* provider call. Without them, Path B still validates the gateway's error behavior (`provider_not_configured`), which is itself a QA check.
- Never commit `.env` anywhere.

---

## 7. Detailed setup: OpenTelemetry path

This is the main event. Work through it in order.

### 7.1 Create an API key in Observe

1. Open Observe in your browser and make sure you are in the right organization.
2. Go to **API Keys**.
3. Create a key named `support-agent-prod` (one key is enough for the whole simulation; create per-agent keys later if you want per-key attribution).
4. Copy the key **immediately** — it is shown once.
5. Put it in `.env` as `OBSERVE_API_KEY` (and `OBSERVE_GATEWAY_API_KEY`).

**Expected:** the key starts with `gk-`. If you lose it, revoke it and create a new one.

### 7.2 Start an OpenTelemetry Collector

**Why a Collector is required:** Observe's OTLP endpoint accepts **JSON only** — direct protobuf posts are rejected with `415`. The Python OTLP exporter sends protobuf. The Collector bridges the two: your agents send protobuf to the Collector locally, and the Collector forwards **OTLP/HTTP JSON** to Observe.

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
    encoding: json          # REQUIRED — Observe rejects protobuf with 415
    headers:
      Authorization: "Bearer ${env:OBSERVE_API_KEY}"

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [otlphttp/observeagents]
```

Run it with Docker (from the `examples/fake_customer_company/` folder, with `.env` values exported into your shell):

```bash
set -a; source .env; set +a   # export OBSERVE_URL and OBSERVE_API_KEY

docker run --rm \
  -p 4318:4318 -p 4317:4317 \
  -e OBSERVE_URL -e OBSERVE_API_KEY \
  -v "$(pwd)/otel-collector.yaml":/etc/otelcol-contrib/config.yaml \
  otel/opentelemetry-collector-contrib:latest
```

Leave this terminal running. Your fake agents send spans to `http://localhost:4318/v1/traces`; the Collector forwards them to Observe.

**Expected:** the Collector logs show it started and, once agents run, no export errors. A `401` in the Collector's export logs means the `Authorization` header / key is wrong.

### 7.3 Install Python dependencies

Create `requirements.txt`:

```
opentelemetry-api
opentelemetry-sdk
opentelemetry-exporter-otlp-proto-http
requests
python-dotenv

# Optional — only for the gateway test in gateway/ (Path B):
openai
```

Then:

```bash
cd examples/fake_customer_company
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows note:** activate with `.venv\Scripts\activate` instead of `source .venv/bin/activate`.

### 7.4 Shared telemetry helper

Create `shared/config.py`:

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

Create `shared/telemetry.py`:

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

Create `shared/fake_tools.py`:

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

### 7.5 Example support-agent

Create `agents/support_agent.py` — the full reference agent. Note what it **never** does: it never sets prompt or response text on any span. No `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`, `gen_ai.request.messages`, `gen_ai.response.choices`, `tool.arguments`, or `tool.result`. Metadata only.

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

### 7.6 Additional agents

The other four agents are copies of `support_agent.py` with a different `SERVICE` / `ENVIRONMENT` / `TEAM` header and a different span body. Only the differing span bodies are shown here — keep the same imports, `run()` skeleton, `provider.shutdown()`, and `__main__` guard.

**`agents/finance_analyst_agent.py`** — `finance-analyst-agent` / `production` / `finance`. High-risk context: a production finance agent with direct database access. Root span `analyze_finance_question`:

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

The `db.system=postgresql` span on a production finance agent is deliberate: it should surface as a database-access capability and feed Security Intelligence. Whether it also produces a high-severity finding depends on the current finding-derivation rules — treat a finding as a bonus, and the capability as the required outcome.

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

The `mcp.server` attribute is what marks the tool as MCP — expect an MCP dependency and MCP-tool capability on this agent's card.

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

**`agents/research_agent.py`** — `research-agent` / `development` / `platform`. Root span `research_topic`, and this is the agent with the **error span** — add one import at the top:

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

The error span should show up as a failed step in the execution timeline and as a runtime-error signal on the agent.

### 7.7 Run one agent

Do the first end-to-end run with a single agent before running the fleet.

1. Make sure Observe is running (local backend + dashboard, or your hosted deployment) and you are logged in to the right organization.
2. Make sure the Collector from §7.2 is running.
3. From `examples/fake_customer_company/` with the venv active, run:
   ```bash
   python -m agents.support_agent
   ```
4. Open **Runtime** in Observe.
5. Find `support-agent` in the trace list.
6. Click the trace.
7. Verify the execution timeline.

**Pass:**

- [ ] The trace appears in Runtime within seconds
- [ ] The timeline shows the root span with five children nested under it
- [ ] Model (`gpt-4o`), provider (OpenAI), tool names, and the CRM/Jira/Slack dependencies are visible
- [ ] No raw prompt or response text appears anywhere

**Fail — check this table:**

| Symptom | Meaning | Fix |
|---|---|---|
| `401` in Collector export logs | API key / auth problem | Re-check `OBSERVE_API_KEY` and the `Authorization: Bearer` header in `otel-collector.yaml` |
| `415` | Protobuf sent directly to Observe | You bypassed the Collector, or `encoding: json` is missing from the exporter |
| Trace missing entirely | Wrong URL or Collector not forwarding | Check `OBSERVE_URL` ends with no trailing slash, exporter endpoint ends in `/otel`, Collector logs show exports |
| Timeline is flat (no nesting) | Parent/child relationship lost | Ensure child spans are created *inside* the root span's `with` block |
| Asset named `observed-ai-system:…` | `service.name` missing | Check the `Resource.create` block in `shared/telemetry.py` |

### 7.8 Run all fake agents

Create `run_all_agents.py`:

```python
"""Run every fake Acme agent, optionally in a loop.

Usage:
    python run_all_agents.py            # one pass
    python run_all_agents.py --loops 5  # five passes (more traces, better dashboards)
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

Each run produces new trace IDs, so looping builds volume: more traces per agent, duration spread, and repeated error spans from `research-agent`.

**Expected result after `--loops 3` or so:**

- **Runtime** shows traces from all five agents, across production / staging / development
- **Asset Intelligence** groups the activity into five AI systems
- **Security, Cost, and Guardrails** pages become populated from the observed behavior

---

## 8. Detailed setup: Gateway / existing provider SDK path

This simulates a customer team that does **not** have OpenTelemetry but can route its AI calls through a gateway with a one-line base-URL change.

Once more, because wording matters in every demo: **do not call this an Observe SDK.** It is the *Gateway / existing provider SDK path* — the customer keeps using the OpenAI SDK (or Anthropic SDK, LangChain, LiteLLM, any OpenAI-compatible client) and only changes the base URL.

### 8.1 Configure provider credentials (optional)

1. Open **Settings** in Observe.
2. Find the **Provider Credentials** section.
3. Add a provider credential (e.g. an OpenAI key) **only if** you want live gateway calls to complete.
4. If you do not add credentials, that's a valid test too: expect a clear `provider_not_configured` error from the gateway. Confirming that error is clean and explanatory is part of the QA.

### 8.2 OpenAI-compatible example

Create `gateway/openai_compatible_gateway_test.py`:

```python
"""Path B: OpenAI SDK pointed at the Observe Gateway.

This is NOT an Observe SDK — it is the standard OpenAI client
with a different base_url. Only run this when you are ready to
test the gateway; if no provider credential is configured in
Observe, expect a provider_not_configured error (that is the
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

Run it with `python gateway/openai_compatible_gateway_test.py` — but only when the Collector story from Path A is done and you deliberately want to exercise Path B. Note the message content here is throwaway test text; the gateway proxies it to the provider but Observe does not persist raw prompt/response content.

### 8.3 cURL gateway smoke test

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
- No provider credential → an error response whose type is `provider_not_configured`, telling you clearly what to configure. **Pass** means the error is clear, not that the call succeeds.
- In either case: no unexpected blocking. Teams are in observe mode by default; requests must not be rejected by policy unless you intentionally enabled enforcement.

### 8.4 What to verify in Observe

- [ ] Request activity appears where gateway telemetry is shown
- [ ] Model / provider usage appears, if the call completed
- [ ] Cost Intelligence may show usage signals from the gateway call
- [ ] Guardrails remain advisory — nothing was blocked
- [ ] Nowhere in the flow did the product describe this as an "Observe SDK"

---

## 9. Manual Observe verification after agents run

After running the fake company's agents (ideally `run_all_agents.py --loops 3`), open Observe and walk the pages. For the deeper page-by-page checklist, use the [manual company simulation QA guide](manual_company_simulation_qa_guide.md); this section is the summary version.

### Dashboard
Should answer at a glance: *what is happening across Acme AI Operations?* Activity, systems, and attention items should reflect the simulation you just ran.

### Runtime
- [ ] Traces from multiple agents (all five if you ran them all)
- [ ] Durations that look like the sleeps you configured
- [ ] `research-agent` traces show an error
- [ ] Clicking a trace opens a nested execution timeline

### Asset Intelligence
- [ ] One grouped card per agent — five AI systems
- [ ] Models and providers (GPT-4o / GPT-4o-mini / OpenAI; the copilot's Anthropic model)
- [ ] Tools (vector_search, crm_account_lookup, jira_issue_search, slack_channel_update, variance_calculator, repo_search, kb_retrieval, onboarding_workflow, web_search)
- [ ] Dependencies (CRM / Jira / Slack hosts, postgres, the MCP server, external APIs)
- [ ] Capabilities and findings per system

### Security Intelligence
- [ ] Database access (finance-analyst-agent → postgresql)
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
- [ ] No mention of a custom Observe SDK
- [ ] No "SDK Metadata" section
- [ ] No manual X-Agent-* header guidance
- [ ] No demo seed commands in customer-facing copy

---

## 10. End-to-end fake company demo script (5–7 minutes)

| # | Page to open | What to point at | What to say |
|---|---|---|---|
| 1 | — (context) | — | "Acme has AI agents across support, finance, engineering, HR, and platform. Leadership doesn't fully know what's running or what it touches." |
| 2 | — (context) | — | "We ran those agents locally and sent their telemetry into Observe — OpenTelemetry for the instrumented teams, the gateway path for the rest. Observe built everything you're about to see from observed behavior." |
| 3 | **Runtime** | Trace list: five services, three environments, one erroring | "Here's what's actually running — not what someone registered. Note the research agent failing in development." |
| 4 | A `support-agent` trace | The nested timeline: plan → KB → CRM → Jira → Slack | "This is one customer escalation, step by step, with timings. The LLM call, the retrieval, and every system it touched." |
| 5 | **Asset Intelligence** | The five grouped cards | "One card per AI system: models, providers, tools, dependencies, capabilities, findings. This is the AI inventory Acme didn't have." |
| 6 | **Security Intelligence** | Finance agent's database access; the MCP tool; runtime errors | "Which systems need a security conversation: a production finance agent with direct Postgres access, an MCP tool in engineering, an agent that's erroring." |
| 7 | **Cost Intelligence** | Slow/heavy traces, token-heavy agents | "Where time and tokens are going — the signals you'd use to find cost hotspots before the invoice does." |
| 8 | **Guardrails** | The observe-only banner; which guardrails would trigger | "Guardrails are observe-only: Observe detects, explains, and recommends. Nothing is blocked until Acme decides it should be." |
| 9 | — (close) | — | "Next step: connect more agents the same way, and later, ecosystem discovery to find AI systems we didn't instrument at all." |

---

## 11. Final pass/fail checklist

### Fake company
- [ ] `examples/fake_customer_company/` folder exists locally
- [ ] `.env` configured from `.env.example`
- [ ] Collector runs and exports without errors
- [ ] At least one agent runs end-to-end
- [ ] All five agents can run (`run_all_agents.py`)

### OTel
- [ ] Spans sent through the Collector as OTLP/HTTP JSON
- [ ] Traces visible in Runtime
- [ ] Execution timeline shows parent/child nesting
- [ ] All five assets discovered with correct names
- [ ] No raw sensitive text in any span

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
- [ ] Fake data only — no real customer records or secrets
- [ ] No prompt or response text sent in spans
- [ ] Raw prompt/response content is not stored by Observe

---

## 12. Known limitations

- **This is a simulation, not a real customer environment.** Latency, volume, and failure patterns are synthetic.
- **Fake agents do not call real vendors.** CRM/Jira/Slack/search URLs are fake `example.com`-style hosts; no external system is contacted by Path A.
- **Exact cost depends on token and pricing data.** Cost Intelligence shows signals derived from what was observed, not an invoice.
- **The gateway path may require provider credentials** for live calls; without them, the deliverable is the clear `provider_not_configured` behavior.
- **Ecosystem Discovery connectors are still future** — this simulation covers runtime and gateway observation only.
- **Observe Advisor / ML recommendations may still be roadmap** — don't expect them in this pass.
- **Do not test enforcement unless you intentionally enable it** for a specific team. The simulation is designed for observe-only mode, which is the default and the recommended starting point.
