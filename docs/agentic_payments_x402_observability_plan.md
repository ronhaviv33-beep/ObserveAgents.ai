# Agentic Payments / x402 Observability Plan

*Future / exploratory — docs only. Nothing here is implemented: no payment processing, no wallet integration, no Cloudflare integration, no backend, no frontend, no migrations, no endpoints, no enforcement. This is a roadmap plan for observing payment-enabled AI-agent behavior if and when customers have that telemetry.*

**Positioning:** Cloudflare's Monetization Gateway (and the broader x402 / HTTP 402 pattern) enables **paid agent requests**. ObserveAgents gives teams **runtime visibility, payment-risk detection, and control recommendations** for those paid requests. ObserveAgents is **not** a payment processor, does **not** verify payments, and does **not** replace Cloudflare, Stripe, wallets, gateways, or billing systems.

> **Observe first. Control only what matters.**
>
> **Rules observe and alert. Gateway can optionally enforce later.**
>
> **Observe can recommend. Gateway can enforce only when explicitly configured.**

---

## Executive summary

As AI agents begin to access paid resources programmatically, teams will need to understand:

- which agents are paying
- what they paid for
- which domains / tools / APIs were paid
- how often payment challenges occurred
- whether payment behavior is expected
- whether payment activity is risky or anomalous
- whether the agent should require review or control

ObserveAgents should treat **payment activity as runtime evidence** — the same way it already treats tool calls, MCP usage, database access, and provider selection. A paid request is just another observable runtime behavior, carrying its own risk, spend, and ownership questions.

**This is a future roadmap item, not a current implementation.** The pattern is emerging; most early customers will not yet emit enough payment telemetry to justify building on it now.

---

## Background — the x402 / HTTP 402 pattern

The generic agentic-payment flow:

1. **Agent requests a resource.**
2. **Gateway returns `HTTP 402 Payment Required`** with payment details (price, currency, accepted assets, a challenge/request id).
3. **Agent wallet authorizes payment.**
4. **Agent retries with payment proof.**
5. **Gateway verifies payment.**
6. **Resource / origin receives a verified paid request.**

**Cloudflare Monetization Gateway** is one example of this pattern — a gateway that returns 402 challenges and verifies agent payments before letting the request reach the origin. The pattern itself is generic (any 402-based paywall / metering layer fits), and this plan stays gateway-agnostic; Cloudflare is named only as the concrete driving example.

---

## Why this matters for ObserveAgents

Payment-enabled agents introduce new runtime questions that map directly onto the questions ObserveAgents already answers:

- Did the agent pay?
- Why did it pay?
- How much did it spend?
- Did it pay an approved vendor?
- Did it repeatedly hit 402 challenges?
- Did it pay *after* reading internal data?
- Did it enter a payment loop?
- Did a no-owner agent perform paid activity?
- Did payment activity happen in production?

Each of these extends an existing ObserveAgents capability rather than inventing a new product area:

- **Runtime Evidence** — 402 responses and paid retries are already HTTP spans; they just carry payment attributes.
- **Asset Intelligence** — a per-agent paid-resource surface joins the existing capability/dependency surface.
- **Security Intelligence** — payment risk becomes another investigation bucket.
- **Detection Rules** — payment thresholds are the same threshold-over-evidence shape as `rule_mcp_tool_access_threshold`.
- **Gateway Control Center** — "review paid requests" / "allowlist paid vendors" are the same observe-to-control recommendation model.

---

## Future telemetry model

Safe, payment-related runtime evidence. These are **proposed / custom attributes** unless and until an open standard (OTel semconv or an x402 convention) defines them; ObserveAgents would consume whatever safe attributes a gateway or SDK emits.

Potential attributes:

- `http.response.status_code = 402`
- `http.request.method`
- `server.address` / `url.domain`
- `gen_ai.agent.name`
- `service.name`
- `deployment.environment`
- `payment.required`
- `payment.amount`
- `payment.currency`
- `payment.asset`
- `payment.provider`
- `payment.status`
- `payment.proof_present` (boolean — presence only, never the proof)
- `payment.gateway`
- `payment.challenge_id`
- `payment.request_id`

**Never stored** (structurally excluded, exactly as content is today):

- wallet private keys
- payment secrets
- authorization headers
- payment proof bodies
- raw request / response bodies
- full URLs with query strings
- credentials
- prompts / responses / tool arguments / tool results

The evaluator would read only the already-scrubbed store, so forbidden items are unavailable to it by construction — the same guarantee that holds for detection rules and runtime security intelligence today.

---

## Future findings

Possible findings, all derivation-only and observe-only, with `source=payment_observability`:

| Finding type | Category |
|---|---|
| `agent_payment_402_challenge_seen` | operations |
| `agent_paid_external_resource` | cost |
| `agent_payment_verified` | operations |
| `agent_payment_failed` | operations |
| `agent_repeated_payment_failures` | operations |
| `agent_payment_to_unapproved_domain` | security |
| `agent_payment_spike_detected` | cost |
| `agent_high_paid_request_volume` | cost |
| `agent_paid_for_flagged_resource` | security |
| `agent_payment_enabled_without_owner` | governance |
| `agent_paid_after_internal_data_access` | security |

Categories reuse the existing finding taxonomy: **security · operations · cost · governance**. Cost-category findings are **spend signals**, not billing-grade accounting — the same posture as today's `high_token_usage_threshold`.

---

## Future detection rules

Possible rules, in the same built-in → configurable shape as the shipped detection rules. Each observes and alerts; none enforces.

### `payment_402_challenge_threshold`

- **Trigger:** an agent receives more than N `HTTP 402` responses in a time window.
- **Example:** *Agent received 20 payment challenges in 10 minutes.*
- **Recommended action:** check whether the agent is repeatedly attempting paid resources or stuck in a payment loop.

### `paid_request_spend_threshold`

- **Trigger:** an agent exceeds a configured payment-amount threshold in a window.
- **Example:** *Agent spent more than $10 in one hour.*
- **Note:** a **spend signal**, not billing-grade accounting — amounts are observed from safe attributes, not reconciled against an invoice.

### `unapproved_paid_vendor`

- **Trigger:** an agent pays (or attempts to pay) a domain / vendor not on a customer-configured approved list.

### `paid_after_internal_data_access`

- **Trigger:** the same trace includes internal DB / API access followed by a paid external request (a data-egress-shaped pattern with money attached).

### `payment_failure_spike`

- **Trigger:** an agent has repeated failed payment attempts in a window.

### `payment_enabled_agent_missing_owner`

- **Trigger:** an agent with observed payment activity has no owner / team metadata.

---

## Product surfaces

Where payment observability would appear later — extending existing pages, not adding a new product area:

### Asset Intelligence

A per-agent paid-resource summary alongside the existing evidence:

- paid domains / APIs / tools
- 402 challenge count
- verified paid request count
- payment failures
- last payment observed
- owner / team

### Security Intelligence

A new **Payment & Monetization Risk** investigation bucket (grouping the payment findings above), consistent with the existing bucket model.

### Rules & Alerts

Payment-related rule templates added to the catalog (built-in once telemetry is common; `planned` until then).

### Gateway Control Center

Recommend controls for payment-enabled agents:

- require review before paid requests
- allowlist paid vendors
- set spend thresholds
- route payment-enabled agents through Gateway
- require owner / team for payment-enabled agents
- alert on payment spikes

**Enforcement only if explicitly configured and traffic is routed through Gateway.** A recommendation is a review card, never an automatic spending limit or block.

---

## Relationship to Cloudflare / x402

- Cloudflare Monetization Gateway **enables** agentic payments.
- ObserveAgents **does not process payments.**
- ObserveAgents **observes payment-related runtime evidence** and helps teams understand risk, spend behavior, and control recommendations.

Put another way:

- **Cloudflare can verify paid requests.**
- **ObserveAgents can explain which agents paid, what they paid for, how often, and whether the behavior should be reviewed.**

The two are complementary layers: Cloudflare (or any 402 gateway) is the payment mechanism; ObserveAgents is the runtime intelligence and control-recommendation layer over the evidence that mechanism produces.

---

## Privacy and safety boundaries

**Allowed:**

- agent name · service name · environment
- status code `402` · payment status
- amount / currency (if safely emitted as attributes)
- vendor / domain · gateway name
- counts · span ids · trace ids · timestamps
- sanitized resource identifiers (scheme + host + path)

**Forbidden:**

- wallet secrets · private keys · credentials
- authorization headers · full payment proofs
- raw request / response bodies
- prompts · responses · tool arguments · tool results
- full URLs with query strings

These mirror the boundaries already enforced by `app/otel_privacy.py` at ingestion and restated across the detection-rules and runtime-security designs.

---

## Non-goals

Do not build or claim:

- payment processing
- wallet management
- payment verification
- billing-grade accounting
- a Cloudflare replacement
- a Stripe replacement
- automatic blocking
- automatic spending limits
- automatic enforcement
- a financial compliance system

---

## Roadmap

| Phase | Deliverable |
|---|---|
| **P0** | Research and docs (this plan) |
| **P1** | Define payment telemetry attributes (custom until standardized) |
| **P2** | Detect `HTTP 402` payment challenges from runtime spans |
| **P3** | Detect verified / failed paid requests when safe attributes exist |
| **P4** | Add payment findings to Asset / Security Intelligence |
| **P5** | Add payment-related Detection Rules |
| **P6** | Add Gateway Control recommendations for payment-enabled agents |
| **P7** | Optional Cloudflare / x402 integration guide |
| **P8** | Optional dashboard cards for Agent Spend & Payment Intelligence |

---

## Recommended current status

**Future / exploratory.**

The pattern is emerging, but most early customers will not yet have enough x402 / payment telemetry to build on. Keep ObserveAgents focused now on what customers can use today:

- OTel runtime discovery
- Asset Intelligence
- Security Intelligence
- Detection Rules
- Rules & Alerts
- Webhook notifications
- Gateway Control recommendations

Revisit when payment-enabled agents and their telemetry become common enough that P2 (detecting 402 challenges) would light up on real customer data.
