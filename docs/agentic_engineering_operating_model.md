# Agentic Engineering Operating Model for ObserveAgents

## Executive summary

ObserveAgents is no longer a small prototype. It started as a fast experiment and it is now a platform: OpenTelemetry / OTLP ingestion, Runtime Evidence, Asset Intelligence, Security Intelligence, Detection Rules, the Gateway Control Center, the Observe-to-Control workflow, and an in-flight ui2 redesign migration. A platform of this size needs disciplined engineering.

We are moving away from a "vibe coding" style:

```
idea → code → patch
```

to an Agentic Engineering operating model:

```
spec → scoped task → implementation → validation → review → merge
```

Every piece of work starts from a written specification, is broken into small scoped tasks with explicit acceptance criteria, passes validation gates before it is considered done, and is reviewed before merge. Context is managed deliberately so that each task — human-driven or Claude Code-driven — starts with the right files, the right constraints, and a clear definition of out-of-scope.

The guiding principle: **Go deep, not just fast.** One went fast. One went deep. ObserveAgents now goes deep.

## Product North Star

**ObserveAgents is the runtime visibility and control layer for AI agents.**

Every architectural and product decision should reinforce this core flow:

```
OpenTelemetry / OTLP
→ Runtime Evidence
→ Asset Intelligence
→ Security Intelligence
→ Detection Rules
→ Gateway Control Center
```

Telemetry comes in through open standards. It becomes runtime evidence. Evidence rolls up into asset and security intelligence. Intelligence drives detection rules. Detection rules inform gateway control recommendations — and only then, with explicit human approval, control.

The core product line:

> **Observe first. Control only what matters.**

If a task does not strengthen a step in this flow, or the connective tissue between steps, question why it exists.

## Workstreams

All work on ObserveAgents belongs to exactly one of the following workstreams. A task that spans workstreams must be split, or explicitly approved as cross-cutting.

### 1. Product Architecture

**Owns:**
- Roadmap
- Product surfaces
- Observe-to-Control architecture
- Gateway Control Center model
- Customer-facing positioning

**Rules:**
- Docs-first: architecture decisions are written down before they are implemented.
- No code in architecture tasks. Architecture tasks produce documents, diagrams, and specs — implementation happens in follow-up tasks in the owning workstream.

### 2. OTel / Ingestion

**Owns:**
- OTLP JSON/protobuf ingestion
- GenAI SemConv attribute handling
- Privacy scrub
- Ingestion health
- Collector examples

**Rules:**
- No raw prompt/response persistence. Ever. The privacy scrub is a hard boundary.
- No metrics/logs ingestion unless explicitly scoped — traces are the default signal.
- Auth and org isolation must remain intact. Any change to the ingestion path re-runs the isolation harnesses.

### 3. Runtime and Intelligence Backend

**Owns:**
- Asset Intelligence
- Security Intelligence
- Findings
- Capabilities
- Dedup / `occurrence_count`
- Gateway control recommendations

**Rules:**
- Aggregate before upsert — never write per-event rows where an aggregate is the product surface.
- Avoid duplicate findings: dedup keys and `occurrence_count` are the mechanism, not repeated rows.
- Evidence must be privacy-safe. Findings carry scrubbed evidence, never raw payloads.
- Tests required. Backend intelligence changes ship with tests in `tests/`.

### 4. Gateway Control

**Owns:**
- Gateway Control Center
- Control recommendations
- Policy drafts
- Future enforcement workflows

**Rules:**
- No automatic enforcement. Recommendations are recommendations until a human approves them.
- No hidden rerouting. Traffic paths are visible and explicit.
- Hard controls require Gateway routing — observation-only integrations cannot enforce.
- Explicit approval required for any state change that affects customer traffic.

### 5. Frontend ui2

**Owns:**
- New design system
- OverviewV2
- GatewayControlCenterV2
- SecurityIntelligenceV2
- AssetIntelligenceV2
- Future migrated pages

**Rules:**
- Migrate one page at a time. One task = one page.
- Keep the old page for rollback until the V2 page has proven itself.
- Route swap only when possible — the V2 page must be feature-complete for its surface before it takes over the route.
- Build + Playwright required: `npm run build` must pass and the migrated page must be exercised (and screenshotted) in a real browser before the task is done.

### 6. Demo Company

**Owns:**
- Fake customer company
- Demo scenarios
- OTel traces for the demo
- Guided walkthrough
- Screenshots

**Rules:**
- Start with two agents only. Grow the demo cast deliberately, not opportunistically.
- No real provider keys.
- No real customer data.
- No raw prompts/responses — demo telemetry obeys the same privacy rules as production telemetry.

### 7. Docs and Sales Narrative

**Owns:**
- Customer value docs
- Demo talk tracks
- Roadmap docs
- Platform guide copy
- Architecture docs

**Rules:**
- Clear customer language — write for the buyer and the operator, not for the codebase.
- No overclaiming.
- No SIEM replacement claims — ObserveAgents complements the SIEM, it does not replace it.
- No automatic blocking claims — we recommend controls; enforcement is explicit and human-approved.

### 8. QA / Release Review

**Owns:**
- Validation commands
- PR readiness reports
- Regression suites
- Grep gates (e.g. scanning the diff for raw prompt persistence, hardcoded keys, route removals)
- Screenshots
- Rollback checks

QA / Release Review is the gatekeeper workstream: it defines what "validated" means for the other seven, and no task is done until its validation gates pass.

## Standard task lifecycle

Every task — regardless of workstream — follows the same eight steps:

1. **Define the goal.** One sentence. If it takes a paragraph, the task is too big.
2. **Define what is out of scope.** Explicitly. This is what keeps agentic tasks from sprawling.
3. **Inspect relevant files.** Read before writing. Confirm the current state matches the spec's assumptions.
4. **Create/confirm plan.** A short plan of the change, checked against the goal and the out-of-scope list.
5. **Implement small change.** The smallest diff that achieves the goal.
6. **Run validation.** The workstream's validation gates: tests, build, grep gates, screenshots as applicable.
7. **Return summary.** Branch status, files changed, validation results, known limitations.
8. **Review before next task.** A human reviews the diff and the summary before the next task begins. No pipelining unreviewed work.

## Task size rules

A task should fit in one review sitting. As a rule, a **small task** is one of:

- 1 page
- 1 backend module
- 1 doc
- 1 migration
- 1 focused test suite

**Avoid:**

- Redesigning multiple pages at once.
- Combining backend + frontend + docs + migrations in a single task unless explicitly approved.
- Changing product architecture inside implementation tasks. If implementation reveals an architecture problem, stop, write it up, and route it to the Product Architecture workstream.

If a task cannot be described as one of the small-task shapes above, split it before starting — not after it has grown.

## Validation gates

Validation is per-workstream, but the baseline gates for this repository are:

- **Backend:** `make verify` (isolation + structural harnesses) plus the focused test files relevant to the change (e.g. `python tests/test_otel_ingestion.py`, `tests/test_asset_intelligence.py`, `tests/test_gateway_control.py`).
- **Frontend (dashboard):** `npm run build` and `npm run lint` in `dashboard/`, plus Playwright-driven page checks and screenshots for ui2 migrations.
- **Privacy grep gates:** scan the diff for raw prompt/response persistence, hardcoded provider keys, and weakened org isolation before any PR is called ready.
- **Docs:** internal consistency with `docs/architecture.md`, `docs/roadmap.md`, and the product North Star; no overclaiming.

A task that skips its gates is not done, no matter how good the diff looks.

## Review before merge

- Every change lands via the lab branch and a reviewed PR — no direct pushes to `main`.
- The PR description states: goal, out-of-scope, files changed, validation results, limitations, and rollback plan where relevant.
- QA / Release Review owns the readiness call; the workstream owner owns the correctness call.

## Context management

Agentic tasks live or die on context. To keep Claude Code tasks scoped and correct:

- **Give files, not vibes.** Every task prompt lists the specific files to inspect.
- **State the invariants.** Privacy scrub, org isolation, no automatic enforcement — repeat them in the prompt for any task that goes near them.
- **One branch.** Persistent lab work happens on `claude/observeagents-review-refactor-aq8f0s`, synced from `main` before each task.
- **Small context, small task.** If the task needs the agent to hold the whole platform in its head, the task is misscoped.
- **Summaries are part of the deliverable.** Each task returns a structured summary so the next task (and the human reviewer) starts from an accurate picture instead of re-deriving state.

## Prompt template for Claude Code

Use this reusable template for every ObserveAgents task:

```text
# Task title

## Context / Why

[Product context and reason]

## Branch policy

Use:
claude/observeagents-review-refactor-aq8f0s

Sync first:
git fetch origin
git checkout main
git pull origin main
git checkout claude/observeagents-review-refactor-aq8f0s
git merge origin/main

## Task / What

[Exact task]

## Out of scope

Do not:
- ...
- ...

## Files to inspect

- ...

## Requirements

- ...

## Validation

Run:
- ...

## Acceptance criteria

- ...

## Commit

[type]: [message]

## Return

Return:
- branch status
- files changed
- summary
- validation results
- limitations
- PR recommendation
```

Fill in every section. An empty "Out of scope" section is a task that has not been thought through yet.

---

**Observe first. Control only what matters. Go deep, not just fast.**
