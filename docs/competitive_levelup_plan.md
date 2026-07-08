# Competitive Review & Level-Up Plan

*What Dash0, SigNoz, Traceloop/OpenLLMetry, Dynatrace, and Datadog do well — and the concrete moves that level up ObserveAgents without losing what makes it different.*

Reviewed: [dash0.com](https://www.dash0.com/), [signoz.io](https://signoz.io/), [traceloop.com/docs](https://www.traceloop.com/docs) + [OpenLLMetry](https://github.com/traceloop/openllmetry), and on the security demand: [Dynatrace AI Observability](https://www.dynatrace.com/solutions/ai-observability/) and [Datadog LLM Observability](https://docs.datadoghq.com/llm_observability/).

---

## 1. What each platform does well

### Dash0 — OTel-native, "observability for the AI era"
- Positions **OpenTelemetry-native** as identity, not a feature: an "OTel telemetry warehouse" with the new GenAI conventions for LLMs, MCPs, and agents as the semantic substrate.
- **Open agent interface**: APIs, MCP servers, and CLIs so *AI agents* can operate the observability platform itself — "closed platforms will starve their own agents."
- Agent observability: LLMs, prompts, sessions, end-to-end agent flows.
- Onboarding framed as *configuration, not assembly* (e.g. one Spring Boot starter wires all signals).

### SigNoz — open-source unified signals
- **Logs + metrics + traces + exceptions + dashboards + alerts in one app**, OTel-first, "instrument once, keep ownership of your telemetry."
- Self-hosted (Docker/K8s) *and* cloud with transparent usage pricing; SOC 2 / HIPAA for enterprise.
- LLM support rides the same pipeline: RAG traces, token usage, cost alongside normal APM.

### Traceloop / OpenLLMetry — the instrumentation on-ramp + quality layer
- **The 2-line start** (`pip install traceloop-sdk` → `Traceloop.init()`) that instruments OpenAI, Anthropic, Bedrock, Mistral, Cohere + vector DBs (Pinecone, Chroma, Qdrant, Weaviate…) + frameworks (LangChain, LlamaIndex, LangGraph, CrewAI, Haystack) — and emits **standard OpenTelemetry**, routable to any backend.
- **Monitors = evaluators on span groups, in real time**: LLM-as-a-judge (faithfulness, relevance) + deterministic evaluators (structure, safety, PII/toxicity), with alert rules like "if >5% of responses flagged unfaithful in 10 minutes, page on-call."
- Prompt management / playground / experiments (their lane, not ours).

### Datadog — the security bar (out-of-the-box checks)
- **OOTB Security & Privacy checks on traces**: prompt-injection detection and toxic-content flags you can *filter the trace list by*.
- **Sensitive Data Scanner** integrated into LLM Observability: scans, identifies, and redacts PII/financial/health data automatically.
- Agent monitoring with anomaly insights on duration/error-rate, RBAC, enterprise controls.

### Dynatrace — the enterprise/agentic bar
- **Guardrail-metric monitoring**: hallucination recognition, prompt-injection misuse detection, PII-leak prevention, toxicity — as monitored metrics.
- **Agentic workload visibility**: execution paths, tool invocations, inter-agent communication across OpenAI Agents SDK, LangGraph, CrewAI, Bedrock AgentCore, **MCP tools**.
- **AI coding agent cost tracking** (tokens, tool behavior across coding agents) and a **full audit trail** (prompt→response lineage) for compliance.

### Market note
`observeagents.com` (not .ai) publishes AI-agent-observability content under the same name. A brand/name collision exists in exactly this category — worth resolving early (trademark/positioning), before both names index against each other.

---

## 2. What Observe already has that they don't

Every one of these platforms is **observability-first**. None of them owns:

1. **The AI asset governance spine** — a canonical, org-scoped AI inventory (`asset_registry`) with ownership, claiming, discovery status, shadow-AI surfacing, and findings that read like an auditor's worklist. Datadog/Dynatrace show you traces; Observe answers *"what AI exists here, who owns it, and what needs attention?"*
2. **Two products, one spine** — Observability (see) and Gateway (control) sharing the same inventory, so observation can graduate into control (observe → alert → enforce, per team) without a second vendor.
3. **Privacy-first by construction** — Datadog scans-and-redacts; Dynatrace *stores* full prompt→response lineage for audit. Observe **never persists content at all** (hash + size + counts only). For regulated orgs that can't ship prompts to a SaaS, that's not a feature — it's the buying reason.

**The wedge:** don't compete as "another LLM observability tool." Position as **the runtime visibility and control layer for AI agents** — inventory, ownership, risk, and cost accountability — that happens to have first-class OTel observability and an optional control plane. That is the "something special."

---

## 3. Level-up backlog (concrete, mapped to our codebase)

Ordered by leverage ÷ effort.

### L1 — Accept OTLP protobuf at `/otel/v1/traces` *(unlocks the 2-line start)*
Today the endpoint is JSON-only (415 otherwise), which forces a Collector between us and every Python SDK — including OpenLLMetry. Adding protobuf decoding (`opentelemetry-proto`, content-type switch in `app/routes/otel.py`, same parser output) makes this the entire onboarding:
```python
pip install traceloop-sdk
Traceloop.init(api_endpoint="https://<observe>/otel", headers={"Authorization": "Bearer gk-..."})
```
**OpenLLMetry becomes our instrumentation catalog** (every provider, vector DB, and framework it supports) with zero SDK of our own — the exact "no proprietary SDK" story, now with a 2-line start that matches Traceloop's own README. *(This is the single highest-leverage backend change on the list.)*

### L2 — OTLP metrics ingestion → AI coding-agent cost dashboard *(Dynatrace's fashionable feature, already half-built)*
We already parse Claude Code's span attributes; its richest data (`claude_code.token.usage`, `claude_code.cost.usage`, per-model/per-agent/per-MCP-tool) arrives as **OTLP metrics**. A `/otel/v1/metrics` endpoint + a "Coding Agents" cost view gives Observe the "track every Claude Code/coding-agent dollar" story with real billing-grade numbers — and finally gives Observability-surface Cost Intelligence honest OTel-native data (closing the plan's §9.8 risk properly).

### L3 — Content-free security verdicts *(beat Datadog's checks on privacy terms)*
Datadog scans content and redacts; we don't store content at all. Level-up: **scan in-flight at ingestion, store only the verdict** — `prompt_injection_suspected`, `pii_detected_in_prompt`, `toxicity_suspected` as AssetFindings + a Runtime filter chip ("Security checks", like Datadog's), while the content itself is still discarded. Optional per-org toggle. Slots directly into `app/otel_privacy.py` (scan before scrub) + existing findings pipeline. Marketing line: *"Security checks without content retention."*

### L4 — Guardrail monitors with alert rules *(Traceloop's monitors, our advisory layer)*
Our Guardrails page evaluates client-side on load. Make guardrail evaluation a **server-side monitor** with thresholds and notifications: "if error-family findings on a production system exceed N in 24h → notify." Reuses `derive_asset_intelligence` on a schedule + a notifications table. Alerting is the biggest maturity gap vs all five platforms.

### L5 — MCP server for Observe itself *(Dash0's open-agent-interface play)*
Expose read-only MCP tools (`list_ai_systems`, `get_findings`, `get_trace`, `get_cost_signals`) so customers' agents — and Claude Code — can query their AI inventory conversationally. We are an *agent observability* company; being operable *by* agents is on-brand and cheap (FastAPI + MCP SDK over existing read routes).

### L6 — Unified-signal roadmap honesty *(SigNoz's bar)*
We ingest traces only. Sequence: metrics (L2) → logs later. Say so in docs/roadmap rather than implying parity.

### L7 — Quality evaluations (LLM-as-judge) — *later, deliberate*
Faithfulness/hallucination verdicts require response content, which collides with our privacy stance. If ever built: opt-in, in-flight evaluation with verdict-only storage (same pattern as L3). Do not chase Traceloop here until L1–L4 are done.

### L8 — Self-host + pricing clarity *(SigNoz's adoption engine)*
We already run single-binary FastAPI + SQLite/Postgres. A documented `docker compose up` self-host path + a public pricing stance removes the biggest evaluation friction for the exact privacy-sensitive orgs our positioning targets.

---

## 4. What we deliberately do NOT copy

- **Prompt playgrounds / prompt management** (Traceloop) — different product; stay out.
- **Storing full prompt→response lineage** (Dynatrace) — opposite of our privacy position; our audit trail is *metadata + verdicts*, and that's the point.
- **General-purpose APM** (SigNoz/Datadog breadth) — we win on the AI governance spine, not on hosting everyone's nginx logs.
- **A proprietary SDK** — never. OpenLLMetry + standard OTel *is* our client story (L1 makes it frictionless).

---

## 5. Suggested sequence

| Order | Item | Size | Surface |
|---|---|---|---|
| 1 | L1 protobuf ingestion | S–M (one route + parser branch + tests) | Backend |
| 2 | README/docs 2-minute quick start (shipped with this doc) | S | Docs |
| 3 | L2 metrics + coding-agent cost view | M | Backend + Observability UI |
| 4 | L3 content-free security verdicts | M | Backend + Runtime/Findings UI |
| 5 | L4 guardrail monitors + notifications | M | Backend + Guardrails UI |
| 6 | L5 Observe MCP server | S–M | Backend |
| 7 | L8 self-host compose + pricing page | S | Docs/infra |

Sources: [Dash0 — AI-era observability](https://www.dash0.com/blog/from-opentelemetry-native-to-observability-for-the-ai-era) · [SigNoz](https://github.com/SigNoz/signoz) · [OpenLLMetry](https://github.com/traceloop/openllmetry) · [Traceloop monitors](https://www.traceloop.com/docs/monitoring/introduction) · [Datadog LLM Observability](https://docs.datadoghq.com/llm_observability/) · [Datadog prompt-injection monitoring](https://www.datadoghq.com/blog/monitor-llm-prompt-injection-attacks/) · [Dynatrace AI Observability](https://www.dynatrace.com/solutions/ai-observability/) · [Dynatrace agentic GA](https://www.dynatrace.com/news/blog/announcing-agentic-framework-support-and-general-availability-of-the-dynatrace-ai-observability-app/)
