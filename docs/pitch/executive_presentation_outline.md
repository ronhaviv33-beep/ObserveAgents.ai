# ObserveAgents — Executive Presentation Outline

*A 10-slide deck for early customers, AI startups, and engineering/product leaders. Companion to [observeagents_pitch.md](observeagents_pitch.md); demo narrative in [demo_story.md](demo_story.md).*

**Deck-wide rules:**

- Plain English. No enterprise-governance vocabulary, no fear.
- Every claim traceable to the current implementation; roadmap items are always labeled "roadmap."
- The two governing lines may appear more than once — that's deliberate:
  - *Observe first. Control only what matters.*
  - *Observe can recommend. Gateway can enforce only when explicitly configured.*

---

## Slide 1 — Title

**Main message:** See what your AI agents are actually doing.

**Bullets:**
- ObserveAgents — the runtime visibility and control recommendation layer for AI agents
- Connect OpenTelemetry → discover agents → detect risky behavior → review what needs control
- Observe first. Control only what matters.

**Speaker notes:**
Open with the core line and stop. Don't define categories, don't say "platform" more than once. One sentence of context: "Teams are shipping AI agents into real workflows, and most of them can't see what those agents actually do. That's the whole product." Then move.

**Suggested visual:** Product wordmark over a dimmed screenshot of the Runtime execution waterfall — real product, real trace, no stock imagery.

**What to avoid saying:** "Revolutionary," "enterprise AI governance platform," any category comparison this early. Don't mention the Gateway yet — enforcement talk on slide 1 sets the wrong frame.

---

## Slide 2 — The problem: AI agents are running, but teams cannot see what they do

**Main message:** Agents decide their behavior at runtime — and that's exactly where most teams have no visibility.

**Bullets:**
- Agents choose tools, call MCP servers, retry, and switch providers at runtime — code review can't predict it
- Simple questions go unanswered: which agents ran this week? what did they touch? who owns them?
- Failures are quiet: repeated tool errors, unapproved providers, unowned agents accumulating in production
- Cheap to catch early. Expensive to discover late.

**Speaker notes:**
Make this feel familiar, not frightening. Best move: ask the room — "Who here could tell me, right now, every tool your agents called yesterday?" Pause. The silence is the slide. Emphasize that these are ordinary engineering questions, not exotic security ones; agents just moved the answers from code into runtime.

**Suggested visual:** A short list of the unanswerable questions ("Which agents are running?" "What did they touch?" "Who owns this one?") each followed by a dimmed "¯\\_(ツ)_/¯" or empty answer field. Simple, a little wry.

**What to avoid saying:** Breach scenarios, "attack surface," rogue-AI framing, any statistic you can't source. The problem is *unknowns*, not catastrophe.

---

## Slide 3 — Why current tools are not enough

**Main message:** Existing tools each see a slice — none explain agent behavior.

**Bullets:**
- Generic APM: shows services and traces, not agents and risk
- Code/config discovery: shows what *might* exist, not what *actually ran*
- CloudWatch and cloud-native telemetry: great for AWS metrics, no agent inventory or findings
- Gateway/proxy-only tools: see only the traffic you rewire through them first

**Speaker notes:**
Be respectful — these tools are good at their jobs, and your audience uses them. The point is a gap, not a failure: "Your APM will tell you a span was slow. It won't tell you an agent touched a database and an external API in the same run and nobody owns it." Land the contrast line: runtime truth first, configured discovery second.

**Suggested visual:** Four quadrants (APM / code discovery / cloud telemetry / proxy-only), each with one line of what it sees — and a gap in the middle labeled "what did the agent actually do?"

**What to avoid saying:** "APM replacement," "SIEM replacement," or anything dismissive of tools the audience already runs. You complement; you don't replace.

---

## Slide 4 — ObserveAgents: runtime visibility for AI agents

**Main message:** Agents are discovered from what they actually did — not from assumptions.

**Bullets:**
- Connect your existing OpenTelemetry — no proprietary SDK, no agent registration
- Agents discovered from runtime evidence: identity, tools, MCP, databases, providers, errors
- Risky behavior becomes findings and alerts; agents that cross a line get recommended for review
- Privacy by construction: prompts and responses are scrubbed at ingestion and never stored

**Speaker notes:**
This is the "what is it" slide — keep it to the promise, not the feature list (that's slide 6). Stress the two builder-friendly facts: standard OpenTelemetry in (OpenLLMetry = two lines of code), and content never stored (hash + byte size only). Close with: "It starts from runtime evidence, not assumptions. If an agent ran, we saw it."

**Suggested visual:** One clean line: OTel logo → ObserveAgents → three outputs (Inventory / Findings / Recommendations). A small lock icon on the ingestion arrow labeled "content scrubbed, never stored."

**What to avoid saying:** "Automatic enforcement," "runtime protection," "we monitor everything." Also don't promise integrations beyond OTel/OTLP and OpenLLMetry — ecosystem connectors are roadmap.

---

## Slide 5 — How it works: OTel → Runtime Evidence → Control Recommendations

**Main message:** One evidence chain — every screen in the product is a step in it.

**Bullets:**
- OpenTelemetry / OTLP → Runtime Evidence → Agent Discovery
- → Asset Intelligence → Security Intelligence → Detection Rules & Alerts
- → Gateway Control Recommendations
- Every finding traces back to the spans that caused it — a number without evidence doesn't ship

**Speaker notes:**
Walk the chain left to right in under a minute: "Traces come in and are scrubbed. Agents are discovered from them. The inventory says who each agent is; Security Intelligence says which ones look risky and why; rules turn patterns into alerts; and the far end is a recommendation — an agent worth reviewing, with its evidence attached." Then the governing line: recommendation, not enforcement. Enforcement exists only when traffic is explicitly routed and explicitly configured.

**Suggested visual:** The pipeline as a single horizontal flow with seven nodes, the last node ("Gateway Control Recommendations") visually distinct — outlined, not filled — to signal "recommendation, not action."

**What to avoid saying:** "The gateway then blocks it." Never let the pipeline imply automation at the end. Also avoid database/schema internals — nobody needs table names in an exec deck.

---

## Slide 6 — Product surfaces: Overview, Asset Intelligence, Security Intelligence, Rules, Gateway Control

**Main message:** Five surfaces, one question each.

**Bullets:**
- **Overview** — is my AI estate healthy? (agents, findings, missing owners, control candidates)
- **Asset Intelligence** — who is this agent, who owns it, what does it touch?
- **Security Intelligence** — which agents are risky and why?
- **Rules & Alerts** — tell me when behavior crosses a line (webhook alerts, observe-only)
- **Gateway Control Center** — which agents need review, and what evidence put them there?

**Speaker notes:**
One sentence per surface, no more — the demo (next slide) makes them real. Useful framing: "Each page answers exactly one question a team actually asks." On Rules, name the three built-in rules (MCP calls over threshold, repeated tool errors, unknown provider in production) and say plainly that more templates are designed but not shipped. On Gateway Control: "It's a review queue, not another dashboard — and a recommendation renders as a review card, never a toggle."

**Suggested visual:** Five small product screenshots in a row, each captioned with its one question. Real screenshots — the ui2 dark console looks credible.

**What to avoid saying:** Don't oversell the rule catalog — three rules are live today. Don't call Security Intelligence a "security product." Don't demo from this slide; keep it moving.

---

## Slide 7 — Example workflow: two agents, one connection

**Main message:** One OTel connection takes you from raw traces to a specific, evidence-backed recommendation.

**Bullets:**
- **support-agent**: ticket lookup → LLM call → answer. Discovered automatically; clean timeline; no significant findings
- **risky-research-agent**: repeated MCP calls, unknown provider, repeated tool errors against an external API
- Detection rules match → alerts fire → Gateway Control Center recommends review, evidence attached
- Nothing was blocked. A human decides — with the facts in front of them.

**Speaker notes:**
This is the demo story ([demo_story.md](demo_story.md)) compressed. The contrast is the point: the healthy agent proves visibility isn't noise — "fine" looks visibly fine; the risky agent proves the chain works end to end. If demoing live, follow the narrative doc; if not, walk the four bullets as a story. End on the last bullet — it's the trust-builder.

**Suggested visual:** Split screen: support-agent's clean execution waterfall on the left, risky-research-agent's finding list + Gateway Control review card on the right.

**What to avoid saying:** Don't invent dramatic consequences ("this would have leaked customer data"). The risky agent is *worth reviewing* — that's the honest and sufficient claim.

---

## Slide 8 — Differentiation

**Main message:** Runtime truth first. Configured discovery second. Correlation is the product.

**Bullets:**
- Generic APM shows services and traces → we explain agent behavior and risk
- Code/config discovery shows what might exist → we show what actually ran
- CloudWatch covers AWS telemetry → we add agent inventory, findings, rules, recommendations
- Gateway-only tools see only rerouted traffic → we observe first, recommend control only where needed

**Speaker notes:**
Same four contrasts as slide 3, but now the audience has seen the product, so state them as positioning rather than gaps. The headline is the differentiator to leave in the room: other tools may discover AI from code, configs, and connected systems; ObserveAgents shows what agents actually *did*. Mention (as roadmap) that configured discovery is coming — as the second source, correlated against runtime truth.

**Suggested visual:** A 2×2: rows "sees runtime behavior" / "understands agents"; competitors each check one box, ObserveAgents checks both. Keep it honest — give competitors their checkmarks.

**What to avoid saying:** "We replace X." "We're the only ones who can do this." Don't name specific competitor companies — categories are enough and age better.

---

## Slide 9 — Roadmap

**Main message:** The spine is shipped; everything ahead extends it — and nothing changes the observe-first posture.

**Bullets:**
- **Shipped:** OTel ingestion (JSON + protobuf), agent discovery, Asset & Security Intelligence, built-in detection rules + webhook alerts, Gateway Control Center
- **Next:** configurable rule builder, Slack alerts, ecosystem discovery (Configured AI vs Runtime AI)
- **Ahead:** Observe Advisor (what should this agent learn next), Observe MCP server
- **Exploratory:** Agent Passport, Runtime Trust Score, Action Ledger, x402 payment observability

**Speaker notes:**
Lead with the shipped column — it's substantial and it's proof. For the future rows, one sentence each, always tagged as roadmap: "Configured AI vs Runtime AI" means correlating what's in your repos and configs against what actually runs; Observe Advisor turns findings into what-to-improve-next recommendations; the exploratory items are directions, not commitments. If asked about payments: we would observe payment behavior as runtime evidence — we will never process payments.

**Suggested visual:** Three-lane horizontal timeline (Shipped / Next / Exploring), shipped lane visibly fullest.

**What to avoid saying:** Dates. Any roadmap item phrased in present tense. "Complete governance," "autonomous," or any suggestion the future includes automatic blocking by default.

---

## Slide 10 — Ask / next step

**Main message:** Connect a trace. See your first agent in minutes.

**Bullets:**
- One curl command proves the pipeline — no SDK, no code change, no commitment
- Already on OpenTelemetry? Point your exporter at us. On OpenLLMetry? Two lines of code
- Design partners: we'll onboard your real agents with you and shape the rule catalog together
- Nothing gets blocked. Ever. You're adding eyes, not risk.

**Speaker notes:**
Make the ask ridiculously small — the whole close is "the cost of finding out is one trace." For design-partner conversations, be specific about what you want (real agent traffic, feedback on findings and rules) and what they get (early influence, direct access). End on the last bullet: adopting ObserveAgents cannot break production, because observation is passive and enforcement is opt-in twice over.

**Suggested visual:** The actual quick-start curl command, large, with a screenshot of the resulting agent appearing in Runtime next to it. The command *is* the call to action.

**What to avoid saying:** Pricing improvisation, enterprise procurement language ("POC," "vendor evaluation"), pressure tactics. Don't end on a feature — end on the action.
