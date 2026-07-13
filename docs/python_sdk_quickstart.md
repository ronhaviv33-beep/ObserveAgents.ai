# Python SDK Quickstart — connect your AI agent in 5 minutes

*Customer-facing guide. You install one small SDK package — that's it. You never clone,
install, or run any ObserveAgents platform code: as soon as the SDK wraps your client,
your agents' runtime metadata starts flowing to your ObserveAgents workspace.*

> **Observe first. Control only what matters.**

**Not just OpenAI.** ObserveAgents observes agents built on **any AI provider with an API
connection** — OpenAI, **Claude (Anthropic)**, Google, or your own model endpoints. The
fastest path today is the drop-in `ObserveOpenAI` wrapper for OpenAI-based agents
(Steps 1–5); Claude and every other provider connect through the same runtime-events API
with a few lines of code (see [Claude & other providers](#claude--other-providers--any-ai-system-with-an-api)),
or through standard OpenTelemetry.

**What you get in 5 minutes:** your agent appears in your ObserveAgents inventory with its
model calls, latency, errors, and token usage — no OTel Collector, no span
instrumentation, and no prompt or response ever leaving your process.

---

## Step 1 — Get your API key (1 min)

Log in to your ObserveAgents workspace → **API Keys → Create**. Keys look like `gk-…`.

Recommended: one key per agent or team (e.g. `support-agent-prod`) — attribution stays
clean, and you can revoke one agent's key without touching others.

## Step 2 — Install the SDK (1 min)

```bash
pip install observeagents
```

That's the only thing you install. The SDK has **zero runtime dependencies** (standard
library only) and works alongside the `openai` package your agent already uses.

## Step 3 — Configure (1 min)

Every setting is a constructor argument or an environment variable
(**precedence: constructor arg → env var → default**):

| Setting | Env var | Required? | Default |
|---|---|---|---|
| OpenAI API key | `OPENAI_API_KEY` | ✅ | — |
| ObserveAgents API key (`gk-…`) | `OBSERVEAGENTS_API_KEY` | ✅ | — |
| Agent name | `OBSERVEAGENTS_AGENT_NAME` | ✅ | — |
| ObserveAgents endpoint | `OBSERVEAGENTS_URL` | — | ObserveAgents Cloud |
| Environment | `OBSERVEAGENTS_ENVIRONMENT` | — | `development` |
| Team hint | `OBSERVEAGENTS_TEAM_HINT` | — | unset |
| Owner hint | `OBSERVEAGENTS_OWNER_HINT` | — | unset |

```bash
export OPENAI_API_KEY="sk-..."
export OBSERVEAGENTS_API_KEY="gk-..."
export OBSERVEAGENTS_AGENT_NAME="support-agent"
export OBSERVEAGENTS_ENVIRONMENT="production"
```

By default events go to **ObserveAgents Cloud** — you don't set a URL at all. Set
`OBSERVEAGENTS_URL` only if your organization runs a self-hosted / customer-side
ObserveAgents collector; the wire format, auth, and privacy rules are identical.

## Step 4 — Wrap your client (1 min)

`ObserveOpenAI` is a drop-in for the OpenAI client — same call signature, same return
value, same exceptions. Change one line and keep coding as before:

```python
from observeagents import ObserveOpenAI

client = ObserveOpenAI(
    openai_api_key="sk-...",          # or OPENAI_API_KEY
    observeagents_api_key="gk-...",   # or OBSERVEAGENTS_API_KEY
    agent_name="support-agent",
    environment="production",
    team_hint="support",
)

response = client.chat.completions.create(
    model="gpt-4.1-mini",
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)
```

With env vars set, it shrinks to:

```python
client = ObserveOpenAI()   # everything resolved from the environment
```

From this moment, every `create()` call goes to OpenAI unchanged, and one `llm_call`
runtime event (metadata only) flows to your ObserveAgents workspace.

Useful extras: `session_id="chat-123"` groups related calls into one workflow;
`debug=True` logs a warning when an event fails to deliver (otherwise silent).

## Step 5 — See it in your workspace (1 min)

1. **Run your agent.** The OpenAI call succeeds exactly as before — even if ObserveAgents
   were unreachable (fail-open by design).
2. **Runtime** — a trace for `support-agent` appears within seconds; each completion call
   is one step with its duration and status.
3. **Asset Intelligence** — `support-agent` appears as a discovered AI system with its
   provider, model, environment, and token-usage evidence.
4. **Security Intelligence / Findings** — derived automatically on the next intelligence
   run: ownership gaps, unknown providers, risky patterns. Recommendations only — nothing
   is ever blocked or enforced from SDK events.

## Privacy — what is sent, what is never sent

The SDK builds events from an explicit allow-list of safe fields. There is **no code path**
that copies your request or response bodies into an event.

**Sent (metadata only):**

| Field | Example |
|---|---|
| `agent_name`, `environment`, `team_hint`/`owner_hint` | `support-agent`, `production`, `support` |
| `provider`, `model` | `openai`, `gpt-4.1-mini` |
| `duration_ms`, `status` | `850`, `ok` / `error` |
| `error_type` | exception **class name** only, e.g. `RateLimitError` — never the message |
| `input_tokens` / `output_tokens` | from `response.usage` when available |
| `trace_id` / `span_id` / `session_id` | generated hex ids / your session id |

**Never sent:** prompts · messages · responses · system instructions · tool arguments ·
tool results · headers · credentials (your OpenAI API key is used only to construct the
OpenAI client and never appears in any event, URL, or header sent to ObserveAgents) ·
full URLs with query strings.

The platform independently enforces the same boundary at ingestion — payloads carrying
forbidden fields are rejected, and free-form metadata is scrubbed server-side.

## Error handling — fail-open

- If ObserveAgents is slow, down, or rejecting: your LLM call is **unaffected**. Delivery
  errors are swallowed (one `logging` warning when `debug=True`).
- If the OpenAI call fails: the SDK emits a `status="error"` event (class name only) and
  **re-raises your original exception unchanged** — same type, same message, same traceback.
- The SDK never raises its own exceptions into your call path and never enforces anything.

## Troubleshooting

| Symptom | Check |
|---|---|
| Nothing appears in Runtime | Set `debug=True` and look for a delivery warning; verify the `gk-` key belongs to the workspace you're looking at, and `OBSERVEAGENTS_URL` (if set) has no trailing path |
| `ValueError` at construction | One of the three required settings is missing (OpenAI key, ObserveAgents key, agent name) — this raises immediately, before any LLM call |
| Agent appears but no findings | Findings derive during the intelligence run — they appear shortly after evidence lands, not instantly |

## Claude & other providers — any AI system with an API

The `ObserveOpenAI` wrapper is the one-liner path for OpenAI-based agents, but the
platform itself is **provider-agnostic**: every agent is observed through the same
runtime-events API, whatever model it calls. Until the native Anthropic/LiteLLM wrappers
ship, connecting a **Claude** agent (or any other provider) takes a few lines around your
existing call — same privacy rules, metadata only:

```python
import json, time, urllib.request, uuid
import anthropic

OBSERVEAGENTS_URL = "https://api.observeagents.ai"   # or your self-hosted collector
OBSERVEAGENTS_API_KEY = "gk-..."

def send_runtime_event(provider, model, duration_ms, status,
                       input_tokens=None, output_tokens=None, error_type=None):
    event = {
        "source": "sdk", "event_type": "llm_call",
        "agent_name": "research-agent", "environment": "production",
        "provider": provider, "model": model,
        "duration_ms": round(duration_ms, 1), "status": status,
        "trace_id": uuid.uuid4().hex, "span_id": uuid.uuid4().hex[:16],
    }
    for k, v in (("input_tokens", input_tokens), ("output_tokens", output_tokens),
                 ("error_type", error_type)):
        if v is not None:
            event[k] = v
    req = urllib.request.Request(
        f"{OBSERVEAGENTS_URL}/runtime-events",
        data=json.dumps({"events": [event]}).encode(),
        method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {OBSERVEAGENTS_API_KEY}"},
    )
    try:
        urllib.request.urlopen(req, timeout=2).read()   # fail-open: never break the app
    except Exception:
        pass

client = anthropic.Anthropic()
started = time.monotonic()
try:
    msg = client.messages.create(
        model="claude-sonnet-5", max_tokens=512,
        messages=[{"role": "user", "content": "Hello"}],
    )
    send_runtime_event("anthropic", "claude-sonnet-5",
                       (time.monotonic() - started) * 1000, "ok",
                       input_tokens=msg.usage.input_tokens,
                       output_tokens=msg.usage.output_tokens)
except Exception as exc:
    send_runtime_event("anthropic", "claude-sonnet-5",
                       (time.monotonic() - started) * 1000, "error",
                       error_type=type(exc).__name__)
    raise
```

The same pattern works for **Google, Mistral, local models, or any internal AI service**
— set `provider` and `model` accordingly, and never put prompts, responses, or credentials
in the event. Your Claude agent then appears in Runtime, Asset Intelligence, and Security
Intelligence exactly like an OpenAI one — same inventory, same findings, same engine.

Already emitting **OpenTelemetry**? Point your existing OTLP exporter at ObserveAgents
instead — no SDK needed at all; the platform consumes standard GenAI trace conventions
from any instrumented system.

## What's next

`session_id` per conversation gives you workflow grouping today. Native
**Anthropic (Claude)**, LiteLLM, and LangChain wrappers — the same one-liner experience as
`ObserveOpenAI` — plus tool-call events, async, and batching are on the roadmap; the SDK
stays a thin evidence adapter either way: it feeds the ObserveAgents intelligence engine
and never creates a pipeline of its own.
