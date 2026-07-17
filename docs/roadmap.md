# ObserveAgents Roadmap

*The central forward roadmap. The full shipped-feature checklist lives in the [README roadmap table](../README.md#roadmap); this document tracks what comes next, phased.*

ObserveAgents is the **runtime visibility and control layer for AI agents**: it turns runtime evidence into AI inventory, ownership, dependencies, capabilities, findings, and observe-only guardrail recommendations. Every phase below extends that spine — nothing here changes the observe-first posture.

---

## Forward phases

| Phase | Theme | Summary |
|---|---|---|
| O1 | Ecosystem Discovery | GitHub / Jira / Slack / n8n / MCP evidence connectors; Active / Dormant / Runtime-only correlation with the runtime inventory |
| O2 | Ingestion depth | OTLP **protobuf** support — ✅ shipped (direct OpenLLMetry-style onboarding, no Collector required); **Runtime Events ingestion seam** (`POST /runtime-events`, Collector R1/R2) — ✅ shipped; **Python SDK MVP** (Collector R3, `sdk/python/observeagents`) — ✅ shipped (PR #114); **next: Python SDK Quickstart → SDK demo agent** (see [Runtime evidence track](#runtime-evidence-track--status--next-milestones)); OTLP **metrics** ingestion (Claude Code / coding-agent token & cost accounting) still ahead; **auto-instrumentation-first discovery** (A1–A8) — see the [Auto-instrumentation-first discovery track](#auto-instrumentation-first-discovery-track-a1a8) |
| O3 | Content-free security verdicts | In-flight scanning at ingestion (prompt injection, PII-in-prompt, toxicity) storing **verdicts only** — never content; Runtime "Security checks" filter |
| O4 | Monitors & notifications | **AI Agent Detection Rules & Alerts** (see below); budget alerts via webhook (Slack / Teams) — canonical design: [ai_agent_detection_rules_alerts_design.md](ai_agent_detection_rules_alerts_design.md) |
| O5 | Product surface deployments | Per-surface builds of the Observability and Gateway products (separation plan Phase 4); surface-scoped API keys |
| O6 | Enterprise readiness | SSO (Okta / Google OAuth), per-tenant API key table, HA / fail-over story, documented self-host path |
| O7 | Observe MCP server | Read-only MCP tools (`list_ai_systems`, `get_findings`, `get_trace`, `get_cost_signals`) so customers' agents can query their AI inventory |
| O8 | **Observe Advisor MVP** | From *what happened* to *what this agent needs to learn next* — see below |
| O9 | **Gateway Control Center / Observe-to-Control** | A one-click workspace that turns observed runtime risk into Gateway control recommendations for specific AI agents. One production app: Observe workspace (runtime evidence into understanding) + Gateway Control Center (action workspace) — no env-var switch, no redeploy, no enforcement without explicit approval. *Observe first. Control only what matters.* Design: [gateway_control_center_architecture.md](gateway_control_center_architecture.md) |
| Future | **Agentic Payments / x402 Observability** *(exploratory)* | Future support for observing payment-enabled AI-agent behavior — HTTP 402 challenges, paid external resources, payment failures, payment spikes, and payment-related detection rules — as runtime evidence, risk findings, and control recommendations. ObserveAgents observes; it does not process or verify payments. Design doc `agentic_payments_x402_observability_plan.md` (retired from docs/; in git history) |

**Shipped:** **AI Agent Runtime Security Intelligence MVP** — agent-specific, environment-aware security findings derived from runtime evidence (database/API reach, MCP in production, broad tool surface, unknown providers, missing ownership, repeated tool errors, human-review combinations). Observe-only, derivation-only, no new ingestion. See [ai_agent_runtime_security_intelligence.md](ai_agent_runtime_security_intelligence.md). O3's in-flight content verdicts (prompt injection / PII / toxicity) remain ahead as the next security layer.

**Shipped:** **Runtime Events ingestion seam (Collector R1/R2)** — `POST /runtime-events` accepts normalized GenAI runtime events from any source, validates them against an allow-list schema, privacy-scrubs at the boundary (no prompts/responses/tool args/credentials/full URLs), and converts them into the existing span pipeline (`normalize_spans`) — OTLP and runtime events converge on the same intelligence engine; no source gets its own findings pipeline. Evidence-ingestion only: no inline detection rules, no control candidates, no enforcement.

**Shipped:** **Python SDK MVP (Collector R3, PR #114)** — `sdk/python/observeagents`: a thin `ObserveOpenAI` wrapper around the OpenAI Python client emitting one safe `llm_call` runtime event per completion call to the configurable `{observeagents_url}/runtime-events` endpoint (Cloud or customer-side collector). Fail-open, content-free (no prompts/messages/responses/tool args/headers/credentials ever leave the customer's process), provider exceptions re-raised unchanged. Guide: [sdk-guide.md](sdk-guide.md). **Next: Python SDK Quickstart** — see the [Runtime evidence track](#runtime-evidence-track--status--next-milestones).

**Shipped:** **Gateway Control Center GCR2–GCR4 (O9 first slice)** — control-candidate derivation from high-risk runtime evidence (`category=control` findings), the Control Center action workspace in the same production app on both surfaces, and one-click Observe→Control navigation. No enforcement, no rerouting; GCR5+ (policy drafts, approval, enforcement for routed agents) remain ahead. See [gateway_control_center_architecture.md](gateway_control_center_architecture.md).

---

## Runtime evidence track — status & next milestones

The multi-source ingestion direction (O2): every source is a small adapter that feeds the
**same** runtime evidence engine. Repo cleanup and infrastructure work are tracked
separately and are deliberately not part of this product track.

### Completed

| # | Milestone | Status |
|---|---|---|
| 1 | **Runtime Events ingestion** — `POST /runtime-events`: validated, privacy-scrubbed normalized GenAI runtime events from any source | ✅ shipped (PR #110) |
| 2 | **Reuse of the existing intelligence engine** — span-like adapter → `normalize_spans` → assets → findings → detection rules → gateway control candidates; no new pipeline | ✅ shipped (PR #110) |
| 3 | **Python SDK MVP** — `ObserveOpenAI` wrapper (`sdk/python/observeagents`): one safe `llm_call` event per completion call, fail-open, content-free | ✅ shipped (PR #114) |

### Next

**4. Python SDK Quickstart** — ✅ shipped: [sdk-guide.md](sdk-guide.md)

> **Goal: a user can connect a simple OpenAI-based agent in 5 minutes.**

Includes:

- install / local usage (in-repo `sdk/python`, no PyPI yet)
- environment variables (`OBSERVEAGENTS_URL`, `OBSERVEAGENTS_API_KEY`, `OBSERVEAGENTS_AGENT_NAME`, …)
- a minimal `ObserveOpenAI` example (constructor + one `chat.completions.create` call)
- privacy explanation — what is sent (metadata only) and what is never sent (prompts, messages, responses, tool args, headers, credentials)
- verification steps — the event appears in Runtime, the agent appears in Asset Intelligence, findings derive on the next intelligence run

### Then

**5. SDK Demo / Sample Agent**

> **Goal: an end-to-end demo — OpenAI call → SDK event → `/runtime-events` → evidence → intelligence.**

A small runnable sample agent that exercises the full chain and shows the product lighting
up from a single script: inventory, runtime activity, token usage, errors, and derived
findings — with zero OTel setup.

### Later

**6. Gateway Telemetry Adapter**

> **Goal: Gateway traffic should also feed the same runtime evidence engine.**

The base_url-swap path today produces cost + inventory only; this adapter makes proxied
traffic produce the same evidence as OTLP and SDK events — assets, findings, detection
rules — with no change to enforcement behavior.

**7. LangChain / LiteLLM Adapter**

> **Goal: framework integrations after SDK adoption is proven.**

Callback handlers that emit the same normalized runtime events; sequenced deliberately
after the SDK quickstart/demo prove the adoption path.

**8. MCP Runtime Events**

> **Goal: visibility into MCP tools, servers, and tool-call behavior.**

MCP server / tool / method usage as runtime events, lighting up the existing MCP findings
(broad tool surface, flagged MCP server, repeated tool errors) without full instrumentation.

### Track principles (hold for every milestone above)

- **No new intelligence pipeline.** Every adapter emits normalized runtime events or
  span-like evidence into the existing engine — one place derives assets, findings, rules,
  and control candidates, forever.
- **Observe first. Control only what matters.**
- **Gateway enforcement remains optional and explicit.** Nothing is enforced unless traffic
  is explicitly routed through Gateway and controls are explicitly configured.
- **No automatic enforcement from detection or SDK events.** Detection rules and SDK
  evidence produce findings and recommendations for humans — never actions against traffic.

---

## Auto-instrumentation-first discovery track (A1–A8)

**Core line: Install the SDK once. We discover AI workloads from runtime behavior.**

The product must deliver a full inventory, timeline, and findings from auto-instrumented
telemetry alone (service.name, GenAI spans, provider/model, token usage, HTTP/DB spans,
external APIs, errors, environment). Manual spans, explicit `gen_ai.agent.name`, tagged
tools, and owner/team metadata are **optional accuracy boosters, never requirements**.
Full plan, discovery levels, identity/confidence model, and the code audit:
[auto_instrumentation_first_discovery_plan.md](auto_instrumentation_first_discovery_plan.md).

### Completed

| # | Milestone | Status |
|---|---|---|
| A1 | **Auto-instrumentation discovery plan** — discovery levels 0–3, identity priority, confidence + evidence model | ✅ shipped (this doc set) |
| A2 | **Code audit for explicit-agent assumptions** — every gen_ai.agent.name / manual-span / owner-team dependency mapped with keep / change-now / change-later | ✅ shipped (inside the plan doc) |
| A3 | **Internal identity scoring and customer-facing discovery evidence** — identity scoring stays backend-only (resolution, dedup, ranking, severity capping, Gateway candidates); Asset Intelligence surfaces discovery method, observed signals, and optional metadata — never confidence percentages or high/medium/low labels | ✅ shipped |
| A4 | **"Runtime-discovered AI Workload" labeling** — first-class discovery badge alongside Explicit Agent (and Gateway-observed), with evidence subcopy | ✅ shipped |

### Next

| # | Milestone |
|---|---|
| A5 | **Observed signals + missing context** beyond Asset Intelligence — extend the same evidence pattern to Overview and Security Intelligence |
| A6 | **UI copy update pass** — complete the de-emphasis of manual instrumentation beyond the initial fixes |

### Later

| # | Milestone |
|---|---|
| A7 | **Optional ObserveAgents SDK wrapper for higher accuracy** — explicit naming/session grouping as the accuracy ceiling (OpenAI wrapper shipped; keep expanding) |
| A8 | **Configured AI vs Runtime AI** — reconcile declared/registered AI systems with what runtime evidence actually shows |

### Track principles

- **Manual annotations improve accuracy; visibility starts without them.**
- **Confidence is internal. Evidence is customer-facing.** Scoring drives backend decisions; the UI shows discovery method, observed signals, and optional metadata — never confidence percentages or high/medium/low labels.
- Absence of a signal lowers internal scoring — it never blocks ingestion, discovery, or findings.
- Missing context surfaces as an optional setup improvement, not an error or a security defect.
- Detection rules key on `asset_key` / `service.name` / resource attributes — never on an agent name existing.

---

## O4 — AI Agent Detection Rules & Alerts

**Definition:** configurable runtime rules that evaluate AI-agent behavior and create alerts when behavior crosses thresholds or matches risky patterns.

Detection Rules are an intelligence layer: they consume normalized runtime evidence and existing asset/security context, and may create rule matches, alerts, findings, and Gateway Control Candidate recommendations. They never block, reroute, reconfigure the Gateway, mutate telemetry, or inspect raw prompts/responses.

Examples:

- MCP calls > threshold in a time window
- repeated tool errors
- unknown provider in production
- database access + external API call in the same trace
- high token usage (an Observability Cost Signal, not billing)
- flagged dependency touched (customer-configured watchlist)

**Posture:** observe-only first. **Webhook notifications shipped** (post-intelligence, `detection_rules` findings only, cooldown-throttled, no enforcement); Slack still ahead. Gateway enforcement only later — and only when traffic is explicitly routed through Gateway and controls are explicitly configured.

> Rules observe and alert. Gateway can optionally enforce later.

Canonical design with rule templates, evaluation model, dedup/anti-spam rules, future data model, and R0–R8 sequence: [ai_agent_detection_rules_alerts_design.md](ai_agent_detection_rules_alerts_design.md) (supersedes [ai_agent_detection_rules_plan.md](archive/legacy/ai_agent_detection_rules_plan.md)).

---

## Future / exploratory — Agentic Payments / x402 Observability

**Status: future / exploratory.** Positioned *below* the current detection-rules and webhook-notification work — not a near-term commitment.

As AI agents begin to pay for resources, APIs, datasets, and MCP tools programmatically (via HTTP 402 payment challenges — e.g. Cloudflare's Monetization Gateway), a new category of runtime behavior appears: *which agents pay, what for, how often, and whether that's risky.* ObserveAgents would treat payment activity as **runtime evidence** — surfacing paid-resource summaries in Asset Intelligence, a Payment & Monetization Risk bucket in Security Intelligence, payment-threshold Detection Rules, and Gateway Control recommendations for payment-enabled agents.

**ObserveAgents observes; it does not process or verify payments** and does not replace Cloudflare, Stripe, wallets, gateways, or billing systems. Enforcement (spend limits, vendor allowlists) would happen only if traffic is explicitly routed through Gateway and controls are explicitly configured.

Full plan — telemetry model, findings, detection rules, product surfaces, privacy boundaries, non-goals, and the P0–P8 sequence: `agentic_payments_x402_observability_plan.md` (retired from docs/; available in git history).

---

## O8 — Observe Advisor MVP

Most observability tools stop at:

> This trace was slow. This request failed. This model was expensive.

ObserveAgents should answer:

> **What does this agent need to learn next?**

Observe Advisor turns the findings the platform already derives into concrete, reviewable improvement recommendations for agent teams. It is an **advisory layer only**:

> Observe recommends skill improvements based on runtime evidence. It does **not** automatically rewrite, deploy, or change agent behavior.

### Sub-phases

| Sub-phase | Deliverable |
|---|---|
| O8.1 | Finding-to-Recommendation Engine — map finding types to recommendation templates |
| O8.2 | Skill Gap Detection — infer weak/missing capabilities from finding patterns per asset |
| O8.3 | Agent Skill Recommendations — the per-agent "what to learn next" surface |
| O8.4 | Skill Improvement Playbooks — practical implementation guidance attached to each recommendation |
| O8.5 | Validation Signals — measure whether the improvement worked, from the same telemetry |
| O8.6 | Optional ticket/export to Jira / GitHub / Linear |

---

### Agent Skill Recommendations

ObserveAgents can use runtime findings to recommend which skills an AI agent should **add, improve, or validate**.

This is not automatic code generation, not automatic agent rewriting, not auto-deployment, and never a hidden behavior change. It is an Advisor feature: findings become skill gaps, skill gaps become recommendations, recommendations come with playbooks, and playbooks close the loop with validation signals.

#### The pipeline

```
Runtime Evidence
  → Finding
    → Skill Gap
      → Skill Recommendation
        → Skill Improvement Playbook
          → Validation Signal
```

**Finding** — what Observe detected from runtime telemetry (an existing AssetFinding: error patterns, token usage, tool surface, environment context).

**Skill Gap** — the missing or weak capability *inferred* from the finding: not "the trace failed" but "this agent lacks fallback behavior."

**Skill Recommendation** — the skill the agent team should add or improve, named in the team's language.

**Skill Improvement Playbook** — practical implementation guidance for the team: concrete steps, ordered, scoped to their agent.

**Validation Signal** — how Observe can later verify whether the improvement worked, from the same telemetry that produced the finding. The loop closes with evidence, not opinion.

#### Finding → skill examples

| Finding | Recommended skill |
|---|---|
| `repeated_tool_errors` | Tool fallback handling skill |
| `high_token_usage` | Context compression skill |
| `broad_tool_surface` | Tool routing skill |
| `human_review_recommended` | Human handoff decisioning skill |
| `unknown_provider_model` | Provider review skill |
| `slow_retrieval` | Retrieval filtering skill |
| `repeated_workflow_failure` | Workflow recovery skill |

#### Skill categories

1. **Tool-use skills** — tool selection · retry/fallback handling · tool argument validation · MCP tool selection
2. **Reasoning/workflow skills** — planning before tool use · task decomposition · confidence estimation · human handoff
3. **Cost/performance skills** — context compression · summary caching · model routing · retrieval filtering
4. **Security/safety skills** — sensitive dependency review · high-risk tool review · unknown provider review · least-privilege tool use
5. **Domain skills** — support triage · finance analysis · engineering code search · HR onboarding · research synthesis

#### Worked examples

##### Example 1 — Jira lookup failures

- **Finding:** `repeated_tool_errors` on `jira_search`
- **Skill Gap:** Agent lacks robust issue lookup and fallback behavior.
- **Recommendation:** Add a Jira lookup fallback skill.
- **Playbook:**
  - Validate issue key format before calling Jira
  - Fall back to text search when exact lookup fails
  - Retry once, not repeatedly
  - Escalate after repeated failure
  - Log `error.type` and tool status on every attempt
- **Validation:**
  - Fewer `jira_search` failures
  - Lower support-agent trace duration
  - Fewer human escalations caused by failed lookups

##### Example 2 — High token usage

- **Finding:** `high_token_usage` in research-agent
- **Skill Gap:** Agent lacks context compression.
- **Recommendation:** Add a context compression and summary reuse skill.
- **Playbook:**
  - Summarize retrieved context before final reasoning
  - Reuse cached summaries for repeated topics
  - Prefer a smaller model for low-risk summarization
- **Validation:**
  - Lower average input tokens
  - Lower cost signals
  - Same or better task completion rate

##### Example 3 — Broad tool surface

- **Finding:** `agent_has_broad_tool_surface`
- **Skill Gap:** Agent lacks disciplined tool routing.
- **Recommendation:** Add a tool selection/routing skill.
- **Playbook:**
  - Classify task type before tool use
  - Choose one primary tool per task stage
  - Require review for high-risk tools
  - Record the selected tool and a reason code
- **Validation:**
  - Fewer unnecessary tool calls
  - Fewer high-risk tool invocations
  - Clearer execution timeline

#### Safety and scope boundaries

- Recommendations are **advisory** — nothing is applied automatically.
- **Human review is required** before any recommendation is implemented.
- No automatic code changes; no automatic deployment; no hidden agent behavior changes.
- No harmful or weaponized skill recommendations.
- No instructions for evasion, offensive misuse, or unsafe autonomous behavior.
- The Advisor inherits the platform's privacy stance: it reasons over derived findings and metadata, never raw prompt/response content.
