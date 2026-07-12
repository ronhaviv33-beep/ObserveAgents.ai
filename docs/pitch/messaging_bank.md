# ObserveAgents — Messaging Bank

*Reusable copy for the website, decks, demos, and outreach. Companion to [observeagents_pitch.md](observeagents_pitch.md). Everything here respects the product's hard lines: observe-first, recommendation not enforcement, no content stored, no enterprise-fear language.*

---

## 10 one-liners

1. See what your AI agents are actually doing.
2. The runtime visibility and control recommendation layer for AI agents.
3. Your agents already emit the evidence. We turn it into understanding.
4. Agent inventory from runtime behavior — not from a spreadsheet.
5. Observe first. Control only what matters.
6. Runtime truth for AI agents.
7. Know your agents by what they did, not what they might do.
8. From OpenTelemetry traces to "this agent needs review" — one connection.
9. Detection rules for AI agents, built on what actually ran.
10. Every agent, every tool call, every risky pattern — visible.

## 10 short website hero options

1. **See what your AI agents are actually doing.** Connect OpenTelemetry, discover agents from runtime evidence, detect risky behavior, and review what needs control.
2. **Your agents are running. Can you see them?** ObserveAgents builds your agent inventory from runtime evidence — tools, MCP, providers, databases, findings.
3. **Runtime truth for AI agents.** One OTel connection. Every agent discovered, every risky pattern explained, every recommendation backed by evidence.
4. **From traces to trust.** ObserveAgents turns the OpenTelemetry your agents already emit into inventory, findings, alerts, and control recommendations.
5. **Know what your agents did yesterday.** Not what the code says. Not what the config promises. What actually ran.
6. **Observe first. Control only what matters.** Runtime visibility for AI agents, with control recommendations you decide on — never automatic enforcement.
7. **AI agents behave at runtime. So watch runtime.** Agent discovery, security intelligence, and detection rules — all from your existing OpenTelemetry.
8. **Every agent accounted for.** Who it is, who owns it, what it touches, and whether it needs a human look — derived from runtime evidence.
9. **The missing layer between your agents and your peace of mind.** Connect OTel once; see behavior, risk, and what to review next.
10. **Stop guessing what your agents do.** ObserveAgents discovers them from runtime evidence and tells you which ones deserve attention.

## 10 customer pain statements

1. "We're running agents in production and I genuinely can't tell you what tools they called yesterday."
2. "An agent retried the same failing tool call all weekend and nobody noticed until Monday."
3. "Someone added an MCP server to an agent months ago. It's a production dependency now. It's in no diagram."
4. "I found out one of our agents was using a provider nobody approved — by accident, in a log."
5. "Every agent question turns into 'go read the code' — and the code doesn't say what actually happened."
6. "We have traces somewhere, but nobody's going to read raw spans all day looking for agent problems."
7. "Three teams ship agents here. Nobody can name all of the agents, let alone their owners."
8. "Our APM shows the service is healthy. It has no idea an agent touched the database and an external API in one run."
9. "I can't tell the difference between an agent that's fine and one that's quietly drifting into trouble."
10. "When leadership asks 'are the agents OK?', my honest answer is 'I think so.'"

## 10 product benefit statements

1. Agents are discovered automatically from runtime evidence — if it sent a trace, it's in your inventory.
2. One place answers "who is this agent, who owns it, and what does it touch" — with evidence behind every field.
3. Risky behavior becomes a plain-English finding: what happened, why it matters, what to do next.
4. Detection rules watch so you don't have to — get a webhook alert when behavior crosses a line.
5. The Gateway Control Center gives you a short review queue, not another dashboard to babysit.
6. Every recommendation carries its evidence — the exact findings and spans that triggered it.
7. Prompts and responses are scrubbed at ingestion and never stored — visibility without your content.
8. No proprietary SDK, no agent registration — standard OpenTelemetry in, understanding out.
9. Healthy agents look visibly healthy — you can finally *show* that things are fine.
10. Nothing is ever blocked automatically — you add eyes to production, not risk.

## 10 demo narration lines

1. "We didn't register these agents. They appeared because they ran."
2. "This is what healthy looks like: one tool call, one model call, done."
3. "Same connection, same screens — the difference between these two agents is entirely in the evidence."
4. "Nobody read these traces manually. The platform derived every finding — and each one links back to the spans that caused it."
5. "Notice it scores this higher in production than it would in dev — the same behavior means different things in different places."
6. "You say it once — 'tell me when MCP calls cross the threshold' — and get on with your work."
7. "Rules observe and alert. Gateway can optionally enforce later."
8. "This list is deliberately short: only the agents that crossed a line. The healthy agent was never here."
9. "Here's why it was recommended — the trigger findings, verbatim, with the evidence attached."
10. "One OTel connection, and we went from raw traces to a specific recommendation — without blocking a single call."

## 10 "what we are not" statements

1. We are not an APM, and we don't replace yours — we explain agent behavior, not service latency.
2. We are not a SIEM — no log correlation, no threat feeds, no detection language borrowed from the SOC.
3. We are not an enforcement product by default — nothing is blocked unless you explicitly route traffic and explicitly configure controls.
4. We are not a prompt logger — prompts, responses, and tool arguments are scrubbed at ingestion and never stored.
5. We are not a code scanner — we don't read your repos; we read what your agents actually did.
6. We are not a proxy you must rewire everything through — observation works on standard OpenTelemetry, no rerouting required.
7. We are not an autonomous security system — every recommendation waits for a human decision.
8. We are not a generic observability dashboard — every screen answers an agent question, not a service question.
9. We are not a governance program in a box — we're the evidence layer a small team can actually run.
10. We are not going to exaggerate your risk to sell you software — findings say "worth a review," not "you've been breached."

## 10 investor-style punchlines

1. Every company shipping AI agents will need to answer "what did they actually do?" — we're the layer that answers it.
2. Agent behavior lives at runtime. Whoever owns the runtime evidence owns the understanding.
3. The telemetry standard already won — OpenTelemetry. We're the agent-understanding layer on top of it.
4. Code discovery tells you what might exist. Runtime tells you what's true. We sell the truth.
5. Observability found the traces; we found the agents inside them.
6. Every new MCP server is a new invisible dependency — and a new reason someone needs us.
7. The wedge is a curl command; the moat is the evidence chain from trace to recommendation.
8. We enter as visibility, expand into rules and alerts, and earn the right to recommend control.
9. Teams don't want another dashboard — they want a short list of agents worth reviewing. That list is the product.
10. Observe first, control only what matters — the adoption physics of observability with the expansion path of control.

## 10 technical buyer lines

1. Standard OTLP/HTTP in — JSON or protobuf — at one endpoint. No proprietary SDK anywhere in the path.
2. On OpenLLMetry? You're two lines of code from full GenAI traces landing in ObserveAgents.
3. We speak the GenAI semantic conventions natively — `gen_ai.*`, `tool.*`, `mcp.*`, `db.*` — plus graceful handling of everything else.
4. Content-bearing attributes are scrubbed at ingestion — only a SHA-256 hash and byte size survive. URLs keep scheme, host, and path; query strings never persist.
5. Agents are keyed by service identity from the traces themselves — no manual registration, no drift between inventory and reality.
6. Intelligence is derivation-only and idempotent: run it twice, get zero duplicate findings — recurring evidence increments a count on one row.
7. Detection rules evaluate during the intelligence run, never in the ingestion path — your trace throughput never pays for rule complexity.
8. Webhook alerts ship with per-finding cooldowns — a flapping agent produces one alert per hour, not one per span.
9. The Gateway is opt-in and OpenAI/Anthropic-compatible — one `base_url` change when (and only when) you decide an agent needs it.
10. Findings carry identifiers and counts, never content — you can adopt this without a data-privacy review of your prompts, because we never have them.
