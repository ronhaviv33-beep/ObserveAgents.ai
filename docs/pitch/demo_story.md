# ObserveAgents — Demo Story

*A simple two-agent demo narrative. Companion to [observeagents_pitch.md](observeagents_pitch.md) and slide 7 of [executive_presentation_outline.md](executive_presentation_outline.md).*

## The arc

The demo proves one sentence:

> **Connect OTel once → agents are discovered → runtime behavior is visible → risky patterns are detected → a rule match appears → Gateway Control Center recommends review.**

Two agents carry the story. One is healthy and stays healthy — it shows that visibility isn't noise. One misbehaves in ordinary, realistic ways — it shows the evidence chain working end to end. Nothing is blocked at any point; the demo ends on a *recommendation*, and that's the point.

Timing: 8–10 minutes live, or a 3-minute compressed walkthrough using just Acts 1, 3, and 5.

---

## The cast

### support-agent — the healthy baseline

A customer-support agent doing exactly what it should:

1. A customer question arrives.
2. The agent looks up the ticket/customer record (CRM or ticketing tool call).
3. One LLM call composes the answer.
4. The response goes back.

What the platform shows:

- **Discovered from OTel automatically** — it appeared in the inventory because it sent traces, not because anyone registered it.
- A clean, readable execution timeline: tool call → LLM call → done.
- Known provider, known model, an assigned owner, a small tool surface.
- **No major risk.** Maybe zero findings, maybe one low-severity note — nothing demanding attention.

### risky-research-agent — the contrast

A research agent that has drifted into patterns worth a human look:

- **Repeated MCP calls** — hammering an MCP tool well past the rule threshold.
- **Unknown provider** — making LLM calls through a provider that isn't in the known catalog, in production.
- **Repeated tool errors** — the same tool failing again and again, with the agent retrying on its own judgment.
- **External API call** — reaching a third-party API outside the expected dependency set.

What the platform shows:

- Security Intelligence findings across several buckets (MCP/tool risk, unknown provider, repeated tool errors, external API access).
- **Detection rule matches** — MCP tool-access over threshold, repeated tool errors, unknown provider in production — surfaced on Rules & Alerts and deliverable to a webhook.
- **Gateway Control Candidate** status, with the trigger findings attached verbatim and suggested controls listed.

---

## The demo, act by act

### Act 1 — Connect OTel once

Start on an empty (or fresh) org. Show the integration surface: one OTLP endpoint, standard OpenTelemetry, no SDK.

> "Both of these agents are instrumented with plain OpenTelemetry — the same traces they'd send anywhere. We didn't register them, describe them, or tell the platform they exist."

Send the traffic (live traffic, or the seeded demo data — the seed runs through the real ingestion pipeline, so it's the same code path either way).

**Beat to land:** the integration is the whole setup. There is no step two.

### Act 2 — Agents are discovered

Open **Overview**, then **Asset Intelligence**.

> "Two agents appeared: support-agent and risky-research-agent. Discovered from runtime evidence — service name, environment, providers, models, tools, dependencies — all read from the traces themselves."

Click into **support-agent** first: identity, owner, capabilities, dependencies. Everything known, everything quiet.

**Beat to land:** the inventory wasn't written by a person. It was derived from behavior.

### Act 3 — Runtime behavior is visible

Open **Runtime** and show support-agent's session: the execution waterfall — ticket lookup, LLM call, response, timing on each step.

> "This is what healthy looks like: one tool call, one model call, done. Being able to *show* that an agent is fine is half the product."

Now switch the filter to **risky-research-agent**. The waterfall tells a different story: bursts of MCP calls, tool steps ending in errors, a call out to an external API.

**Beat to land:** same connection, same screens — the difference between the agents is entirely in the evidence.

### Act 4 — Risky patterns are detected

Open **Security Intelligence**.

> "Nobody read those traces manually. The platform derived findings from them — and every finding links back to the spans that caused it."

Walk risky-research-agent's findings, worst first: MCP usage in production, unknown provider, repeated tool errors, external API access. Note the environment awareness — the same behavior scores higher in production than it would in dev.

**Beat to land:** findings are explanations, not alarms. Each one says what happened, why it matters, and what to do next.

### Act 5 — A rule match appears

Open **Rules & Alerts**.

> "Findings explain; rules watch. You say once — 'tell me when MCP calls cross the threshold' — and get on with your work."

Show the built-in rules and the recent-matches feed: risky-research-agent has matched **MCP tool-access over threshold**, **repeated tool errors**, and **unknown provider in production**. Mention the webhook: matches deliver to your channel with a per-finding cooldown, so a noisy agent never becomes a noisy inbox.

> "Rules observe and alert. Gateway can optionally enforce later."

**Beat to land:** observe-only. No rule blocks anything.

### Act 6 — Gateway Control Center recommends review

Open the **Gateway Control Center** — either directly, or via the one-click "Review in Gateway Control Center →" link on the agent itself.

> "This is deliberately a short list — only the agents that crossed a line. support-agent isn't here, and never was."

Show risky-research-agent's review card:

- **Why it was recommended** — the trigger findings, verbatim from Observe.
- **What evidence fired** — the rule matches and high-severity findings, each traceable to spans.
- **What controls might help** — suggested controls typed `soft` (available now), `routing` (route through Gateway), or `hard` (requires Gateway routing).
- **What happens next** — a human reviews. Enforcement would require explicitly routing this agent's traffic through the Gateway and explicitly configuring controls.

Close:

> "One OTel connection. The platform walked from raw traces to a specific, evidence-backed recommendation — and blocked nothing along the way. Observe first. Control only what matters."

---

## Presenter notes

- **Always show support-agent first.** The healthy baseline is what makes the risky agent legible — and it preempts "won't this just drown us in alerts?"
- **Say the recommendation line out loud, twice.** *Observe can recommend. Gateway can enforce only when explicitly configured.* Once in Act 5, once in Act 6. It is the most trust-building sentence in the demo.
- **If asked about prompt content:** we never see it. Prompts, responses, and tool arguments are scrubbed at ingestion and never stored — only a hash and byte size survive. The whole demo ran on structural metadata.
- **If asked "can it block the risky agent?":** yes — but only if you route that agent's traffic through the Gateway and set its team to enforce. Both steps are explicit and yours. Nothing in the demo did that.
- **Don't dramatize.** The risky agent isn't compromised or malicious — it's *unreviewed*. "Worth a human look" is the honest claim and the credible one.
- **Seeded vs. live:** the demo seed pushes synthetic systems through the real ingestion pipeline, so the seeded demo is the actual product exercising the actual code path — say so if asked.
