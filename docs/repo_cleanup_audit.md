# Repo Cleanup Audit

*Audit only — this document changes nothing. Every classification is backed by the
evidence listed (imports, git grep, router/nav checks, Makefile, render.yaml,
package.json scripts, deployment config, live README/doc links). Uncertain files are
classified REVIEW or ARCHIVE, never DELETE. Cleanup itself happens in separate,
individually-approved PRs — none are created by this audit.*

Audit date: 2026-07-19 · Base: `main` @ `c97d8b5` (source of truth).
Supersedes the 2026-07-13 audit (whose five cleanup PRs were executed and merged).

**Standing facts this audit treats as ground truth:** the Python SDK is **implemented
and packaged** under `sdk/python/` (`pyproject.toml`, package `observeagents` v0.1.0,
customer README, 6 source modules, 5 test modules wired into `make test`); the
telemetry batch-ingestion path (`/api/v1/telemetry/batch` + queue/worker + risk
findings) is shipped; there is no `.github/` directory (no CI — `make verify`/`make
test` are the only gates, run locally).

---

## Executive Summary

The tree itself is healthy: **no tracked build artifacts** (`git ls-files` clean of
`__pycache__`/`dist/`/`egg-info`), **no dead backend modules** (every `app/` module has
a verified importer), archive links all resolve, and `Makefile`/`render.yaml`/
`package.json` reference only real files. **Nothing in this audit warrants DELETE.**

The real debt is of two kinds:

1. **Documentation drift after fast parallel development** — the root README carries
   **7 links to 3 deleted docs**, `docs/architecture.md` is wrong on four verifiable
   counts (table count, router count, Alembic head, one broken link), a design doc's
   header claims "nothing implemented" above a fully shipped feature, and
   `DEVELOPMENT.md` still describes the pre-rename, pre-ui2 project.
2. **Unrouted UI left behind by the ui2 migration** — 9 unimported page components,
   including one **live navigation bug**: routed pages still link to `guardrails`,
   which has no route, so clicking the card renders a blank page.

## Cleanup Principles

- Preserve: `app/` (all modules verified live), `alembic/` (never remove migrations;
  head `c0d1e2f3a4b5`), `tests/` (51 files, all resolvable from `make test`),
  `sdk/python/**` (shipped SDK), `dashboard/` routed pages + all `components/`,
  `website/` sources (deployed Render static service), `render.yaml`,
  `requirements.txt`, `Makefile`, `alembic.ini`, `.env.example`, `reset_admin.py`,
  `scripts/seed_demo_data.py` (test-protected), all `docs/` (none qualify for delete).
- Prefer ARCHIVE over DELETE; prefer REVIEW over ARCHIVE when a decision or fix is
  needed first.
- A doc is "source of truth" only if verified against the current implementation and
  active navigation — never by filename or age.

## Active Core — Keep (verified)

| Area | Evidence |
|---|---|
| `app/` — all modules incl. `ingestion/`, `telemetry_ingest/`, `risk_processor.py` | every module has ≥1 importer (e.g. `telemetry_ingest/worker.py` ← `routes/telemetry_v1.py:30` + `startup.py:325`; `scanner.py` ← `main.py:43`; `migrate_orgs.py` ← `startup.py:125`) |
| `sdk/python/**` | packaged (`pyproject.toml`), tested (`Makefile:31` runs `sdk/python/tests`), backend-acceptance test imports both `app.main` and `observeagents` |
| `dashboard/` routed pages (19) + `components/` (15/15 imported) + `ui2/` (all but one) | router `App.jsx:858-905`; `components/CollapsiblePanel.jsx` ← `CostIntelligence.jsx:14` |
| `scripts/seed_demo_data.py` | `README.md:285`, `DEVELOPMENT.md`, `docs/architecture.md`, **`tests/test_seed_demo_data.py`** |
| docs core set: `otel-deployment-guide` (canonical OTLP), `telemetry_ingestion` (only doc for the batch path — load-bearing), `customer-integration-guide`, `create_first_agent_guide`, `sdk-guide`, `runtime-flow`, `asset_intelligence`, `ai_agent_runtime_security_intelligence`, `product_discovery_model`, both plan docs (`auto_instrumentation_first…`, `reasoning_observability…` — verified genuinely-future), `docs/README.md` (all 17 links resolve), `otel_unmapped_fields_walkthrough` | per-file verification vs code & nav (see agent evidence in tables below) |
| Root/config: `Makefile` (all 16 referenced test files exist), `render.yaml` (4 services match tree), both `package.json`s, `alembic.ini`, `.vscode/` | direct reads + cross-checks |

## REVIEW — needs a fix or a decision (not removal)

| Path | Finding | Evidence | Risk |
|---|---|---|---|
| **`dashboard` nav → `guardrails`** | **Live bug**: routed pages link to page id `guardrails` but the router has no `case "guardrails"` → blank page on click | links: `PlatformGuideV2.jsx:46` (clickable card), `ExecutiveDashboard.jsx:193,207`, `ui2/Sidebar.jsx:24` icon, `App.jsx:1003` filter list; no route in switch | **High (UX)** — decide: re-route `Guardrails.jsx` or remove the links |
| `README.md` (root) | 7 links to 3 deleted docs (`ui_redesign_plan.md` ×3, `ui_contract.md` ×3, `demo_seed_data.md` ×1); page table omits live Telemetry Quality; API reference omits `/api/v1/telemetry/batch`, `/risk-findings`, `/agents/{id}/timeline`, `/detection-rules` | deletions confirmed via `git log --diff-filter=D` (`70c2d14`, `1c1578a`, `3aadaa6`) | Medium — front-door credibility |
| `docs/architecture.md` | broken `demo_seed_data.md` link (`:12`); "24 tables" vs **30** `__tablename__` in `app/models.py`; "14 routers" vs **20** registered in `app/main.py`; Alembic head cited `d5e6f7a8b9c0` vs real `c0d1e2f3a4b5` | line-verified | Medium |
| `docs/ai_agent_detection_rules_alerts_design.md:3` | Header banner says "nothing in this file is implemented" — contradicted by 5 shipped endpoints (`routes/detection_rules.py:103-210`), migration `c0d1e2f3a4b5`, live Rules & Alerts page, and the file's own `:320`/`:488` "shipped" notes | line-verified | Low (one-line banner fix) |
| `DEVELOPMENT.md` | Calls the project `ai-asset-management` (`:24,:174,:202`); project-structure section predates ui2 (3 route modules listed vs 20; no V2 pages, no `sdk/`, no `alembic/`); advertises default admin `Admin123!` contradicting `.env.example:54-58` (random seeded password); orphaned — linked from nowhere | line-verified | Medium — misleads new developers |
| `docs/telemetry_ingestion.md` | `## Risk Findings v1` section duplicated verbatim (`:251` and `:327`, ~75 lines) | sed-verified | Low (dedupe) |
| `dashboard/src/` ×11 code comments | cite deleted `docs/ui_redesign_plan.md` as the rollback-policy source (`App.jsx:26,34,42,45,81`; 5 V2 pages; `ui2/OverviewV2.jsx:21`) — the V1-rollback policy has **no surviving written definition** | grep-verified | Medium — blocks archiving the V1 pages (below) until policy is restated |
| `requirements.txt` | `httpx` imported at `app/notifications.py:30` but undeclared (arrives transitively via `openai`); `pytest` undeclared anywhere though `Makefile` runs it | grep-verified | Medium (latent breakage) |
| `docs/roadmap.md` | `:56` "no PyPI yet" vs `sdk-guide.md:46` + `sdk/python/README.md:14` instructing `pip install observeagents` (publish status must be settled one way); telemetry batch-ingestion MVP absent from the runtime-evidence track | line-verified | Low |
| `docs/gateway_control_center_architecture.md:5` | names `GatewayControlCenter.jsx`; live page is `GatewayControlCenterV2.jsx` (`App.jsx:877`) | line-verified | Low (one line) |
| `.env.example` | omits `TELEMETRY_WORKER_ENABLED`/`TELEMETRY_WORKER_MODE` (read by `telemetry_ingest/worker.py:18,55`); model-name comments drifted | line-verified | Low |
| `.github/` absent | no CI enforces `make verify`/`make test`/`eslint` on PRs | `ls`/`git ls-files` | Decision item (gap, not cleanup) |
| `app/routes/` auth helpers | `_get_org_id`/`_get_api_key_id` duplicated ×3 (`otel.py:80,89`, `runtime_events.py:38,46`, `telemetry_v1.py:45,53`) + 2 `_org_id` variants (`detection_rules.py:42`, `pricing_registry.py:19`) — 8 defs, 2 shapes | grep-verified | Low (consolidation refactor; signatures differ, read before merging) |
| `docs/telemetry_post_merge_validation.md` | accurate point-in-time PR checklist (all 9 named test files + every artifact verified to exist) — placement call: keep live or move to `archive/reports/` | verified | Low |

## ARCHIVE candidates (safe once the noted gate clears)

| Path | Why | Evidence | Gate |
|---|---|---|---|
| `dashboard/src/pages/DemoDashboard.jsx` | zero references anywhere (not even a rollback comment); superseded twice (→ DemoDashboardV2 → OverviewV2) | grep: no importer, no comment | none — strongest candidate |
| `dashboard/src/ui2/EvidenceCard.jsx` | zero importers repo-wide | grep | none |
| V1 rollback set: `pages/{AssetIntelligence, GatewayControlCenter, RuntimeTimeline, SecurityIntelligence, PlatformGuide, OverviewHub, DemoDashboardV2}.jsx` | each unimported; each declared "stays in the tree for rollback" in `App.jsx` comments | router + grep verified per file | **gated on** restating the rollback policy (its source doc `ui_redesign_plan.md` was deleted) — note `SecurityIntelligence.jsx` was still edited on 2026-07-18 while unrouted |
| `dashboard/src/pages/Guardrails.jsx` | unimported, unrouted | router check | **gated on** the `guardrails` nav-bug decision above (re-route vs remove links) |
| `scripts/{seed_synthetic_enterprise, generate_synthetic_traffic, synthetic_payloads}.py` | self-contained cluster, zero references outside `scripts/` (their doc `synthetic_enterprise.md` was archived earlier); natural destination `docs/archive/scripts/` where the prior synthetic harness already lives | grep over live docs/tests/Makefile/render.yaml: nothing | owner confirm the 3-org synthetic demo is no longer used |

## DELETE candidates

**None.** Every candidate above is either gated on a decision or has historical value;
per the audit rules, uncertain items stay REVIEW/ARCHIVE.

## Duplicate / Conflicting Docs

| Docs | Verdict |
|---|---|
| `otel-deployment-guide` / `telemetry_ingestion` / `customer-integration-guide` / `create_first_agent_guide` / `sdk-guide` / `runtime-flow` | **Not duplicates** — verified distinct scopes (OTLP canonical · batch-API + risk findings (only doc) · org rollout phases · 15-min hands-on on the batch path · SDK reference · post-parse pipeline). Keep all six. |
| `sdk-guide.md` vs `sdk/python/README.md` | Long form vs package short form — intentional pair, keep both. |
| `roadmap.md` vs `sdk-guide.md` on PyPI | Real contradiction ("no PyPI yet" vs `pip install observeagents`) — settle by publishing or rewording. |
| Archive supersession pointers | All correct and resolving (`archive/superseded/otel_ingestion.md` → `otel-deployment-guide.md`, etc.). |

## Scripts Review

| Script | Referenced by | Class |
|---|---|---|
| `seed_demo_data.py` | README, DEVELOPMENT.md, architecture.md, `tests/test_seed_demo_data.py` | **KEEP** |
| `seed_synthetic_enterprise.py` | only its sibling scripts | ARCHIVE candidate (gated) |
| `generate_synthetic_traffic.py` | only its sibling scripts | ARCHIVE candidate (gated) |
| `synthetic_payloads.py` | only its sibling scripts | ARCHIVE candidate (gated) |

No script is referenced by Makefile, render.yaml, or any CI (none exists).

## Root-Level Files Review

`README.md` REVIEW (links/coverage) · `DEVELOPMENT.md` REVIEW (rewrite) ·
`Makefile`, `render.yaml`, `alembic.ini`, `requirements.txt` (2 dep gaps → REVIEW),
`.env.example` (REVIEW, minor), `reset_admin.py`, `.vscode/` — KEEP.
No tracked artifacts; `.gitignore` covers `dist/`, `egg-info`, `__pycache__`.

## Suggested Cleanup PRs (not created by this audit)

1. **Docs truth pass** — fix README broken links + page/API tables; architecture.md
   four corrections; detection-rules banner; gateway-arch one-liner; roadmap PyPI line
   + batch-ingestion milestone; telemetry_ingestion dedupe. Docs-only.
2. **Guardrails nav decision** — re-route or remove the dead `guardrails` links
   (+ optionally archive `Guardrails.jsx`). Small dashboard PR, build-verified.
3. **DEVELOPMENT.md rewrite** — current structure, correct name, correct admin-seed
   flow; link it from README.
4. **V1 rollback retirement** — restate the rollback policy in a short doc (replacing
   the deleted `ui_redesign_plan.md` citations), then archive the 7 V1 pages +
   `DemoDashboard.jsx` + `EvidenceCard.jsx`. Requires dashboard build + smoke check.
5. **Dependency hygiene** — declare `httpx`; add dev/test requirements (pytest);
   optionally `.env.example` worker vars.
6. **(Decision) CI bootstrap** — `.github/workflows` running `make verify`, per-file
   pytest sweep, dashboard/website builds. Biggest risk-reducer on this list.
7. **(Gated) synthetic-scripts archive** — move the 3-script cluster to
   `docs/archive/scripts/`.

## Do Not Touch

`app/**` (all live) · `alembic/**` · `tests/**` · `sdk/python/**` · routed dashboard
pages + all `components/` · `website/` sources · `render.yaml` · `Makefile` ·
`requirements.txt` (additions only) · `scripts/seed_demo_data.py` · all of
`docs/archive/**` (clean, correctly cross-linked).

## Validation (run for this audit, honest results)

- `pytest tests/test_runtime_events.py -q` → **9 passed** ✅
- `pytest sdk/python/tests -q` → **24 passed** ✅
- `make verify` → **all harnesses passed** ✅
- `npm --prefix dashboard run build` → ✓ built ✅
- `npm --prefix website run build` → ✓ built ✅
- Targeted `git grep` checks were run per candidate (router case for `guardrails`,
  importer search per page/component/module, reference search per script/doc link);
  key ones re-verified independently: `guardrails` has no route; `DemoDashboard.jsx`
  has zero external refs; the 3 deleted docs are linked 7× from README; roadmap says
  both "shipped (PR #114)" and "no PyPI yet".
- Not available in this environment: none — all requested commands ran.

After each future cleanup PR: re-run the five commands above, plus
`git grep -n "<moved-or-removed name>"` to prove no dangling references.
