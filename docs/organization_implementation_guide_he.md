# מדריך הטמעה לארגון — ObserveAgents

מדריך מעשי, שלב אחר שלב, להטמעת ObserveAgents בארגון — מהכניסה הראשונה ועד תצפית מלאה על כל מערכות ה-AI.

> English version: [organization_implementation_guide.md](organization_implementation_guide.md)

**למי המדריך מיועד:** מהנדסי פלטפורמה, מהנדסי אבטחה וראשי צוותי פיתוח שמטמיעים את Observe בארגון.

**מה יהיה לכם בסוף:** כל מערכת AI מחוברת מתגלה אוטומטית, ה-traces וציר הזמן של הריצה (Execution Timeline) שלה גלויים, היכולות (Capabilities) והממצאים (Findings) שלה נגזרים אוטומטית, ו-Guardrails ייעוציים רצים במצב תצפית בלבד — בלי לשנות את התנהגות מערכות ה-AI שלכם בפרודקשן.

**הערכת זמן:** מערכת AI ראשונה מחוברת בפחות מ-30 דקות; פריסה ארגונית מלאה מתבצעת בהדרגה לאחר מכן.

---

## שלב 0 — הקמת סביבת העבודה (15 דקות, אדמין)

### 0.1 התחברות ובדיקת הארגון

התחברו עם חשבון האדמין. הכול ב-Observe מתוחם לארגון שלכם — משתמשים, מערכות AI, traces וממצאים של ארגונים אחרים לעולם אינם גלויים לכם.

### 0.2 הוספת הצוות

**Users → Add User.** שלושה תפקידים:

| תפקיד | מתאים ל | הרשאות |
|---|---|---|
| **Admin** | בעלי הפלטפורמה | הכול: משתמשים, מפתחות API, הגדרות, כללי תקציב, guard modes |
| **Analyst** | מהנדסים, אנליסטים של אבטחה | כל דפי המוצר, טיפול בממצאים (resolve/dismiss), הגדרות חיבור |
| **Viewer** | הנהלה, בעלי עניין | קריאה בלבד: Runtime, Asset Intelligence, Security, Cost, Budgets, Pricing, Guardrails |

התחילו בקטן: אדמין אחד, וכמה Analysts עבור הצוותים שמתחברים ראשונים.

### 0.3 יצירת מפתחות API

**API Keys → Create.** המפתחות נראים כך: `gk-…` ומשמשים לאימות שליחת טלמטריה.

קונבנציה מומלצת: **מפתח אחד לכל צוות או שירות מרכזי**, עם שם תואם (`payments-team`, `support-agent-prod`). כך הייחוס (attribution) נשאר נקי, ואפשר לבטל מפתח של צוות אחד בלי לגעת באחרים.

### 0.4 (למשתמשי Gateway בלבד) הגדרת אישורי ספקים

אם תנתבו תעבורת AI דרך ה-gateway (מסלול B בהמשך), הוסיפו את מפתחות OpenAI/Anthropic/Google תחת **Settings → Organization AI Providers** (מודל BYOK — נשמרים מוצפנים, לכתיבה בלבד, לעולם לא מוצגים שוב). דלגו על זה אם אתם שולחים רק traces של OpenTelemetry.

---

## שלב 1 — חיבור מערכת ה-AI הראשונה

בחרו שירות AI **אחד** להתחיל איתו. שני מסלולים — בחרו את המתאים לסטאק שלכם. (אין לכם אף אחד מהם? ראו שלב 2.)

### מסלול A — אתם כבר משתמשים ב-OpenTelemetry

אם שירות ה-AI שלכם כבר פולט OTel traces, פשוט מכוונים את ה-pipeline הקיים אל Observe. **חשוב: נקודת הקצה מקבלת OTLP/HTTP בפורמט JSON בלבד — protobuf נדחה.** המשמעות לפי סטאק:

**דרך OpenTelemetry Collector (מומלץ — עובד לכל שפה):**

```yaml
exporters:
  otlphttp/observeagents:
    endpoint: "https://<your-observeagents-url>/otel"
    encoding: json          # חובה — Observe מקבל OTLP JSON, לא protobuf
    headers:
      Authorization: "Bearer gk-<your-api-key>"

service:
  pipelines:
    traces:
      exporters: [otlphttp/observeagents]
```

הוסיפו את ה-exporter הזה לצד הקיימים — Observe הופך ליעד נוסף; שום דבר אחר ב-pipeline לא משתנה.

**Node.js (ישירות — ה-exporter שלו שולח JSON באופן טבעי):**

```js
const { OTLPTraceExporter } = require('@opentelemetry/exporter-trace-otlp-http');

const exporter = new OTLPTraceExporter({
  url: 'https://<your-observeagents-url>/otel/v1/traces',
  headers: { Authorization: 'Bearer gk-<your-api-key>' },
});
```

**Python ושפות אחרות שה-exporter שלהן שולח protobuf:** נתבו דרך תצורת ה-Collector שלמעלה — הוא ממיר ל-JSON עבורכם.

### מסלול B — אין OTel, אבל אתם קוראים ל-API בסגנון OpenAI/Anthropic

נתבו את התעבורה דרך ה-gateway של Observe באמצעות **ה-SDK הקיים של הספק שלכם** — אין SDK ייחודי של Observe להתקנה. שינוי תצורה אחד:

```python
# Python — OpenAI SDK
client = openai.OpenAI(
    base_url="https://gateway.observeagents.ai/v1",
    api_key="gk-<your-api-key>",        # מפתח Observe שלכם, לא מפתח הספק
)
```

```python
# Python — Anthropic SDK
client = anthropic.Anthropic(
    base_url="https://gateway.observeagents.ai",
    api_key="gk-<your-api-key>",
)
```

```bash
# משתני סביבה בלבד — בלי שינוי קוד בכלל (כל לקוח תואם-OpenAI)
export OPENAI_API_KEY=gk-<your-api-key>
export OPENAI_BASE_URL=https://gateway.observeagents.ai/v1
```

עובד עם OpenAI SDK, Anthropic SDK, LangChain, CrewAI, LiteLLM, לקוחות MCP, Vercel AI SDK, וכל דבר תואם-OpenAI. מפתחות הספק שלכם נשארים בצד השרת של Observe (שלב 0.4); קוד האפליקציה לעולם לא רואה אותם.

ה-gateway רץ **במצב ייעוצי (advisory) כברירת מחדל** — הוא צופה, מייחס ומעריך עלות; הוא לעולם לא חוסם אלא אם צוות הועבר במפורש למצב enforce בהמשך.

### אימות (שני המסלולים)

1. הריצו בקשה אחת דרך שירות ה-AI שלכם.
2. **Runtime** — ה-trace מופיע תוך שניות; לחצו עליו כדי לראות את ציר הזמן של הריצה.
3. **Asset Intelligence** — מערכת ה-AI מופיעה ככרטיס מתגלה עם המודל והספק שלה.

אם שום דבר לא מופיע — ראו "פתרון תקלות" בסוף המדריך.

---

## שלב 2 — מתחילים מאפס: אין OTel ואין מסלול SDK מתאים

השלב הזה מיועד לארגונים שאף מסלול לא מתאים להם עדיין — למשל קוד AI מותאם-אישית בלי observability, או קריאות AI שלא עוברות דרך API בסגנון OpenAI/Anthropic. יש שתי אפשרויות; רוב הארגונים בוחרים **באפשרות 1** כי מדובר בכ-20 שורות קוד שמשתלמות בכל כלי observability, לא רק ב-Observe.

### אפשרות 1 — הוספת אינסטרומנטציית OpenTelemetry מאפס

OTel הוא הסטנדרט הנייטרלי בתעשייה; אינסטרומנטציה אחת משרתת את Observe וכל כלי אחר שתאמצו בעתיד.

**צעד 1 — התקנה (דוגמה ב-Python):**

```bash
pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http
```

**צעד 2 — הקמת Collector מינימלי** (קונטיינר אחד קטן; מגשר בין כל שפה לנקודת ה-JSON של Observe):

```yaml
# otel-collector.yaml
receivers:
  otlp:
    protocols:
      http:
      grpc:
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
docker run -v $(pwd)/otel-collector.yaml:/etc/otelcol/config.yaml \
  -p 4318:4318 otel/collector-contrib:latest
```

**צעד 3 — אתחול tracing פעם אחת בעליית האפליקציה:**

```python
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

resource = Resource.create({
    "service.name": "support-agent",            # הופך לזהות של מערכת ה-AI
    "deployment.environment": "production",     # production | staging | development
    "team": "customer-support",                 # ייחוס אופציונלי
})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces")  # → ה-Collector שלכם
))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("support-agent")
```

**צעד 4 — עטיפת קריאות ה-AI ב-spans.** ה-attributes שלמטה הם מה ש-Observe מבין — כל אחד מהם הופך ליכולת, תלות או צעד בציר הזמן:

```python
# span שורש אחד לכל בקשה/משימה — זהו עמוד השדרה של ה-Execution Timeline
with tracer.start_as_current_span("handle_customer_request"):

    # קריאת LLM → גילוי מודל + ספק
    with tracer.start_as_current_span("llm.plan") as span:
        span.set_attribute("gen_ai.system", "openai")
        span.set_attribute("gen_ai.request.model", "gpt-4o")
        span.set_attribute("gen_ai.usage.input_tokens", 512)   # אופציונלי
        span.set_attribute("gen_ai.usage.output_tokens", 128)  # אופציונלי
        response = call_your_llm(...)

    # קריאת tool → יכולת tool מתגלה
    with tracer.start_as_current_span("tool.search_kb") as span:
        span.set_attribute("tool.name", "kb_search")
        results = search_knowledge_base(...)

    # גישה לבסיס נתונים → יכולת database + ממצא אבטחה
    with tracer.start_as_current_span("db.lookup") as span:
        span.set_attribute("db.system", "postgresql")
        span.set_attribute("db.name", "customers")
        rows = query_db(...)

    # קריאה ל-API חיצוני → תלות external_api
    with tracer.start_as_current_span("crm.update") as span:
        span.set_attribute("url.full", "https://api.your-crm.example/v1/update")
        update_crm(...)
```

מדריך מלא ל-attributes הנתמכים (MCP, workflows, זהות agent): [otel_ingestion.md](otel_ingestion.md).

**הערת פרטיות — אין צורך להיזהר עם prompts:** גם אם ספריות אינסטרומנטציה מצרפות `gen_ai.input.messages` / `gen_ai.output.messages` / `tool.arguments`, Observe מנקה אותם בקליטה ושומר רק hash וגודל בבייטים. תוכן גולמי של prompt/response לעולם אינו נשמר.

**קיצור דרך — אינסטרומנטציה אוטומטית:** אם השירות שלכם משתמש בספריות נפוצות (requests/httpx, FastAPI וכו'), הפקודה `pip install opentelemetry-distro && opentelemetry-instrument python app.py` יחד עם משתני הסביבה `OTEL_SERVICE_NAME` ו-`OTEL_EXPORTER_OTLP_ENDPOINT` מייצרת spans בלי שינויי קוד. עדיין כדאי להוסיף ידנית את ה-attributes של `gen_ai.*` / `tool.*` על הצעדים הייחודיים ל-AI לקבלת האינטליגנציה העשירה ביותר, אבל האינסטרומנטציה האוטומטית מזרימה צירי זמן כבר מהיום הראשון.

### אפשרות 2 — ניתוב דרך ה-gateway בלי לגעת בקוד האפליקציה

אם אינכם יכולים להוסיף אינסטרומנטציה בכלל, עדיין אפשר לקבל Runtime Discovery לכל שימוש AI שניתן לקרוא לו ב-HTTP, על ידי הפנייתו ל-gateway:

```bash
curl https://gateway.observeagents.ai/v1/chat/completions \
  -H "Authorization: Bearer gk-<your-api-key>" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"demo request"}]}'
```

כל דבר שיכול לשנות base URL — משימות cron, פלטפורמות low-code, סקריפטים פנימיים — יכול לאמץ את זה. תקבלו גילוי, ייחוס, שימוש ב-tokens ואיתותי עלות; לא תקבלו צירי זמן ברמת צעד (אלה דורשים spans) — ולכן אפשרות 1 היא היעד המומלץ.

### איך לבחור

| המצב שלכם | מה לעשות |
|---|---|
| יש pipeline קיים של OTel | שלב 1 מסלול A (הוספת ה-exporter ל-Collector) |
| קריאות SDK בסגנון OpenAI/Anthropic, בלי observability | שלב 1 מסלול B היום; הוסיפו spans מאפשרות 1 כשתרצו צירי זמן |
| קוד AI מותאם-אישית, בלי observability | אפשרות 1 (Collector + כ-20 שורות spans) |
| אי אפשר לשנות קוד בכלל | אפשרות 2 (החלפת URL של gateway בכל מקום שהתצורה מאפשרת) |

---

## שלב 3 — פריסה בכל הארגון

חזרו על שלב 1/2 שירות אחר שירות. קונבנציות ששומרות על סדר:

- **`service.name` = מערכת AI אחת.** השתמשו בשמות יציבים ומשמעותיים (`support-agent`, `invoice-extractor`) — זו הזהות שהכול מתקבץ תחתיה.
- **תמיד הגדירו `deployment.environment`** (`production` / `staging` / `development`) — זה מפעיל ממצאים ו-guardrails ייעודיים לפרודקשן.
- **מפתח API אחד לכל צוות/שירות**, עם שם תואם.
- חברו קודם מערכות פרודקשן (שם האינטליגנציה חשובה), אחר כך staging.

ככל שמערכות מתחברות, **Discovery Center** מציג מערכות חדשות שנצפו וממתינות לסקירה; **Dependency Map** מתמלאת במה שהן נוגעות בו.

---

## שלב 4 — תפעול האינטליגנציה (שגרה שבועית)

1. **Asset Intelligence → AI Systems** — תמונת המצב המקובצת של הארגון: לכל מערכת — המודלים, הכלים, התלויות, שטח היכולות, הממצאים והראיות מזמן ריצה. לחצו **▶ Run Intelligence** אחרי חיבור מערכות חדשות לרענון הגזירות.
2. **טיפול בממצאים** — עברו על לשונית Findings לפי חומרה. סמנו *Resolve* למה שתוקן ו-*Dismiss* למה שמקובל עליכם; אף אחד מהם לא נפתח מחדש בגזירה חוזרת.
3. **Guardrails** — בדקו אילו guardrails ייעוציים הופעלו (גישה לבסיסי נתונים, כלי MCP, קריאות API חיצוניות, שטח כלים רחב, מערכות פרודקשן עם ממצאי חומרה גבוהה, שגיאות ריצה, מסלולי ריצה איטיים). תצפית בלבד: הם מזהים, מסבירים וממליצים — שום דבר לא נחסם.
4. **Security / Cost Intelligence** — טבלת המערכות המסוכנות ואיתותי השימוש/יעילות ("נקודות עלות פוטנציאליות" מצעדים איטיים ונפחי traces גבוהים).
5. **Budgets (אדמין)** — הגדירו ספי שימוש צפוי לכל צוות כאיתותי תכנון.
6. **מעבר הדרגתי לאכיפה (אופציונלי, בהמשך):** guard modes הם פר-צוות. עקבו אחרי **Settings → Guard Modes → "Would block (30d)"** — הוא מראה מה מצב enforce *היה* חוסם. רק כשהמספר של צוות מסוים יציב ומובן, העבירו את אותו צוות בלבד observe → alert → enforce. רוב הארגונים נשארים במצב תצפית בלבד ללא הגבלת זמן.

**ממשל (אופציונלי):** ב-Discovery Center / Agents אפשר לתבוע בעלות (claim) על מערכות שהתגלו, להקצות בעלים, לאשר או לדחות. זה נבנה מעל המצאי — ולעולם אינו נדרש כדי שהאינטליגנציה תעבוד.

---

## פרטיות וטיפול בנתונים (לסקירת האבטחה שלכם)

- **לעולם לא נשמר:** טקסט prompts, טקסט תשובות, הוראות מערכת, ארגומנטים של tools, תוצאות tools — מנוקים בקליטה ל-`{redacted, sha256, size_bytes}`.
- **כן נשמר:** שמות שירות/מודל/ספק/כלי, תזמוני spans, ספירות tokens, attributes מנוקים, מזהים סינתטיים.
- **בידוד:** כל שורה מתוחמת לארגון; גישה בין ארגונים בלתי אפשרית דרך ה-API.
- **מפתחות:** אישורי ספקים מוצפנים ב-Fernet ולכתיבה בלבד; מפתחות `gk-` נשמרים כ-SHA-256 hash וניתנים לביטול פרטני.

---

## פתרון תקלות

| תסמין | סיבה סבירה |
|---|---|
| `401` על `/otel/v1/traces` | כותרת `Authorization: Bearer gk-…` חסרה/שגויה ב-exporter/Collector |
| `415 Content-Type must be application/json` | ה-exporter שולח protobuf — נתבו דרך Collector עם `encoding: json` |
| traces מגיעים אבל המערכת נקראת `observed-ai-system:…` | חסר resource attribute בשם `service.name` — הגדירו אותו |
| Runtime מציג traces אבל Asset Intelligence ריק | לחצו **▶ Run Intelligence** (הגזירה מופעלת לפי דרישה) |
| ה-gateway מחזיר `424 provider_not_configured` | הוסיפו מפתח ספק תחת Settings → Organization AI Providers (שלב 0.4) |
| ה-waterfall מציג span שטוח אחד | הוסיפו spans-ילדים סביב כל צעד (LLM / tool / DB) — ציר הזמן משקף את היררכיית ה-spans שלכם |
| Viewer לא יכול ליצור תקציבים | צפוי — תקציבים קריאים לכל התפקידים, מנוהלים על ידי אדמינים |

---

## צ'קליסט פריסה

- [ ] אדמין מחובר; משתמשים הוזמנו עם תפקידים
- [ ] מפתח API נוצר לכל צוות/שירות
- [ ] (Gateway) אישורי ספקים הוגדרו
- [ ] מערכת AI ראשונה חוברה (Collector עם `encoding: json`, Node ישירות, החלפת base_url ל-gateway, או אינסטרומנטציה מאפס לפי שלב 2)
- [ ] `service.name` + `deployment.environment` מוגדרים על כל שירות מחובר
- [ ] trace נראה ב-Runtime; ה-waterfall מוצג
- [ ] Run Intelligence הופעל; המערכת מופיעה ב-Asset Intelligence עם יכולות וממצאים
- [ ] Guardrails נסקרו (תצפית בלבד)
- [ ] סוכמה שגרת טיפול שבועית (ממצאים, אבטחה, עלות)
- [ ] תוזמן חיבור של יתר השירותים
