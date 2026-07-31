# observeagents — Python SDK

**See what your AI agents are actually doing.** ObserveAgents discovers your agents
automatically from runtime evidence — model calls, latency, errors, token usage, and
derived security findings — in your [ObserveAgents](https://www.observeagents.ai)
workspace.

> **Observe first. Control only what matters.**

## Recommended integration: OpenTelemetry

The recommended way to send runtime evidence to ObserveAgents is **standard
OpenTelemetry instrumentation** exporting **OTLP** — directly or through an
OpenTelemetry Collector. No proprietary wrapper, no changes to your provider clients,
and it works with any AI provider (OpenAI, Anthropic, Google, local models, internal
services).

```
Your runtime → OpenTelemetry instrumentation → OTLP / OTel Collector → ObserveAgents
```

## What this package contains

Low-level, content-free building blocks for the `POST /runtime-events` API
(`observeagents.events`, `observeagents.client`, `observeagents.privacy`,
`observeagents.ids`). It contains **no provider-specific wrapper**. This package is
under architectural review — see `docs/otlp_native_audit.md` in the repository.

## Install

```bash
pip install observeagents
```

Zero runtime dependencies (standard library only).

## Privacy — hard guarantees

The SDK **never** sends prompts, messages, responses, system instructions, tool
arguments/results, headers, or credentials to ObserveAgents. Events carry metadata only:
agent name, provider, model, duration, status, error **class name**, token counts, and
trace/span/session ids.

## Fail-open

Event delivery is best-effort with a ~2s budget and never raises into your call path —
if ObserveAgents is unreachable, your application is unaffected.
