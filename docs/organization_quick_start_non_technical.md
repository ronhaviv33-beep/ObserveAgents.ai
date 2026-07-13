# Getting Started with Observe

*A simple rollout guide for teams that want to understand their AI systems before adding controls.*

This guide is for business stakeholders, product leaders, security leaders, and managers. It explains what happens during a rollout — who does what, what you will see, and what comes next. No technical knowledge needed. (Implementers: the [technical implementation guide](organization_implementation_guide.md) has the exact setup steps.)

---

## 1. What Observe does

Observe helps teams see what AI exists, what is actually running, what it connects to, and where it needs attention.

In practice, Observe shows your organization:

- **Which AI systems exist** — including ones nobody registered anywhere
- **Which AI systems are actually running** — not just which ones are supposed to exist
- **What each system connects to** — the models, tools, databases, and outside services it touches
- **Which systems have risky behavior** — like direct database access or broad tool access
- **Which systems are slow, heavy, or potentially expensive**
- **Which guardrails would be triggered** — in observe-only mode, before anything is enforced

One important idea to hold onto:

> **Observe does not need to block anything on day one. It first helps you understand what is happening.**

Nothing about how your AI systems behave changes when you connect them. Observe watches, explains, and recommends.

---

## 2. Who should be involved

A rollout works best with a small group and clear roles:

### Admin / platform owner
Creates user accounts, manages who can see what, creates access keys, and configures settings. Usually one person.

### Platform or engineering team
Connects the first AI system to Observe. This is the only technical part of the rollout, and it is small — usually under an hour for the first system.

### Security team
Reviews risky behavior once data flows: findings, sensitive access, and guardrail signals.

### Product or business owner
Uses Observe to understand which AI systems exist and how they are being used.

### Leadership / viewer
Gets a read-only picture of AI activity, risk, and usage — no setup, no actions required.

---

## 3. Start with one AI system

**Do not try to connect the whole organization on day one.**

Pick one real AI system your team knows well — for example a support agent, a finance analysis agent, an engineering copilot, an onboarding bot, or a research assistant.

The goal of the first connection is simple:

- Prove that data is flowing
- See the system appear in **Runtime**
- See it appear in **Asset Intelligence**
- Understand its models, tools, dependencies, and first findings

Once one system is visible and understood, connecting the next ones is repetition, not a new project.

---

## 4. How data gets into Observe

There are two ways data flows in. Your technical team picks whichever fits — the choice does not change what you see.

### OpenTelemetry

If your organization already uses observability tools (many engineering teams do), your technical team can send AI activity to Observe through OpenTelemetry — an industry standard they will recognize.

This lets Observe show runtime traces, execution timelines, slow steps, errors, and the models, tools, and dependencies each system uses.

### Gateway

If your AI systems call common AI providers (like OpenAI or Anthropic), your team can route those calls through the Observe gateway — a small configuration change on their side.

This helps Observe see which AI systems are making requests, which providers and models they use, token and usage signals, cost signals, and advisory guardrail signals.

**Either way, the technical setup guide covers the exact steps.** From your perspective as a stakeholder, the outcome is the same: your AI systems start appearing in Observe.

---

## 5. What you will see after the first connection

### Runtime
Shows whether the AI system is actually running, when it ran, and where its time was spent. Each run appears as a trace you can click into.

### Execution Timeline
Shows the steps inside a single request — for example: planning, retrieval, tool calls, database calls, and the final response — each with how long it took. This is how you spot the slow or surprising parts.

### Asset Intelligence
Shows one card per AI system: its models, providers, tools, dependencies, capabilities, findings, and when it was last seen. This becomes your organization's AI inventory.

### Security Intelligence
Shows risky observed behavior per system — things like database access, MCP tools, external API calls, broad tool access, runtime errors, and high-severity findings. It answers: *which AI systems need a security conversation?*

### Cost Intelligence
Shows usage and efficiency signals — slow traces, heavy workflows, which models are used, repeated tool calls, and possible cost hotspots. These are signals based on observed behavior, not an invoice.

### Guardrails
Guardrails start in **observe-only mode**. That means Observe **detects, explains, and recommends — it does not block production AI systems.** You see which recommended guardrails would be triggered by real behavior, and what to do about it, without any risk to production.

---

## 6. What the first week should look like

**Day 1**
- Admin creates the workspace and adds the first users
- The group chooses the first AI system
- The technical team connects it

**Day 2–3**
- Confirm activity appears in Runtime
- Check the system's card in Asset Intelligence
- Review the first capabilities and findings together

**Day 4–5**
- Security team reviews Security Intelligence
- Product/business owner reviews Cost Intelligence
- Review Guardrails in observe-only mode
- Decide which systems to connect next

**End of week**
- The first AI system is fully visible
- The team understands what it connects to
- Findings are triaged (fixed, planned, or accepted)
- Guardrails have been reviewed
- A rollout plan exists for more systems

---

## 7. Weekly operating rhythm

Once systems are connected, a short weekly review keeps the picture current. Recommended checklist:

- Which AI systems were active this week?
- Did any **new** systems appear that nobody expected?
- Which findings are open, and who owns them?
- Which systems connect to sensitive tools or databases?
- Which traces are slow or heavy?
- Which guardrails were triggered in observe-only mode?
- Which systems should be connected next?

Fifteen minutes with the right people in the room is usually enough.

---

## 8. When to use enforcement

**Enforcement is optional. Many organizations stay in observe-only mode for a long time — and get full value.**

If and when you want more, there is a deliberate progression, applied one team at a time:

### Observe-only
Detect and recommend. Nothing is blocked. This is where everyone starts.

### Alert
Notify the right people when something needs attention. Still nothing is blocked.

### Enforce
Block or require action — only when the organization intentionally enables it, for a specific team, after reviewing what enforcement *would have* blocked.

> **Do not start with enforcement. Start by understanding what is happening.**

This is what makes Observe safe to adopt: nothing about your production AI changes until you decide it should.

---

## 9. What success looks like

By the end of the first rollout stage, your organization should have:

- At least one AI system connected
- Runtime traces visible
- The Execution Timeline working
- Asset Intelligence showing the system's card
- Capabilities detected
- Findings generated and triaged
- Security and Cost Intelligence populated
- Guardrails reviewed in observe-only mode
- A clear plan to connect more systems

At that point you can answer, with evidence, the questions this started with: what AI exists, what is actually running, what it connects to, and where it needs attention.

---

## 10. For technical teams

If you are responsible for implementation, start with the **[onboarding self-lab guide](otel_customer_onboarding_guide.md)** (bilingual), then use the **[technical implementation guide](organization_implementation_guide.md)** for the exact OpenTelemetry, gateway, access key, and instrumentation instructions. This document intentionally leaves those details out.
