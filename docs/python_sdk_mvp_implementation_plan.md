# Python SDK MVP — Implementation Plan (Collector R3)

*Status: **implemented** — the SDK shipped as `sdk/python/observeagents/` (PR #114),
built from this plan. The document is kept as the scoping record for that MVP.
Design rationale and product positioning live in the companion plan,
[python_sdk_wrapper_plan.md](python_sdk_wrapper_plan.md).*

> **Observe first. Control only what matters.**

---

## 1. Executive Summary

The MVP is a single wrapper class, `ObserveOpenAI`, that wraps the official OpenAI Python
client and emits **one safe `llm_call` runtime event per completion call** to
`POST {observeagents_url}/runtime-events` — the ingestion seam shipped in PR #110. It is
the first low-friction adapter over that endpoint: one import, one constructor, no OTel
Collector, no instrumentation.

Hard principles, restated as implementation requirements:

- **No new intelligence pipeline.** The SDK only produces normalized runtime events; the
  backend's existing flow (runtime-events endpoint → span-like adapter → `normalize_spans`
  → intelligence engine) does everything else, unchanged.
- **No content leaves the customer's process.** Prompts, messages, responses, system
  instructions, tool arguments/results, headers, and credentials are never sent to
  ObserveAgents. The SDK passes `messages` to OpenAI — that is its job — but never
  forwards them.
- **Fail open.** If ObserveAgents is slow, down, or rejecting, the customer's LLM call
  succeeds (or fails) exactly as it would without the SDK installed.

---

## 2. MVP Scope

- Python only
- OpenAI **chat-completions-style wrapper only** (`client.chat.completions.create`)
- **Synchronous best-effort POST** after the LLM call returns (or raises)
- Short timeout, **~2 seconds**
- Configurable `observeagents_url` (Cloud or customer-side Collector)
- Configurable `observeagents_api_key` (`gk-` key)
- `agent_name` **required**
- `environment` optional, default `"development"`
- `owner_hint` / `team_hint` optional
- `session_id` optional
- `trace_id` / `span_id` **generated if not provided**
- Token counts from `response.usage` when available
- **Error event emitted if the provider call fails** (`status="error"`, `error_type` =
  exception class name only)
- **Original provider exception re-raised unchanged**

## 3. Out of Scope

Explicitly not in the MVP:

- Anthropic wrapper · LiteLLM wrapper · LangChain callback
- async support · batching · retry queue · background delivery
- tool-call helper (`tool_call` events)
- Node SDK
- Gateway adapter · MCP adapter · any other source adapter
- metrics · billing
- prompt/response capture of any kind
- backend changes · dashboard changes · DB migrations · auth changes
- enforcement of any kind

## 4. Architecture Flow

```
Customer App
  → ObserveOpenAI wrapper                    (SDK: wrap call, measure, build safe event)
  → POST {observeagents_url}/runtime-events  (HTTP, Bearer gk- key, ~2s timeout, fail-open)
  → runtime-events endpoint                  (app/routes/runtime_events.py — validate, 202)
  → span-like adapter                        (app/runtime_events.py:to_span_dict)
  → normalize_spans                          (app/otel_normalizer.py)
  → existing intelligence engine             (assets → findings → detection rules →
                                              gateway control candidates, derived later
                                              in /intelligence/run — never inline)
```

Everything below the HTTP boundary already exists and is not touched by this work.

## 5. Package Structure

```
observeagents/
  __init__.py        # exports ObserveOpenAI (and __version__)
  client.py          # transport: POST events to {observeagents_url}/runtime-events;
                     #   timeout, fail-open swallow, optional debug logging
  openai.py          # ObserveOpenAI: wraps the OpenAI client, proxies
                     #   chat.completions.create, measures duration, emits events
  events.py          # build the llm_call RuntimeEvent payload dict (schema §7)
  privacy.py         # client-side allow-list: construct-only-safe-fields helpers +
                     #   guard that strips/refuses forbidden keys in metadata
  ids.py             # trace_id / span_id generation (uuid4().hex; hex[:16] for span)
tests/
  test_events.py     # payload construction, mapping, ids
  test_privacy.py    # forbidden content never present in payloads
  test_openai_wrapper.py      # success/error flow, re-raise, fail-open (mock transport)
  test_backend_acceptance.py  # generated payload accepted by the real POST /runtime-events
```

Each module stays small and single-purpose; `openai.py` contains no HTTP code and
`client.py` knows nothing about OpenAI.

*(Repo location — this repo under `sdk/python/` vs a separate repo — is Open Question #1;
the internal layout above is the same either way.)*

## 6. Public API

One class for the MVP:

```python
from observeagents import ObserveOpenAI

client = ObserveOpenAI(
    openai_api_key="...",
    observeagents_api_key="gk_...",
    observeagents_url="https://api.observeagents.ai",  # or customer-side collector URL
    agent_name="support-agent",
    environment="production",
    team_hint="support"
)

response = client.chat.completions.create(
    model="gpt-4.1-mini",
    messages=[...]
)
```

- The wrapper is a **drop-in**: same call signature, same return value, same exceptions
  as the underlying OpenAI client.
- Constructor accepts: `openai_api_key`, `observeagents_api_key`, `observeagents_url`,
  `agent_name` (required), `environment="development"`, `owner_hint=None`,
  `team_hint=None`, `session_id=None`, plus `timeout_seconds=2.0` and `debug=False`.
- **The SDK may pass `messages` to OpenAI, but must never send those messages to
  ObserveAgents.** Only the fields in §7 leave for ObserveAgents.

## 7. Runtime Event Mapping

One event per completion call, sent as `{"events": [<event>]}` with
`Authorization: Bearer gk-...`. Example event:

```json
{
  "source": "sdk",
  "agent_name": "support-agent",
  "event_type": "llm_call",
  "provider": "openai",
  "model": "gpt-4.1-mini",
  "duration_ms": 850,
  "status": "ok",
  "input_tokens": 1200,
  "output_tokens": 300,
  "environment": "production",
  "team_hint": "support",
  "trace_id": "...",
  "span_id": "...",
  "session_id": "..."
}
```

Field-by-field mapping to the backend `RuntimeEvent` schema (`app/runtime_events.py`):

| Field | Value in the MVP |
|---|---|
| `source` | constant `"sdk"` |
| `agent_name` | constructor argument (required) |
| `event_type` | constant `"llm_call"` |
| `provider` | constant `"openai"` |
| `model` | the `model` argument of the call (response model may refine it) |
| `duration_ms` | wall-clock around the provider call |
| `status` | `"ok"` on success, `"error"` on provider exception |
| `error_type` | exception **class name** only (e.g. `RateLimitError`) — never the message |
| `input_tokens` / `output_tokens` | `response.usage.prompt_tokens` / `completion_tokens` when present; omitted otherwise |
| `environment` | constructor argument (default `"development"`) |
| `owner_hint` / `team_hint` | constructor arguments, sent only if set |
| `session_id` | constructor argument, sent only if set |
| `trace_id` | provided or generated (`uuid4().hex`) |
| `span_id` | generated per call (`uuid4().hex[:16]`) |

Backend contract the SDK relies on (already shipped, not modified): `202` + counts on
success; `422` on unknown/forbidden fields (`extra="forbid"`) or missing required fields;
max 500 events per request (MVP always sends 1).

## 8. Privacy Rules

The SDK must **never** send to ObserveAgents:

- prompts · messages · responses · system instructions
- tool arguments · tool results
- headers · credentials (including the OpenAI API key)
- full URLs with query strings

Only the §7 fields are ever placed in the outgoing payload. Enforcement is structural,
not filter-based: `events.py` **constructs** the payload from an explicit safe-field list —
there is no code path that copies request/response bodies into it. `privacy.py` adds a
guard for any future free-form field (e.g. metadata) using the same denylist the server
enforces.

Defense in depth: the backend independently rejects forbidden fields
(`RuntimeEvent`, `extra="forbid"` → 422) and scrubs `metadata_json` / `external_domain`.
The SDK must not rely on that — a payload the server would reject is an SDK bug.

## 9. Error Handling / Fail Open

- **Provider call fails** → emit `status="error"` + `error_type` (best-effort), then
  **re-raise the original exception unchanged** — same type, same message, same traceback.
- **Event delivery fails** (timeout, connection error, 4xx/5xx) → swallow; the customer's
  call result is unaffected. Optionally log one warning when `debug=True`.
- No retries in the MVP. No blocking. No enforcement. The SDK never raises its own
  exception into the customer's call path.

## 10. Configuration

| Setting | Constructor arg | Env-var fallback | Default |
|---|---|---|---|
| ObserveAgents endpoint | `observeagents_url` | `OBSERVEAGENTS_URL` | — (required) |
| API key | `observeagents_api_key` | `OBSERVEAGENTS_API_KEY` | — (required) |
| Agent name | `agent_name` | — | — (required) |
| Environment | `environment` | — | `"development"` |
| Owner / team hints | `owner_hint` / `team_hint` | — | `None` |
| Session | `session_id` | — | `None` |
| Delivery timeout | `timeout_seconds` | — | `2.0` |
| Debug logging | `debug` | — | `False` |

`observeagents_url` is never hardcoded. Events go to `POST {observeagents_url}/runtime-events`,
and the URL may point to either **ObserveAgents Cloud** (`https://api.observeagents.ai`)
or a **customer-side ObserveAgents Collector** (`https://observeagents-collector.customer.com`).
Wire format, auth, and privacy rules are identical for both.

## 11. Testing Plan

Required cases (all must exist before the MVP ships):

1. **Successful OpenAI call emits exactly one `llm_call` event** with the §7 fields
   (mock OpenAI client + mock transport; assert on the raw outgoing JSON).
2. **Failed OpenAI call emits `status="error"` + `error_type`** and **re-raises the
   original exception unchanged** (assert exception identity/type).
3. **Prompts/messages are not present in the outgoing ObserveAgents payload** — serialize
   the outgoing body and assert the message text, system instruction text, and marker
   secrets appear nowhere in it.
4. **ObserveAgents endpoint unavailable does not fail the LLM call** — transport raises
   timeout/connection error; the wrapped call still returns the provider response.
5. **`observeagents_url` can point to Cloud or a customer-side Collector** — two configs,
   assert the POST goes to `{url}/runtime-events` in both.
6. **Generated payload is accepted by the real `POST /runtime-events`** — integration test
   against the backend route (FastAPI TestClient, pattern of
   `tests/test_runtime_events.py`): SDK-built payload → 202, and evidence appears via the
   `normalize_spans` path.
7. **No SDK code sends raw content** — a payload-construction audit test: build events from
   calls containing sentinel strings in messages/system/tool args and assert the sentinels
   never appear in any outgoing payload byte.

## 12. Implementation Steps

Ordered steps for the future implementation PR(s) — nothing here is executed now:

1. Scaffold the package (`observeagents/` layout from §5, `pyproject.toml`, no runtime
   dependency beyond an HTTP client).
2. Implement `ids.py` (trace/span hex generation) and `events.py` (safe payload builder,
   §7 mapping) with unit tests.
3. Implement `privacy.py` (allow-list construction helpers + denylist guard) with tests
   asserting sentinel content never survives.
4. Implement `client.py` (transport: POST `{url}/runtime-events`, Bearer auth, ~2s
   timeout, fail-open swallow, debug logging).
5. Implement `openai.py` (`ObserveOpenAI`: constructor, passthrough proxy for
   `chat.completions.create`, duration measurement, success/error event emission,
   re-raise unchanged).
6. Wire the backend-acceptance integration test against the real `/runtime-events` route.
7. Write the SDK README with the §6 example and privacy statement.

## 13. Validation Commands

For the future implementation (recorded now so the PR has an agreed gate):

```bash
# SDK unit + privacy + wrapper tests
pytest <sdk-tests-path> -q          # exact path depends on Open Question #1

# Backend acceptance (existing suite must stay green; SDK payloads accepted)
pytest tests/test_runtime_events.py -q

# Manual smoke: a sample SDK-shaped payload is accepted end-to-end
curl -X POST "$OBSERVEAGENTS_URL/runtime-events" \
  -H "Authorization: Bearer $OBSERVEAGENTS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"events":[{"source":"sdk","agent_name":"smoke-agent","event_type":"llm_call","provider":"openai","model":"gpt-4.1-mini","duration_ms":850,"status":"ok","trace_id":"<hex>","span_id":"<hex>","environment":"development"}]}'
# expect: 202 with ingestion counts
```

## 14. Open Questions

Recommendations are defaults to confirm, not decisions.

| # | Question | Recommended default |
|---|---|---|
| 1 | Where does the SDK live — this repo under `sdk/python/` or a separate repo? | This repo under `sdk/python/` first (shared CI, backend-acceptance test runs in-tree); extract to its own repo when publishing cadence demands it. |
| 2 | Publish to PyPI at MVP, or in-repo install first? | In-repo (`pip install -e sdk/python`) first; PyPI once the API surface survives first real usage. |
| 3 | Pin the OpenAI client version or duck-type it? | Duck-type (proxy attribute access, depend on the documented `usage` shape); declare a tested version range, no hard pin. |
| 4 | Per-call `session_id`/`trace_id` override kwargs in the MVP, or constructor-only? | Constructor-only for MVP; per-call overrides are a small fast-follow. |
| 5 | Debug logging default | Off (`debug=False`); one `logging` warning per failed delivery when on — never raises. |
