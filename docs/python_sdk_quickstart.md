# Python SDK Quickstart — connect an OpenAI-based agent in 5 minutes

*Runtime evidence track, milestone 4 (see [roadmap.md](roadmap.md)). This guide covers the
shipped SDK MVP (`sdk/python/observeagents`, PR #114): a drop-in `ObserveOpenAI` wrapper
that emits one safe, content-free `llm_call` runtime event per completion call.*

> **Observe first. Control only what matters.**

**What you get in 5 minutes:** your agent appears in the ObserveAgents inventory with its
model calls, latency, errors, and token usage — without deploying an OTel Collector,
without instrumenting spans, and without any prompt or response ever leaving your process.

**What the SDK never does:** it never sends prompts, messages, responses, system
instructions, tool arguments/results, headers, or credentials to ObserveAgents (§ Privacy),
it never blocks your app (fail-open, ~2s budget), and it never triggers enforcement —
events are evidence for the existing intelligence engine, nothing more.

---

## Step 1 — Get an ObserveAgents API key (1 min)

In the dashboard: **API Keys → Create**. Keys look like `gk-…`.

Recommended: one key per agent or team (e.g. `support-agent-prod`) — it keeps attribution
clean and lets you revoke one agent's key without touching others.

## Step 2 — Install / local usage (1 min)

The SDK is not on PyPI yet — it lives in this repo under `sdk/python/` and has **zero
runtime dependencies** (standard library only; the `openai` package is required only
because your agent calls OpenAI anyway):

```bash
git clone https://github.com/ronhaviv33-beep/ObserveAgents.ai.git
pip install openai
export PYTHONPATH="$PWD/ObserveAgents.ai/sdk/python:$PYTHONPATH"
```

(Alternatively, copy the `sdk/python/observeagents/` directory into your project, or add
`sys.path.insert(0, "<repo>/sdk/python")` at the top of your script.)

## Step 3 — Configure (1 min)

Everything can be set as a constructor argument or an environment variable
(**precedence: constructor arg → env var → default**):

| Setting | Env var | Required? | Default |
|---|---|---|---|
| OpenAI API key | `OPENAI_API_KEY` | ✅ | — |
| ObserveAgents API key (`gk-…`) | `OBSERVEAGENTS_API_KEY` | ✅ | — |
| Agent name | `OBSERVEAGENTS_AGENT_NAME` | ✅ | — |
| ObserveAgents endpoint | `OBSERVEAGENTS_URL` | — | `https://api.observeagents.ai` |
| Environment | `OBSERVEAGENTS_ENVIRONMENT` | — | `development` |
| Team hint | `OBSERVEAGENTS_TEAM_HINT` | — | unset |
| Owner hint | `OBSERVEAGENTS_OWNER_HINT` | — | unset |

```bash
export OPENAI_API_KEY="sk-..."
export OBSERVEAGENTS_API_KEY="gk-..."
export OBSERVEAGENTS_AGENT_NAME="support-agent"
export OBSERVEAGENTS_ENVIRONMENT="production"
```

`OBSERVEAGENTS_URL` may point at **ObserveAgents Cloud** or a **customer-side / self-hosted
instance** (e.g. `http://localhost:8000` when running the backend locally) — the SDK sends
every event to `POST {OBSERVEAGENTS_URL}/runtime-events`, and the wire format, auth, and
privacy rules are identical in both cases.

## Step 4 — Minimal example (1 min)

`ObserveOpenAI` is a drop-in for the OpenAI client — same call signature, same return
value, same exceptions:

```python
from observeagents import ObserveOpenAI

client = ObserveOpenAI(
    openai_api_key="sk-...",                            # or OPENAI_API_KEY
    observeagents_api_key="gk-...",                     # or OBSERVEAGENTS_API_KEY
    observeagents_url="https://api.observeagents.ai",   # or customer-side collector URL
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

That's it. Each `create()` call goes to OpenAI unchanged, and one `llm_call` runtime event
(metadata only — provider, model, duration, status, token counts, ids) is POSTed
best-effort to `/runtime-events` afterwards.

With env vars set, the constructor shrinks to:

```python
client = ObserveOpenAI()   # everything resolved from the environment
```

Useful extras: `session_id="chat-123"` groups related calls; `debug=True` logs one warning
per failed event delivery (deliveries are otherwise silent); `timeout_seconds=2.0` is the
delivery budget.

## Step 5 — Verify (1 min)

1. **Run your script.** The OpenAI call succeeds exactly as before — even if ObserveAgents
   were unreachable (fail-open by design).
2. **Runtime** page — a trace for `support-agent` appears within seconds; each completion
   call is one step with its duration and status.
3. **Asset Intelligence** — `support-agent` appears as a discovered AI system with its
   provider (`openai`), model, environment, and token usage evidence.
4. **Findings** — derived on the next intelligence run (automatic, or trigger one with
   `POST /intelligence/run`); e.g. an unknown-provider or missing-owner finding if
   applicable. Detection rules evaluate there too — never inside ingestion.
5. Optional wire-level check — send one event by hand and expect **202**:

```bash
curl -X POST "$OBSERVEAGENTS_URL/runtime-events" \
  -H "Authorization: Bearer $OBSERVEAGENTS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"events":[{"source":"sdk","agent_name":"quickstart-check","event_type":"llm_call","provider":"openai","model":"gpt-4.1-mini","duration_ms":850,"status":"ok","trace_id":"0123456789abcdef0123456789abcdef","span_id":"0123456789abcdef"}]}'
```

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

Defense in depth: the server independently enforces the same boundary — unknown fields are
rejected with `422` (`extra="forbid"`), and metadata is denylist-scrubbed. Details:
[python_sdk_wrapper_plan.md](python_sdk_wrapper_plan.md) §7.

## Error handling — fail-open

- If ObserveAgents is slow, down, or rejecting: your LLM call is **unaffected**. Delivery
  errors are swallowed (one `logging` warning when `debug=True`).
- If the OpenAI call fails: the SDK emits a `status="error"` event (class name only) and
  **re-raises your original exception unchanged** — same type, same message, same traceback.
- The SDK never raises its own exceptions into your call path and never enforces anything.

## Troubleshooting

| Symptom | Check |
|---|---|
| Nothing appears in Runtime | Set `debug=True` and look for a delivery warning; verify `OBSERVEAGENTS_URL` (no trailing path) and that the `gk-` key belongs to the org you're looking at |
| `ValueError` at construction | One of the three required settings is missing (OpenAI key, ObserveAgents key, agent name) — this raises immediately, before any LLM call |
| Agent appears but no findings | Findings derive during the intelligence run — trigger `POST /intelligence/run` or wait for the next scheduled run |
| Want to see the events themselves | `debug=True` + the curl check above; the endpoint answers `202` with ingestion counts |

## What this is not

No batching, no retries, no async, no Anthropic/LiteLLM/LangChain wrappers yet — those are
sequenced later on the [roadmap](roadmap.md#runtime-evidence-track--status--next-milestones)
(milestones 5–8), after the quickstart path proves adoption. The SDK is an evidence
adapter: it feeds the existing intelligence engine and creates no new pipeline.
