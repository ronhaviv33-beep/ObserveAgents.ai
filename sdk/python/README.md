# observeagents — Python SDK

**See what your AI agents are actually doing.** Wrap your OpenAI or Anthropic client with
one class and every call sends one safe, **content-free** runtime event to your
[ObserveAgents](https://www.observeagents.ai) workspace — where your agents are discovered
automatically, with their model calls, latency, errors, token usage, and derived security
findings.

> **Observe first. Control only what matters.**

## Install

```bash
pip install observeagents
```

Zero runtime dependencies (standard library only).

## Use

```python
from observeagents import ObserveOpenAI

client = ObserveOpenAI(
    openai_api_key="sk-...",
    observeagents_api_key="gk-...",     # from your ObserveAgents workspace → API Keys
    agent_name="support-agent",
    environment="production",
)

response = client.chat.completions.create(
    model="gpt-4.1-mini",
    messages=[{"role": "user", "content": "Hello"}],
)
```

Or wrap Anthropic instead:

```python
from observeagents import ObserveAnthropic

client = ObserveAnthropic(
    anthropic_api_key="sk-ant-...",
    observeagents_api_key="gk-...",
    agent_name="research-agent",
    environment="production",
)

response = client.messages.create(
    model="claude-sonnet-5",
    max_tokens=512,
    messages=[{"role": "user", "content": "Hello"}],
)
```

Both wrappers are drop-in replacements for their respective clients: same call signature,
same return value, same exceptions. All settings are also available as environment
variables (`OBSERVEAGENTS_API_KEY`, `OBSERVEAGENTS_AGENT_NAME`, `OBSERVEAGENTS_URL`,
`OBSERVEAGENTS_ENVIRONMENT`, `OBSERVEAGENTS_TEAM_HINT`, `OBSERVEAGENTS_OWNER_HINT`).

## Privacy — hard guarantees

The SDK **never** sends prompts, messages, responses, system instructions, tool
arguments/results, headers, or credentials to ObserveAgents. Events carry metadata only:
agent name, provider, model, duration, status, error **class name**, token counts, and
trace/span/session ids. Your provider API key is used only to construct that provider's
client and never appears in any event.

## Fail-open

If ObserveAgents is unreachable, your LLM calls are unaffected — event delivery is
best-effort with a ~2s budget and never raises into your call path. If the provider call
fails, your original exception is re-raised unchanged.

## Not just OpenAI and Anthropic

The platform observes agents on **any AI provider with an API** — Google, local models,
internal services, and more. `ObserveOpenAI` and `ObserveAnthropic` are the drop-in
wrappers today; every other provider connects with a few lines against the same
runtime-events API (see the Python SDK Guide), and LiteLLM/LangChain wrappers are on the
roadmap.
