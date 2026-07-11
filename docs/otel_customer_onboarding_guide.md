<!--
Bilingual (Hebrew + English) customer onboarding / self-lab guide for
connecting OpenTelemetry to ObserveAgents. Code, commands and config are
in English; explanatory text is provided in both Hebrew and English.
-->

# ObserveAgents — OpenTelemetry Onboarding & Self-Lab
# ObserveAgents — חיבור OpenTelemetry ומעבדה עצמית

**~1 hour · rehearses the exact flow you run at a customer**
**כשעה · מדמה בדיוק את התהליך שתריצו אצל לקוח**

---

## What this is / מה זה

**EN.** A self-contained lab you can run on your own laptop against the real production platform. You stand up an OpenTelemetry Collector, emit realistic agent spans from a fake "customer agent", ship them to ObserveAgents, and watch the platform discover the agent, extract its capabilities, and raise runtime-security findings — the exact "aha" moment you'll show a customer.

**HE.** מעבדה עצמאית שאתם מריצים על המחשב שלכם מול הפלטפורמה האמיתית ב‑production. מקימים OpenTelemetry Collector, פולטים spans ריאליסטיים מ"סוכן לקוח" מדומה, שולחים ל‑ObserveAgents, ורואים את הפלטפורמה מגלה את הסוכן, מחלצת את היכולות שלו ומעלה ממצאי runtime‑security — בדיוק רגע ה"וואו" שתציגו ללקוח.

---

## 3 platform-specific facts — read before a customer call
## 3 עובדות ספציפיות לפלטפורמה — לקרוא לפני שיחת לקוח

> These correct the generic OpenTelemetry guides. They are verified against the backend.
> אלה מתקנים את המדריכים הגנריים של OpenTelemetry. מאומתים מול ה‑backend.

1. **HTTP + traces only.** ObserveAgents ingests **OTLP over HTTP**, **traces only**, at `POST /otel/v1/traces` (JSON or protobuf). There is **no gRPC (4317) listener** and **no metrics/logs endpoints**. The Collector must use the **`otlphttp`** exporter, and only the **`traces`** pipeline points at ObserveAgents.
   *HE:* קליטה ב‑**HTTP בלבד**, **traces בלבד**, בכתובת `POST /otel/v1/traces`. אין מאזין gRPC ואין endpoints ל‑metrics/logs. ה‑Collector חייב להשתמש ב‑exporter מסוג `otlphttp`, ורק ה‑pipeline של `traces` מפנה ל‑ObserveAgents.

2. **Auth = API key (`gk-…`), not a JWT.** The endpoint accepts both, but dashboard JWTs expire after 8 hours. A Collector needs the **long-lived `gk-` key** you create in the dashboard.
   *HE:* אימות עם **מפתח API (`gk-…`)**, לא עם JWT. ה‑endpoint מקבל את שניהם, אבל JWT של הדשבורד פג אחרי 8 שעות. ל‑Collector צריך את מפתח ה‑`gk-` ארוך‑הטווח.

3. **Exporter endpoint = `https://app.observeagents.ai/otel`.** The `otlphttp` exporter appends `/v1/traces` itself, landing exactly on `/otel/v1/traces`. Do **not** add `/v1/traces` yourself.
   *HE:* כתובת ה‑exporter היא `https://app.observeagents.ai/otel`. ה‑exporter מוסיף `/v1/traces` בעצמו. אל תוסיפו `/v1/traces` ידנית.

---

## Phase 0 — Prepare the platform side (5 min)
## שלב 0 — הכנת צד הפלטפורמה (5 דק')

**EN.** Log into [app.observeagents.ai](https://app.observeagents.ai) as admin → open the **API Keys** page → create a key and save the `gk-…` value. *Optional but recommended:* first create a separate **"lab" organization** (Admin → Organizations) and create the key there, so your test agents don't mix into your main org's inventory — this also rehearses customer tenant onboarding.

**HE.** התחברו ל‑[app.observeagents.ai](https://app.observeagents.ai) כאדמין → עמוד **API Keys** → צרו מפתח ושמרו את הערך `gk-…`. *רשות אך מומלץ:* צרו תחילה **ארגון "lab" נפרד** (Admin → Organizations) ופתחו שם את המפתח, כדי שסוכני הבדיקה לא יתערבבו ב‑inventory של הארגון הראשי — זה גם מתרגל onboarding של tenant לקוח.

---

## Phase 1 — Collector with a debug exporter (prove telemetry flows)
## שלב 1 — Collector עם debug exporter (הוכחת זרימת טלמטריה)

**EN.** Start with debug output only, to confirm spans arrive before you touch the platform.
**HE.** מתחילים עם פלט debug בלבד, כדי לוודא ש‑spans מגיעים לפני שנוגעים בפלטפורמה.

`otel-collector-config.yaml`:

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
processors:
  batch: {}
exporters:
  debug:
    verbosity: normal
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
```

Run it:

```bash
docker run --rm -p 4318:4318 \
  -v $(pwd)/otel-collector-config.yaml:/etc/otelcol/config.yaml \
  otel/opentelemetry-collector:latest --config=/etc/otelcol/config.yaml
```

---

## Phase 2 — A fake "customer agent" that emits realistic spans
## שלב 2 — "סוכן לקוח" מדומה שפולט spans ריאליסטיים

**EN.** This script plays the customer's AI system. The attributes are chosen so the platform lights up: session grouping (`session.id`), a GenAI call, a database dependency, and an MCP tool call.

**HE.** הסקריפט הזה משחק את מערכת ה‑AI של הלקוח. התכונות נבחרו כך שהפלטפורמה "תידלק": קיבוץ session (`session.id`), קריאת GenAI, תלות במסד נתונים, וקריאת כלי MCP.

```bash
pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
```

`lab_agent.py`:

```python
# lab_agent.py — pretend customer-support-agent
import time
import uuid
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

resource = Resource.create({
    "service.name": "customer-support-agent",
    "deployment.environment": "production",   # -> findings become "high" severity
    "team": "support-ai",
})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces")))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("lab")

session = uuid.uuid4().hex
with tracer.start_as_current_span("agent.workflow") as root:
    root.set_attribute("session.id", session)

    with tracer.start_as_current_span("gen_ai.request") as s:
        s.set_attribute("session.id", session)
        s.set_attribute("gen_ai.provider.name", "anthropic")
        s.set_attribute("gen_ai.request.model", "claude-sonnet-5")
        s.set_attribute("gen_ai.usage.input_tokens", 850)
        s.set_attribute("gen_ai.usage.output_tokens", 300)
        time.sleep(0.2)

    with tracer.start_as_current_span("db.query") as s:
        s.set_attribute("session.id", session)
        s.set_attribute("db.system", "postgresql")
        s.set_attribute("db.name", "tickets")

    with tracer.start_as_current_span("mcp.call") as s:
        s.set_attribute("session.id", session)
        s.set_attribute("mcp.method.name", "tools/call")
        s.set_attribute("gen_ai.tool.name", "jira_search")

provider.shutdown()
print("sent — session", session)
```

**EN.** Run `python lab_agent.py` and confirm the spans print in the Collector's debug output. That's your checkpoint before pointing at the platform.
**HE.** הריצו `python lab_agent.py` וודאו שה‑spans מודפסים בפלט ה‑debug של ה‑Collector. זו נקודת הביקורת לפני שמפנים לפלטפורמה.

> **Note / הערה:** the generic Python examples floating around have copy-paste-broken imports (e.g. `from opentelemetryimport trace`). Use the imports above exactly.
> הדוגמאות הגנריות ברשת מכילות imports שבורים מהעתקה (למשל `from opentelemetryimport trace`). השתמשו ב‑imports שכאן בדיוק.

---

## Phase 3 — Point the Collector at ObserveAgents
## שלב 3 — הפניית ה‑Collector ל‑ObserveAgents

**EN.** Add the `otlphttp` exporter on the **traces** pipeline. Keep `debug` too, so you still see local output.
**HE.** הוסיפו את ה‑exporter מסוג `otlphttp` ל‑pipeline של **traces**. השאירו גם `debug` כדי לראות פלט מקומי.

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch: {}

exporters:
  debug:
    verbosity: normal

  otlphttp/observeagents:
    endpoint: https://app.observeagents.ai/otel
    headers:
      authorization: "Bearer YOUR_API_KEY_HERE"

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug, otlphttp/observeagents]
```

> The endpoint stays `…/otel` — the `otlphttp` exporter appends `/v1/traces` itself. `YOUR_API_KEY_HERE` is the `gk-…` key from Phase 0.
> הכתובת נשארת `…/otel` — ה‑exporter מוסיף `/v1/traces` בעצמו. `YOUR_API_KEY_HERE` הוא מפתח ה‑`gk-…` משלב 0.

Restart the Collector, run `python lab_agent.py` again. A successful ingest returns **HTTP 202** to the Collector.
*HE:* הפעילו מחדש את ה‑Collector, הריצו שוב `python lab_agent.py`. קליטה מוצלחת מחזירה ל‑Collector **HTTP 202**.

---

## Phase 4 — See the value appear (the customer demo moment)
## שלב 4 — לראות את הערך מופיע (רגע הדמו ללקוח)

In the dashboard / בדשבורד:

1. **Runtime** — the trace appears as **one collapsed session row**; expand it into a per-step execution waterfall.
   *HE:* ה‑trace מופיע כ**שורת session אחת מכווצת**; פתחו אותה ל‑waterfall של הצעדים.
2. **Asset Intelligence / Inventory** — `customer-support-agent` now exists, with model/provider evidence.
   *HE:* `customer-support-agent` קיים כעת, עם ראיות של model/provider.
3. **Security Intelligence** — capabilities (provider, model, database, MCP) plus the runtime-security findings below.
   *HE:* יכולות (provider, model, database, MCP) ובנוסף ממצאי ה‑runtime‑security שלמטה.
4. **Close the governance loop** — **Claim** the asset and assign an **owner** (admin action). The `agent_missing_owner` finding clears — showing the observe → govern loop closing.
   *HE:* **סגירת לולאת ה‑governance** — בצעו **Claim** לנכס ושייכו **owner** (פעולת אדמין). הממצא `agent_missing_owner` נעלם — ממחיש את סגירת הלולאה observe → govern.

### Findings this lab agent raises / ממצאים שהסוכן הזה מעלה

| Finding | Severity | Why it fires / למה נורה |
|---|---|---|
| `agent_has_database_access` | **high** | A DB span is present (`db.system=postgresql`); high because `deployment.environment=production`. |
| `agent_uses_mcp_tool_in_production` | **high** | An MCP call is present (`mcp.method.name=tools/call`) in a production environment (production-only finding). |
| `agent_missing_owner` | **high** | No owner/team assigned yet — clears after you Claim the asset. |
| `human_review_recommended` | **high** | High-risk combination: a production agent with both DB access and MCP use (2 reasons → high). |

> `anthropic` / `claude-sonnet-5` is a **known** provider, so the lab agent deliberately raises **no** unknown-provider finding. Swap the provider to something like `"acme-llm"` to demo `agent_uses_unknown_model_provider`.
> `anthropic` / `claude-sonnet-5` הוא provider **מוכר**, ולכן הסוכן במכוון **לא** מעלה ממצא unknown-provider. החליפו את ה‑provider ל‑`"acme-llm"` כדי להדגים את `agent_uses_unknown_model_provider`.

---

## Direct path (no Collector) — the fastest onboarding fallback
## נתיב ישיר (בלי Collector) — נפילת‑ברירת‑מחדל המהירה ל‑onboarding

**EN.** When a customer's platform team can't provision a Collector on day one, the SDK can post straight to ObserveAgents. Change only the exporter in `lab_agent.py`:

**HE.** כשצוות התשתיות של הלקוח לא יכול להקים Collector ביום הראשון, ה‑SDK יכול לשלוח ישירות ל‑ObserveAgents. שנו רק את ה‑exporter ב‑`lab_agent.py`:

```python
provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporter(
        endpoint="https://app.observeagents.ai/otel/v1/traces",   # full path here
        headers={"Authorization": "Bearer gk-YOUR-KEY-HERE"},
    )))
```

> When posting **directly from the SDK**, give the **full** path `…/otel/v1/traces`. The `/v1/traces` suffix is only auto-appended by the **Collector's** `otlphttp` exporter (Phase 3), not by the raw SDK exporter.
> בשליחה **ישירה מה‑SDK**, ציינו את הנתיב ה**מלא** `…/otel/v1/traces`. הסיומת `/v1/traces` מתווספת אוטומטית רק ע"י ה‑exporter של ה‑**Collector** (שלב 3), לא ע"י ה‑SDK.

The Collector then becomes the **enterprise-hardening step** — central routing, filtering, and fan-out to Datadog/Grafana alongside ObserveAgents.
*HE:* ה‑Collector הופך אז ל**שלב ההקשחה הארגוני** — ניתוב מרכזי, סינון, ופיזור ל‑Datadog/Grafana במקביל ל‑ObserveAgents.

---

## Troubleshooting / פתרון תקלות

| Response | Meaning / משמעות | Fix / תיקון |
|---|---|---|
| **202 Accepted** | Ingested OK / נקלט בהצלחה | Nothing — check Runtime. |
| **401** | Bad/missing key, or key has no org / מפתח שגוי־חסר, או ללא org | Use a valid `gk-` key from the dashboard. |
| **400** | Malformed body, or non-trace payload / גוף פגום או payload שאינו trace | Send OTLP **traces** only; metrics/logs are rejected here. |
| **415** | Wrong `Content-Type` / סוג תוכן שגוי | Send `application/json` or `application/x-protobuf`. |
| No agent in Runtime | Spans exported to the wrong URL / נשלח לכתובת שגויה | Collector → `…/otel`; direct SDK → `…/otel/v1/traces`. |

---

## Optional — a second agent, to demo error findings and multi-asset views
## רשות — סוכן שני, להדגמת ממצאי שגיאות ותצוגת ריבוי נכסים

**EN.** Emit **3+ failing tool spans** from a *different* team/service to trigger `repeated_tool_errors` (and, combined with a DB/API dependency, escalate `human_review_recommended`). This shows the inventory holding **multiple assets** and the error-findings path.

**HE.** פלטו **3+ spans של כלי שנכשל** מ‑team/service *אחר* כדי להפעיל `repeated_tool_errors` (ובשילוב תלות DB/API — להסלים את `human_review_recommended`). זה מציג inventory עם **מספר נכסים** ואת נתיב ממצאי השגיאות.

```python
# add to a second script with service.name="billing-agent", team="billing-ai"
from opentelemetry.trace import Status, StatusCode
for i in range(3):
    with tracer.start_as_current_span("mcp.call") as s:
        s.set_attribute("session.id", session)
        s.set_attribute("mcp.method.name", "tools/call")
        s.set_attribute("gen_ai.tool.name", "stripe_charge")
        s.set_status(Status(StatusCode.ERROR, "tool timeout"))
```

---

*Every endpoint, attribute, status code and finding in this guide is verified against the ObserveAgents backend.*
*כל endpoint, תכונה, קוד סטטוס וממצא במדריך זה אומתו מול ה‑backend של ObserveAgents.*
