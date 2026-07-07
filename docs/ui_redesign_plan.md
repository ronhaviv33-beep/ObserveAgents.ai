# ObserveAgents UI Redesign Plan

*Docs-only plan. No code, no new components, no frontend behavior change, no backend change. Companion documents: [ui_contract.md](ui_contract.md) (the data/API contract any new UI must honor) and [gateway_control_center_architecture.md](gateway_control_center_architecture.md) (the O9 one-app workspace model this design realizes).*

---

## Executive summary

The current UI was built incrementally — page by page, feature by feature — and no longer tells the product story at a glance. The redesign keeps the **existing backend, API model, and auth untouched** and replaces the frontend experience **gradually**: a new design system (`ui2`) grows alongside the old one, and pages migrate one at a time, starting with Overview.

The new UI must communicate, on every relevant screen:

- **Observe-first integration** — OpenTelemetry is the front door, not an afterthought
- **AI runtime evidence** — everything shown traces back to observed spans
- **AI assets and ownership** — inventory + governance are first-class
- **Security findings** — agent-specific, environment-aware, deduplicated
- **Detection rules** — configurable thresholds over the same evidence (planned)
- **Gateway Control Center recommendations** — the action workspace
- **No automatic enforcement** — recommendations, never silent blocking

The story arc the whole UI is organized around:

```
OpenTelemetry / OTLP → Runtime Evidence → Asset Intelligence → Security Intelligence
                                              → Detection Rules → Gateway Control Center
```

> **Observe first. Control only what matters.**

Hard constraints: do not rewrite the whole frontend at once · do not change backend APIs · do not change auth · do not change routes unless needed later · do not remove existing pages yet.

---

## Design principles

1. **Evidence-first.** Every screen shows what runtime evidence supports the insight — span counts, trigger finding types, last-seen, provenance links. A number without evidence behind it doesn't ship. (The backend already provides this: findings carry `evidence`, candidates carry `trigger_finding_ids`.)
2. **Risk-first hierarchy.** The most important agents and findings are visually obvious — severity drives position, size, and color before anything else does. Worst first, always.
3. **Observe-to-Control flow.** The UI physically guides the user from observation to recommended control: findings link to candidates, candidates open the Control Center, the Control Center explains why and suggests what. One click, no mode switch.
4. **Progressive disclosure.** Simple summaries first (tiles, one-line rows), detail on demand (expansion → evidence panels → trace waterfalls). Landing pages stay executive-calm; depth is always one interaction away.
5. **No enforcement confusion.** Gateway control recommendations never look like switches that block. Hard controls carry the "requires Gateway routing" label; every control surface repeats "nothing is applied automatically." A recommendation renders as a review card, not a toggle.
6. **Enterprise clarity.** Less marketing copy inside the product, more operational clarity: exact counts, exact timestamps, exact names. The tagline appears once per page at most; the rest is data.

---

## Proposed visual direction

**Enterprise command center** — the feel of a security operations console, not a marketing dashboard:

- **Clean dark/light-compatible design** — design tokens defined once with semantic names (`surface`, `surface-raised`, `risk-high`…) so a light theme is a token swap, not a rewrite. Dark remains the default.
- **Strong cards** — cards are the unit of meaning (an agent, a candidate, a finding group), with a clear header row, evidence body, and action footer.
- **Clear risk badges** — one `RiskBadge` component with exactly five levels (critical/high/medium/low/info), used identically everywhere; never ad-hoc colored text.
- **Compact tables** — dense, sortable, searchable, monospaced data columns; row expansion instead of navigation where possible.
- **Timeline evidence** — traces and sessions render as time: waterfalls, last-seen recency, occurrence sparkcounts (`×N`).
- **Workspace navigation** — the sidebar states the two workspaces (Observe / Gateway Control) as the primary mental model, with Administration tucked below.
- **Minimal noise** — no decorative charts; a chart earns its place only when the shape of the data is the insight (cost trend, waterfall).
- **Strong empty states** — every empty view explains what would fill it and offers the one action that gets data flowing ("Send your first OTLP trace → Setup").

---

## New frontend structure

New design system grows in its own directory; nothing existing moves:

```
dashboard/src/ui2/
  tokens.js        # semantic design tokens (color/space/type), dark + light values
  AppShell.jsx     # shell: sidebar + topbar + content slot
  Sidebar.jsx      # workspace-grouped nav (Observe / Gateway Control / Admin)
  Topbar.jsx       # page title, org/user, refresh indicators
  PageHeader.jsx   # title + one-line purpose + actions row
  Section.jsx      # labeled content band with consistent spacing
  MetricCard.jsx   # stat tile: label, value, tone, click-through
  RiskBadge.jsx    # the one severity badge
  StatusPill.jsx   # env/status/kind pills (production, open, routing…)
  EvidenceCard.jsx # "why you're seeing this": evidence fields + provenance links
  EmptyState.jsx   # icon + sentence + primary action
```

- **`ui2` is the new design system.** It imports nothing from the old `theme.js`/`components/ui.jsx`.
- **Existing components remain for old pages** — `theme.js`, `ui.jsx`, and all current pages keep working untouched during the whole migration.
- **Pages migrate one by one:** a migrated page imports from `ui2/` only; `App.jsx`'s renderPage switch simply points the page id at the new component. Old and new pages coexist behind the same router, auth, and role gating.
- Data access stays exactly where it is: `api.js` / `overviewApi.js` are shared by both generations (see Component migration strategy).

---

## Navigation model

**One production app, two connected workspaces** (per the O9 architecture):

```
Observe                         Gateway Control
  Overview                        Control Center
  Runtime                         Control Recommendations
  Asset Intelligence              Policy Drafts        (future, GCR5)
  Security Intelligence           Providers
  Rules & Alerts   (planned)      Budgets
  Cost Signals                    Guard Modes

Administration
  Governance · Security & Audit · Users · API Keys · OTel Setup · Settings
```

- `VITE_PRODUCT_SURFACE` **remains** for dedicated deployments and white-label packaging — the build-time gate (`productSurface.js`) keeps working unchanged.
- The **main product experience** is both workspaces in one app with **one-click movement** between them: a workspace switcher in the sidebar (or grouped nav, as today with the Gateway Control group), plus contextual jumps ("Review in Gateway Control Center") that carry the agent focus across.
- During migration the new `Sidebar.jsx` reads the same page-id registry and `surfaceAllowsPage()` gate, so a dedicated observability build still hides gateway-only pages — the workspace model and the surface model coexist until the in-app switcher proves itself (the migration path documented in the O9 architecture).

---

## Page migration order

| # | Page | Why this order |
|---|---|---|
| 1 | **New Overview Dashboard** | Highest visibility; defines the design system under real data; no destructive risk (old dashboard stays routable) |
| 2 | **Gateway Control Center** | Newest page, smallest legacy surface, already close to the target design language |
| 3 | **Security Intelligence** | The risk-first hierarchy showcase; feeds the Control Center story |
| 4 | **Asset Intelligence** | The largest evidence surface; benefits most from EvidenceCard + progressive disclosure |
| 5 | **Platform Guide** | Pure content; restyle to ui2 once tokens are stable |
| 6 | **Runtime Timeline** | Timeline/waterfall components are the hardest — build them after the basics are proven |
| 7 | **Rules & Alerts** | Lands together with detection rules R3 — built ui2-native from day one |

Administration pages migrate opportunistically at the end; they must never be hidden or broken meanwhile.

---

## New Overview Dashboard concept

```
┌────────────────────────────────────────────────────────────────────┐
│ HERO      Observe first. Control only what matters.                │
│ FLOW      OTel → Runtime → Assets → Security → Rules → Gateway     │
├────────────────────────────────────────────────────────────────────┤
│ PRIMARY   [AI assets discovered] [Agents with findings]            │
│ CARDS     [Agents needing owner] [Gateway control candidates]      │
├────────────────────────────────────────────────────────────────────┤
│ ZONE OF ATTENTION                                                  │
│   · high-risk agent (worst offender, evidence summary, Investigate)│
│   · agent needs owner            · unknown provider in production  │
│   · MCP spike                    · human review recommended        │
├──────────────────────────────┬─────────────────────────────────────┤
│ RUNTIME ACTIVITY             │ GATEWAY CONTROL PREVIEW             │
│   recent traces · last seen  │   risky agents recommended for      │
│   agents · errors · slow     │   control · suggested controls ·    │
│   spans                      │   [Review →]                        │
└──────────────────────────────┴─────────────────────────────────────┘
```

- **Hero**: the core line, small and confident — not a banner.
- **Flow strip**: the six-step chain as clickable chips (each navigates to its page); this is the product model taught in one glance.
- **Primary cards** (MetricCard ×4): *AI assets discovered* (`asset-summary` count) · *Agents with findings* (assets with `open_findings_count > 0`) · *Agents needing owner* (open `agent_missing_owner`/`unmanaged_runtime`, distinct assets) · *Gateway control candidates* (open `category=control` findings). All four exist in current API responses — zero backend work.
- **Zone of Attention**: evidence-backed attention cards, each rendered only when its condition is live (no permanent grid of zeros): high-risk agent (worst offender), agent needs owner, unknown provider in production, MCP spike, human review recommended. Each card: reason, evidence summary, one action.
- **Runtime Activity**: compact recent-trace list (name, agent, duration, errors), last-seen agents, error/slow-span counts — the 30s refresh countdown kept from the current design.
- **Gateway Control Preview**: up to 3 candidate rows (agent, risk badge, top suggested control) + **Review →** into the Control Center pre-filtered. This panel is the Observe-to-Control flow made visible on the landing page.

---

## Component migration strategy

- **Do not refactor all pages at once.** One page per PR-sized change, verified before the next.
- **Build ui2 components first** against the Overview's needs only — no speculative components.
- **Migrate Overview first**, keeping the old `overview_hub` implementation in the tree until the new one is verified, then swap the renderPage case.
- **Keep existing API hooks/fetch logic** — `api.js` and `overviewApi.js` are the stable data layer for both UI generations; new pages import the same functions.
- **Do not rename backend fields.** Components consume API field names as-is (`open_findings_count`, `occurrence_count`, `recommended_controls`).
- **Use adapters only if needed** — if a ui2 component genuinely wants a different shape, a small `adapters.js` maps API → view model in one place; never scattered inline reshaping, never a backend change.

---

## Risks

- **A large visual rewrite can break flows** — mitigated by the one-page-at-a-time order, keeping old pages routable, and Playwright checks per migrated page (login → page → key elements → actions).
- **Inconsistent old/new UI during migration** — accepted and time-boxed; the migration order front-loads the highest-traffic pages so the mixed period is mostly behind the first three migrations. Old pages are not restyled mid-flight.
- **Product-surface env logic may conflict with the new workspace model** — the new Sidebar must consume `surfaceAllowsPage()` from day one (as the current nav does), and the in-app workspace switcher only replaces the surface gate after dedicated deployments get an explicit decision (O9 migration path).
- **Too much copy can clutter the dashboard** — principle 6: the tagline once, everything else is data. Copy review is part of each page's migration checklist.
- **The redesign must not hide admin/settings functions** — Administration stays permanently reachable in the sidebar; no migration step may remove Users/API Keys/Settings/Setup from navigation even temporarily.

---

## Acceptance criteria for future implementation

- Existing backend APIs still work — zero endpoint or field changes.
- Auth unchanged — same login flow, token handling, role gating.
- `cd dashboard && npm run build` passes at every migration step.
- Old pages continue to work throughout — mixed-generation UI is functional at all times.
- Overview can be migrated first, alone, and shipped.
- The new design supports Observe-to-Control: flow strip, control preview, one-click Review.
- No automatic enforcement language anywhere in the new UI.
- Mobile/responsive behavior is not worse than today (current breakpoint hooks or equivalent).

---

## Validation (for each future migration step, not this doc)

- `npm run build` + eslint with zero net-new issues.
- Playwright smoke per migrated page on the observability build (and demo build where relevant).
- Grep gate: no forbidden copy ("blocks", "enforces automatically", APM/SIEM claims) in `ui2/` or migrated pages.
- The [ui_contract.md](ui_contract.md) samples are the reference shapes for component props.
