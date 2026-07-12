# ObserveAgents — Product Pitch

*The written pitch for early customers, AI startups, SaaS teams, and technical founders. Grounded in the current implementation — see [Proof points](#proof-points-from-the-current-implementation) for what is real today and [What not to claim](#what-not-to-claim) for the lines we never cross.*

---

## One-liner

**See what your AI agents are actually doing.**

ObserveAgents is the runtime visibility and control recommendation layer for AI agents.

---

## Short pitch

Teams are shipping AI agents into real workflows — support, research, ops — and most of them cannot answer basic questions about what those agents do in production. Which agents are running? What tools are they calling? Are they using MCP? Did one touch a database and an external API in the same run?

ObserveAgents answers those questions from runtime evidence. Connect OpenTelemetry once, and agents are discovered from what they actually did — not from a config file or a spreadsheet. The platform builds an agent inventory, explains which agents look risky and why, turns risky patterns into detection-rule alerts, and recommends which agents deserve a control path.

**Observe first. Control only what matters.** Observe can recommend. Gateway can enforce only when explicitly configured. Nothing is blocked automatically, ever.

---

## 60-second pitch

You're running AI agents in production. Quick question: what did they do yesterday?

Most teams can't answer that. The agent code is in the repo, the prompts are in a config, but the actual behavior — which tools got called, which MCP servers, which databases, which providers, how many retries — lives in runtime, and nobody is looking at it.

ObserveAgents looks at it. You point your existing OpenTelemetry setup at us — no proprietary SDK, and if you use OpenLLMetry it's two lines of code. From your traces we discover your agents, build an inventory of what each one is, who owns it, and what it touches, and derive findings: this agent reaches a database in production, this one uses an unknown provider, this one is failing the same tool call over and over.

Detection rules turn those patterns into alerts. And when an agent crosses a real line, the Gateway Control Center recommends it for review — with the evidence that put it there and the controls that would help. Recommends. It never blocks anything unless you explicitly route traffic through the Gateway and explicitly turn enforcement on.

Runtime truth first. That's the product.

---

## 3-minute pitch

**The setup.** AI agents are no longer demos. Small teams are wiring them into support queues, research pipelines, internal tools. And agents behave differently from normal software: they choose their own tools at runtime, call MCP servers, retry on their own judgment, reach APIs and databases, and switch models. What an agent actually does is an emergent property of its prompt, tools, and inputs — not something a code review predicts.

**The problem.** Ask a team running five agents: which ones ran this week? What did they touch? Who owns the one calling that external API? The honest answer is usually "let me check the code" — which tells you what the agent *might* do, not what it *did*. Traces exist somewhere, but nobody reads raw traces all day, and generic APM shows services and spans, not agents and risk.

**The product.** ObserveAgents turns runtime telemetry into agent understanding. The whole product is one evidence chain:

> OpenTelemetry / OTLP → Runtime Evidence → Agent Discovery → Asset Intelligence → Security Intelligence → Detection Rules & Alerts → Gateway Control Recommendations

You connect OTel once — your existing exporter, a Collector, or OpenLLMetry auto-instrumentation. Agents are discovered from the traces themselves; no manual registration. From there:

- **Asset Intelligence** becomes the source of truth for each agent: identity, owner, capabilities, tool/MCP/API/database dependencies, findings, and next action.
- **Security Intelligence** explains which agents are risky and why — from behavior, not scanners: MCP in production, broad tool surface, database plus external-API reach, unknown providers, missing ownership, repeated tool errors.
- **Rules & Alerts** turns the same evidence into threshold alerts — "MCP calls over the limit", "repeated tool errors", "unknown provider in production" — delivered to a webhook. Rules observe and alert. Gateway can optionally enforce later.
- **Gateway Control Center** is a short review queue: the agents that crossed a line, the evidence that put them there, and the controls that would address it. Enforcement exists in the product — but only for traffic explicitly routed through the Gateway, only for teams explicitly set to enforce.

**The differentiation.** Other tools discover AI from code, configs, and connected systems — what *might* exist. ObserveAgents shows what agents *actually did* at runtime. Runtime truth first. Configured discovery second. Correlation is the product.

**Privacy, by construction.** We store structural metadata only. Prompts, responses, and tool arguments are scrubbed at ingestion and never stored — only a hash and a byte size survive. You get behavior visibility without shipping us your customers' content.

**The ask.** If you're running agents and can't answer "what did they do yesterday," connect a trace. First agent appears in the dashboard in minutes.

---

## The problem

AI teams are shipping agents into real workflows, but they often cannot answer simple questions:

- Which agents are actually running?
- What tools are they calling?
- Are they using MCP?
- Which model and provider are they using?
- Did they touch databases or external APIs?
- Are they failing or retrying?
- Who owns each agent?
- Which agents need review or control?

None of these are exotic. They're the questions any engineering leader asks about any production system. Agents just make them harder to answer, because agent behavior is decided at runtime — and most teams' visibility stops at the code.

The result isn't (usually) a disaster. It's a slow accumulation of unknowns: an agent nobody owns, a tool call that fails silently a hundred times a day, a provider nobody approved, an MCP server that quietly became a production dependency. Each one is cheap to catch early and expensive to discover late.

## The solution

ObserveAgents answers, from runtime evidence:

| Question | Where it's answered |
|---|---|
| Who are my agents? | Agent discovery + Asset Intelligence inventory |
| What did they actually do? | Runtime execution timelines (sessions, waterfalls) |
| What did they touch? | Capabilities and dependencies: tools, MCP, APIs, databases, providers |
| What looks risky? | Security Intelligence findings, worst-first |
| Which agents need review? | Human-review recommendations + detection-rule matches |
| Which agents should move to Gateway Control? | Gateway Control Center candidates, with evidence |

The product starts from runtime evidence, not assumptions. Discovery is automatic: an agent that sends a trace exists; an agent in a config file might.

## Why now

- **Agents crossed from demo to production.** Support, research, ops, and internal tooling agents run real workflows at small companies today — not just in labs.
- **The telemetry standard arrived.** OpenTelemetry GenAI semantic conventions (`gen_ai.*`) and open instrumentation like OpenLLMetry mean agent behavior is already being emitted in a standard shape. The data exists; the understanding layer doesn't.
- **MCP made the tool surface explode.** Agents now attach to external tool servers in one config line. Every new MCP server is a new runtime dependency someone should be able to see.
- **Teams are too small for a governance program.** The people shipping agents are 3–30 person engineering teams. They need a dashboard that answers questions in minutes, not an enterprise rollout.

## Target customer

- AI startups and SaaS teams building agents on OpenAI, Anthropic, or Claude Code
- Small engineering teams already using (or willing to add) OpenTelemetry / OpenLLMetry
- Product teams shipping agent features who need to answer "what is it doing?" for themselves and their customers
- Technical founders and engineering leaders who own the "are we OK?" question

Not the primary audience: large-enterprise CISOs, compliance programs, SOC teams looking for a SIEM. The product may grow toward them; it isn't written for them today.

## Product workflow

```
OpenTelemetry / OTLP
  → Runtime Evidence          (immutable, privacy-scrubbed spans and events)
    → Agent Discovery         (agents from service.name / agent identity — no registration)
      → Asset Intelligence    (inventory: identity, owner, capabilities, dependencies, findings)
        → Security Intelligence   (which agents are risky and why)
          → Detection Rules & Alerts  (thresholds over the same evidence → webhook alerts)
            → Gateway Control Recommendations  (review queue; enforcement only if explicitly configured)
```

Three ways in, all standard:

1. **Already on OTel** — point your existing exporter or Collector at `POST /otel/v1/traces` (JSON or protobuf).
2. **OpenLLMetry** — two lines of Python; auto-instruments OpenAI, Anthropic, LangChain, LlamaIndex, CrewAI, and more.
3. **A single curl** — one hand-written span proves the pipeline end to end in under a minute.

## Key features

### Overview
The runtime posture of your AI estate at a glance: agents discovered, agents with findings, agents needing owners, control candidates, and live runtime activity — with an evidence-backed "Zone of Attention" that only shows conditions that are actually live.

### Asset Intelligence
The source of truth for each agent: who it is, which owner and team, what it does, its tool/MCP/API/database dependencies, its findings grouped by category, its next action, and whether it's a Gateway Control candidate. Worst-first sorting; every number backed by evidence.

### Security Intelligence
Explains runtime risk in agent terms, across seven investigation buckets: MCP/tool risk, database & API access, unknown providers/models, missing ownership, repeated tool errors, human-review recommendations, and detection-rule matches. Agent-specific and environment-aware — the same behavior scores differently in production than in dev.

### Rules & Alerts
Detection rules convert runtime behavior into alerts. Built-in today: MCP tool-access over threshold, repeated tool errors, unknown provider in production. Designed next in the rule catalog: database + external API in the same trace, broad tool surface, high token usage, flagged dependency touched. Alerts deliver to webhooks with per-finding cooldowns so a noisy agent never becomes a noisy inbox.

**Rules observe and alert. Gateway can optionally enforce later.**

### Gateway Control Center
A short review queue, not another dashboard: the agents recommended for control, *why* each is there (the trigger findings, verbatim), what evidence fired, and which controls would help — typed as `soft` (available now), `routing` (route through Gateway), or `hard` (requires Gateway routing). Everyone can view; only admins act. Enforcement requires explicit routing and explicit configuration — a recommendation renders as a review card, never a toggle.

### Privacy guarantee
Runtime evidence is structural metadata only. Prompts, responses, system instructions, and tool arguments/results are scrubbed at ingestion and never stored — only a SHA-256 hash and byte size survive. URLs keep scheme + host + path only. Findings carry identifiers and counts, never content.

## Differentiation

**Runtime truth first. Configured discovery second. Correlation is the product.**

### vs. generic observability / APM
Generic APM shows services and traces. ObserveAgents explains AI-agent behavior and risk: which agent, what tools, which MCP servers, what it reached, whether that combination deserves review. An APM trace tells you a span was slow; ObserveAgents tells you an agent touched a database and an external API in the same run and nobody owns it.

### vs. AI security platforms that start from code/config discovery
Code and config discovery shows what *might* exist — every API key in a repo, every model in a config. ObserveAgents shows what *actually ran*. A discovered-in-code agent that never executes is noise; an agent running in production with no owner is signal. (Ecosystem discovery is on our roadmap — as the *second* source, correlated against runtime truth.)

### vs. cloud-native tools like CloudWatch
CloudWatch is good for AWS-native telemetry: metrics, logs, service health. ObserveAgents adds what it doesn't attempt: an AI-agent inventory built from behavior, agent-specific findings, detection rules written in agent terms, and control recommendations.

### vs. gateway/proxy-only products
A gateway can only see — and only enforce on — traffic you route through it. That's a real capability (we ship one), but it's the wrong *starting point*: it makes visibility conditional on rewiring every client first. ObserveAgents starts with observation through OpenTelemetry, discovers everything that emits traces, and recommends the gateway path only for the agents that need one.

## Demo story

Two agents, one connection. (Full narrative: [demo_story.md](demo_story.md).)

**support-agent** is the healthy baseline: a customer question comes in, the agent looks up the ticket in the CRM, makes one LLM call, and answers. It's discovered from OTel automatically, its timeline is clean, and it carries no significant findings. This is what "fine" looks like — and being able to *show* fine is half the value.

**risky-research-agent** is the contrast: repeated MCP calls that cross the rule threshold, an unknown provider in production, repeated tool errors against an external API. Security Intelligence explains each risk; the Rules & Alerts page shows the rule matches; and the Gateway Control Center recommends the agent for review — with the exact findings that put it there and suggested controls.

The arc the demo proves: **connect OTel once → agents are discovered → runtime behavior is visible → risky patterns are detected → a rule match appears → Gateway Control Center recommends review.** One integration, and the platform walked from raw telemetry to a specific, evidence-backed recommendation — without blocking anything.

## Proof points from the current implementation

Everything below is shipped and inspectable in the repo:

- **OTLP/HTTP ingestion, JSON + protobuf** — `POST /otel/v1/traces` (`app/routes/otel.py`, `app/otel_parser.py`); GenAI semantic conventions (`gen_ai.*`, `tool.*`, `mcp.*`, `db.*`, `url.*`) understood natively.
- **Agent discovery from traces** — agents identified from `service.name` / agent identity attributes; no manual registration step.
- **Privacy scrubbing at ingestion** — `app/otel_privacy.py` removes prompts, responses, system instructions, and tool arguments/results before storage; SHA-256 hash + byte size only; URLs reduced to scheme + host + path.
- **Runtime execution timelines** — session-grouped traces with per-step waterfalls; steps classified as llm / tool / mcp_tool / database / external_api.
- **Asset Intelligence** — `app/asset_intelligence.py`; idempotent derivation with occurrence dedup: recurring evidence lands as a count on one finding row, never row spam.
- **Runtime Security Intelligence** — `app/runtime_security_intelligence.py`; eight agent-specific, environment-aware finding types (database access, unmanaged external API, MCP in production, broad tool surface, unknown provider, missing owner, repeated tool errors, human-review combinations).
- **Detection Rules (built-in)** — `app/detection_rules.py`; MCP tool-access threshold, repeated tool errors, unknown provider in production; evaluated during the intelligence run, never at ingestion.
- **Webhook alert delivery** — admin-managed channels, encrypted URLs, 60-minute per-finding cooldown, fail-safe delivery.
- **Gateway Control Center** — `app/gateway_control.py`; candidates derived from open high-severity evidence or human-review recommendations; suggested controls typed soft/routing/hard; admin-only actions; one-click navigation from Overview, Asset Intelligence, and Security Intelligence.
- **Gateway (opt-in path)** — OpenAI-compatible and Anthropic-compatible proxies with streaming, BYOK, budgets, and per-team guard modes (observe / alert / enforce); blocking happens only for teams explicitly set to enforce.
- **Runtime event ingestion** — `POST /runtime-events` accepts normalized GenAI runtime events from any source and feeds the *same* intelligence engine as OTLP; the schema is an allow-list, so content can't ride in even by accident.
- **Demo seed** — a five-system synthetic org pushed through the real ingestion pipeline, so a demo is the actual product, not screenshots.

## What not to claim

Hard lines. These keep the pitch honest and match how the product is built:

- **Never claim automatic enforcement or automatic blocking.** Nothing is blocked, rerouted, or enforced unless traffic is explicitly routed through the Gateway *and* a team is explicitly set to enforce. Observe can recommend. Gateway can enforce only when explicitly configured.
- **Never position as a SIEM or SIEM replacement.** No log correlation, no threat-intel feeds, no cross-system detection language.
- **Never position as an APM or APM replacement.** We don't compete on latency dashboards; we explain agent behavior and risk.
- **Never claim "complete governance" or "guaranteed prevention."** We surface evidence and recommend review; humans decide.
- **Never claim we analyze prompt or response content.** We can't — it's scrubbed at ingestion and never stored. This is a feature; state it as one.
- **Never present designed-but-unshipped rules or roadmap items as current product.** Three detection rules are built-in today; the rest of the catalog is designed. Ecosystem discovery, Observe Advisor, Agent Passport, Runtime Trust Score, Action Ledger, and x402 payment observability are future roadmap.
- **Never lead with enterprise-governance or fear language.** The buyer is a builder; the tone is "see clearly," not "be afraid."

## Roadmap (future — say so when mentioning)

Directions under design or exploration; none are current product claims:

- **Configured AI vs Runtime AI** — ecosystem discovery (GitHub / Jira / Slack / n8n / MCP configs) correlated against runtime truth: what's configured, what actually runs, what's dormant.
- **Observe Advisor** — from "what happened" to "what this agent should learn next": findings become skill-gap recommendations with playbooks and validation signals. Advisory only.
- **Observe MCP server** — read-only MCP tools so your agents can query their own inventory and findings.
- **Agent Passport** *(exploratory)* — a portable, evidence-backed identity summary per agent: who it is, what it touches, who owns it.
- **Runtime Trust Score** *(exploratory)* — a per-agent score derived from runtime evidence and finding history.
- **Action Ledger** *(exploratory)* — an append-only record of consequential agent actions for review and audit.
- **Agentic Payments / x402 Observability** *(exploratory)* — treating agent payment activity (HTTP 402 flows) as runtime evidence: which agents pay, what for, how often. ObserveAgents would observe payments, never process them.

## Suggested website copy

**Hero:**

> **See what your AI agents are actually doing.**
>
> Connect OpenTelemetry, discover agents from runtime evidence, detect risky behavior, and review what needs control — before it becomes a production problem.
>
> [Send your first trace] — one curl command, first agent in the dashboard in under a minute.

**Section — how it works:**

> **One evidence chain, start to finish.**
> Your agents already emit OpenTelemetry. ObserveAgents turns those traces into an agent inventory, explains which agents look risky and why, alerts when behavior crosses a threshold, and recommends which agents deserve a control path.
>
> Observe first. Control only what matters.

**Section — trust:**

> **Behavior, never content.**
> Prompts, responses, and tool arguments are scrubbed at ingestion and never stored. ObserveAgents sees what your agents did — not what your users said.

**Section — for builders:**

> **No proprietary SDK. No agent registration. No rewiring.**
> If it emits OpenTelemetry, it's discovered. Already using OpenLLMetry? You're two lines of code away.

## Suggested sales email copy

**Email 1 — cold, technical founder:**

> Subject: what did your agents do yesterday?
>
> Hi {name},
>
> Quick question about {company}'s AI agents: if one of them started calling an MCP server it shouldn't, or retrying a failing tool call 50 times an hour — would anyone notice?
>
> ObserveAgents answers that from your existing OpenTelemetry traces. Connect once, and we discover your agents from what they actually did at runtime: tools, MCP servers, databases, providers, errors. Risky patterns become findings and alerts; agents that cross a line get recommended for review — nothing is ever blocked automatically.
>
> If you're on OpenLLMetry it's two lines of code; otherwise it's an exporter endpoint. First agent shows up in minutes.
>
> Worth 20 minutes to see your own agents in it?
>
> {sender}

**Email 2 — warm follow-up after a demo or signup:**

> Subject: your first agent, in one command
>
> Hi {name},
>
> Fastest way to see ObserveAgents work is with your own traffic. Create an API key in the dashboard, then either:
>
> 1. point your existing OTel exporter at our endpoint, or
> 2. run the one-curl quick start from the README — a single hand-written span, and your first agent appears in Runtime with an execution timeline.
>
> From there, Asset Intelligence builds the inventory and Security Intelligence starts explaining anything risky. Nothing to install, nothing gets blocked, and we never store prompt or response content — structural metadata only.
>
> Happy to walk through your first findings together.
>
> {sender}
