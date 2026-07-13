# observeagents — Python SDK

**See what your AI agents are actually doing.** Wrap your OpenAI client with one class and
every chat-completion call sends one safe, **content-free** runtime event to your
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

`ObserveOpenAI` is a drop-in replacement for the OpenAI client: same call signature, same
return value, same exceptions. All settings are also available as environment variables
(`OBSERVEAGENTS_API_KEY`, `OBSERVEAGENTS_AGENT_NAME`, `OBSERVEAGENTS_URL`,
`OBSERVEAGENTS_ENVIRONMENT`, `OBSERVEAGENTS_TEAM_HINT`, `OBSERVEAGENTS_OWNER_HINT`).

## Privacy — hard guarantees

The SDK **never** sends prompts, messages, responses, system instructions, tool
arguments/results, headers, or credentials to ObserveAgents. Events carry metadata only:
agent name, provider, model, duration, status, error **class name**, token counts, and
trace/span/session ids. Your OpenAI API key is used only to construct the OpenAI client
and never appears in any event.

## Fail-open

If ObserveAgents is unreachable, your LLM calls are unaffected — event delivery is
best-effort with a ~2s budget and never raises into your call path. If the OpenAI call
fails, your original exception is re-raised unchanged.
