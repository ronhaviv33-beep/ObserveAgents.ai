# Product Discovery Model: Runtime + Ecosystem Discovery

This document defines the core product architecture of ObserveAgents.ai ("Observe"): two complementary discovery modes — **Runtime Discovery** and **Ecosystem Discovery** — correlated into one canonical AI inventory, analyzed by multiple intelligence layers.

---

## 1. Product Positioning

**Observe is the runtime visibility and control layer for AI agents.**

> Observe helps teams understand what AI exists, what is actively running, how it is connected, and how it evolves over time.

Observe is explicitly **not**:

- **Not security-only.** Security is one intelligence layer among several. Framing Observe as a security tool understates the product and misleads buyers who need discovery, dependency, and operational intelligence first.
- **Not governance-only.** Governance workflows (reviews, approvals, ownership) build on the inventory, but the inventory and intelligence come first.
- **Not cost-only.** Cost intelligence exists in the platform but is not the core narrative.
- **Not gateway-only.** The proxy gateway is one runtime evidence source. Observe ingests evidence from OpenTelemetry, SDKs, and (in the future) ecosystem sources — no gateway required.

The intelligence layers Observe provides:

- discovery intelligence
- runtime intelligence
- dependency intelligence
- capability intelligence
- performance intelligence
- operational intelligence
- security intelligence
- inventory intelligence

---

## 2. Discovery Model

Observe discovers AI systems in two complementary modes. Each answers a different question, and neither alone gives the full picture.

### Runtime Discovery

**Answers: "What AI systems are actively running?"**

Runtime Discovery observes AI systems as they execute — real traffic, real spans, real timing.

| | |
|---|---|
| **Sources** | OpenTelemetry (implemented), SDK, Gateway, runtime signals, CLI wrappers |
| **Evidence** | `service.name`, environment, models, providers, tools, dependencies, runtime activity, `last_seen`, execution timing |
| **Status** | Implemented (OTel path) |

**Current implementation** (OTel path):

- `POST /otel/v1/traces` accepts OTLP/HTTP JSON spans (see `docs/otel_ingestion.md`)
- `otel_spans` stores individual span records (privacy-scrubbed — raw prompt/response/tool content is never stored)
- `otel_assets` aggregates evidence per (org, service, environment): models, providers, tools, dependencies, first/last seen, span and trace counts
- Each discovered service/agent is reconciled against `asset_registry` — identity is derived from `agent.name` (declared) or `service.name` (inferred), entering the inventory with `discovery_status="potential"` and `discovery_source="otel_trace"`
- `otel_assets.ai_asset_id` links each evidence row back to its canonical `asset_registry` row

### Ecosystem Discovery

**Answers: "What AI systems exist across the organization?"**

Ecosystem Discovery inventories AI systems where they are *defined* — in repositories, agent platforms, workflow builders, and connected tools — whether or not they are currently running.

| | |
|---|---|
| **Sources** | GitHub, Copilot Studio, Claude ecosystem, n8n, MCP servers, Slack, Jira, ServiceNow, cloud platforms |
| **Evidence** | repositories, workflows, agent definitions, MCP configs, connectors, knowledge sources, permissions, prompt libraries |
| **Status** | Roadmap — future evidence tables |

### Why both

Runtime Discovery alone misses AI systems that exist but haven't executed recently. Ecosystem Discovery alone misses AI systems that run without being registered anywhere visible. Observe correlates both into a single canonical inventory — that correlation is the product.

---

## 3. Canonical Inventory

**Observe maintains exactly one canonical AI inventory: `asset_registry`.**

- `asset_registry` is the single source of truth for AI systems. Conceptually, `asset_registry` = `ai_assets` for now — no rename, no parallel table.
- Every discovery source writes to a **source-specific evidence table**, and every evidence table links back to `asset_registry`. Evidence tables are never inventories of their own.
- Observe does **not** maintain separate inventories per source. One AI system seen by three sources is one inventory row with three bodies of evidence.

### Current evidence tables

| Evidence table | Discovery mode | Source | Status |
|---|---|---|---|
| `otel_assets` | Runtime | OpenTelemetry traces | ✅ Implemented |

### Future evidence tables

| Evidence table | Discovery mode | Source |
|---|---|---|
| `sdk_assets` | Runtime | SDK-attested identity (self-reporting agents) |
| `observed_assets` | Runtime | Passive network observation |
| `ecosystem_assets` | Ecosystem | Generic ecosystem connectors |
| `github_assets` | Ecosystem | GitHub repositories, workflows, agent definitions |
| `n8n_assets` | Ecosystem | n8n workflow automations |
| `copilot_assets` | Ecosystem | Copilot Studio agents |

```
                    ┌──────────────────┐
 Runtime evidence   │                  │   Ecosystem evidence
 ┌──────────────┐   │  asset_registry  │   ┌────────────────┐
 │ otel_assets  ├──▶│   (canonical AI  │◀──┤ github_assets  │  (future)
 │ sdk_assets*  ├──▶│    inventory)    │◀──┤ n8n_assets     │  (future)
 │ observed_*   ├──▶│                  │◀──┤ copilot_assets │  (future)
 └──────────────┘   └──────────────────┘   └────────────────┘
                          * = future
```

---

## 4. Correlation Examples

The value of the two-mode model is in the inferences correlation makes possible:

### Example A — Active

> GitHub says `support-agent` exists.
> OpenTelemetry says `support-agent` executed 1,200 times.
>
> **Observe infers: Active.** The system is both defined and running — full evidence from both modes.

### Example B — Dormant

> GitHub says `legacy-agent` exists.
> OpenTelemetry never observes it.
>
> **Observe infers: Dormant.** The system is defined but shows no runtime activity — a candidate for retirement, and invisible to any runtime-only tool.

### Example C — Runtime-only / Unmanaged

> OpenTelemetry observes `unknown-agent` running in production.
> No GitHub, SDK, or source evidence exists.
>
> **Observe infers: Runtime-only / Unmanaged.** The system is running but not registered anywhere the organization can see — invisible to any ecosystem-only tool, and the classic shadow-AI case.

---

## 5. Intelligence Layers

Observe analyzes the correlated inventory through multiple intelligence layers:

| Layer | What it answers |
|---|---|
| **Discovery Intelligence** | Which AI systems exist, and how were they found? |
| **Runtime Intelligence** | What is actually executing, how often, and where? |
| **Dependency Intelligence** | What does each AI system depend on — models, tools, APIs, databases? |
| **Capability Intelligence** | What can each AI system do — its tool surface and runtime access? |
| **Performance Intelligence** | Where is time being spent? Where are the bottlenecks? |
| **Operational Intelligence** | Are AI systems managed, healthy, and behaving normally? |
| **Security Intelligence** | Which capability combinations and behaviors create risk? |
| **Inventory Intelligence** | Is the inventory complete, current, and accurate? |

**Security is one view, not the whole product.** A security finding like `shell_enabled` and a performance finding like `slow_tool_call` are the same kind of object — a normalized signal derived from evidence — surfaced through different layers.

### Finding categories

Findings (see `docs/asset_intelligence.md`) are organized by category:

| Category | Example finding types | Status |
|---|---|---|
| `security` | `shell_enabled`, `database_access`, `mcp_enabled` | ✅ Implemented |
| `performance` | `slow_runtime_step`, `slow_tool_call`, `slow_llm_call` | ✅ Implemented |
| `operations` | `production_runtime`, `runtime_error` | ✅ Implemented |
| `dependency` | `external_api_access`, `broad_tool_access` | ✅ Implemented |
| `inventory` | `new_ai_system_detected` (implemented), `dormant_asset` (future — requires Ecosystem Discovery correlation) | Partial |
| `governance` | (future) | Roadmap |

---

## 6. Runtime Timing / Execution Hops

Runtime Discovery does more than confirm an AI system is running — it should show **where an AI system spends time**.

### Concepts

- **Execution Timeline** — the ordered sequence of steps in a single AI request, with timing
- **Runtime Step** — one unit of work within an execution (an LLM call, a retrieval, a tool invocation)
- **Execution Hop** — a transition from one system to another (agent → LLM provider, agent → CRM, agent → MCP server)
- **Trace Waterfall** — the visual representation: steps as horizontal bars positioned by start time and sized by duration

### Example

```
Support Agent request — 8.4s total
├─ LLM planning:        1.2s
├─ Retrieval:           2.8s
├─ Jira search:         0.7s
├─ CRM lookup:          1.9s
└─ Final LLM response:  1.8s
```

This view immediately answers questions no aggregate metric can: *the retrieval step is the bottleneck, not the LLM.*

### Where the data comes from

Everything needed for the Execution Timeline is already captured by OTel span ingestion. Each `otel_spans` row stores:

- `trace_id` — groups all steps of one execution
- `span_id` — identifies the step
- `parent_span_id` — builds the step hierarchy
- `start_time` / `end_time` — positions the step on the timeline
- `duration_ms` — sizes the step

No new collection is required — the Execution Timeline is a **read view over existing span data**.

---

## 7. Product Navigation Direction

Recommended future navigation, in order:

1. **Discovery** — what was found, from which sources, at what confidence
2. **Inventory** — the canonical AI asset list (`asset_registry`)
3. **Runtime** — activity, execution timelines, trace waterfalls
4. **Ecosystem** — where AI systems are defined across the organization
5. **Dependencies** — the runtime dependency map
6. **Capabilities** — the capability surface per asset
7. **Findings** — normalized signals across all categories

The following are **not** the core MVP narrative. They may exist later, but they should not lead the product story or the navigation:

- Governance
- Reviews
- Approvals
- Exposure Score
- Policies
- Ownership Center
- Cost Intelligence
- Guardrails

---

## 8. Roadmap Implications

### Current / implemented

- OTel Runtime Discovery (`POST /otel/v1/traces`, `otel_spans`, `provenance_events`)
- OTel evidence summary (`otel_assets`)
- Canonical inventory linkage (`otel_assets.ai_asset_id` → `asset_registry`)
- Capabilities (`asset_capabilities`, derived by the Asset Intelligence engine)
- Findings (`asset_findings`, across security / performance / operations / dependency / inventory)

### Near next

- Frontend UI for Inventory / Capabilities / Findings
- Runtime Activity view (per-asset activity from `otel_assets` + `otel_spans`)
- Execution Timeline from OTel spans (trace waterfall read view)
- Ecosystem Discovery foundation (evidence table pattern, correlation states: Active / Dormant / Runtime-only)

### Future

- GitHub ecosystem discovery
- n8n discovery
- Copilot Studio discovery
- Claude ecosystem discovery
- Trust Radius
- Governance
- Policies
- Attestation
- Control recommendations

---

## Related documents

- `docs/otel_ingestion.md` — OTel trace ingestion: endpoint, privacy guarantees, data architecture
- `docs/asset_intelligence.md` — capability and finding derivation, finding catalog, API reference
