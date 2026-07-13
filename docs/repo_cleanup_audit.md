# Repo Cleanup Audit

*Audit only — nothing was deleted, moved, or edited in this task. Every classification
below is a recommendation backed by the evidence listed; the actual cleanup happens in
the small follow-up PRs proposed at the end, each individually reviewable.*

Audit date: 2026-07-13 · Base: `main` after PR #114 (Python SDK MVP).

## Executive Summary

The repo is in better shape than it looks: **no committed build artifacts or cache junk
exist** (`git ls-files` is clean of `__pycache__`/`.pyc`/`dist/`/`.pytest_cache` — all
gitignored), the deployed surfaces (backend, dashboard, demo, website) are all live in
`render.yaml`, and most files trace to something real. The clutter is concentrated in
three places:

1. **docs/ (29 files)** — a handful of superseded plans and old-positioning docs
   (AI-Asset-Management/CMDB framing, "dark console" language, fake-customer simulation
   guides), plus a 4-way overlapping onboarding cluster and a Hebrew duplicate that will
   drift. Only 2 files are clear archive candidates today; most need light review or an
   owner decision, not deletion.
2. **Two SDKs coexist** — `ai_agent_inventory/` (old header-injection client SDK, packaged
   by `setup.py`) is superseded by `sdk/python/observeagents/` (PR #114) but is still
   imported by one active test (`tests/test_relationships.py`), so it is an archive
   candidate *gated on repointing that test*, not a delete.
3. **scripts/ (13 files)** — all are documented dev/QA/demo utilities; none are dead, but
   the three overlapping synthetic-customer E2E harnesses are a consolidation candidate.

Exactly **one dead-code file** was found: `dashboard/src/components/IntegrationsPage.jsx`
(imported nowhere). Recommended strategy: archive rather than delete wherever there is any
doubt, in five small PRs, each followed by the validation commands at the bottom.

**Validation run for this audit:**
- `pytest tests/test_runtime_events.py -q` → **9 passed** ✅
- `npm --prefix dashboard run build` → **built successfully** ✅ (warning only: main JS
  chunk is 1.2 MB > 500 kB — a pre-existing code-splitting note, unrelated to cleanup)

## Cleanup Principles

**Must preserve:**
- Active runtime code and its tests: `app/`, `dashboard/` (all routed pages),
  `tests/`, `sdk/python/**` (new SDK, PR #114), runtime-events files
  (`app/runtime_events.py`, `app/routes/runtime_events.py`, `tests/test_runtime_events.py`).
- Migrations: `alembic/`, `alembic.ini` (loaded at runtime by `app/startup.py` and
  by `tests/test_schema_repair.py`). Never remove migrations.
- Deployment/dev infra: `render.yaml`, `requirements.txt`, `Makefile`,
  `tests/pre-commit-hook` (runs `make verify`), `.env.example`, `DEVELOPMENT.md`.
- `website/` **sources** — the website is a deployed Render static service
  (`buildCommand: cd website && npm install && npm run build`,
  `staticPublishPath: website/dist`); `goal.html` is a live nav-linked page and a Vite
  build input.
- Auth/org/RBAC, Gateway, Detection Rules, Intelligence engine code — nothing in this
  audit found any of it unused.
- Every doc linked from README.md (12 of 29) unless the link is replaced in the same PR.

**Can be removed/archived (with evidence):** superseded plans, old-positioning docs,
duplicates, dead components — always preferring `docs/archive/` moves over deletion when
the file has historical value.

## Active Core — Keep

| Area | What | Why |
|---|---|---|
| `app/` | FastAPI backend (all modules incl. `runtime_events.py`, `otel_normalizer.py`, `gateway_control.py`, auth/RBAC) | Deployed by render.yaml (`app.main:app`, two services) |
| `dashboard/` | React/Vite dashboard (all components verified imported except one — see Delete Candidates) | Deployed by render.yaml; build verified in this audit |
| `alembic/`, `alembic.ini` | DB migrations + config | Loaded at runtime (`app/startup.py`) and by tests |
| `tests/` | 44 backend test files | Active protection; 6 harnesses run by `make verify` (test_mgmt_isolation, test_w1_alerts, test_teams, test_guardmode_recheck, test_proxy_team_register, test_team_scope) |
| `sdk/python/**` | New Python SDK MVP + its tests | PR #114; do not touch |
| `website/` sources (`index.html`, `goal.html`, `tour.html`, `vite.config.js`, `package.json`, `public/`) | Deployed marketing site | Render static service builds from these |
| `README.md`, `render.yaml`, `requirements.txt`, `Makefile`, `.env.example`, `DEVELOPMENT.md`, `.vscode/` | Entry point + deploy/dev infra | Referenced by deployment and dev workflow docs |
| docs/ core set | `otel_ingestion.md`, `architecture.md`, `asset_intelligence.md`, `ai_agent_runtime_security_intelligence.md`, `ai_agent_detection_rules_alerts_design.md`, `gateway_control_center_architecture.md`, `roadmap.md`, `ui_contract.md`, `demo_seed_data.md`, `python_sdk_wrapper_plan.md`, `python_sdk_mvp_implementation_plan.md`, `product_discovery_model.md`, `agentic_payments_x402_observability_plan.md` | README-linked and/or referenced from code comments; current positioning |

## Likely Legacy / Archive Candidates

| Path | Reason | Evidence | Risk | Recommended Action |
|---|---|---|---|---|
| `docs/TRAINING_INTRO.md` | Old "AI Asset Management" training doc: verified/potential-agent, gateway/CMDB-first, cost-intelligence framing — contradicts "runtime visibility and control layer" positioning | `git grep TRAINING_INTRO` → zero references (not in README, docs, code) | Low | Move to `docs/archive/positioning/TRAINING_INTRO.md` |
| `docs/ai_agent_detection_rules_plan.md` | Superseded plan — its successor `ai_agent_detection_rules_alerts_design.md` states on line 3 that it "supersedes and expands" this file | Referenced only from docs that name it as superseded (alerts_design, gateway arch, roadmap); not README-linked | Low | Move to `docs/archive/plans/ai_agent_detection_rules_plan.md`; update the three doc references to point at the successor |
| `docs/customer_validation_report_2026-07.md` | Point-in-time validation snapshot (2026-07-09); many findings marked "now fixed"; historical record, not a living doc | Unreferenced by README/docs/code | Low | Move to `docs/archive/reports/customer_validation_report_2026-07.md` |
| `ai_agent_inventory/` (whole package) + `setup.py` | The OLD client SDK (X-Agent-* header injection; packaged by `setup.py` as `ai-agent-inventory-sdk` v0.1.0) — superseded by `sdk/python/observeagents/` | Not imported by `app/` anywhere; **but** `tests/test_relationships.py` imports `ai_agent_inventory.headers.build_headers` (6×), and `setup.py` packages only this | **Medium** | OWNER DECISION first (see below), then archive to `legacy/ai_agent_inventory/` or delete — **gated on** keeping `tests/test_relationships.py` green (it tests the header-based relationship capture the backend still supports; the header-building helper could be inlined into the test) |
| `docs/fake_customer_company_simulation_guide.md` | Internal 925-line dogfooding simulation guide; some stale surface names (Cost Intelligence / Gateway pages) | Referenced only from other internal sim/QA docs | Low | Owner decision; if unused in practice → `docs/archive/simulation/` |
| `docs/manual_company_simulation_qa_guide.md` | Internal QA walkthrough with stale page names (Budgets/Guardrails/Cost Intelligence) | Referenced only from the other sim docs | Low | Owner decision; same archive path |
| `docs/organization_implementation_guide_he.md` | Hebrew duplicate of `organization_implementation_guide.md`; translation will drift from English source | Referenced only from its English source and the onboarding cluster | Low | Owner decision: keep only if Hebrew onboarding is actively used; otherwise `docs/archive/onboarding/` |
| `docs/synthetic_enterprise.md` | Documents the older 3-org (globex/cybertech) budget/RBAC-heavy demo — different from the README-canonical single Acme demo | Backs a real, working script (`scripts/seed_synthetic_enterprise.py`); unreferenced from README | Medium | Keep while the script is kept (see Scripts Review); if the synthetic-enterprise suite is retired, archive doc + scripts together |

## Delete Candidates

| Path | Reason | Evidence | Risk | Recommended Action |
|---|---|---|---|---|
| `dashboard/src/components/IntegrationsPage.jsx` | Dead component — imported nowhere; the "integrations" route uses `pages/Setup.jsx` (`SimpleIntegrationsPage`) instead | `git grep IntegrationsPage` → defined only in its own file; `App.jsx:84/862` imports `pages/Setup.jsx`; every other component verified imported ≥1× | **Low** | Delete in PR 5 (after `npm --prefix dashboard run build` passes without it) |

That is the only clean delete candidate found. Notably **absent** from this list:
- No committed `__pycache__` / `.pyc` / `.pytest_cache` / `dist/` files exist in git
  (`git ls-files | grep -E "__pycache__|pytest_cache|\.pyc|dist/"` → empty). The copies on
  disk are untracked local artifacts — nothing to clean in the repo.
- No script in `scripts/` is unreferenced (each is documented by a scripts README or a doc,
  and `seed_demo_data.py` is protected by `tests/test_seed_demo_data.py`).
- `scripts/collector_smoke_otlp.py` has zero references but is the newest script (Jul 11)
  and a plausibly useful manual OTLP smoke tool → NEEDS OWNER DECISION, not delete.

## Duplicate / Conflicting Docs

| Path | Conflict | Recommended Source of Truth | Action |
|---|---|---|---|
| `docs/ai_agent_detection_rules_plan.md` vs `docs/ai_agent_detection_rules_alerts_design.md` | Successor explicitly supersedes the plan | `ai_agent_detection_rules_alerts_design.md` (README-linked, code-referenced) | Archive the plan (PR 1) |
| Onboarding cluster: `organization_implementation_guide.md` / `organization_implementation_guide_he.md` / `organization_quick_start_non_technical.md` / `otel_customer_onboarding_guide.md` | Four overlapping onboarding guides; the 2026-07 validation report itself flagged "a competing legacy onboarding guide" as a setup-flow problem | `otel_customer_onboarding_guide.md` (newest, bilingual, current positioning) — with `otel_ingestion.md` staying the technical reference | Owner decision: pick one entry path, fold the others in or archive them (PR 1/4) |
| `docs/ui_redesign_plan.md` (+ README line 41) vs shipped theme | Doc says "Dark remains the default" and README says "dark console", but the shipped dashboard theme is **light** (`dashboard/src/index.css`: "ObserveAgents light SaaS theme") | Shipped light theme + `ui_contract.md` | Keep the doc (it's the README-linked ui2 design record) but fix the theme wording; fix README:41 in a later copy pass — **not in this audit task** |
| `docs/demo_seed_data.md` vs `docs/synthetic_enterprise.md` | Two demo-data stories: single Acme org (README-canonical) vs older 3-org synthetic enterprise | `demo_seed_data.md` | Keep both while both scripts exist; revisit with the synthetic-suite owner decision |
| `docs/python_sdk_wrapper_plan.md` broken link | Links `docs/genai_runtime_collector_roadmap.md`, which does not exist on main (it lives only on an old lab branch) | Link should point at `docs/roadmap.md` (or the roadmap doc should be landed separately) | Fix the link in a later docs PR — needs owner decision on whether to land the collector roadmap doc first |
| Status-stale plan headers | `product_surface_separation_plan.md` and `python_sdk_mvp_implementation_plan.md` still say "nothing implemented", contradicted by `dashboard/src/productSurface.js` and `sdk/python/observeagents/` | The code | Add a one-line "status: shipped/partially shipped" note in a later docs PR |

## Scripts Review

None of the 13 files in `scripts/` are referenced by `Makefile` or `render.yaml` — all are
dev/QA/demo utilities invoked manually.

| Script | Purpose | Referenced By | Keep/Delete/Archive | Risk |
|---|---|---|---|---|
| `seed_demo_data.py` | Seeds the Acme demo org through the real OTel pipeline (wraps `app/demo_otel_seed.py`, same module as the admin "Populate Org" button) | README, DEVELOPMENT.md, 5 docs, **`tests/test_seed_demo_data.py`** | **KEEP** | High if removed |
| `seed_synthetic_enterprise.py` | Seeds 3 synthetic orgs (teams/users/keys/budgets/policies/telemetry) | `docs/synthetic_enterprise.md` | KEEP BUT REVIEW LATER (owner: is the 3-org demo still used?) | Medium |
| `generate_synthetic_traffic.py` | Multi-day synthetic AI traffic for those orgs | `docs/synthetic_enterprise.md` | KEEP BUT REVIEW LATER (pairs with the above) | Medium |
| `synthetic_payloads.py` | Shared fake-credential/PII payload templates | Used by the synthetic scripts | KEEP BUT REVIEW LATER (moves with its consumers) | Low |
| `synthetic_customer.py` | 8-flow synthetic-customer E2E | `README_e2e.md`, `README_long_run.md`, `README_synthetic_customer.md` | NEEDS OWNER DECISION (overlaps `synthetic_customer_e2e.py`) | Medium |
| `synthetic_customer_e2e.py` | Full 23-section / 96-check E2E suite | `README_e2e.md`; driven by `run_8h_e2e.py` | KEEP BUT REVIEW LATER (the comprehensive one) | Medium |
| `long_run_synthetic_customer.py` | N-hour full-platform soak test (91 KB) | `README_long_run.md` | NEEDS OWNER DECISION (still run?) | Medium |
| `run_8h_e2e.py` | 8-hour scheduler around `synthetic_customer_e2e.py` | `README_e2e.md` | NEEDS OWNER DECISION (one-off driver?) | Low |
| `collector_smoke_otlp.py` | Manual OTLP/HTTP protobuf smoke test against `/otel/v1/traces` | Nothing (newest script, Jul 11) | NEEDS OWNER DECISION (likely keep; consider documenting it in `docs/otel_ingestion.md`) | Low |
| `README_e2e.md` / `README_long_run.md` / `README_synthetic_customer.md` | Docs for the E2E harnesses | (are the references) | Follow their scripts | Low |

Consolidation suggestion (later, owner-approved): one E2E harness (`synthetic_customer_e2e.py`
+ its scheduler) is probably enough; `synthetic_customer.py` and possibly
`long_run_synthetic_customer.py` could be archived with their READMEs merged into one
`scripts/README.md`.

## Root-Level Files Review

| File | Purpose | Keep/Delete/Move | Reason |
|---|---|---|---|
| `README.md` | Product entry point | KEEP | — |
| `render.yaml` | Deploys all 4 services (backend, demo, dashboard, website) | KEEP | Deployment |
| `requirements.txt` | Backend deps | KEEP | Used by render.yaml (×2) and .vscode tasks |
| `Makefile` | `make verify` — 6 isolation/RBAC harnesses | KEEP | Run by `tests/pre-commit-hook` |
| `alembic.ini` | Migration config | KEEP | Loaded by `app/startup.py` + `tests/test_schema_repair.py` |
| `.env.example` | Env template | KEEP | Referenced by README, DEVELOPMENT.md, docs, an SDK test |
| `DEVELOPMENT.md` | Dev setup guide | KEEP | Primary dev doc; documents .vscode + scripts |
| `reset_admin.py` | Ops recovery: reset/create default admin password (Render shell or local) | KEEP | Operational tool referenced in the validation report; small and harmless |
| `setup.py` | Packages **`ai_agent_inventory` only** (the old SDK, `ai-agent-inventory-sdk` v0.1.0) — not `app/`, not the new SDK | NEEDS OWNER DECISION | Its fate is tied to the old-SDK decision; if `ai_agent_inventory/` is archived, `setup.py` goes with it |
| `.vscode/` (extensions/launch/tasks) | Shared editor config, documented in DEVELOPMENT.md | KEEP | Deliberate team ergonomics |
| `tests/pre-commit-hook` | Git hook → `exec make verify` | KEEP | The only commit-time guardrail (repo has no CI) |
| `tests/check_pricing.py` | Manual pricing-integrity audit | KEEP BUT REVIEW LATER | Wired to nothing automated; consider adding to `make verify` |
| `dashboard/smoke_check.cjs` | AST check for stray top-level React hooks in App.jsx | KEEP BUT REVIEW LATER | Useful guard, but not in package.json scripts or any automation — wire it up or acknowledge manual-only |

## Suggested Cleanup PRs

Each PR is small, single-purpose, and followed by the Validation Plan below.

**PR 1 — Docs archive only (lowest risk)**
- Create `docs/archive/` with `positioning/`, `plans/`, `reports/` subfolders.
- Move: `TRAINING_INTRO.md` → `archive/positioning/`; `ai_agent_detection_rules_plan.md`
  → `archive/plans/` (updating its three inbound doc links to the successor);
  `customer_validation_report_2026-07.md` → `archive/reports/`.
- No code, no README changes beyond none-needed (none of the three is README-linked).

**PR 2 — Delete low-risk unreferenced scripts** *(currently empty)*
- The audit found **no** unreferenced scripts safe to delete today. This PR happens only
  after the owner decisions on the E2E trio + `collector_smoke_otlp.py`; whatever is
  retired moves to `docs/archive/` or is deleted with its README references cleaned.

**PR 3 — Root-level cleanup (owner-gated)**
- Decide `ai_agent_inventory/` + `setup.py`: repoint `tests/test_relationships.py` (inline
  the small `build_headers` helper into the test, keeping the header-based relationship
  behavior protected), then archive the package to `legacy/` or delete it.
- Validation must include the full pytest suite — `test_relationships.py` especially.

**PR 4 — Stale website/docs artifacts**
- Website: nothing to remove (dist/ untracked, goal.html live). This PR is the onboarding
  consolidation instead: pick `otel_customer_onboarding_guide.md` as the single entry path,
  archive/merge the overlapping org guides (incl. the Hebrew duplicate, per owner decision),
  and fix the two status-stale plan headers + the broken `genai_runtime_collector_roadmap.md`
  link in `python_sdk_wrapper_plan.md`.

**PR 5 — Optional deeper app/dashboard cleanup (after tests)**
- Delete `dashboard/src/components/IntegrationsPage.jsx` (dead).
- Optionally wire `dashboard/smoke_check.cjs` and `tests/check_pricing.py` into
  `make verify` so the guard tools actually run.
- Nothing else in `app/` or `dashboard/` was found removable.

## Do Not Touch List

- `app/` — entire backend (including `app/runtime_events.py`, `app/routes/runtime_events.py`, all otel/gateway/auth/RBAC/detection/intelligence modules)
- `dashboard/` — all routed pages and components (sole exception: the one dead component listed above, and only in PR 5 with a build check)
- `alembic/`, `alembic.ini` — never remove migrations
- `tests/` — all test files (they protect active behavior); `tests/pre-commit-hook`
- `sdk/python/**` — the new SDK (PR #114)
- `README.md` — no changes in cleanup PRs unless a moved doc's link must be updated in the same PR
- `render.yaml`, `requirements.txt`, `Makefile`, `.env.example`, `DEVELOPMENT.md`
- `website/` sources — deployed static site (`index.html`, `goal.html`, `tour.html`, `vite.config.js`, `package.json`, `public/`)
- `docs/` core set listed under Active Core
- `scripts/seed_demo_data.py` — test-protected demo seed

## Validation Plan

After **every** cleanup PR:

```bash
# Backend: runtime-events seam + the suites owner cares about
pytest tests/test_runtime_events.py tests/test_otel_ingestion.py \
       tests/test_asset_intelligence.py tests/test_detection_rules.py -q

# Isolation/RBAC harnesses (also enforced by the pre-commit hook)
make verify

# Dashboard still builds (required for PR 5; cheap enough to run always)
npm --prefix dashboard run build

# Website still builds (required if PR 4 ever touches website/, else optional)
npm --prefix website run build

# No accidental scope creep
git diff --name-only <base>...HEAD
```

Additionally per PR:
- PR 1/4 (docs moves): `git grep -n "<moved-filename>"` must return no dangling references.
- PR 3 (old SDK): full `pytest tests -q`, with special attention to `tests/test_relationships.py`.
- PR 5 (dead component): `git grep -n "IntegrationsPage"` returns nothing; dashboard build green.

**This audit's validation results:** `pytest tests/test_runtime_events.py -q` → 9 passed;
`npm --prefix dashboard run build` → success (pre-existing >500 kB chunk-size warning only).
