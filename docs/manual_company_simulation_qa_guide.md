# Manual Company Simulation QA Guide

*A step-by-step guide for manually testing Observe as if a new customer organization just onboarded.*

This is an **internal QA manual for you, the tester**. It contains technical detail (curl, Python, Collector config) that intentionally does **not** appear in the customer-facing quick start. Companion docs: [technical implementation guide](organization_implementation_guide.md) · [non-technical quick start](organization_quick_start_non_technical.md).

---

## 1. Purpose of this guide

This guide helps you manually simulate a real company joining Observe. You will create or use a fake company, connect AI data through both ingestion paths, and check that the product clearly explains:

- what AI exists
- what AI is actually running
- what each AI system connects to
- what risks exist
- what cost/usage signals exist
- which guardrails would trigger in observe-only mode

This is **not an automated QA run**. This is a manual walkthrough you perform yourself, clicking through the product like a customer would.

---

## 2. Fake company profile

Use this fake company throughout:

| | |
|---|---|
| **Company name** | Acme AI Operations |
| **Industry** | B2B SaaS / Customer Support Automation |
| **Departments** | Platform, Customer Support, Finance, Engineering, HR, Security |
| **Main goal** | Understand which AI systems are running, what they connect to, where the risks are, and which guardrails would trigger in observe-only mode |

---

## 3. Step-by-step: create or select the fake company

### Option A — Use the existing seeded demo company

Use this if demo seed data already exists in your environment.

1. Open the app.
2. Log in as `demo@observeagents.ai` / `Demo123!`.
3. Confirm the organization shown is **Acme AI Operations** (check the header/org context).
4. Open **Dashboard** and confirm data appears.

**Pass:**
- [ ] You can log in
- [ ] The organization shown is the demo organization
- [ ] Runtime and Asset Intelligence have data

**Fail:** login fails → the seed hasn't been run in this environment (see §7 A1). Header shows the wrong organization → you're logged in as a different user; log out fully. Runtime/Asset Intelligence empty → run the seed (A1) or check you're in the right org.

### Option B — Create a fresh fake organization

Use this to test onboarding from scratch. Organization creation **is available in the UI** for platform admins.

1. Log in as a **platform admin** user.
2. Go to **Organizations** (bottom of the Administration nav — platform admins only).
3. Create a new organization named **Acme AI Operations**.
4. Switch into it using the **◆ Platform View** selector at the bottom of the sidebar.
5. Confirm the header shows **Viewing: Acme AI Operations**.
6. Go to **Users** and add the test users from §4.
7. Go to **API Keys** and create the keys from §5.

**Pass:**
- [ ] Organization is created
- [ ] Platform View shows the correct organization
- [ ] New users belong to the organization
- [ ] No data from other organizations is visible anywhere

**Fail:** can't see the Organizations page → your user isn't a platform admin. Data from another org appears → **stop and report; this is a serious isolation bug.** Users land in the wrong org → check which org was selected when you created them.

> Tip: in demo/dev environments, the Platform View panel also has a **Populate Organization** button that fills the selected org with the full demo dataset (gateway + OTel) in one click — useful when you want data without running anything locally.

---

## 4. Create test users

Create (or verify, if using the seeded org) these users under **Users**:

| User | Email | Role | What to verify |
|---|---|---|---|
| Admin | admin@acme-demo.example | Admin | Can manage users, API keys, settings, budgets |
| Analyst | analyst@acme-demo.example | Analyst | Can review Runtime, Asset Intelligence, findings |
| Viewer | viewer@acme-demo.example | Viewer | Can view intelligence pages but cannot mutate settings/budgets |

Then log in as each one and check:

**Admin** — can open:
- [ ] Settings
- [ ] Users
- [ ] API Keys (and create a key)
- [ ] Budgets (and create/delete a budget rule)

**Analyst** — can open:
- [ ] Runtime, Asset Intelligence, Security Intelligence, Cost Intelligence, Guardrails
- [ ] Cannot see Users / API Keys / Settings in the nav

**Viewer** — can open:
- [ ] All read-only intelligence pages (Runtime, Asset Intelligence, Security, Cost, Guardrails)
- [ ] Budgets and Pricing Registry (read-only — no "Add Budget Rule" form, no Delete buttons)
- [ ] Cannot create API keys, cannot change settings

**Fail:** a viewer sees an Add/Delete control on Budgets, or any role opens a page it shouldn't — note the role + page and report.

---

## 5. Create API keys for simulated AI systems

Go to **API Keys → Create**. Create one key per simulated AI system:

- `support-agent-prod`
- `finance-agent`
- `engineering-copilot`
- `hr-onboarding-bot`
- `research-agent`

Why: separate keys let you test team attribution, ownership, and revocation independently.

**Check:**
- [ ] Each key is created and starts with `gk-`
- [ ] The full key value is shown **only once** at creation (copy it immediately)
- [ ] Key names are clear in the list
- [ ] (Optional) Revoke one key, retry a request with it, and confirm it is rejected

---

## 6. Define the simulated AI systems

These five systems represent the fake company's AI footprint. The seed dataset creates exactly these; if you're building manually, aim for the same shape:

| AI system | Team | Environment | Purpose | Expected signals |
|---|---|---|---|---|
| support-agent | Customer Support | production | Handles customer escalations | LLM, retrieval, Jira, CRM, Slack |
| finance-analyst-agent | Finance | production | Financial analysis | LLM, documents, database, calculation tool |
| engineering-copilot | Engineering | staging | Developer assistant | repo context, MCP/tools, code suggestions |
| hr-onboarding-bot | HR | production | Employee onboarding | knowledge base, workflow, Slack |
| research-agent | Platform | development | Research assistant | search, external API, one runtime error |

---

## 7. Path A — Manual test with OpenTelemetry / OTLP

This path tests the primary Runtime Discovery flow. Three ways, easiest first:

### A1 — Use demo seed data (internal/local only)

From the repo root, with `DATABASE_URL`, `JWT_SECRET`, and `CREDENTIAL_ENCRYPTION_KEY` set to your environment's values:

```bash
python scripts/seed_demo_data.py
```

**Expected:** 5 traces, 5 AI systems, 32 capabilities, 22 findings, one error trace. Running it twice creates nothing new (idempotent).

⚠️ This command is **internal-only**. Part of your QA (§15) is confirming it does **not** appear anywhere in the customer-facing UI.

### A2 — Send a sample OTLP JSON payload yourself

The fastest hands-on proof that ingestion works. Full walkthrough in the **Detailed setup** section below — do that section now if you want the deep test, or skim it and come back.

### A3 — Through an OpenTelemetry Collector

1. Ask engineering to add Observe as an exporter on an existing Collector (config is in the [technical guide](organization_implementation_guide.md) — the exporter **must use `encoding: json`**).
2. Trigger one request in the instrumented AI system.
3. Open **Runtime**.

**Pass criteria for Path A (any mode):**
- [ ] Runtime shows at least one trace
- [ ] The trace opens into an execution timeline
- [ ] Asset Intelligence discovers the AI system
- [ ] No raw prompts or responses are visible anywhere
- [ ] If an error span was sent, the UI shows an error signal

---

## Detailed setup: OpenTelemetry / OTLP path for the simulated company

This section connects **one** simulated system end to end:

> **AI system:** support-agent · **Company:** Acme AI Operations · **Team:** Customer Support · **Environment:** production
> **Purpose:** handles customer escalation requests using an LLM, retrieval, CRM lookup, Jira lookup, and Slack notification.

### What OpenTelemetry is (in one paragraph)

OpenTelemetry is a standard way for an application to send *traces* — structured records of what happened during a request and how long each step took. When those traces reach Observe, they become: Runtime traces, Execution Timelines, discovered AI systems, model/provider evidence, tool/dependency evidence, capabilities, findings, and the security/cost/guardrail signals built on top of them.

### What you need before starting

- [ ] Your Observe app URL
- [ ] The right organization selected (Acme AI Operations)
- [ ] An Observe API key (`gk-…`)
- [ ] For Mode 2: Python 3.10+, ability to run a local script, and (recommended) Docker for the Collector
- [ ] Access to the Runtime and Asset Intelligence pages to verify results

### The two setup modes

| | Mode 1 — Direct OTLP JSON test | Mode 2 — Real OTel instrumentation |
|---|---|---|
| What it is | One curl command with a hand-written payload | A small Python "support-agent" script with real OTel libraries |
| Installs anything? | No | Yes (pip packages + optional Collector container) |
| Good for | Proving ingestion works in 2 minutes | Realistic simulation of how a customer's service behaves |

---

### Mode 1 — Direct manual OTLP JSON test

#### 1. Create the API key

**API Keys → Create**, name it `support-agent-prod`, copy the key.

#### 2. Set variables in your terminal

```bash
OBSERVE_URL=https://<your-observeagents-url>
OBSERVE_API_KEY=gk-<your-api-key>

# Current time in nanoseconds (Linux). On macOS use:
#   NOW=$(python3 -c 'import time; print(int(time.time()*1e9))')
NOW=$(date +%s%N)
```

#### 3. Send the payload

This simulates one full support-agent escalation: a root request with five child steps. All values are fake — **no prompt text, no customer data**.

```bash
curl -sS -X POST "$OBSERVE_URL/otel/v1/traces" \
  -H "Authorization: Bearer $OBSERVE_API_KEY" \
  -H "Content-Type: application/json" \
  -d @- <<EOF
{
  "resourceSpans": [{
    "resource": {"attributes": [
      {"key": "service.name",           "value": {"stringValue": "support-agent"}},
      {"key": "deployment.environment", "value": {"stringValue": "production"}},
      {"key": "team",                   "value": {"stringValue": "customer-support"}}
    ]},
    "scopeSpans": [{"spans": [
      {
        "traceId": "aaaa1111bbbb2222cccc3333dddd4444",
        "spanId": "1111222233334444",
        "name": "support-agent escalation",
        "kind": 3,
        "startTimeUnixNano": $NOW,
        "endTimeUnixNano": $((NOW + 8400000000)),
        "status": {},
        "attributes": []
      },
      {
        "traceId": "aaaa1111bbbb2222cccc3333dddd4444",
        "spanId": "aaaa000000000001", "parentSpanId": "1111222233334444",
        "name": "llm.planning", "kind": 3,
        "startTimeUnixNano": $NOW,
        "endTimeUnixNano": $((NOW + 1200000000)),
        "status": {},
        "attributes": [
          {"key": "gen_ai.system",              "value": {"stringValue": "openai"}},
          {"key": "gen_ai.request.model",       "value": {"stringValue": "gpt-4o"}},
          {"key": "gen_ai.usage.input_tokens",  "value": {"intValue": 640}},
          {"key": "gen_ai.usage.output_tokens", "value": {"intValue": 180}}
        ]
      },
      {
        "traceId": "aaaa1111bbbb2222cccc3333dddd4444",
        "spanId": "aaaa000000000002", "parentSpanId": "1111222233334444",
        "name": "retrieval.kb_search", "kind": 3,
        "startTimeUnixNano": $((NOW + 1200000000)),
        "endTimeUnixNano": $((NOW + 4000000000)),
        "status": {},
        "attributes": [{"key": "tool.name", "value": {"stringValue": "vector_search"}}]
      },
      {
        "traceId": "aaaa1111bbbb2222cccc3333dddd4444",
        "spanId": "aaaa000000000003", "parentSpanId": "1111222233334444",
        "name": "crm.account_lookup", "kind": 3,
        "startTimeUnixNano": $((NOW + 4000000000)),
        "endTimeUnixNano": $((NOW + 5900000000)),
        "status": {},
        "attributes": [
          {"key": "tool.name", "value": {"stringValue": "crm_account_lookup"}},
          {"key": "url.full",  "value": {"stringValue": "https://api.acme-crm-demo.example/v1/accounts"}}
        ]
      },
      {
        "traceId": "aaaa1111bbbb2222cccc3333dddd4444",
        "spanId": "aaaa000000000004", "parentSpanId": "1111222233334444",
        "name": "jira.issue_search", "kind": 3,
        "startTimeUnixNano": $((NOW + 5900000000)),
        "endTimeUnixNano": $((NOW + 6600000000)),
        "status": {},
        "attributes": [{"key": "tool.name", "value": {"stringValue": "jira_issue_search"}}]
      },
      {
        "traceId": "aaaa1111bbbb2222cccc3333dddd4444",
        "spanId": "aaaa000000000005", "parentSpanId": "1111222233334444",
        "name": "slack.notify", "kind": 3,
        "startTimeUnixNano": $((NOW + 6600000000)),
        "endTimeUnixNano": $((NOW + 8400000000)),
        "status": {},
        "attributes": [{"key": "tool.name", "value": {"stringValue": "slack_channel_update"}}]
      }
    ]}]
  }]
}
EOF
```

You should get back `{"accepted": true, "spans": 6, …, "content_redacted": true}`.

**Optional error variant:** to also test error signals, resend with a **new** `traceId` (change the letters — duplicate trace+span IDs are deduplicated and silently skipped) and add `"status": {"code": 2, "message": "upstream timeout (synthetic)"}` to one child span.

#### 4. Verify in the app

1. Open **Runtime** — a `support-agent escalation` trace should appear within seconds, ~8.40s.
2. Click it — the timeline should show the five steps in hierarchy, with the LLM step badged as LLM and the tools as TOOL.
3. Open **Asset Intelligence** — click **▶ Run Intelligence** — the `support-agent` card should appear with model `gpt-4o`, provider OpenAI, the four tools, and the CRM API dependency.
4. Check its findings: expect at least production runtime + new system detected; the CRM+provider combination should raise a sensitive-access finding.

**Pass:**
- [ ] Trace appears within seconds
- [ ] Timeline has multiple steps in a hierarchy
- [ ] support-agent appears as an AI system with model/provider/tools
- [ ] No raw prompt/response appears anywhere

**If it fails:**

| Symptom | Check |
|---|---|
| `401` | API key wrong or `Authorization: Bearer gk-…` header malformed |
| `415` | Content-Type isn't `application/json` — or something sent protobuf. Observe accepts **OTLP JSON only** |
| Accepted but no trace in Runtime | Wrong org selected in the UI vs the key's org; or wrong URL path (`/otel/v1/traces`) |
| Trace appears flat (one bar) | Child spans missing `parentSpanId` |
| System named `observed-ai-system:…` | `service.name` resource attribute missing |
| Asset Intelligence empty | You didn't press **▶ Run Intelligence** |
| Re-sent payload, nothing new | Same traceId/spanIds are deduplicated — change the `traceId` |

---

### Mode 2 — Real Python OpenTelemetry instrumentation

A more realistic simulation: a small Python script acts as the support-agent, instrumented with real OTel libraries. **Create the working folder yourself locally — nothing here is committed to the repo.** Copy the code blocks below into the files described.

#### 1. Create a folder and environment

```bash
mkdir -p examples/support_agent_otel_simulation
cd examples/support_agent_otel_simulation
python3 -m venv .venv && source .venv/bin/activate
```

#### 2. `requirements.txt`

```
opentelemetry-sdk
opentelemetry-exporter-otlp-proto-http
```

```bash
pip install -r requirements.txt
```

#### 3. Start a local Collector (recommended)

Why the Collector: **Python's OTLP/HTTP exporter sends protobuf, but Observe accepts OTLP JSON only.** The Collector receives the protobuf locally and re-exports as JSON.

`otel-collector.yaml`:

```yaml
receivers:
  otlp:
    protocols:
      http:
exporters:
  otlphttp/observeagents:
    endpoint: "https://<your-observeagents-url>/otel"
    encoding: json
    headers:
      Authorization: "Bearer gk-<your-api-key>"
service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [otlphttp/observeagents]
```

```bash
docker run --rm -v $(pwd)/otel-collector.yaml:/etc/otelcol-contrib/config.yaml \
  -p 4318:4318 otel/opentelemetry-collector-contrib:latest
```

#### 4. `support_agent.py`

```python
"""Simulated support-agent for the Acme AI Operations QA walkthrough.
Emits one realistic escalation trace per run. All values are synthetic."""
import time
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

resource = Resource.create({
    "service.name": "support-agent",
    "deployment.environment": "production",
    "team": "customer-support",
})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces")  # → local Collector
))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("support-agent")

def step(name, seconds, attrs=None):
    with tracer.start_as_current_span(name) as span:
        for k, v in (attrs or {}).items():
            span.set_attribute(k, v)
        time.sleep(seconds)

with tracer.start_as_current_span("support-agent escalation"):
    step("llm.planning", 1.2, {
        "gen_ai.system": "openai",
        "gen_ai.request.model": "gpt-4o",
        "gen_ai.usage.input_tokens": 640,
        "gen_ai.usage.output_tokens": 180,
    })
    step("retrieval.kb_search", 2.8, {"tool.name": "vector_search"})
    step("crm.account_lookup", 1.9, {
        "tool.name": "crm_account_lookup",
        "url.full": "https://api.acme-crm-demo.example/v1/accounts",
    })
    step("jira.issue_search", 0.7, {"tool.name": "jira_issue_search"})
    step("slack.notify", 0.6, {"tool.name": "slack_channel_update"})

provider.shutdown()   # flush spans before exit
print("escalation trace sent — check Runtime in Observe")
```

#### 5. Run it

```bash
python support_agent.py
```

**Expected:** the script sleeps ~7 seconds simulating the steps, prints the confirmation line, and a new `support-agent escalation` trace appears in **Runtime** with the five-step waterfall. Every run generates fresh trace IDs, so run it several times to build up a realistic trace list. Then **▶ Run Intelligence** and check the support-agent card as in Mode 1 step 4.

**If it fails:** same table as Mode 1, plus — Collector logs show `415`/encoding errors → the `encoding: json` line is missing; script hangs at exit → the `provider.shutdown()` flush line is missing.

---

## 8. Path B — Manual test with the Gateway using existing provider SDKs

**This is not an Observe SDK.** There is no Observe SDK. This path uses *existing* provider SDKs or OpenAI-compatible clients — OpenAI SDK, Anthropic SDK, LangChain, CrewAI, LiteLLM — with the Observe Gateway as the base URL.

1. As admin, confirm provider credentials are configured under **Settings → Organization AI Providers** (needed for the gateway to reach the real provider).
2. Copy an Observe API key (e.g. `support-agent-prod`).
3. Configure an existing client to use the gateway as base URL (exact snippets: [technical guide](organization_implementation_guide.md), "Path B").
4. Send one test AI request.
5. Check Runtime/Dashboard/Cost pages for activity.

**Expected:**
- Request succeeds if provider credentials are configured
- If credentials are missing, you get a **clear** `provider_not_configured` (HTTP 424) error naming the provider and pointing to Settings — this is correct behavior, verify the message is understandable
- No unexpected blocking — the gateway stays advisory unless a team is intentionally set to enforce mode
- Usage/cost signals appear where supported

**Pass:**
- [ ] Gateway request is observed, or gives a clear setup error
- [ ] No customer-facing screen calls this an "Observe SDK"
- [ ] No unexpected blocking

**Fail:** setup language implies a custom Observe SDK · a request is blocked while the team is in observe mode · the missing-provider-key error is confusing · nothing appears and no error explains why.

---

## 9. Runtime page manual QA

1. Open **Runtime**.
2. Confirm the trace list appears.
3. Click a trace.
4. Review the waterfall.

**Check:**
- [ ] Root request exists
- [ ] LLM step appears (purple LLM badge) if sent
- [ ] Retrieval/tool steps appear (TOOL badge) if sent
- [ ] Database/API steps appear if sent
- [ ] Error span appears highlighted if sent
- [ ] Durations make sense (bars positioned and sized by time)
- [ ] No raw prompts or responses appear anywhere

**Expected with seeded data:** 5 traces; `support-agent customer escalation` ≈ **8.40s**; `research request` includes a **1 ERROR** badge.

---

## 10. Asset Intelligence manual QA

1. Open **Asset Intelligence**.
2. Confirm the **AI Systems** tab is the default.
3. Confirm systems are grouped by AI system (cards, not raw rows).
4. Expand a system (click a card).
5. Review models, providers, tools, dependencies, capabilities, and findings in the expanded sections.
6. Open the **Capabilities** tab — confirm it has an Asset column and filters.
7. Open the **Findings** tab — confirm asset attribution, severity/category filters, and Resolve/Dismiss (as admin/analyst).

**Expected seeded systems:** support-agent, finance-analyst-agent, engineering-copilot, hr-onboarding-bot, research-agent.

**Pass:**
- [ ] You can understand what each AI system does
- [ ] You can see what it connects to
- [ ] You can see findings per system with severity
- [ ] Capabilities/findings are not just unexplained raw rows
- [ ] research-agent shows an **Error observed** badge

---

## 11. Security Intelligence manual QA

1. Open **Security Intelligence**.
2. Look for the **Risky AI Systems** section.
3. Check findings are tied to specific assets.
4. Review the risky capability chips per system.

**Expected signals (seeded):** database access (finance-analyst-agent), MCP tools (engineering-copilot), external APIs, broad tool access, runtime errors (research-agent), high-severity findings.

**Pass:** the page answers *"Which AI systems have risky observed behavior?"* — not framed as a compliance workflow.

---

## 12. Cost Intelligence manual QA

1. Open **Cost Intelligence**.
2. Review the **Runtime Usage & Efficiency Signals** panel.
3. Look for slow/heavy systems ("potential cost hotspots").
4. Check model usage per system.
5. Confirm cost figures are labeled **Estimated** (and "Provider Billed" only shows data if invoices were imported).

**Pass:** the page answers *"Which AI systems look heavy, slow, or potentially expensive?"* and does **not** claim exact billing.

---

## 13. Budgets and Pricing Registry manual QA

**Budgets:**
- [ ] Framed as budget awareness / planning (advisory banner at the top)
- [ ] Viewer can read the page
- [ ] Viewer sees **no** Add form / Delete buttons
- [ ] Admin can create and delete a rule
- [ ] The "Block" action option says it only applies in enforce guard mode

**Pricing Registry:**
- [ ] Framed as a pricing **reference layer** (banner at the top)
- [ ] Not presented as exact billing
- [ ] Versioned model/provider prices visible, clearly feeding cost estimation

---

## 14. Guardrails manual QA

1. Open **Guardrails**.
2. Confirm the **Observe-only mode** banner is prominent and clear.
3. Review the triggered guardrails list (severity, affected systems, recommendations on expand).
4. As admin, check the Guard Modes table below (per team, "would block (30d)"). As viewer, confirm the page still works with that section hidden.

**Expected guardrails (seeded — all 7 trigger):** database access, MCP tools, external APIs, broad tool access, production + high severity, runtime errors, slow/expensive path.

**Pass:** you understand what would trigger and that **nothing is blocked by default**.
**Fail:** the page sounds like it is blocking production AI by default.

---

## 15. Setup and Integrations manual QA

Open **Setup**. Confirm:

- [ ] **No** demo seed command appears anywhere
- [ ] **No** custom Observe SDK language
- [ ] **No** "SDK Metadata" section
- [ ] **No** Manual Headers / X-Agent-* setup
- [ ] "Connect your first AI system" block with the five plain steps is present
- [ ] OpenTelemetry is the primary path (OTLP block visible in the Runtime Discovery guide)
- [ ] Gateway is presented as the second supported path with client examples
- [ ] Ecosystem Discovery is clearly badged **"Coming later"** — both on the option card and inside its preview

---

## 16. End-to-end demo script you can perform (5–7 minutes)

| # | Click | Say | Should be visible |
|---|---|---|---|
| 1 | **Dashboard** | "Observe shows the real AI footprint — what exists, what's running, what needs attention." | "See your real AI footprint" hero, six pillar cards, KPIs |
| 2 | **Runtime** → click `support-agent customer escalation` | "Here's a real execution — 8.4 seconds, and here's exactly where the time went." | Trace list → waterfall with LLM/retrieval/CRM/Jira/Slack steps |
| 3 | **Asset Intelligence** | "One card per AI system: its models, tools, everything it touches, and its findings." | Five grouped cards; expand support-agent to show detail sections |
| 4 | **Security Intelligence** | "Which systems have risky observed behavior — this one touches the database, this one uses MCP tools." | Risky AI Systems table with capability chips |
| 5 | **Cost Intelligence** | "Which workflows are slow or heavy — these are the likely cost hotspots. Signals, not invoices." | Usage & Efficiency Signals panel |
| 6 | **Guardrails** | "Guardrails run observe-only: detect, explain, recommend. Nothing gets blocked until *you* decide." | Observe-only banner, 7/7 triggered with affected systems |
| 7 | **Setup** | "And this is how real data gets in — OpenTelemetry or the gateway; ecosystem connectors are next." | Connect-first-system steps, OTLP block, "Coming later" ecosystem |

---

## 17. Final pass/fail checklist

**Organization**
- [ ] Company exists or demo org selected
- [ ] Users exist with correct roles
- [ ] Role access behaves per §4
- [ ] API keys exist

**OTel path**
- [ ] Trace ingested (curl or script)
- [ ] Runtime shows the trace
- [ ] Timeline renders with hierarchy
- [ ] Asset discovered
- [ ] Intelligence derived after Run Intelligence

**Gateway path**
- [ ] Existing SDK/client can point at the gateway
- [ ] Request is observed, or the setup error is clear
- [ ] No unexpected blocking

**Product pages**
- [ ] Dashboard clear · Runtime works · Asset Intelligence grouped
- [ ] Security useful · Cost useful · Budgets/Pricing understandable
- [ ] Guardrails observe-only clear · Setup clean · Integrations clear

**Privacy**
- [ ] No raw prompts · no raw responses · no secrets · no raw tool args/results anywhere in the UI

**Copy/product**
- [ ] No customer-facing local seed command
- [ ] No custom Observe SDK claims
- [ ] No manual X-Agent header setup
- [ ] No exact-billing overclaim
- [ ] No enforcement-by-default claim

---

## 18. Known limitations (expected — do not file as bugs)

- **Ecosystem Discovery** (GitHub / Jira / Slack / n8n / MCP connectors) is future — the UI marks it "Coming later"
- **Exact cost** requires token usage + pricing data; otherwise you see estimates and signals
- **Enforcement** is optional and deliberately not the first step — observe-only is the intended starting mode
- **Observe Advisor / ML recommendations** are future roadmap
- **A custom Observe SDK is not part of the product** — the gateway path uses existing provider SDKs, and that's by design
