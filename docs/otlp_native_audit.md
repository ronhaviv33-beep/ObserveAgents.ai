# OTLP-Native Audit — sdk/python and POST /runtime-events

> **Status: EXECUTED.** Both audits concluded "no remaining product value", and the
> follow-up PR removed `sdk/python` and `POST /runtime-events` completely, per the
> removal manifest at the end of this document. This file remains as the decision record.

**Decision context.** ObserveAgents is OTLP-native: exactly one recommended integration
path — Customer runtime → OpenTelemetry instrumentation → OpenTelemetry Collector →
ObserveAgents OTLP ingestion → Runtime → Intelligence. Transport belongs to
OpenTelemetry; ObserveAgents owns intelligence (runtime, discovery, dependency,
capability, operational, performance, security). No provider-specific wrappers, no
generic wrapper abstraction, no competing telemetry path.

The proprietary `ObserveOpenAI` wrapper was removed in the same PR that adds this audit.
This document answers two questions with codebase evidence, and makes no removals itself:

1. **Does the remaining `sdk/python` package still provide product value under
   OTLP-only?**
2. **Does `POST /runtime-events` still have real product value or consumers?**

Evidence was gathered by exact-match sweeps over the entire repository (`ObserveOpenAI`,
`observeagents.openai`, `runtime-events`, `runtime_events`, `SDK wrapper`) plus import
tracing across `app/`, `dashboard/src/`, `website/`, `scripts/`, `tests/`, and
`sdk/python/`.

---

## Phase 2 — sdk/python audit

State after wrapper removal: `sdk/python/observeagents/` contains `__init__.py`
(exports only `__version__`), `client.py`, `events.py`, `privacy.py`, `ids.py`, plus
15 tests and packaging (`pyproject.toml`, `README.md`).

| File | Classification | Evidence |
|---|---|---|
| `observeagents/client.py` (`ObserveAgentsClient` — urllib POST to `/runtime-events`) | **Can Remove** | Zero production imports. Its only consumer was the deleted `openai.py` wrapper; the only test importing it (`tests/test_openai_wrapper.py:14`) was deleted with the wrapper. |
| `observeagents/events.py` (`build_llm_call_event`) | **Can Remove** (tied to `/runtime-events` fate) | Consumers: `sdk/python/tests/test_events.py:1` and `sdk/python/tests/test_backend_acceptance.py` only. No `app/`, `dashboard/`, or `scripts/` import. |
| `observeagents/privacy.py` | **Can Remove** | Support module for `events.py`. Its denylist duplicates the server-side scrub in `app/runtime_events.py`, which is authoritative (`extra="forbid"` + metadata scrub at ingestion). |
| `observeagents/ids.py` | **Can Remove** | Trivial hex-id helpers; consumed only by `events.py` and `tests/test_ids.py`. |
| `tests/test_events.py`, `tests/test_privacy.py`, `tests/test_ids.py`, `tests/conftest.py` | **Legacy** | Test only the modules above; they die with them. They test no product feature. |
| `tests/test_backend_acceptance.py` | **Required while `/runtime-events` exists** | The only cross-boundary test proving a well-formed events payload is accepted by the real route (boots `app.main`, POSTs, asserts 202 + `OtelSpan` rows). Becomes **Can Remove** the moment `/runtime-events` is removed. |
| `pyproject.toml`, `README.md`, `Makefile:31` (sdk test target) | **Legacy** | Packaging and CI wiring for the package; follow the package's fate. The package was never published to PyPI. |

### Answer: does sdk/python still provide product value under OTLP-only?

**No.** Evidence:

- **No production consumer.** Nothing under `app/` imports anything from
  `sdk/python` — the backend's runtime-events parsing lives in `app/runtime_events.py`
  and `app/ingestion/sdk.py`, independent of the SDK package.
- **No dashboard, demo, seed, script, or CI usage.** Zero hits in `dashboard/src/`,
  `scripts/`, `app/demo_otel_seed.py`; there is no `.github/` directory.
- **No distribution.** The package was never published to PyPI, so no external customer
  can be depending on it.
- **Its sole purpose was feeding `POST /runtime-events`** — a path the OTLP-native
  decision closes. Every capability it enabled (agent discovery, model calls, latency,
  errors, tokens, findings) is delivered by standard OTel instrumentation through OTLP.

**Recommendation: remove `sdk/python` completely in a follow-up PR**, together with
`/runtime-events` (below). Keeping it would preserve a second integration story with an
ongoing maintenance, packaging, and documentation cost and zero unique capability.

---

## Phase 3 — POST /runtime-events audit

| Consumer class | Evidence |
|---|---|
| **Production code** | `app/routes/runtime_events.py` (the route), `app/main.py:405-406` (registration), `app/runtime_events.py` (schema + `to_span_dict`), `app/ingestion/sdk.py:5` (parse module), `app/ingestion/__init__.py:19-20` (docstring). The route converts events into the same `normalize_spans` pipeline OTLP uses — removing it removes **no intelligence capability**. |
| **Customer usage** | No evidence of any external consumer. The dashboard **never advertises the endpoint** — zero hits across `dashboard/src/` (Setup, onboarding, guides all sell OTLP). The package that wrapped it was never published. |
| **Documentation** | `README.md` (×4 mentions), `docs/sdk-guide.md` (now a legacy reference marked "under review for removal"), `docs/runtime-flow.md`, `docs/architecture.md:132`, `docs/telemetry_ingestion.md:7`, `docs/telemetry_post_merge_validation.md`, `docs/roadmap.md` (×4), `website/integration.html:129` (SVG label). All are descriptions of the endpoint itself, not features built on it. |
| **Tests** | `tests/test_runtime_events.py` (9 tests), runtime-events cases in `tests/test_ingestion_layer.py` (:36,178,182), `sdk/python/tests/test_backend_acceptance.py` (2 tests). All test **the endpoint itself** — no product feature's test suite depends on it. |
| **Demos / seeds / scripts** | **Zero.** `scripts/seed_demo_data.py`, `scripts/seed_synthetic_enterprise.py`, `scripts/generate_synthetic_traffic.py`, `scripts/synthetic_payloads.py`, and `app/demo_otel_seed.py` all seed through the OTel path. |
| **Examples** | Only the code samples inside `docs/sdk-guide.md` (curl + raw-HTTP Python). No runnable example file in the repo uses it. |
| **CI workflows** | N/A — the repository has no `.github/` directory. |

### The honest counter-argument, and why it doesn't hold

`/runtime-events` was the "simple JSON, no OTel required" door — a few lines of raw HTTP
instead of OTel setup. But: the dashboard never sold it to customers, no demo or seed
uses it, the wrapper built on it is gone, and the OTLP path (with or without a Collector,
JSON or protobuf, plus auto-instrumentation like OpenLLMetry) serves the same customers
with a standard, portable contract. An endpoint whose only consumers are its own tests
and its own documentation is maintenance cost without product value.

### Recommendation

**Remove `POST /runtime-events` completely in a follow-up PR.** It has no real
consumers. Keeping a public ingestion endpoint "because it already exists" carries an
ongoing cost: schema maintenance, privacy-scrub duplication, auth surface, test upkeep,
and a second integration story that dilutes the OTLP-native message.

---

## Follow-up PR removal manifest (evidence-based, not executed here)

- **Delete `sdk/python/` entirely** — remaining modules, 15 tests, `pyproject.toml`,
  `README.md` — and the sdk test target at `Makefile:31`.
- **Delete `/runtime-events`** — `app/routes/runtime_events.py`, `app/runtime_events.py`,
  `app/ingestion/sdk.py`, the registration at `app/main.py:405-406`,
  `tests/test_runtime_events.py`, and the runtime-events cases in
  `tests/test_ingestion_layer.py`.
- **Purge documentation mentions** — `README.md` (×4), delete `docs/sdk-guide.md`,
  `docs/runtime-flow.md`, `docs/architecture.md:132`, `docs/telemetry_ingestion.md:7`,
  `docs/telemetry_post_merge_validation.md`, `docs/roadmap.md` (×4), and the SVG label in
  `website/integration.html:129`.
- **Validation for that PR** — full backend test sweep, `make verify`, dashboard +
  website builds, and `git grep -ni "runtime.events\|observeagents\." -- ':!docs/archive'`
  returning no live hits.

Out of scope for this audit (by explicit decision): all other ingestion paths. This
document evaluates only the wrapper, `sdk/python`, and `/runtime-events`.
