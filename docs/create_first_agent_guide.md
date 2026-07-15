# Create Your First Agent — Local Developer Onboarding

Build a small, safe AI agent on your machine, send its activity to your
**live ObserveAgents environment**, and watch it appear in the product.
Beginner-friendly and copy/paste oriented — the agent runs on your machine
(plain Python or a throwaway Docker container) with fake data; ObserveAgents
itself is already running, nothing needs to be deployed for this guide.

## 1. What you will build

A tiny Python "agent" that performs a harmless fake task (an invoice status
lookup), reports what it did to ObserveAgents, and then shows up in:

- **Agent Inventory** — your agent is auto-discovered with its owner/team/environment
- **Runtime** — the activity itself (two views: **Traces** and **Agent events**)
- **Rules & Alerts** — if the activity trips a detection rule, a finding appears
- **Metrics** — daily per-agent rollups update after the worker processes events

There are two connection methods:

| | Option A — OTLP / OpenTelemetry | Option B — Gateway key / Runtime events |
|---|---|---|
| Best for | Agents already instrumented with OpenTelemetry-style traces/spans | Agents that report activity directly using an ObserveAgents `gk-` key |
| Endpoint | `POST /otel/v1/traces` | `POST /api/v1/telemetry/batch` (also: `POST /runtime-events`) |
| Shows up in | Agent Inventory + Runtime → **Traces** | Agent Inventory + Runtime → **Agent events** + Rules & Alerts + metrics |

Both use the same `gk-` API key for authentication. **Note the key format is
`gk-` with a dash** (e.g. `gk-a1b2c3...`), not `gk_`.

## 2. Prerequisites

- A **live, running ObserveAgents environment** and its base URL — e.g.
  `https://your-observeagents-domain.com`. Nothing needs to be started for
  this guide; you are testing against the deployment that already runs.
  (If you self-host in Docker on your machine, the base URL is
  `http://localhost:<mapped-port>` — check `docker ps` for the port.)
- Visual Studio Code installed (optional: GitHub Copilot enabled)
- **Python 3.10+ installed, or Docker** — with Docker you can run the test
  agent in a throwaway container without installing Python at all (see §3)
- A valid `gk-` API key from that live environment — create one in the
  dashboard under **Administration → API Keys** (copy it once; it is never
  shown again)
- A `.env` file for secrets (created below)

> ⚠️ **Never hardcode API keys, routing keys, tokens, passwords, or customer
> data in code.** Keep secrets in `.env` (and keep `.env` out of git).

## 3. Project setup in VS Code

```bash
mkdir observeagents-first-agent
cd observeagents-first-agent
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install requests python-dotenv
```

Create these files (VS Code: File → New File):

```text
.env
agent_otlp.py
agent_gateway.py
README.md
```

### Alternative: run with Docker (no local Python)

Since the ObserveAgents environment is already live, the only thing that
needs Python is the little test agent — and Docker can supply that. Skip the
venv/pip steps above and, once the files exist, run either script in a
throwaway container:

```bash
docker run --rm --env-file .env -v "$PWD":/app -w /app python:3.12-slim \
  sh -c "pip install -q requests python-dotenv && python agent_gateway.py"
```

Windows PowerShell:

```powershell
docker run --rm --env-file .env -v "${PWD}:/app" -w /app python:3.12-slim `
  sh -c "pip install -q requests python-dotenv && python agent_gateway.py"
```

Notes:
- `--env-file .env` passes your configuration in; secrets stay out of the image.
- One Docker quirk: `.env` values must be **unquoted** for `--env-file`
  (`KEY=value`, not `KEY="value"`).
- If your ObserveAgents instance also runs in Docker **on the same machine**
  and you call it via `localhost`, the container can't see the host's
  localhost — use `http://host.docker.internal:<port>` in `.env` instead
  (add `--add-host=host.docker.internal:host-gateway` on Linux). With a real
  live domain this doesn't apply.

## 4. Option A — OTLP / OpenTelemetry path

This option sends telemetry as an OpenTelemetry trace to the real OTLP
endpoint: **`POST /otel/v1/traces`**. ObserveAgents parses the span, discovers
the agent from `service.name` / resource attributes, and stores
privacy-scrubbed runtime evidence (prompts/responses are never stored on this
path — only structure and metadata).

### `.env` for OTLP

```env
# Replace YOUR-LIVE-DOMAIN with your deployment's host.
# Self-hosting in local Docker instead? Use http://localhost:<mapped-port>.
OBSERVEAGENTS_OTLP_URL=https://YOUR-LIVE-DOMAIN/otel/v1/traces
OBSERVEAGENTS_API_KEY=gk-REPLACE_WITH_YOUR_KEY
AGENT_ID=billing-agent-otlp-local
AGENT_NAME=Billing Agent OTLP Local
AGENT_TEAM=Finance
AGENT_ENVIRONMENT=development
AGENT_OWNER=ron@example.com
```

- `OBSERVEAGENTS_OTLP_URL` — the OTLP traces endpoint on your live deployment
- `OBSERVEAGENTS_API_KEY` — your `gk-` key (sent as a Bearer token)
- `AGENT_ID` — the stable identity; becomes the discovered agent
- `AGENT_TEAM` / `AGENT_ENVIRONMENT` / `AGENT_OWNER` — governance metadata shown in Agent Inventory

### `agent_otlp.py`

```python
"""Send one safe OpenTelemetry-style span to ObserveAgents (OTLP JSON)."""
import os
import time
import uuid

import requests
from dotenv import load_dotenv

load_dotenv()

URL = os.environ["OBSERVEAGENTS_OTLP_URL"]
API_KEY = os.environ["OBSERVEAGENTS_API_KEY"]

now_ns = time.time_ns()
latency_ms = 850  # fake work duration

def attr(key, value):
    kind = "intValue" if isinstance(value, int) else "stringValue"
    return {"key": key, "value": {kind: value}}

payload = {
    "resourceSpans": [{
        "resource": {"attributes": [
            attr("service.name", os.environ["AGENT_ID"]),
            attr("deployment.environment", os.environ["AGENT_ENVIRONMENT"]),
            attr("team", os.environ["AGENT_TEAM"]),
            attr("service.owner", os.environ["AGENT_OWNER"]),
        ]},
        "scopeSpans": [{
            "spans": [{
                "traceId": uuid.uuid4().hex,           # 32 hex chars
                "spanId": uuid.uuid4().hex[:16],       # 16 hex chars
                "name": "chat gpt-4o-mini",
                "kind": 3,  # CLIENT
                "startTimeUnixNano": str(now_ns - latency_ms * 1_000_000),
                "endTimeUnixNano": str(now_ns),
                "attributes": [
                    attr("gen_ai.operation.name", "chat"),
                    attr("gen_ai.system", "openai"),
                    attr("gen_ai.request.model", "gpt-4o-mini"),
                    attr("gen_ai.usage.input_tokens", 320),
                    attr("gen_ai.usage.output_tokens", 64),
                    # harmless fake task — no real data, no tools that act
                    attr("gen_ai.agent.description", "invoice status lookup (demo)"),
                ],
                "status": {},
            }]
        }]
    }]
}

resp = requests.post(
    URL,
    json=payload,
    headers={"Authorization": f"Bearer {API_KEY}"},
    timeout=15,
)
print("HTTP", resp.status_code)
print(resp.text)
if resp.status_code == 202:
    print("✓ Trace accepted — check Runtime → Traces and Agent Inventory.")
elif resp.status_code == 401:
    print("✗ Auth failed — check OBSERVEAGENTS_API_KEY in .env (gk- prefix).")
else:
    print("✗ Unexpected response — check the endpoint URL and payload.")
```

Run it:

```bash
python agent_otlp.py
```

### Verify OTLP in the dashboard

1. Open the ObserveAgents dashboard and log in.
2. Go to **Agents** (Agent Inventory) — find *billing-agent-otlp-local* with
   its team/owner/environment.
3. Open **Runtime** — the **Traces** view shows your agent's execution trace
   (grouped by agent; click it to see the span waterfall with provider,
   model, and token metadata).
4. OTLP spans appear as **traces/runtime activity** — the **Agent events**
   view is fed by Option B's batch API, so an OTLP-only agent shows its
   evidence in the Traces view.

## 5. Option B — Gateway key / Runtime events path

This option uses your ObserveAgents **gateway API key (`gk-`)** to report
agent activity directly. The primary endpoint is the batch telemetry API —
**`POST /api/v1/telemetry/batch`** — which feeds the richest product surface:
Runtime → **Agent events**, Rules & Alerts findings, and daily metrics.

> Naming note: in this repo, `gk-` keys are the gateway/ingestion credential
> (created under **API Keys**). The same key authenticates
> `/api/v1/telemetry/batch`, `/runtime-events`, and `/otel/v1/traces`.
> If you route live LLM traffic through the ObserveAgents Gateway proxy
> (`/v1/chat/completions` with an `X-Guard-Agent` header), that traffic is
> captured automatically — this guide simulates activity without a real
> provider call.

### `.env` for the Gateway key path

```env
# Replace YOUR-LIVE-DOMAIN with your deployment's host.
OBSERVEAGENTS_TELEMETRY_URL=https://YOUR-LIVE-DOMAIN/api/v1/telemetry/batch
OBSERVEAGENTS_RUNTIME_EVENTS_URL=https://YOUR-LIVE-DOMAIN/runtime-events
OBSERVEAGENTS_API_KEY=gk-REPLACE_WITH_YOUR_KEY
AGENT_ID=billing-agent-gateway-local
AGENT_NAME=Billing Agent Gateway Local
AGENT_TEAM=Finance
AGENT_ENVIRONMENT=development
AGENT_OWNER=ron@example.com
```

### `agent_gateway.py`

```python
"""Simulate a safe agent action and report it to ObserveAgents (batch API)."""
import os
import uuid
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

URL = os.environ["OBSERVEAGENTS_TELEMETRY_URL"]
API_KEY = os.environ["OBSERVEAGENTS_API_KEY"]

def base_event(**overrides):
    event = {
        "event_id": str(uuid.uuid4()),        # idempotency key — unique per event
        "agent_id": os.environ["AGENT_ID"],
        "agent_name": os.environ["AGENT_NAME"],
        "team": os.environ["AGENT_TEAM"],
        "environment": os.environ["AGENT_ENVIRONMENT"],
        "owner": os.environ["AGENT_OWNER"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
    }
    event.update(overrides)
    return event

events = [
    # 1. an LLM call — cost is computed server-side from the pricing registry
    base_event(
        event_type="llm_call",
        provider="openai",
        model="gpt-4o-mini",
        input_tokens=420,
        output_tokens=95,
        latency_ms=780,
        action_name="invoice_lookup",
    ),
    # 2. a harmless tool call
    base_event(
        event_type="tool_call",
        tool_name="crm_contact_search",
        action_name="support_ticket_summary",
        latency_ms=310,
    ),
]

resp = requests.post(
    URL,
    json={"events": events},
    headers={"Authorization": f"Bearer {API_KEY}"},
    timeout=15,
)
print("HTTP", resp.status_code)
print(resp.text)
if resp.status_code == 202:
    body = resp.json()
    print(f"✓ accepted={body['accepted']} duplicated={body['duplicated']} failed={body['failed']}")
    print("The background worker normalizes each event, scores it against the")
    print("detection rules, updates daily metrics, and registers the agent in")
    print("Agent Inventory — usually within a couple of seconds.")
elif resp.status_code == 401:
    print("✗ Auth failed — check OBSERVEAGENTS_API_KEY in .env (gk- prefix).")
else:
    print("✗ Rejected — check endpoint URL and event fields.")
```

Run it:

```bash
python agent_gateway.py
```

**How the data reaches the dashboard:** the API stores your exact payload and
returns immediately; an in-process worker then normalizes each event, runs the
real-time risk rules (producing `risk_score`, `risk_reasons`, `policy_action`),
updates the `agent_metrics_daily` rollups, and upserts the agent into the
Asset Registry — so Inventory, Agent events, findings, and metrics all light
up from one call.

### The `/runtime-events` alternative

The same `gk-` key also works with `POST /runtime-events`, the SDK-style
endpoint for normalized GenAI runtime events. Its schema is strict
(`extra="forbid"`); required fields are `source`, `agent_name`, `trace_id`,
`span_id`, `event_type`. Events sent here become spans and appear in
Runtime → **Traces** (like OTLP), not in Agent events. Use it when you want
the trace-shaped view without full OTel instrumentation.

### Verify in the dashboard

1. Open the dashboard and log in.
2. **Agents** (Agent Inventory) — find *billing-agent-gateway-local* with
   team `Finance`, your owner email, and environment `development`.
3. Open **Runtime** and switch the toggle to **Agent events**.
4. Pick your agent in the selector — both events appear with model/tool,
   latency, cost (marked `est` when computed from the pricing registry),
   status, and risk badges when rules fired.
5. Open **Rules & Alerts** — if any event tripped a rule, it's in
   **Recent findings** with the reason and a click-through back to the agent.
6. Metrics (summary cards and `GET /telemetry/metrics/daily`) update once the
   worker finishes — normally seconds.

## 6. Trigger a safe warning

Add one intentionally "noisy" event to see risk scoring work. Safe triggers:
high latency, unknown model, missing owner, error status, high token count.

Append this to the `events` list in `agent_gateway.py`:

```python
    # 3. a safe warning example: an error with very high latency
    base_event(
        event_type="tool_call",
        tool_name="invoice_lookup",
        status="error",
        error_message="Tool returned timeout (demo)",
        latency_ms=45000,
    ),
```

For OTLP, the equivalent is setting the span's
`"status": {"code": 2, "message": "timeout (demo)"}` and a long duration.

The error (+25) and high latency (+15) rules fire, so the event scores 40 —
a **medium risk** badge in Runtime → Agent events and a row in Rules &
Alerts → Recent findings (exact scores depend on which rules your admins
have enabled and their thresholds). To push it over the `policy: warn`
threshold (50), also omit the `owner` field (+10 for missing owner). Never
use shell execution, file deletion, credential access, or real PII to
trigger warnings.

## 7. Build the same agent with GitHub Copilot

Open Copilot Chat in VS Code and use these prompts.

**Copilot prompt — OTLP:**

```text
Create a Python script called agent_otlp.py that loads configuration from a .env file and sends a safe OpenTelemetry-style agent event to ObserveAgents using the OTLP endpoint. Include agent identity fields, provider/model, latency, token usage, and status. Do not hardcode secrets. Use requests and python-dotenv.
```

**Copilot prompt — Gateway key:**

```text
Create a Python script called agent_gateway.py that loads a Gateway routing key from a .env file and sends a safe simulated AI-agent runtime event to ObserveAgents through the Gateway / Runtime Events path. Include agent id, agent name, team, environment, owner, provider, model, latency, tokens, status, tool_name, and action_name. Do not hardcode secrets.
```

**Copilot prompt — error handling:**

```text
Add error handling to the script. Print the HTTP status code, response body, and a clear message explaining whether the event was accepted, duplicated, or failed.
```

**Copilot prompt — dashboard verification README:**

```text
Create a README section explaining how to run this local agent and verify the result in ObserveAgents Agent Inventory, Runtime Agent events, and Rules & Alerts.
```

Review what Copilot generates against the endpoint names and field lists in
this guide before running it — especially the `gk-` Bearer auth header and
the exact endpoint paths.

## 8. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `401 Unauthorized` | Missing/invalid key — must be `Authorization: Bearer gk-...`; check the key is active in API Keys |
| `404 Not Found` | Wrong endpoint path — use `/otel/v1/traces`, `/api/v1/telemetry/batch`, or `/runtime-events` exactly |
| `413 Payload Too Large` | Too many events in one request (batch max 1,000; runtime-events max 500) |
| `accepted: 0, duplicated: 1` | Same `event_id` already sent — dedup is per `(org, event_id)`; generate a new UUID per event |
| `422` on `/runtime-events` | Strict schema — unknown fields are rejected; check required `source`/`agent_name`/`trace_id`/`span_id`/`event_type` |
| Agent not visible | Wait a few seconds for worker processing, then refresh Agent Inventory |
| Agent events empty | Check you're on the **Agent events** view (not Traces), the right agent is selected, and the time range covers your event's timestamp |
| Rules & Alerts empty | The event may not trigger any enabled rule — try the warning example in §6 |
| Metrics not updated | Rollups update after worker processing — wait and refresh |
| Connection refused / DNS error | Wrong base URL — use your live domain exactly (https, no trailing slash); for local Docker, match the mapped port from `docker ps` |
| Works with curl, fails from Docker | Container can't reach the host's `localhost` — use `http://host.docker.internal:<port>` (see §3), or your live domain |
| `.env` values look wrong in Docker | `docker run --env-file` doesn't strip quotes — keep values unquoted (`KEY=value`) |
| SSL certificate error | Your live deployment's HTTPS cert isn't trusted by the container/host — fix the cert; never disable TLS verification |
| CORS errors | You're calling from a browser page — call the API from Python/curl instead, or go through the dashboard's dev proxy |

## 9. Data safety

- Use **fake test data** only.
- Never send secrets: no passwords, tokens, API keys, or credentials as
  telemetry field values.
- Never send private customer data or PII.
- The batch API **preserves your raw payload byte-for-byte** for
  investigation — whatever you send is stored. Send metadata about activity,
  not content. (The OTLP path stores content hashes only.)
- Use `environment=development` so test agents are clearly separated from
  production — especially important here, since you're sending into a live
  deployment: the test events and demo agents will be visible to everyone
  who uses that environment until cleaned up.

## 10. Optional curl examples

OTLP:

```bash
curl -s -X POST https://YOUR-LIVE-DOMAIN/otel/v1/traces \
  -H "Authorization: Bearer gk-YOUR_KEY" -H "Content-Type: application/json" \
  -d '{"resourceSpans":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"curl-demo-agent"}}]},"scopeSpans":[{"spans":[{"traceId":"5b8efff798038103d269b633813fc60c","spanId":"eee19b7ec3c1b174","name":"chat gpt-4o-mini","kind":3,"startTimeUnixNano":"1752570000000000000","endTimeUnixNano":"1752570001000000000","attributes":[{"key":"gen_ai.operation.name","value":{"stringValue":"chat"}},{"key":"gen_ai.system","value":{"stringValue":"openai"}},{"key":"gen_ai.request.model","value":{"stringValue":"gpt-4o-mini"}}],"status":{}}]}]}]}'
```

Batch telemetry (Gateway key path):

```bash
curl -s -X POST https://YOUR-LIVE-DOMAIN/api/v1/telemetry/batch \
  -H "Authorization: Bearer gk-YOUR_KEY" -H "Content-Type: application/json" \
  -d '{"events":[{"event_id":"demo-1","agent_id":"curl-demo-agent","agent_name":"Curl Demo Agent","team":"Finance","owner":"ron@example.com","environment":"development","event_type":"llm_call","provider":"openai","model":"gpt-4o-mini","input_tokens":100,"output_tokens":20,"latency_ms":800,"status":"ok"}]}'
```

## 11. Final validation checklist

- [ ] Live environment is reachable (`curl https://YOUR-LIVE-DOMAIN/health` returns `"status":"ok"`)
- [ ] Dashboard opens and you can log in
- [ ] `.env` points at the live base URL and the `gk-` API key (never hardcoded)
- [ ] OTLP script returns `202` and the trace appears in Runtime → Traces
- [ ] Gateway script returns `202` with `accepted > 0`
- [ ] Both agents appear in Agent Inventory with team/owner/environment
- [ ] Events appear in Runtime → Agent events for the gateway agent
- [ ] The warning example shows a risk badge and/or a Rules & Alerts finding
- [ ] No real secrets or customer data were sent

**Where to go next:** [telemetry_ingestion.md](telemetry_ingestion.md) for the
full ingestion architecture, dedup semantics, risk rules, and metrics;
[otel-deployment-guide.md](otel-deployment-guide.md) for production OTel
setups; [sdk-guide.md](sdk-guide.md) for the Python SDK.
