# Walkthrough — Connecting an OTLP Agent With Unmapped (Custom) Fields

**The scenario:** you already have an agent in your organization, it's
connected via OTLP, but your instrumentation uses **your own attribute
names** — not the OpenTelemetry GenAI conventions. Nothing was "prepared" for
ObserveAgents. This guide shows exactly what happens, what the product tells
you, and how you fix it in ~2 minutes without touching code.

Every step below was executed against a live environment; the outputs shown
are real.

---

## Step 1 — Send telemetry the way it really looks

A typical unprepared trace: a workflow with an LLM call, a tool call, and a
DB query — where the LLM/tool attributes use company-internal names
(`acme.*`, `tool_used`) and there's no `deployment.environment`.

Save as `naive_agent.py` (uses your `.env` from the
[getting-started guide](create_first_agent_guide.md)):

```python
import os, time, uuid, requests
from dotenv import load_dotenv
load_dotenv()

BASE = os.environ["OBSERVEAGENTS_BASE_URL"]      # e.g. https://YOUR-LIVE-DOMAIN
KEY  = os.environ["OBSERVEAGENTS_API_KEY"]       # gk-...
now = time.time_ns()

def attr(k, v):
    kind = "intValue" if isinstance(v, int) else "stringValue"
    return {"key": k, "value": {kind: v}}

def span(name, attrs, dur_ms, parent=None, tid=None):
    s = {"traceId": tid, "spanId": uuid.uuid4().hex[:16], "name": name, "kind": 3,
         "startTimeUnixNano": str(now - dur_ms * 1_000_000), "endTimeUnixNano": str(now),
         "attributes": [attr(k, v) for k, v in attrs.items()], "status": {}}
    if parent: s["parentSpanId"] = parent
    return s

tid = uuid.uuid4().hex
root = span("handle_quote_request", {"session.id": uuid.uuid4().hex}, 2400, tid=tid)
spans = [root,
  # custom names — NOT gen_ai.* conventions:
  span("call_llm", {"acme.llm.model": "gpt-4o", "acme.llm.vendor": "openai",
                    "acme.tokens_in": 900, "acme.tokens_out": 210}, 1300, root["spanId"], tid),
  span("run_tool", {"tool_used": "quote_calculator"}, 400, root["spanId"], tid),
  # db.system IS a standard convention — this one will be understood as-is:
  span("query_db", {"db.system": "postgresql", "db.name": "quotes"}, 180, root["spanId"], tid),
]
payload = {"resourceSpans": [{"resource": {"attributes": [attr("service.name", "quote-engine-agent")]},
                              "scopeSpans": [{"spans": spans}]}]}
r = requests.post(f"{BASE}/otel/v1/traces", json=payload,
                  headers={"Authorization": f"Bearer {KEY}"})
print(r.status_code, r.text)
```

Real response:

```json
202 {"accepted": true, "resource_spans": 1, "spans": 4, "ai_systems": 1,
     "relationships": 1, "provenance_events": 4, "otel_assets": 1, "content_redacted": true}
```

**Nothing is rejected.** The agent is discovered, all 4 spans are stored, and
the one standard attribute (`db.system`) already produced a dependency
relationship. The custom `acme.*` fields are stored too — just not yet
*understood*.

## Step 2 — See what the product tells you

Open **Observe → Telemetry Quality**. This is the honest-mirror page:

- `quote-engine-agent` shows **Partially classified — score 60/100** —
  "4 spans · 4 missing signals · 5 custom keys"
- A banner: *"Custom attribute keys were detected but no attribute mapping is
  configured yet — **map them in Settings**"*
- **Custom attribute keys detected** lists your exact keys:
  `acme.llm.model →`, `acme.llm.vendor →`, `acme.tokens_in →`,
  `acme.tokens_out →`, `tool_used →`
- **Missing signals** names what mapping can't provide:
  *"Deployment environment — 4 spans → add `deployment.environment`"*

Meanwhile the agent already exists in **Agents** (auto-discovered, status
*potential*) and its trace renders in **Runtime → Traces** — with the DB
step understood and the LLM step generic.

## Step 3 — Map your fields (admin, ~2 minutes, no code)

In **Settings → OTel Attribute Mapping** (or via API), map each custom key to
its canonical attribute:

| Your key | Canonical attribute |
|---|---|
| `acme.llm.model` | `gen_ai.request.model` |
| `acme.llm.vendor` | `gen_ai.provider.name` |
| `acme.tokens_in` | `gen_ai.usage.input_tokens` |
| `acme.tokens_out` | `gen_ai.usage.output_tokens` |
| `tool_used` | `gen_ai.tool.name` |

API equivalent (admin JWT):

```bash
curl -X PUT https://YOUR-LIVE-DOMAIN/settings/otel-attribute-mapping \
  -H "Authorization: Bearer <ADMIN_JWT>" -H "Content-Type: application/json" \
  -d '{"mapping": {"acme.llm.model": "gen_ai.request.model",
        "acme.llm.vendor": "gen_ai.provider.name",
        "acme.tokens_in": "gen_ai.usage.input_tokens",
        "acme.tokens_out": "gen_ai.usage.output_tokens",
        "tool_used": "gen_ai.tool.name"},
       "reprocess": true}'
```

Real response (`reprocess: true` repairs **history**, not just future data):

```json
{"reprocess": {"spans_seen": 6, "spans_reclassified": 0, "spans_rescored": 1,
               "provenance_updated": 1, "assets_rebuilt": 3,
               "relationships_created": 1, "capped": false}}
```

Notes: a canonical key emitted natively is never overwritten by a mapping,
and you can re-run reprocessing any time with **Reclassify** on the
Telemetry Quality page.

## Step 4 — What's fixed, and the one thing that isn't

After mapping:

- **New spans** from this agent arrive fully understood — model, provider,
  tokens, and tool are extracted natively; model/tool dependency
  relationships build up in Asset Intelligence and the Dependency Map.
- **Stored history** was rescored/rebuilt per the reprocess counts above.
- The agent **stays "Partially classified"** for one honest reason:
  `deployment.environment` is missing, and **a mapping cannot invent it** —
  it must be added at the source as a resource attribute:

```python
# in your OTel Resource:
"deployment.environment": "production"
```

That's the platform's contract with unprepared telemetry: **ingest
everything → classify and score honestly → name each missing signal and every
custom key that looks useful → let an admin map keys in minutes → reprocess
history → tell you the one thing only the source can fix.**

## Quick checklist

- [ ] `202` with `ai_systems: 1` — agent discovered despite custom fields
- [ ] Telemetry Quality shows *Partially classified* + your custom keys by name
- [ ] Mapping saved (Settings → OTel Attribute Mapping) with reprocess
- [ ] Reprocess counters returned (spans rescored / relationships created)
- [ ] `deployment.environment` added at the source → agent reaches full classification

Related: [otel-deployment-guide.md](otel-deployment-guide.md) (full OTLP
reference, Collector, semantic conventions) ·
[create_first_agent_guide.md](create_first_agent_guide.md) (first steps) ·
Telemetry Quality concepts in the deployment guide's
[Telemetry Quality](otel-deployment-guide.md#telemetry-quality) section.
