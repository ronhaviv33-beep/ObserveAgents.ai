# Reasoning Observability Plan

## Executive summary

The reasoning/planning stage is where an agent chooses between paths — and where deviation begins. By the time a risky tool call is visible in a trace, the mistake has already happened; the *why* lives in the reasoning that preceded it.

ObserveAgents will observe agent reasoning **rigorously in structure, never in content**. Raw chain-of-thought is the most sensitive text an agent produces (it routinely quotes user data verbatim); storing it would turn the platform into its own worst exposure and break the core privacy invariant that anchors the security pitch. It is also fragile as a strategy: providers increasingly do not expose raw reasoning at all (OpenAI o-series hides it; Anthropic extended thinking is partial).

Core line:

> **Track how the agent thinks — never what it thinks.**

## Product rule

This extends the platform's existing rule pair:

1. **Raw content is never stored** (architecture invariant #2) — reasoning text, plans, and self-questions included, by default and by construction.
2. **Confidence is internal. Evidence is customer-facing.** — reasoning insight ships as structural signals and verdicts, never as "the agent seemed confused/uncertain" language.

Reasoning observability therefore has exactly three allowed output shapes: **structural metrics** (counts, ratios, sequences), **verdicts** (classifications with hash + size, no text), and — far later, behind an explicit customer decision — **time-boxed forensic capture**.

## Layer 1 — Structural reasoning signals (near-term)

The evidence already exists in the store today; this layer is derivation-only — no new ingestion, no schema change.

| Signal | Source (already stored) |
|---|---|
| Reasoning-token volume and spikes per call | `OtelSpan.gen_ai_reasoning_output_tokens` (extracted tiered in `app/genai_semconv.py`; aggregated in `/runtime/genai-usage`) |
| Reasoning-to-output token ratio | same, with `gen_ai_output_tokens` |
| Plan-step counts and loops (the same plan step revisited repeatedly = thrashing) | `plan_step` / `agent_step` ProvenanceEvents (`app/otel_normalizer.py` maps op `plan` → `plan_step`) |
| Plan → action sequences; considered-vs-called tools where instrumentation emits candidates | step classification (`classify_step` in `app/genai_semconv.py`) |
| Self-correction patterns (tool → error → different tool), retries | span status + sequence, already persisted |
| Deviation from the agent's own historical step-sequence fingerprint | behavioral-similarity direction (see Related tracks) |

**Candidate findings** (derivation-only, severities low/medium, evidence = counts and ratios only):

- `reasoning_spike_before_sensitive_action` — reasoning tokens far above the agent's own baseline immediately before a database / MCP / external-API call.
- `plan_loop_detected` — the same plan step repeated beyond a threshold within one trace.
- `reasoning_pattern_shift` — the agent's plan→action sequence diverges from its own history.

Customer-facing copy uses evidence language only:

> Reasoning activity spiked 6× above this agent's baseline before a database call.

Never: "the agent was confused", "uncertain", "low confidence in its plan".

## Layer 2 — Verdict-only reasoning scanning (O3 extension)

O3 already defines the pattern for prompts and responses: **in-flight scanning that stores verdicts only, never content**. Reasoning joins the same layer.

Reasoning text is scanned in flight — client-side (SDK/instrumentation) or at ingestion, before anything is written — and only a classification survives, in exactly the existing scrub shape (`{verdict, sha256, size_bytes}`):

- `goal_drift_detected` — the reasoning departs from the task the trace started with.
- `considered_unauthorized_access` — the reasoning weighed an action against a resource the agent then did or did not touch.
- `injection_markers_in_reasoning` — prompt-injection artifacts surfaced inside the reasoning itself.

This is what answers "*why* did it deviate" — as an evidence-backed finding, without the platform ever holding a word of the text. The hash preserves provenance (the customer can correlate against their own logs); the size preserves the volume signal.

## Layer 3 — Forensic opt-in (much later; explicit product decision)

For incident investigation only: when a detection rule fires on a specific agent, the customer may **explicitly enable** reasoning capture for that agent — per-agent, time-boxed (TTL), encrypted, and off again by default when the window closes.

This mirrors the platform's graduated-control philosophy: *Observe first. Deepen only what matters.* It is never default-on, never org-wide, and never silent.

## What we will never do by default

- Store raw chain-of-thought, plans, or agent self-questions.
- Send reasoning text to any third party for scoring.
- Render "uncertainty" / "confused" / confidence-flavored language in customer-facing UI.
- Treat the absence of reasoning telemetry as an error — providers that hide reasoning still get Layer-1 signals from tokens and step structure where available, and full platform value regardless.

## Detection-rule implications

The three Layer-1 candidate rules follow the A-track principles: keyed on `asset_key` / step structure — never on an agent name existing — evaluated in the batch intelligence run, never inline at ingestion, observe-only. Layer-2 verdicts become findings through the same single engine (no separate pipeline).

## Roadmap

| # | Milestone | Status |
|---|---|---|
| RO1 | Reasoning observability design (this document) | ✅ this PR |
| RO2 | Structural reasoning signals derivation — reasoning-token baselines/spikes, plan-loop detection, the three candidate findings | next |
| RO3 | Drift vs behavioral fingerprint — step-sequence baseline per agent, deviation finding | then |
| RO4 | Verdict-only reasoning scanning — ships with/after O3, same scanning layer | with O3 |
| RO5 | Forensic time-boxed opt-in capture | later — explicit product + privacy decision first |

## Related tracks

- **O3 — content-free security verdicts**: Layer 2 is the same pattern applied to reasoning; they should ship as one scanning layer.
- **Auto-instrumentation-first discovery track (A1–A8)**: the evidence-not-confidence rule governs all reasoning copy; the behavioral fingerprint that A-track discovery builds is the natural baseline for RO3's drift detection.
- **Privacy guarantee** ([otel-deployment-guide.md](otel-deployment-guide.md#privacy-guarantee)): reasoning-bearing attributes fall under the same scrub-before-storage boundary as prompts and responses.
