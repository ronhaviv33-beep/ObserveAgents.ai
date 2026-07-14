# SOC Agents — Internal Model (Detect → Triage → Respond)

*Internal architecture lens only. Nothing here renames the product, changes customer-facing
positioning, or is implemented by this document. It reframes how we sequence and judge
roadmap work using a security-operations model — "SOC for AI agents" — while the product
remains ObserveAgents, the runtime visibility and control layer for AI agents.*

> **Observe first. Control only what matters.**
> The SOC phrasing of the same invariant: **visibility first, then an explicit,
> human-approved enforcement operation — never an automatic one.**

---

## 1. Why this lens

Industry framing (AI-security webinars, market maps) now splits AI security into five
pillars: AI Development (build-time), **Agent & MCP Runtime**, AI App Runtime (prompt
control), User/Network & Access, and Software/Endpoint. ObserveAgents sits squarely in the
**Agent & MCP Runtime** pillar — the one the market labels **AI-DR: "control the action"**
— with a foothold in AI App Runtime (gateway, model observability).

That pillar's operating loop is a SOC loop, and it maps one-to-one onto what we already
built:

| SOC phase | What it means for AI agents | What we have today |
|---|---|---|
| **Detect** | Collect runtime evidence, derive behavioral findings, evaluate rules | Evidence sources → `normalize_spans` → Asset/Security Intelligence → Detection Rules |
| **Triage** | A human understands which agents matter and why | Security Intelligence buckets, worst-first findings, finding lifecycle, Gateway Control candidate queue |
| **Respond** | An explicit, approved enforcement operation | Gateway Control Center → suggested controls → human approval → Gateway enforcement (only for routed traffic) |

The model is a *lens*: every roadmap item should strengthen one of the three phases, and
anything that strengthens none of them is suspect.

## 2. Evidence layer — multi-source, one engine

The old story ("OTel → Runtime → Assets → Security → Rules → Control") is stale at the
head. The chain starts with an **Evidence Sources layer**, not with OTel:

```
Evidence Sources
  OTLP traces            (shipped)      · POST /otel/v1/traces
  Runtime Events API     (shipped)      · POST /runtime-events — any source
  Python SDK             (shipped)      · ObserveOpenAI → runtime events
  Gateway telemetry      (planned)      · proxied traffic → same evidence
  Platform connectors    (planned, O1)  · GitHub / Jira / Slack / n8n
  MCP runtime events     (planned)      · servers, tools, methods
        │
        ▼
  One engine: normalize → assets → findings → rules → control candidates
```

Invariant unchanged: **no source gets its own findings pipeline.** Adding a source adds an
adapter, never an engine.

## 3. Capability map

### Lean on — already ours, sharpen the framing

1. **Every tool call documented & investigable.** Trace waterfalls, tool/MCP spans,
   immutable scrubbed evidence — the answer to the SecOps question "is every tool call
   documented and investigable?" is already *yes*. This becomes a headline claim of the
   Detect phase.
2. **Shadow AI discovery.** Runtime discovery + `agent_missing_owner` + unknown-provider
   findings *are* Shadow-AI detection: an observed agent nobody claimed is a **shadow
   agent**. Copy-level reframing over existing evidence.
3. **Human-in-the-loop response.** Control candidates → explicit approval → enforcement
   only for routed traffic. Already matches the market's "Action Control" layer; keep
   as-is.
4. **Blast radius.** The relationships/dependency graph per agent, framed as "what can
   this agent reach" — DBs, external APIs, MCP servers, downstream agents. Small work,
   differentiating story.

### Add — new capabilities, in priority order

5. **Agent = Non-Human Identity (NHI).** The strongest external idea: *an agent is a
   non-human identity with permissions — sometimes privileged.* Evolve the identity
   resolver + asset registry into an **agent identity record**: which API key/credential
   the agent acts through, whether it shares a human's credentials, what it is permitted
   to touch. New findings: `agent_sharing_human_identity`, `privileged_agent_without_owner`,
   `unapproved_mcp_server_in_use`. Builds directly on `app/identity_resolver.py`'s
   existing trust tiers.
6. **Read/write action classification.** Classify tool/MCP calls as read vs. write
   (metadata-level, content-free — tool name/method heuristics, declared MCP method).
   Unlocks least-privilege findings and answers "which write actions is this agent
   performing?"
7. **Chain-level detection rules.** The sharpest webinar insight: *each step alone looks
   legitimate; the risk is the chain.* We already store the chain (trace → spans). Add
   rule templates over **sequences within one trace**: sensitive-read → shell/exec →
   external domain; DB read → external API (already planned as
   `db_to_external_api_same_trace`). AIDR that competitors without our evidence model
   cannot do.
8. **Behavior anomaly / intention drift.** Per-agent behavioral baseline (tools used,
   providers, domains, token profile, error rate) → drift findings when behavior departs:
   new tool never seen before, new external domain, provider switch, volume spike.
   Derivation-only, same findings model (e.g. `source="behavior_anomaly"`). This is the
   centerpiece of new Detect-phase engineering — today's rules are thresholds; this is
   the baseline/deviation layer the market calls AIDR/"drift in agent intention."
9. **MCP server approval status.** A lightweight status on observed MCP servers
   (`approved / unreviewed / flagged`) feeding findings. Cheap; answers "who approved
   this MCP server?" — a question every SecOps team asks.

### Coding-agent arena — pull earlier

The "vibe coding" arena (Claude Code / Cursor with developer-level permissions: read env →
touch secrets → run shell → install packages → open PRs) is our collector-roadmap
coding-agent wedge (R7). The market pain is immediate and we already ingest Claude Code
telemetry via OTel; chain-level rules (#7) + NHI identity (#5) apply to it directly.
Recommendation: treat coding agents as a first-class evidence source when sequencing
Detect-phase work, not as a late wedge.

## 4. Guardrails → Detection Rules merge (decided)

The Advisory Guardrails page is retired as a standalone surface; its catalog folds into
Detection Rules. Grounded facts (verified in code):

- The advisory catalog is **client-only**: 7 checks defined inside
  `dashboard/src/pages/Guardrails.jsx` (230 lines), evaluated in-browser against
  `GET /intelligence/assets/summary`. No backend code, no persistence, no tests.
- **Guard modes are a different thing and stay put**: per-team observe/alert/enforce is
  Gateway enforcement configuration (`guard_modes` table, `/guard-modes` endpoints,
  enforcement pipeline in `app/routes/proxy.py`), protected by isolation tests
  (`test_guardmode_recheck.py`, `test_mgmt_isolation.py`, `test_multitenant_isolation.py`).
  Untouched by this merge.

Catalog disposition:

| Guardrail catalog entry | Disposition |
|---|---|
| `mcp_tools` | Covered by `rule_mcp_tool_access_threshold` — drop |
| `runtime_errors` | Covered by `rule_repeated_tool_errors` — drop |
| `broad_tool_access` | Covered by runtime-security finding — drop |
| `slow_model_path` | Covered by runtime-security slow findings — drop |
| `prod_high_severity` | **New rule template**: `high_severity_finding_in_production` |
| `database_access` | **New rule template** (capability-driven): `database_access_in_production` |
| `external_api` | **New rule template** (capability-driven): `external_api_access` |

Merge steps (one PR when approved): add the 3 rule templates to `app/detection_rules.py`
(+ tests); surface them in `RulesAlertsV2.jsx`'s catalog; remove the Guardrails page,
route, and nav entries (`App.jsx`), keeping the guard-modes table reachable from
Settings/Gateway config; update README/roadmap copy. Validation: detection-rules suite,
`make verify` (guard modes), dashboard build.

## 5. Non-goals (explicit)

- **AI Development pillar** — model scanning, red teaming, AI-BOM, secure AI SDLC:
  build-time security, not runtime. Not us.
- **User/Network & Access + Software/Endpoint pillars** — SWG/CASB, DLP, device posture,
  browser extensions, package supply-chain scanning: network/endpoint products. We
  complement them with runtime evidence; we do not build them.
- **Prompt-level controls** — prompt-injection firewalls and prompt-DLP require reading
  content. Our content-free boundary stays: O3 remains "verdicts only", and we never
  become a prompt proxy filter.
- **Automatic enforcement** — AIDR framing tempts products into auto-blocking. Never:
  detection and SDK evidence produce findings and recommendations; response is always an
  explicit human operation, and only for traffic routed through Gateway.
- **A SIEM** — no log ingestion, no cross-system correlation language, no threat-intel
  feeds (unchanged from the detection-rules design).
- **Renaming the product** — "SOC Agents" / Detect→Triage→Respond is an internal lens;
  customer-facing copy keeps the current positioning until explicitly decided otherwise.
- **Cost/FinOps de-emphasis** in this lens: cost stays a supporting signal ("expensive
  path" evidence), not the story.

## 6. Phases

| Phase | Deliverable | SOC phase served |
|---|---|---|
| S0 | This document | — |
| S1 | **Guardrails → Detection Rules merge** (§4): 3 new rule templates, page retired, nav simplified | Detect + Triage |
| S2 | **Evidence-sources story fix**: diagrams/copy start from the Evidence Sources layer, not "OTel →" (README, architecture doc, dashboard Platform Guide) | Detect |
| S3 | **NHI / agent identity record** (#5) + **MCP approval status** (#9) | Detect + Triage |
| S4 | **Read/write classification** (#6) + **chain-level rule templates** (#7) | Detect |
| S5 | **Behavior baseline & drift findings** (#8) — the AIDR layer | Detect |
| S6 | **Blast-radius view** (#4) over the existing graph | Triage |

Respond-phase work continues on its own track (Gateway Control Center GCR5+), unchanged.

## 7. Invariants (restated, non-negotiable)

- Observe first. Control only what matters.
- Evidence is immutable and content-free; privacy boundaries hold at every source.
- One intelligence engine; adapters, never pipelines.
- Detection creates findings and recommendations — never actions against traffic.
- Enforcement requires explicit routing + explicit configuration + human approval.
