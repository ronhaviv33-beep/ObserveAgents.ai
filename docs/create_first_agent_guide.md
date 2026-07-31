# Getting Started — See Your First Agent in ObserveAgents

**Who this is for:** you're new to ObserveAgents, it's already running (you
have a URL and a login), and you want to see *something real* in the product
in the next 15 minutes.

**What you'll do:** run one tiny, safe script that pretends to be an AI agent
("Billing Agent") and emits one **OpenTelemetry trace** with a few fake steps.
A few seconds later you'll see that agent — with its execution timeline,
models, tools, and derived findings — inside ObserveAgents.

**What you need:** your ObserveAgents URL, a login, and either Python **or**
Docker on your machine. That's all. Nothing gets installed on the server —
it's already live. OpenTelemetry/OTLP is the platform's one integration path;
this guide sends the same OTLP JSON a real instrumented agent would.

Follow the 5 steps in order. Each step ends with a ✅ checkpoint — if the
checkpoint fails, fix it before moving on (there's a
[what went wrong?](#what-went-wrong) section at the bottom).

---

## Step 1 — Get your API key (2 min)

An API key is how your agent proves to ObserveAgents who it is.

1. Open your ObserveAgents dashboard in the browser and log in.
2. In the left menu, under **Administration**, click **API Keys**.
3. Click create, give it any name (e.g. `my-first-agent`), and copy the key.
   It starts with **`gk-`**. **Copy it now** — it's shown only once.

> ✅ **Checkpoint:** you have a key that looks like `gk-a1B2c3...` saved
> somewhere safe (not in your code!).

---

## Step 2 — Create the project (3 min)

Make a folder with **two files**. You can use VS Code or any editor.

```bash
mkdir observeagents-first-agent
cd observeagents-first-agent
```

**File 1: `.env`** — your settings. Paste this and fill in the two
placeholders (your real ObserveAgents URL, and the key from Step 1):

```env
OBSERVEAGENTS_BASE_URL=https://YOUR-OBSERVEAGENTS-URL
OBSERVEAGENTS_API_KEY=gk-PASTE_YOUR_KEY_HERE
```

Rules for this file: no quotes around values, no trailing slash on the URL,
and never commit it to git.

**File 2: `agent.py`** — the fake agent. Paste as-is, no edits needed:

```python
"""My first agent: emits one safe, fake OTel trace to ObserveAgents."""
import os
import time
import uuid

import requests
from dotenv import load_dotenv

load_dotenv()

BASE = os.environ["OBSERVEAGENTS_BASE_URL"]      # e.g. https://YOUR-LIVE-DOMAIN
KEY  = os.environ["OBSERVEAGENTS_API_KEY"]       # gk-...

def attr(k, v):
    kind = "intValue" if isinstance(v, int) else "stringValue"
    return {"key": k, "value": {kind: v}}

now = time.time_ns()
trace_id = uuid.uuid4().hex                       # new trace every run

def span(span_id, name, start_offset_ms, duration_ms, attributes, parent=None):
    s = {
        "traceId": trace_id,
        "spanId": span_id,
        "name": name,
        "kind": 3,
        "startTimeUnixNano": str(now + start_offset_ms * 1_000_000),
        "endTimeUnixNano":   str(now + (start_offset_ms + duration_ms) * 1_000_000),
        "attributes": attributes,
        "status": {},
    }
    if parent:
        s["parentSpanId"] = parent
    return s

root_id = uuid.uuid4().hex[:16]
spans = [
    # the workflow root — this is the Execution Timeline's spine
    span(root_id, "agent.workflow", 0, 1400, [attr("session.id", trace_id)]),
    # step 1: the "agent" asked an LLM to look up an invoice (fake)
    span(uuid.uuid4().hex[:16], "chat gpt-4o-mini", 50, 780, [
        attr("gen_ai.operation.name", "chat"),
        attr("gen_ai.provider.name", "openai"),
        attr("gen_ai.request.model", "gpt-4o-mini"),
        attr("gen_ai.usage.input_tokens", 420),
        attr("gen_ai.usage.output_tokens", 95),
    ], parent=root_id),
    # step 2: the "agent" used a harmless tool (fake)
    span(uuid.uuid4().hex[:16], "execute_tool crm_contact_search", 900, 310, [
        attr("gen_ai.operation.name", "execute_tool"),
        attr("gen_ai.tool.name", "crm_contact_search"),
    ], parent=root_id),
]

payload = {"resourceSpans": [{
    "resource": {"attributes": [
        attr("service.name", "billing-agent-demo"),
        attr("deployment.environment", "development"),
        attr("team", "finance"),
    ]},
    "scopeSpans": [{"spans": spans}],
}]}

resp = requests.post(
    f"{BASE}/otel/v1/traces",
    json=payload,
    headers={"Authorization": f"Bearer {KEY}"},
    timeout=15,
)
print("HTTP", resp.status_code, "-", resp.text)
```

> ✅ **Checkpoint:** your folder contains `.env` (with your real URL + key)
> and `agent.py`.

---

## Step 3 — Run it (1 min)

Pick **one** of these:

**If you have Docker** (nothing to install):

```powershell
docker run --rm --env-file .env -v "${PWD}:/app" -w /app python:3.12-slim sh -c "pip install -q requests python-dotenv && python agent.py"
```

(That's one single line — on macOS/Linux replace `"${PWD}:/app"` with
`"$PWD":/app`. Don't split it across lines in PowerShell.)

**If you have Python:**

```bash
python -m venv .venv
# Windows PowerShell:   .venv\Scripts\Activate.ps1
# macOS/Linux:          source .venv/bin/activate
pip install requests python-dotenv
python agent.py
```

> ✅ **Checkpoint:** the script prints
> `HTTP 202 - {"accepted": true, ... "spans": 3, ...}` with
> `"content_redacted": true`. **ObserveAgents took the whole trace** —
> discovered the agent, mapped its model and tool, and stored the
> privacy-scrubbed spans.

---

## Step 4 — See it in the product (3 min)

Open the dashboard and refresh. Look in three places, in this order:

1. **Runtime** (left menu) — make sure the **Traces** view is selected at the
   top of the page. Your trace appears as one collapsed session row for
   *billing-agent-demo*; expand it into the per-step **execution waterfall**:
   the workflow root, the LLM call (model + token usage), and the tool call,
   each with its duration.

2. **Asset Intelligence** (left menu) — *billing-agent-demo* now has a card:
   provider **openai**, model **gpt-4o-mini**, tool **crm_contact_search**,
   team and environment. ObserveAgents discovered it automatically from the
   telemetry — nobody registered it by hand.

3. **Security Intelligence** — probably quiet for now. Your trace was clean,
   so there's little to derive. Let's fix that.

> ✅ **Checkpoint:** you found your trace's waterfall in **Runtime → Traces**
> and the agent's card in **Asset Intelligence**.

---

## Step 5 — Make something go wrong (on purpose) (2 min)

The product's real job is catching *risky* behavior. Add two bad-but-safe
steps: a **database query** and a **failing tool call**. Add these to the
`spans` list in `agent.py` (before the closing `]`):

```python
    # step 3: the "agent" reads a database directly — risky-looking, fake
    span(uuid.uuid4().hex[:16], "db.query", 1250, 60, [
        attr("db.system", "postgresql"),
        attr("db.name", "billing"),
    ], parent=root_id),
    # step 4: a tool call that failed — safe, but it carries a typed error
    span(uuid.uuid4().hex[:16], "execute_tool invoice_lookup", 1350, 45000, [
        attr("gen_ai.operation.name", "execute_tool"),
        attr("gen_ai.tool.name", "invoice_lookup"),
        attr("error.type", "tool_timeout"),
    ], parent=root_id),
]
```

Run the script again (same command as Step 3) — each run is a fresh trace, so
all spans are accepted. Now look again:

- **Runtime → Traces** — the new session's waterfall shows the database step
  and the failed tool step.
- **Asset Intelligence** — click **▶ Run Intelligence** (derivation is
  on-demand). The agent's card now shows a **database capability** and
  findings such as `agent_has_database_access` — with the evidence that
  triggered each one. In `development` these derive at moderate severity; the
  same behavior in `production` escalates.
- **Security Intelligence** — the agent appears with its risky observed
  behavior, answering *why* it needs a conversation.

> ✅ **Checkpoint:** you can see a finding and explain *why* it fired.
> **That's the whole product loop:** agent acts → OTel trace in → evidence,
> capabilities, and findings out.

---

## You're done — what next?

| I want to… | Go to |
|---|---|
| Connect a **real** agent that uses OpenTelemetry | [otel-deployment-guide.md](otel-deployment-guide.md) — quick start, direct SDK export, production Collector |
| The exact endpoint contract (status codes, limits, identity) | [otlp-api-reference.md](otlp-api-reference.md) |
| Every attribute the platform understands | [genai-semantic-conventions.md](genai-semantic-conventions.md) |
| Let GitHub Copilot write the agent for you | [Copilot prompts below](#bonus-let-github-copilot-write-it) |

**Good to know:**
- Prompt and response content is **never stored** — even if instrumentation
  attaches it, ObserveAgents scrubs it at ingestion to a hash + byte size
  ([privacy.md](privacy.md)). Still, send only **fake data** while learning.
- Keep `deployment.environment=development` on test agents so they never mix
  with production data — remember you're sending into a live system that your
  teammates also see.
- Re-running the script never duplicates anything: each run is a new trace,
  and re-sent spans with the same ids are skipped automatically.

---

## Bonus: let GitHub Copilot write it

Open Copilot Chat in VS Code and paste:

```text
Create a Python script called agent.py that loads OBSERVEAGENTS_BASE_URL and OBSERVEAGENTS_API_KEY from a .env file and sends one fake AI-agent trace to ObserveAgents as standard OTLP/HTTP JSON at POST {base_url}/otel/v1/traces. Build a resourceSpans envelope with resource attributes service.name=billing-agent-demo, deployment.environment=development, team=finance, and three spans sharing one generated traceId: a root agent.workflow span, a child chat span with gen_ai.operation.name=chat, gen_ai.provider.name=openai, gen_ai.request.model=gpt-4o-mini and token usage attributes, and a child tool span with gen_ai.operation.name=execute_tool and gen_ai.tool.name. Use hex trace/span ids, startTimeUnixNano/endTimeUnixNano as strings, kind 3, empty status. Authenticate with a Bearer gk- API key from .env. Do not hardcode secrets. Use requests and python-dotenv. Print the HTTP status and response body.
```

Then compare what it wrote against Step 2 above — especially the endpoint
path, the `Bearer gk-` header, and that no secret is hardcoded.

---

## What went wrong?

| You see | It means | Do this |
|---|---|---|
| `HTTP 401` | Wrong or missing key | Check `.env`: the key starts with `gk-` (a dash), no quotes, no spaces. Is the key still active in the API Keys page? |
| `HTTP 404` | Wrong URL | The path must be exactly `/otel/v1/traces` after your domain. No trailing slash in `OBSERVEAGENTS_BASE_URL`. |
| `HTTP 415` | Wrong content type | Send JSON (the script does) — the endpoint accepts `application/json` and `application/x-protobuf` only. |
| `HTTP 400` | Malformed envelope | Compare against Step 2 exactly — `resourceSpans` → `scopeSpans` → `spans`, times as strings. |
| Agent named `observed-ai-system:…` | No `service.name` resource attribute | Keep the `service.name` attribute from Step 2 — it's the agent's identity. |
| Trace missing in Runtime | Wrong view or time range | Make sure the **Traces** toggle is selected and the time range covers now; refresh. |
| Findings empty after Step 5 | Derivation not run | Click **▶ Run Intelligence** on Asset Intelligence — findings derive on demand, not during ingestion. |
| Connection error / timeout | Can't reach the server | Open `https://YOUR-OBSERVEAGENTS-URL/health` in a browser — you should see `"status":"ok"`. If not, the URL is wrong. |
| Docker: `-p is not recognized` (PowerShell) | A multi-line command got split | Paste the Docker command as **one line** (PowerShell doesn't understand `\` line-breaks). |
| Docker can't reach `localhost` | Containers have their own localhost | If ObserveAgents runs on your own machine, use `http://host.docker.internal:<port>` in `.env` instead of `localhost`. Real domains are unaffected. |
