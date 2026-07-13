# Gateway Control Center Architecture

*Roadmap phase: **O9 — Gateway Control Center / Observe-to-Control** (see [roadmap.md](roadmap.md)).*

**Implementation status:** GCR1 (this doc) and **GCR2–GCR4 are shipped** — candidate derivation (`app/gateway_control.py` → `gateway_control_recommended` findings), the Gateway Control Center page (`dashboard/src/pages/GatewayControlCenter.jsx`, visible on both surfaces), and one-click deep links from Asset/Security Intelligence. GCR5+ (policy drafts, approval workflow, enforcement for routed agents) remain future. Still true by construction: no enforcement, no rerouting, no migrations, no Gateway behavior change.

---

## Executive summary

ObserveAgents starts with **OpenTelemetry as the primary integration path**. Customers instrument (or auto-instrument) their AI systems, point OTLP at ObserveAgents, and the platform derives the source of truth: AI assets, owners, dependencies, capabilities, findings, security intelligence, detection rule matches, and risk signals.

That runtime evidence identifies which agents are **risky, expensive, unreliable, or unmanaged**. Those agents become **Gateway control candidates**. A user reviewing an agent in Observe can move to the **Gateway Control Center with one click** — same app, same session, no redeploy, no environment variable.

The Gateway Control Center is deliberately small: it shows **only the agents that need review or control**, each with the evidence that put it there and the controls that would address it. Everything else stays in Observe.

> **Observe first. Control only what matters.**

This is one production platform with two connected workspaces — not two deployments, not a mode switch, not "observability app" vs. "gateway app" for the main customer experience.

## Current problem

The existing product-surface separation (`VITE_PRODUCT_SURFACE=observability|gateway`, built per deploy target in `render.yaml`, gated by `dashboard/src/productSurface.js`) makes Observability and Gateway feel like **two different products or deployments**. That separation is genuinely useful — focused navigation, clean packaging, honest positioning — but it is the wrong *primary* workflow.

Today a customer must decide upfront:

- Should I deploy Observability?
- Should I deploy Gateway?
- Do I change environment variables to switch?
- Which product mode am I in right now?

Those are deployment questions, and the customer shouldn't need to answer them to get value. The right sequence is: **integrate OTel first, let ObserveAgents discover what matters, then use Gateway only for the agents that need control.** The product should carry the customer along that sequence inside one app — evidence in Observe, action in the Control Center — rather than asking them to choose a product at the front door.

## Proposed product model

**Single production app with two connected workspaces.**

### Observe workspace — source of truth

Everything derived from runtime evidence lives here. Responsible for:

- OTel / OTLP ingestion (`POST /otel/v1/traces`)
- Runtime Timeline (sessions, traces, steps)
- Asset Inventory (discovery, ownership, lifecycle)
- Capabilities
- Dependencies
- Findings
- Security Intelligence (`source=runtime_security` findings)
- Detection Rules ([ai_agent_detection_rules_alerts_design.md](ai_agent_detection_rules_alerts_design.md))
- Cost Signals
- Advisor recommendations (roadmap O8)

### Gateway Control Center — action workspace

A short, prioritized worklist, not another dashboard. Responsible for:

- showing the agents **recommended for Gateway control** (candidates)
- explaining **why** each agent is there — the triggered findings and rule matches, verbatim from Observe
- showing **suggested controls** per agent (§ Suggested controls)
- preparing **future policy drafts** (GCR5) a human can review
- showing **routing / enforcement readiness** — is this agent's traffic routed through the Gateway at all?
- linking to the existing Gateway configuration pages (Providers, Budgets, Guard Modes) where a suggested control maps to a real setting

The Control Center reads from Observe; it never bypasses it. If Observe has no evidence for an agent, the Control Center has nothing to say about it.

## End-to-end flow

```
Customer AI systems
  → OTel / OTLP
    → ObserveAgents Runtime Evidence   (otel_assets, otel_spans, asset_registry)
      → Asset Intelligence             (capabilities, findings)
        → Security / Cost / Reliability Findings
          → Detection Rules            (configurable thresholds → matches)
            → Gateway Control Candidate
              → Gateway Control Center (review, evidence, suggested controls)
                → Suggested Controls
                  → Customer Approval  (explicit, human)
                    → Optional Gateway Policy / Enforcement
                      (only for traffic routed through the Gateway)
```

Every arrow to the left of "Customer Approval" is automatic and observe-only. Every arrow to the right of it is manual, explicit, and opt-in.

## One-click product transition

From the places where a user is already looking at evidence:

- **Asset Intelligence** (asset detail / findings tab)
- **Security Intelligence**
- **Rules & Alerts** (detection rule matches, once built)
- **Findings table**

…the UI offers contextual actions:

- **Review in Gateway Control Center** — on any asset that is a candidate
- **Create Gateway Control Plan** — on a candidate, starts the (future) policy-draft flow
- **View Control Recommendation** — on a finding/rule match that produced a candidate

Clicking any of these navigates to the Gateway Control Center **pre-filtered to that agent or recommendation** — in the current app's hash router (`navigate("gateway_control_center")` with a filter param), exactly like existing cross-page links.

**No environment variable switch. No redeploy. No separate app.** The transition is a route change, nothing more.

## Candidate definition

> **A Gateway Control Candidate is an observed AI asset whose runtime evidence indicates that it may need Gateway-level control.**

Candidate triggers may include (all already derivable from existing findings and planned detection rules):

| Trigger | Today's evidence |
|---|---|
| High-risk security finding | any `severity=high` finding, `source=runtime_security` |
| MCP usage threshold | `agent_uses_mcp_tool_in_production` / `mcp_tool_access_threshold` rule |
| Unknown provider in production | `agent_uses_unknown_model_provider` (prod) |
| Database access in production | `agent_has_database_access` (prod) |
| Database + external API in same trace | `db_to_external_api_same_trace` rule (planned) |
| Broad tool surface | `agent_has_broad_tool_surface` |
| Repeated tool errors | `repeated_tool_errors` |
| High token/cost signal | `high_token_usage_threshold` rule / cost signals |
| Missing owner in production | `agent_missing_owner` (prod) |
| Human review recommended | `human_review_recommended` |

Being a candidate is **not** an accusation and **not** an action — it is a review queue entry with evidence attached.

**Candidate threshold (decided):** an asset becomes a candidate when it has any **high-severity** finding or rule match, **or** a `human_review_recommended` finding **at any severity, including medium** — human-review combinations are exactly the signal the Control Center exists to route to a person, so they qualify even when no single contributing finding is high on its own. Other medium findings alone do not create candidates; that keeps the queue short and the recommendation meaningful.

## Candidate status model

Full future status vocabulary:

| Status | Meaning |
|---|---|
| `recommended` | Derivation put this agent in the queue |
| `reviewing` | A human picked it up |
| `control_plan_created` | A policy draft exists (GCR5) |
| `routing_required` | Chosen controls are hard controls, but traffic isn't routed through Gateway yet |
| `gateway_configured` | Gateway settings exist for this agent (alert-only or better) |
| `alert_only` | Customer chose observe/alert posture explicitly |
| `enforce_ready` | Routed + policy approved, enforcement not yet switched on |
| `enforce_enabled` | Enforcement live (GCR7, explicit approval only) |
| `dismissed` | Reviewed and consciously declined |

**MVP recommendation: start with `recommended` / `reviewing` / `dismissed` only.** (Plain `recommended`/`dismissed` is acceptable if `reviewing` adds UI cost.) Every state from `control_plan_created` onward is **future-only** — they exist in the vocabulary now so the status column never needs a breaking rename, but no MVP code path sets them.

**Dismissal independence (decided):** dismissing a candidate does **not** dismiss the underlying findings, and vice versa. They answer different questions — a finding says *"this behavior was observed"*; a candidate says *"this agent should be considered for Gateway control"*. Dismissing the candidate means "I decline to control this agent," while the evidence stays open in Observe for the team that owns it. This also keeps the audit trail honest (a Control Center action never silently mutates the Observe source of truth) and lets the candidate be re-recommended if *new* high-risk evidence appears after dismissal — a dismissed candidate stays dismissed for its existing evidence, but a newly triggered finding type reopens the question deliberately.

## Suggested controls

Per candidate, the Control Center shows controls that would address its specific evidence:

| Suggested control | Addresses | Kind |
|---|---|---|
| Provider allowlist | unknown provider in production | hard (needs routing) |
| Model allowlist | unapproved/unknown models | hard (needs routing) |
| MCP/tool usage policy | MCP thresholds, broad tool surface | hard (needs routing) |
| Rate limit | MCP/tool call bursts | hard (needs routing) |
| Budget threshold | high token/cost signal | hard to enforce; soft as alert |
| Alert-only rule | any recurring pattern | soft |
| Human review requirement | human_review_recommended combos | soft (workflow) |
| Owner assignment | missing owner | soft (governance, exists today) |
| Route through Gateway | prerequisite for all hard controls | routing step |
| Block unknown provider | unknown provider — **only after Gateway routing and explicit approval** | hard, gated twice |

**Hard controls only work after traffic is routed through the Gateway.** The UI must say this on every hard control, and a candidate whose agent is not routed shows `routing_required` next to any hard suggestion — never a working "block" button.

## Soft control vs hard control

**Soft control works from OTel evidence alone** — no routing change, available to every customer from day one:

- findings and recommendations
- Slack/webhook alerts (detection rules R4)
- owner assignment
- tickets / review workflows
- policy drafts (documents, not live policies)

**Hard control requires Gateway routing** — the agent's LLM traffic must actually pass through the ObserveAgents Gateway (`/v1` proxy):

- blocking
- provider/model enforcement
- rate limits
- budget enforcement
- request-level policy enforcement

> **Observe can recommend. Gateway can enforce only when explicitly configured.**

The platform must never imply that Observe can block an agent whose traffic it merely observes. OTel is evidence, not a control plane.

## Relationship to existing product-surface separation

The `VITE_PRODUCT_SURFACE` separation (observability / gateway / combined) **stays** — it remains right for:

- focused navigation on dedicated deployments
- enterprise packaging (selling the Gateway console standalone)
- future white-label or product-specific apps
- the public demo's guided walkthrough

What changes is the **primary customer experience**: one app, both workspaces available, **Observe is the default landing** and source of truth, and the Gateway Control Center is reached *from* recommendations — not chosen at deploy time.

**Migration path (no removal yet):**

1. Today — surfaces selected at build time; `combined` exists for demo/local dev.
2. GCR3–GCR4 — the Control Center page ships inside the main app; the nav gains a workspace grouping (Observe / Gateway Control) instead of relying on surface builds to hide halves of the product.
3. Later — `productSurface.js` evolves from a build-time gate into an **in-app workspace switcher** default: the same mechanism, driven by user navigation instead of `VITE_PRODUCT_SURFACE`, with the env var retained as a hard filter for dedicated/white-label deployments.
4. Only after the switcher proves itself do we consider retiring any build target. Nothing is removed prematurely.

## UI proposal

Suggested navigation (single app):

```
Observe
  Dashboard
  Runtime
  Asset Intelligence
  Security Intelligence
  Rules & Alerts        (planned — detection rules)
  Cost Signals

Gateway Control
  Control Center
  Control Recommendations
  Policy Drafts         (future, GCR5)
  Providers
  Budgets
  Guard Modes
  Audit
```

Gateway Control Center page sections:

1. **Recommended for Control** — the active candidate queue, worst first
2. **High Risk Agents** — candidates with high-severity evidence
3. **Triggered Rules** — rule matches that produced candidates
4. **Suggested Controls** — per selected agent
5. **Routing Required** — candidates whose suggested controls are hard controls but whose traffic isn't routed
6. **Dismissed / Resolved** — the audit trail of conscious decisions

Agent card / table fields:

`agent name` · `asset key` · `owner/team` · `environment` · `risk level` · `triggered findings` · `triggered rules` · `last seen` · `recommended controls` · `status` · action button (**Review** / **Create Control Plan**)

**Access control (decided):** the Control Center is visible to **admin, analyst, and viewer** roles — everyone who can see findings can see why an agent is recommended for control. **Only admin can act**: review, dismiss, create a control plan, approve. Analyst and viewer get the full read-only view with action buttons hidden/disabled, following the same role-gating pattern the rest of the dashboard uses (`require_page_access` server-side, role checks in `auth.jsx` client-side).

Implementation later follows the existing conventions: PAGES/NAV_GROUPS/renderPage registration in `dashboard/src/App.jsx`, roles in `app/roles.py` + `dashboard/src/auth.jsx`, theme tokens, `Card`/`Pill`/`sevColor` from `ui.jsx`.

## Data model proposal

### Future table: `gateway_control_recommendations`

| Field | Notes |
|---|---|
| `id` | PK |
| `org_id` | FK → organizations, indexed — strict org isolation like every table |
| `asset_id` / `asset_key` | which agent |
| `severity` | worst contributing evidence |
| `status` | § Candidate status model |
| `reason` | one-sentence human explanation |
| `recommended_controls_json` | list of § Suggested controls entries |
| `evidence_summary_json` | privacy-safe summary (identifiers + counts only) |
| `triggered_finding_ids_json` | provenance → asset_findings |
| `triggered_rule_match_ids_json` | provenance → rule matches |
| `created_at` / `updated_at` | timestamps |
| `dismissed_at` / `dismissed_by` | audit |
| `approved_at` / `approved_by` | audit (GCR6+) |
| `gateway_policy_id` | link once a policy draft/policy exists (GCR5+) |

### Alternative MVP: reuse `AssetFinding`

Create candidates as findings: `category="control"`, `source="observe_to_control"`, `finding_type="gateway_control_recommended"`, with the reason/controls/provenance in `evidence_json`.

**Pros:** zero migration; inherits the proven dedup/occurrence machinery (`_upsert_finding`), status lifecycle (open/dismissed/resolved + reopen), org isolation, serialization, and the existing findings UI plumbing; GCR2 becomes a small derivation pass exactly like `runtime_security_intelligence`.

**Cons:** the finding status vocabulary (open/dismissed/resolved) can't express `routing_required`/`enforce_ready` without abusing `evidence_json`; no clean FK to a future gateway policy; approval audit fields don't exist; and "control recommendation" semantically isn't a *finding about behavior* — mixing it into the findings feed risks the same concept-blur the detection-rules plan warns about.

**Recommendation:** **start with the AssetFinding reuse for GCR2–GCR4** (statuses needed: recommended≈open, dismissed≈dismissed — exactly what findings already do), and introduce `gateway_control_recommendations` in GCR5 when policy drafts and approval audit make the dedicated table genuinely necessary. The finding row then becomes the provenance pointer, not the recommendation itself.

## MVP recommendation

| Phase | Deliverable |
|---|---|
| **GCR1** | This document + roadmap entry (this task) |
| **GCR2** | Backend recommendation derivation — a post-pass of `/intelligence/run` (same orchestration point as runtime security) creates `gateway_control_recommended` findings from high-risk existing findings/rule matches. No new table |
| **GCR3** | Gateway Control Center UI — a page listing control-recommendation findings grouped by agent, with evidence and suggested controls (read-only) |
| **GCR4** | One-click navigation — "Review in Gateway Control Center" buttons on Asset Intelligence and Security Intelligence, deep-linking with an asset filter |
| **GCR5** | Policy draft — generate a suggested Gateway policy document from a recommendation. Draft only, no enforcement; introduce the dedicated table here |
| **GCR6** | Explicit approval workflow — a human approves a draft; still nothing enforced until routing exists |
| **GCR7** | Enforcement for routed agents only — provider traffic that already flows through the Gateway `/v1` proxy can have approved policies enforced, per team guard mode |

## Trust and safety boundaries

- **No automatic blocking.** A candidate is a review item, never an action.
- **No automatic rerouting.** ObserveAgents never redirects an agent's traffic; routing through the Gateway is a customer infrastructure decision.
- **No hidden enforcement.** Enforcement state is always visible, always attributable to an explicit approval.
- **No false capability claims.** Observe cannot block non-routed agents, and no UI copy may imply it can.
- **Privacy-safe evidence only.** Recommendations carry identifiers and counts — agent/tool/provider/model names, MCP methods, sanitized domains+paths, error types, span/token counts. **Never** raw prompts, responses, tool arguments, tool results, credentials, full URLs with query strings, headers, or request bodies (the same boundary enforced at ingestion by `app/otel_privacy.py`).
- **Customer approval required for enforcement.** GCR6 is a hard gate, not a formality.
- **Gateway enforcement requires traffic routed through the Gateway.** Stated everywhere a hard control appears.

## Acceptance criteria for future implementation

- A single production app can show both the Observe workspace and the Gateway Control Center.
- No environment variable switch is required for the primary workflow — moving between workspaces is in-app navigation.
- Risky agents appear as Gateway control candidates, derived automatically from existing evidence.
- Every recommendation is evidence-backed: it links to the findings/rule matches that produced it.
- No enforcement occurs without explicit customer approval.
- Hard controls clearly require Gateway routing; non-routed candidates show `routing_required`, never a live block control.
- Recommendations contain privacy-safe evidence only.
- Existing dedicated surface modes (`VITE_PRODUCT_SURFACE`) are not removed prematurely; the migration path runs through an in-app workspace switcher first.
