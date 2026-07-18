# Getting Started — See Your First Agent in ObserveAgents

**Who this is for:** you're new to ObserveAgents, it's already running (you
have a URL and a login), and you want to see *something real* in the product
in the next 15 minutes.

**What you'll do:** run one tiny, safe script that pretends to be an AI agent
("Billing Agent") and reports two fake actions. A few seconds later you'll
see that agent — with its activity, cost, and risk — inside ObserveAgents.

**What you need:** your ObserveAgents URL, a login, and either Python **or**
Docker on your machine. That's all. Nothing gets installed on the server —
it's already live.

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
OBSERVEAGENTS_TELEMETRY_URL=https://YOUR-OBSERVEAGENTS-URL/api/v1/telemetry/batch
OBSERVEAGENTS_API_KEY=gk-PASTE_YOUR_KEY_HERE
AGENT_ID=billing-agent-demo
AGENT_NAME=Billing Agent Demo
AGENT_TEAM=Finance
AGENT_ENVIRONMENT=development
AGENT_OWNER=you@yourcompany.com
```

> `AGENT_NAME`, `AGENT_TEAM`, and `AGENT_OWNER` are **optional attribution metadata** —
> the platform backfills them from the Asset Registry when omitted. This demo sets them
> for a richer first result, not because discovery requires them. `AGENT_ID` is
> **recommended but also optional**: without it, identity resolves through
> agent_name → service attribute → a stable runtime fingerprint, and the event
> is still ingested (an explicit id simply gives the strongest attribution).

Rules for this file: no quotes around values, and never commit it to git.

**File 2: `agent.py`** — the fake agent. Paste as-is, no edits needed:

```python
"""My first agent: reports two safe, fake actions to ObserveAgents."""
import os
import uuid
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

def event(**fields):
    e = {
        "event_id": str(uuid.uuid4()),               # unique per event
        "agent_id": os.environ["AGENT_ID"],
        "agent_name": os.environ["AGENT_NAME"],
        "team": os.environ["AGENT_TEAM"],
        "environment": os.environ["AGENT_ENVIRONMENT"],
        "owner": os.environ["AGENT_OWNER"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
    }
    e.update(fields)
    return e

events = [
    # action 1: the "agent" asked an LLM to look up an invoice (fake)
    event(event_type="llm_call", provider="openai", model="gpt-4o-mini",
          input_tokens=420, output_tokens=95, latency_ms=780,
          action_name="invoice_lookup"),
    # action 2: the "agent" used a harmless tool (fake)
    event(event_type="tool_call", tool_name="crm_contact_search",
          action_name="support_ticket_summary", latency_ms=310),
]

resp = requests.post(
    os.environ["OBSERVEAGENTS_TELEMETRY_URL"],
    json={"events": events},
    headers={"Authorization": f"Bearer {os.environ['OBSERVEAGENTS_API_KEY']}"},
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
> `HTTP 202 - {"accepted":2,"duplicated":0,"failed":0,...}`.
> **`accepted: 2` means ObserveAgents took both events.** Behind the scenes
> a background worker now processes them: it registers your agent, computes
> cost from the model's price, and checks every event against the risk rules
> — this takes a few seconds at most.

---

## Step 4 — See it in the product (3 min)

Open the dashboard and refresh. Look in three places, in this order:

1. **Agents** (left menu) — *Billing Agent Demo* is now in your Agent
   Inventory, with team **Finance**, your email as owner, and environment
   **development**. ObserveAgents discovered it automatically from the
   telemetry — nobody registered it by hand.

2. **Runtime** (left menu) → click the **Agent events** toggle at the top of
   the page → pick *Billing Agent Demo* in the selector. Both actions are
   there: the LLM call (with model, tokens, latency, and a cost that
   ObserveAgents computed itself — marked `est`) and the tool call.

3. **Rules & Alerts** (left menu) — probably quiet for now. That's correct:
   your two events were clean, so no rule fired. Let's fix that.

> ✅ **Checkpoint:** you found your agent in **Agents** and its two events in
> **Runtime → Agent events**.

---

## Step 5 — Make something go wrong (on purpose) (2 min)

The product's real job is catching *risky* behavior. Add one bad-but-safe
event: an action that failed and took far too long. Add this to the `events`
list in `agent.py` (before the closing `]`):

```python
    # action 3: a failure — safe, but risky-looking
    event(event_type="tool_call", tool_name="invoice_lookup",
          status="error", error_message="Tool returned timeout (demo)",
          latency_ms=45000),
```

Run the script again (same command as Step 3). You'll get `accepted: 1,
duplicated: 0` — only the new event is new; the first two are recognized as
already-sent and ignored (that's the `event_id` doing its job).

Now look again:

- **Runtime → Agent events** — the new event has an **error** badge, a
  **MEDIUM** risk badge, and the reasons: *"Event reported an error"* and
  *"Latency 45000ms exceeds threshold"*. ObserveAgents scored it
  automatically (error +25, slow +15 = risk 40).
- **Rules & Alerts** — the event now appears in **Recent findings**, naming
  the rule that fired, with a button that jumps you back to the agent's
  activity. This page is also where admins tune the rules themselves —
  thresholds, severity, on/off.

> ✅ **Checkpoint:** you can see a risk finding and explain *why* it fired.
> **That's the whole product loop:** agent acts → telemetry in → evidence,
> cost, and risk out.

---

## You're done — what next?

| I want to… | Go to |
|---|---|
| Connect a **real** agent that uses OpenTelemetry | [otel-deployment-guide.md](otel-deployment-guide.md) — from a first curl to a production Collector |
| Understand everything the telemetry API can do (all fields, dedup, metrics) | [telemetry_ingestion.md](telemetry_ingestion.md) |
| Use the Python SDK instead of raw HTTP | [sdk-guide.md](sdk-guide.md) |
| Let GitHub Copilot write the agent for you | [Copilot prompts below](#bonus-let-github-copilot-write-it) |

**Good to know:**
- The same `gk-` key also works for OpenTelemetry traces
  (`POST /otel/v1/traces`). Those show up in **Runtime → Traces** (the other
  toggle), as expandable execution waterfalls.
- Send only **fake data** while learning. ObserveAgents keeps the raw payload
  of everything you send (that's a feature — it's investigation evidence), so
  never put passwords, keys, or customer data in telemetry fields.
- Keep `environment=development` on test agents so they never mix with
  production data — remember you're sending into a live system that your
  teammates also see.

---

## Bonus: let GitHub Copilot write it

Open Copilot Chat in VS Code and paste:

```text
Create a Python script called agent.py that loads configuration from a .env file and sends a batch of safe, fake AI-agent telemetry events to ObserveAgents at POST /api/v1/telemetry/batch. Each event needs a unique event_id (uuid), agent_id, agent_name, team, environment, owner, timestamp, event_type, and where relevant provider, model, input_tokens, output_tokens, latency_ms, tool_name, action_name, and status. Authenticate with a Bearer gk- API key from .env. Do not hardcode secrets. Use requests and python-dotenv. Print the HTTP status and response body.
```

Then compare what it wrote against Step 2 above — especially the endpoint
path, the `Bearer gk-` header, and that no secret is hardcoded.

---

## What went wrong?

| You see | It means | Do this |
|---|---|---|
| `HTTP 401` | Wrong or missing key | Check `.env`: the key starts with `gk-` (a dash), no quotes, no spaces. Is the key still active in the API Keys page? |
| `HTTP 404` | Wrong URL | The path must be exactly `/api/v1/telemetry/batch` after your domain. No trailing slash. |
| `accepted: 0, duplicated: 2` | You re-sent the same events | Fine — nothing is stored twice. New runs create new `event_id`s automatically. |
| `failed: 1` with an error message | One event had a bad field | The response names the field and the problem; fix just that event. Other events still went in. |
| Connection error / timeout | Can't reach the server | Open `https://YOUR-OBSERVEAGENTS-URL/health` in a browser — you should see `"status":"ok"`. If not, the URL is wrong. |
| Docker: `-p is not recognized` (PowerShell) | A multi-line command got split | Paste the Docker command as **one line** (PowerShell doesn't understand `\` line-breaks). |
| Docker can't reach `localhost` | Containers have their own localhost | If ObserveAgents runs on your own machine, use `http://host.docker.internal:<port>` in `.env` instead of `localhost`. Real domains are unaffected. |
| Agent missing in the dashboard | Worker still processing, or wrong view | Wait ~5 seconds, refresh. In Runtime, make sure the **Agent events** toggle is selected and the time range covers now. |
| Nothing in Rules & Alerts | Your events were clean | That's success, not failure. Do Step 5 to trigger a finding. |
