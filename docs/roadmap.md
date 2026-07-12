# ObserveAgents Roadmap

*The central forward roadmap. The full shipped-feature checklist lives in the [README roadmap table](../README.md#roadmap); this document tracks what comes next, phased.*

ObserveAgents is the **runtime visibility and control layer for AI agents**: it turns runtime evidence into AI inventory, ownership, dependencies, capabilities, findings, and observe-only guardrail recommendations. Every phase below extends that spine — nothing here changes the observe-first posture.

---

## Forward phases

| Phase | Theme | Summary |
|---|---|---|
| O1 | Ecosystem Discovery | GitHub / Jira / Slack / n8n / MCP evidence connectors; Active / Dormant / Runtime-only correlation with the runtime inventory |
| O2 | Ingestion depth | OTLP **protobuf** support — ✅ shipped (direct OpenLLMetry-style onboarding, no Collector required); **Runtime Events ingestion seam** (`POST /runtime-events`, Collector R1/R2) — ✅ shipped; **Python SDK wrapper** (Collector R3) — plan approved ([python_sdk_wrapper_plan.md](python_sdk_wrapper_plan.md)); OTLP **metrics** ingestion (Claude Code / coding-agent token & cost accounting) still ahead |
| O3 | Content-free security verdicts | In-flight scanning at ingestion (prompt injection, PII-in-prompt, toxicity) storing **verdicts only** — never content; Runtime "Security checks" filter |
| O4 | Monitors & notifications | **AI Agent Detection Rules & Alerts** (see below); budget alerts via webhook (Slack / Teams) — canonical design: [ai_agent_detection_rules_alerts_design.md](ai_agent_detection_rules_alerts_design.md) |
| O5 | Product surface deployments | Per-surface builds of the Observability and Gateway products (separation plan Phase 4); surface-scoped API keys |
| O6 | Enterprise readiness | SSO (Okta / Google OAuth), per-tenant API key table, HA / fail-over story, documented self-host path |
| O7 | Observe MCP server | Read-only MCP tools (`list_ai_systems`, `get_findings`, `get_trace`, `get_cost_signals`) so customers' agents can query their AI inventory |
| O8 | **Observe Advisor MVP** | From *what happened* to *what this agent needs to learn next* — see below |
| O9 | **Gateway Control Center / Observe-to-Control** | A one-click workspace that turns observed runtime risk into Gateway control recommendations for specific AI agents. One production app: Observe workspace (runtime evidence into understanding) + Gateway Control Center (action workspace) — no env-var switch, no redeploy, no enforcement without explicit approval. *Observe first. Control only what matters.* Design: [gateway_control_center_architecture.md](gateway_control_center_architecture.md) |
| Future | **Agentic Payments / x402 Observability** *(exploratory)* | Future support for observing payment-enabled AI-agent behavior — HTTP 402 challenges, paid external resources, payment failures, payment spikes, and payment-related detection rules — as runtime evidence, risk findings, and control recommendations. ObserveAgents observes; it does not process or verify payments. Design: [agentic_payments_x402_observability_plan.md](agentic_payments_x402_observability_plan.md) |

**Shipped:** **AI Agent Runtime Security Intelligence MVP** — agent-specific, environment-aware security findings derived from runtime evidence (database/API reach, MCP in production, broad tool surface, unknown providers, missing ownership, repeated tool errors, human-review combinations). Observe-only, derivation-only, no new ingestion. See [ai_agent_runtime_security_intelligence.md](ai_agent_runtime_security_intelligence.md). O3's in-flight content verdicts (prompt injection / PII / toxicity) remain ahead as the next security layer.

**Shipped:** **Runtime Events ingestion seam (Collector R1/R2)** — `POST /runtime-events` accepts normalized GenAI runtime events from any source, validates them against an allow-list schema, privacy-scrubs at the boundary (no prompts/responses/tool args/credentials/full URLs), and converts them into the existing span pipeline (`normalize_spans`) — OTLP and runtime events converge on the same intelligence engine; no source gets its own findings pipeline. Evidence-ingestion only: no inline detection rules, no control candidates, no enforcement. **Next (Collector R3): Python SDK wrapper** — a thin `ObserveOpenAI`-style client emitting runtime events to a configurable endpoint (Cloud or customer-side collector); plan approved: [python_sdk_wrapper_plan.md](python_sdk_wrapper_plan.md).

**Shipped:** **Gateway Control Center GCR2–GCR4 (O9 first slice)** — control-candidate derivation from high-risk runtime evidence (`category=control` findings), the Control Center action workspace in the same production app on both surfaces, and one-click Observe→Control navigation. No enforcement, no rerouting; GCR5+ (policy drafts, approval, enforcement for routed agents) remain ahead. See [gateway_control_center_architecture.md](gateway_control_center_architecture.md).

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

Canonical design with rule templates, evaluation model, dedup/anti-spam rules, future data model, and R0–R8 sequence: [ai_agent_detection_rules_alerts_design.md](ai_agent_detection_rules_alerts_design.md) (supersedes [ai_agent_detection_rules_plan.md](ai_agent_detection_rules_plan.md)).

---

## Future / exploratory — Agentic Payments / x402 Observability

**Status: future / exploratory.** Positioned *below* the current detection-rules and webhook-notification work — not a near-term commitment.

As AI agents begin to pay for resources, APIs, datasets, and MCP tools programmatically (via HTTP 402 payment challenges — e.g. Cloudflare's Monetization Gateway), a new category of runtime behavior appears: *which agents pay, what for, how often, and whether that's risky.* ObserveAgents would treat payment activity as **runtime evidence** — surfacing paid-resource summaries in Asset Intelligence, a Payment & Monetization Risk bucket in Security Intelligence, payment-threshold Detection Rules, and Gateway Control recommendations for payment-enabled agents.

**ObserveAgents observes; it does not process or verify payments** and does not replace Cloudflare, Stripe, wallets, gateways, or billing systems. Enforcement (spend limits, vendor allowlists) would happen only if traffic is explicitly routed through Gateway and controls are explicitly configured.

Full plan — telemetry model, findings, detection rules, product surfaces, privacy boundaries, non-goals, and the P0–P8 sequence: [agentic_payments_x402_observability_plan.md](agentic_payments_x402_observability_plan.md).

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
