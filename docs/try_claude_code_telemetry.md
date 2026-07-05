# Try It Yourself: Watch Claude Code in Observe

*A 20-minute self-test: run Claude Code as a real web-research agent, stream its OpenTelemetry traces into Observe, and watch yourself appear in Runtime and Asset Intelligence.*

This is the realest dogfooding loop available today: **you are the customer, Claude Code is the agent, Observe is watching.** No simulation scripts — real agent activity around the web, real telemetry, direct protobuf ingestion (no Collector).

**Prerequisites:** Claude Code CLI or desktop app on your machine · access to the labs deployment (`labs.observeagents.ai`) running the lab branch with protobuf support (`4086e45` or later).

---

## Step 0 — Confirm labs is protobuf-ready (30 seconds)

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST "https://labs.observeagents.ai/otel/v1/traces" \
  -H "Content-Type: application/x-protobuf" -H "Authorization: Bearer gk-invalid" --data-binary "x"
```

- `401` → protobuf path is live (it got past content-type to auth). Proceed.
- `415` → labs hasn't redeployed the lab branch yet. Deploy latest commit in Render first.

## Step 1 — Create a fresh API key

In the labs dashboard: **API Keys → New**, name it `claude-code-selftest`. Copy the `gk-` key immediately.

> Use a **new** key, not one you've already shared or pasted anywhere. One key per person/experiment means you can revoke this one afterwards without touching anything else — and remember a `gk-` key also authenticates the gateway, so treat it like a secret.

## Step 2 — Configure Claude Code to emit traces

In the terminal where you'll run Claude Code:

```bash
# Claude Code's own switches — telemetry on, tracing beta on
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1
export OTEL_TRACES_EXPORTER=otlp

# Where the traces go — Observe labs, direct protobuf
export OTEL_EXPORTER_OTLP_ENDPOINT=https://labs.observeagents.ai/otel
export OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer gk-<your-new-key>
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf

# Who this agent is in Observe
export OTEL_SERVICE_NAME=web-research-agent
export OTEL_RESOURCE_ATTRIBUTES=deployment.environment=development,team=platform

claude
```

Notes:
- **Do not** set `OTEL_METRICS_EXPORTER` or `OTEL_LOGS_EXPORTER` — Observe ingests traces only today; Claude Code's metrics would just 404.
- To make this permanent, the same variables can live in Claude Code's `settings.json` `env` block instead of shell exports.
- Claude Code on the **web** can't take shell exports — use the CLI or desktop app for this exercise.

## Step 3 — Run the agent task

Paste this into the Claude Code session you just started. It's deliberately multi-step web activity — searches, fetches, file writes — so the trace has texture:

```
Research task: I'm comparing how observability vendors position "AI agent
observability" in 2026.

1. Search the web for how Dash0, SigNoz, and Traceloop each describe AI/LLM
   agent observability.
2. Fetch one primary page for each vendor and extract their positioning
   sentence and 3 headline capabilities.
3. Write a comparison table (vendor · positioning · capabilities · pricing
   model if stated) to a new file called otel-landscape.md.
4. Finish with a 5-bullet summary of what all three have in common and what
   none of them offers.
```

Let it run to completion. Then, for trace volume, follow up with one or two more prompts in the same session, e.g.:

```
Now check the OpenTelemetry GenAI semantic conventions repo for the current
list of gen_ai.operation.name values and append them as a section to
otel-landscape.md.
```

Every prompt becomes a trace: a root interaction span, `llm_request` spans for each model call, and tool spans for each WebSearch / WebFetch / Write.

## Step 4 — Watch yourself in Observe

Open the labs dashboard:

1. **Runtime** — `web-research-agent` appears with one trace per prompt. Open one: nested timeline, LLM steps and tool steps, durations per step.
2. **Asset Intelligence** — press **Run Intelligence**. A `web-research-agent` card appears: provider **Anthropic**, the Claude model(s) used, tools as capabilities, `development` environment, `platform` team.
3. **Findings** — expect at least *New AI System Detected*; possibly *Unmanaged AI System* until you claim it in the inventory. If you used MCP servers in the session, expect MCP capabilities too.
4. **Guardrails** — see which advisory guardrails your own session's behavior would trigger. Nothing is blocked; that's the product.

## What you should expect (and not expect)

| Works today | Not yet |
|---|---|
| Traces per prompt, nested timelines | Token/cost totals may be partial — Claude Code puts token counts in non-standard span attrs; full cost accounting arrives with metrics ingestion (roadmap O2) |
| Provider/model/tool discovery, findings | Metrics & logs ingestion (don't enable those exporters) |
| Direct protobuf, no Collector | — |

## Troubleshooting

| Symptom | Check |
|---|---|
| Nothing in Runtime | Is `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` set? Traces are beta — without it Claude Code sends no spans |
| `415` in any export error | Labs not redeployed with protobuf yet (Step 0) |
| `401` | Key wrong/revoked, or `OTEL_EXPORTER_OTLP_HEADERS` malformed (must be `Authorization=Bearer gk-...`) |
| Agent named `claude-code` instead of `web-research-agent` | `OTEL_SERVICE_NAME` wasn't exported in the same shell before launching `claude` |
| Data in the wrong org | The key determines the org — check which org the key belongs to |

## Afterwards

Revoke `claude-code-selftest` in API Keys if you're done, or keep it and rename the service per experiment (`OTEL_SERVICE_NAME=bug-bounty-agent`, …) — each name becomes its own AI system in the inventory.
