# ObserveAgents — Customer Validation Report

**Date:** 2026-07-09
**Evaluator perspective:** CISO / VP Engineering / Head of AI evaluating the product before connecting real AI-agent runtime traffic.
**Method:** Full codebase review (FastAPI backend, React dashboard, marketing site), hands-on RBAC probing against a live instance, and execution of the project's own build/test/lint/smoke tooling. A small set of high-impact, low-risk fixes were applied and verified — see **Fixes applied in this pass**.

---

## A. Executive Summary

ObserveAgents tells a genuinely clear and honest product story: **Observe → Understand → Control**, driven by OpenTelemetry evidence, with an explicit "observe-only until control is configured — nothing is blocked automatically" stance. The core V2 pages (Overview, Runtime, Asset Intelligence, Security Intelligence, Gateway Control Center) are polished, evidence-backed, and have real empty/loading states. Security fundamentals are largely sound: BYOK provider keys are Fernet-encrypted, API keys are hashed and shown once, OTel content is scrubbed of prompt/response text at ingestion, org isolation is enforced, and no real secrets are committed.

However, the product is **not yet trustworthy enough for a paid pilot without remediation**. The headline problem was a **broken-access-control gap**: state-changing endpoints (claim/retire assets, the whole agent lifecycle, provider-billing import/edit) required only authentication, not an admin role — a non-admin analyst could retire agents and inject billing ground-truth. This pass fixes that. Beyond it, the product shows the seams of a recent rebrand/refactor: **terminology sprawl** (agent vs asset vs inventory; guardrail vs guard mode vs policy), ~8 orphaned pages and ~12 hidden-but-routable legacy hash routes, a demo build that leaked the production gateway hostname (fixed), hardcoded `Admin123!` default credentials in shipped files (fixed), and a **test suite that had bit-rotted** against prior project renames (partially fixed — 30 of 34 test files now pass, up from 25).

**Bottom line:** demo-ready for a controlled/internal demo today; needs the terminology and legacy-surface cleanup plus the remaining test/CI hardening before an external paid pilot.

---

## B. Customer Journey Scores (1–10)

| Area | Score | Rationale |
|---|---:|---|
| Product clarity | 7 | Strong Observe→Control narrative and honest observe-only framing; undercut by naming sprawl (asset/agent/inventory). |
| Setup flow | 7 | `Setup.jsx` is concrete and surface-aware with a live discovery counter; a competing legacy onboarding guide and a demo hostname leak (now fixed) hurt it. |
| Agent discovery | 7 | Auto-discovery from OTel + gateway works; discovered/unassigned/managed/retired lifecycle is real; but three overlapping inventory surfaces confuse the model. |
| Dashboard usefulness | 8 | V2 pages are evidence-first, worst-first, with good empty states and labeled sample-data pills. |
| Security / governance | 6 | Encryption/hashing/scrubbing are solid, but the mutation-authz gap (now fixed) and fail-open enforcement + plaintext prompt storage defaults need CISO attention. |
| Admin experience | 6 | Admin gating is mostly correct in the UI and now consistent in the API; hardcoded default creds and a prod-usable reset script (now fixed) were footguns. |
| UI polish | 6 | Clean core, but two parallel design-token systems, unused Tailwind dep, light-only theme, and raw-error-text surfacing. |
| Technical reliability | 6 | Backend boots cleanly, core tests pass; test suite had systemic path bit-rot (now largely fixed) and there is **no CI**. |
| Demo readiness | 7 | Very demo-able on the happy path; avoid the hidden legacy routes and the two half-built areas (Rules & Alerts, Ecosystem Discovery). |

---

## C. Critical Blockers

### C1 — Broken access control on state-changing endpoints  *(FIXED this pass)*  — **P0**
- **Issue:** Asset claim/edit/retire, the full `/agents` lifecycle (claim, approve-suggestions, ignore, validate, reject), and provider-billing import/edit required only `get_current_user`, not an admin role. A dead `require_admin` import at `app/routes/assets.py` confirmed an intended check had been dropped.
- **Customer impact:** A read-only or analyst user could retire ("hide from inventory") a production agent, rewrite ownership/criticality governance metadata, or inject false provider-invoice figures that drive cost reconciliation. For a governance product this is a direct integrity failure.
- **Evidence:** `app/routes/assets.py:205,265`; `app/routes/agent_inventory.py:178,227,290,336,401`; `app/routes/cost_intelligence.py:70,134`. `app/roles.py` shows viewer/analyst roles include the `assets`/`agent_inventory`/`governance` pages, so page-based gating did not block them — only a role guard could. Confirmed by live probe: a team-scoped analyst on the agent's own team received **200** on claim/approve/ignore/reject before the fix.
- **Fix applied:** Added `Depends(require_admin)` to all listed mutation endpoints (matching the already-admin-gated `PATCH /agents/{id}`), removed the dead import, and added a regression test `tests/test_mutation_rbac.py`. Post-fix probe: analyst → **403**, admin → unaffected.
- **Behavioral note:** analysts can no longer claim/validate/retire; those are now admin-only. If teams intend analysts to manage their own agents, introduce a dedicated `can_manage_assets` capability rather than reopening the endpoints.

### C2 — Terminology sprawl (asset vs agent vs inventory; guardrail vs guard mode vs policy)  — **P1**
- **Issue:** The same core object is labeled "AI assets discovered," "Agents discovered," "AI Assets," "Asset Inventory," "AI Agent Inventory," "Discovery Center," and "Asset Intelligence" across pages. Control vocabulary mixes "Guardrails," "Guard Modes," and "Policies" — and there is no policy UI at all (`dashboard/src/App.jsx` comment admits "Policies & rate limits have no dedicated UI yet").
- **Customer impact:** A CISO's first question becomes "is an asset the same as an agent?" It reads as an unfinished pivot and erodes confidence that the team has a settled product model.
- **Evidence:** `dashboard/src/ui2/OverviewV2.jsx` ("AI assets discovered") vs `dashboard/src/pages/DemoDashboardV2.jsx` ("Agents discovered"); nav labels in `dashboard/src/App.jsx` (`agent_inventory`="Agents", `intelligence`="Asset Intelligence", hidden `assets`="Asset Inventory", `discovery`="Discovery Center"); `website/index.html` "AI Asset Intelligence."
- **Recommended fix:** Pick one noun ("agent") for the object and one word ("control") for enforcement, and sweep labels. Report-only in this pass (copy/UX decision, not a code bug).

### C3 — Legacy/orphaned pages and hidden routable surfaces  — **P1**
- **Issue:** ~8 page components are shipped in the bundle but imported nowhere, and ~12 legacy pages remain reachable by typing a `#hash` (e.g. `#exec_dashboard`, `#home`, `#overview`, `#assets`, `#chat`, `#onboarding`, `#discovery`, `#ecosystem`) even though they were pulled from navigation. The legacy `#onboarding` guide contradicts the current setup story and deep-links to other legacy pages.
- **Customer impact:** A diligent evaluator who explores will hit contradictory, half-abandoned screens and conclude the product is unfinished.
- **Evidence:** `dashboard/src/App.jsx` `PAGES`/`renderPage()` and the `NAV_GROUPS_*` definitions; orphaned files under `dashboard/src/pages/` (e.g. `OverviewHub.jsx`, `RuntimeTimeline.jsx`, `AssetIntelligence.jsx`, `GatewayControlCenter.jsx`, `PlatformGuide.jsx`) and `components/IntegrationsPage.jsx`.
- **Recommended fix:** Delete the orphaned files and remove the legacy hash routes (or gate them behind a debug flag). Report-only — deferred because it is a larger UI cleanup that should be reviewed by the product owner.

---

## D. Important Improvements (non-blocking)

1. **Half-built features are visible in the live UI.** `dashboard/src/pages/RulesAlertsV2.jsx` ships a rule catalog where 5 of 9 rules are `implemented: false` (rendered at 60% opacity with a "planned" pill), and Setup's "Ecosystem Discovery" is a "Coming later" preview for connectors that don't exist. Honest, but plan the demo path to avoid dwelling here.
2. **Two design-token systems coexist** (`dashboard/src/theme.js` exports `T`; `dashboard/src/ui2/tokens.js` exports `C`) with duplicated hex values; **Tailwind v4 is a dependency but effectively unused** (all styling is inline style objects); the app is **light-only** despite a tokens.js comment promising a dark theme.
3. **Error handling surfaces raw text.** No toast system; several pages render `e.message` or even `await r.text()` (`dashboard/src/components/BudgetsPage.jsx`) directly, and `PageErrorBoundary` shows raw `error.message`. A 500's body can render verbatim.
4. **`make verify` covers only 6 of 34 test files.** It's a thin isolation/structural gate; the substantive suites (asset intelligence, OTel ingestion, GenAI semconv, runtime) are not part of it, so a "verify passed" signal is misleadingly narrow.
5. **No dependency pinning for Python** (`requirements.txt` is lower-bounds only, no lockfile) and **`pytest`/`httpx` are not declared** even though 23 test files need them — reproducibility gap.
6. **`DEVELOPMENT.md` is stale** — uses the old project name `ai-asset-management`, lists pages that no longer exist, and documents a default admin password that the code does not use. First-read credibility hit.

---

## E. Bugs Found

| # | Bug | Evidence | Status |
|---|---|---|---|
| E1 | Mutation endpoints missing role checks | see C1 | **Fixed** |
| E2 | Public demo build leaked the production gateway hostname in copy-paste API-key snippets | `dashboard/src/components/ApiKeysPage.jsx` and `OnboardingPage.jsx` ignored the `demoMode` prop and called `gatewayBaseUrl()` with no arg (defaults to prod) | **Fixed** — thread `demoMode` through to `gatewayBaseUrl(demoMode)` |
| E3 | Hardcoded `Admin123!` default admin credentials in shipped files | `reset_admin.py`, `.env.example`, `app/migrate_orgs.py` (the last also logged the plaintext) | **Fixed** — random password + banner, env/argv-required reset, no plaintext logging |
| E4 | Error responses leaked raw exception text | `app/routes/cost_intelligence.py:100,151`, `app/routes/pricing_registry.py:102` | **Fixed** — generic messages + server-side `log.warning` |
| E5 | Test suite bit-rot: 8 files hardcoded obsolete absolute paths (`/home/user/ai-asset-management`, `/home/user/aifinops-guard`) from prior renames, so they errored at collection | `tests/test_relationships.py`, `test_credential_save_errors.py`, `test_slowapi_response_compat.py`, `test_startup_secret_check.py`, `test_provider_not_configured.py`, `test_pricing_estimated.py`, `test_asset_registry.py` | **Mostly fixed** — replaced with a portable `os.path.dirname(...)` root; recovered ~5 files fully |
| E6 | Test suite bit-rot: proxy tests patch `app.main.get_client_for_org` / `proxy_chat_complete`, which no longer intercept after the proxy moved to `app/routes/proxy.py` → tests get 424 `provider_not_configured` | `tests/test_upstream_error_telemetry.py`, `test_pricing_estimated.py`, `test_asset_registry.py`, `test_agent_discovery_lifecycle.py` | **Partially fixed** — corrected target where it fully recovered coverage; see Known-remaining below |
| E7 | `dashboard` lint has 170 errors (mostly `react-hooks/static-components`, plus `no-undef` on `process` in `vite.config.js`) | `npm run lint` | **Report-only** — pre-existing, not introduced here |

**Known-remaining test failures (documented, not masked):**
- `test_agent_discovery_lifecycle.py` and `test_asset_registry.py` — deeper drift: even with corrected mocks the proxy discovery flow no longer creates the registry row the tests expect (identity/asset_key evolution). Needs test updates to match current behavior; reverted to original to avoid a misleading partial change.
- `test_pricing_estimated.py` (1/9) — asserts an unknown model logs a warning; current code path doesn't emit it.
- `test_upstream_error_telemetry.py` (1/7) — asserts the telemetry `agent` equals the `X-Guard-Agent` header, but identity now resolves the agent name from the API-key scope.

**Final tally:** 30 of 34 test files green (up from 25 before this pass); `make verify` green; dashboard and website builds green; dashboard smoke check green.

---

## F. Security / Trust Findings

**Fixed this pass:** C1 (broken access control), E2 (demo hostname leak), E3 (hardcoded admin credentials + plaintext credential logging), E4 (exception-text leakage).

**Reassuring (credit where due):**
- BYOK provider credentials and webhook URLs are Fernet-encrypted at rest; only `last4`/host are ever returned (`app/models.py`).
- `gk-` API keys are stored as SHA-256 hash + prefix and shown once (`app/auth.py`).
- OTel ingestion scrubs all prompt/response/tool content to `{redacted, sha256, size}` — raw content is never persisted (`app/otel_privacy.py`).
- Org identity is always re-resolved from the DB, never trusted from the JWT; null-org callers are hard-401; a tenancy-hardening gate blocks telemetry reads until org backfill completes (`app/auth.py`).
- Production can never enter demo mode even if `DEMO_MODE=true` (`app/config.py`); `/docs` is disabled unless `DEBUG=true`; security headers + HSTS + login rate-limiting are applied; `render.yaml` uses `generateValue`/`sync:false` for all secrets; **no real secrets are committed** (every key-shaped string is an explicit test fixture).

**Report-only trust findings (no code change; flag for the security conversation):**
- **Intra-org team-scope bypass on reads:** `/runtime/*`, `/intelligence/*`, and `/relationships*` filter by `org_id` only and ignore team-scoped roles, so a team-walled analyst can still read every team's traces, findings, and dependency graph. Cross-**org** isolation is intact. (`app/routes/runtime.py`, `asset_intelligence.py`, `relationships.py`.)
- **Enforcement is best-effort, not guaranteed:** default posture is observe-only, and if the enforcement pipeline throws or the (process-local) circuit breaker is open, requests fail **open** by design (`app/routes/proxy.py`). "Gateway Control" is recommendation-only today — worth stating plainly to buyers.
- **Prompt/response stored in plaintext by default on the gateway/chat path** (`pii_redaction_mode="full"`, `pii_detection_enabled=False` in `app/org_config.py`). The OTel path never stores content; the proxy path does. Non-admins get sensitive rows blanked at read time, but the raw text is persisted.
- **JWT stored in `localStorage`** (`dashboard/src/api.js`) — XSS-exfiltratable; a pen-test will flag it. Consider httpOnly cookies.
- **`scripts/seed_demo_data.py` writes fake "Acme AI Operations" data through the real pipeline without `is_demo=True` and with no production guard** — the demo *service* isolates demo data correctly, but this CLI *script* bypasses that tagging. Add an `is_demo` tag or a production-DB guard before shipping it as an operator tool.

---

## G. Customer Confusion Points

- **"Do I need to give ObserveAgents my full codebase?"** No — and the product should say so louder. It consumes OpenTelemetry traces (or gateway-proxied calls), not source. The `ai_agent_inventory/` SDK is an optional thin client wrapper. State this on the Platform Guide.
- **"What's the difference between telemetry and the registry?"** Telemetry/runtime = raw evidence (immutable, auto-discovered). Registry = customer-governed metadata (owner/team/criticality/lifecycle) you manage on top. The UI blurs this by exposing multiple "inventory" surfaces (see C2).
- **"What is an unmanaged/unassigned agent?"** One discovered from runtime that no admin has claimed yet — it has evidence but no ownership. Clear in code; make it explicit in the empty states.
- **"Is the gateway inline or observe-only?"** Observe-only by default; it only enforces when a team is explicitly put in `enforce` mode. Say this on the Gateway Control Center page.
- **"What happens if enforcement blocks a request?"** In `observe`/`alert` it never blocks (logs a `would_block` finding); in `enforce` it blocks — but fails **open** if the pipeline errors. Buyers will want this documented precisely.

---

## H. Recommended Product Changes

**Must fix before an external demo**
1. ✅ Close the mutation-authz gap (C1) — **done**.
2. ✅ Stop the demo build leaking the production gateway hostname (E2) — **done**.
3. ✅ Remove hardcoded `Admin123!` defaults and plaintext credential logging (E3) — **done**.
4. Decide the demo script/path so the presenter avoids the hidden legacy routes and the two half-built areas (Rules & Alerts, Ecosystem Discovery).

**Should fix before a paid pilot**
5. Terminology sweep — one noun for the object, one word for control (C2).
6. Delete orphaned pages and remove/guard the legacy hash routes (C3).
7. Add a minimal CI pipeline (run the full test suite + lint on PR) and expand `make verify` beyond 6 files; pin Python deps and add `pytest`/`httpx` to a dev-requirements file.
8. Update or remove the remaining bit-rotted tests (E6 known-remaining) so the suite is fully green.
9. Refresh `DEVELOPMENT.md` to the current product name, page list, and admin-bootstrap behavior.
10. Decide the position on team-scope read exposure, fail-open enforcement, and default plaintext prompt storage — and document each for buyers.

**Nice to have later**
11. Consolidate the two design-token systems, drop unused Tailwind, and add a dark theme.
12. Add a toast/notification system and stop rendering raw error bodies.
13. Move the JWT to an httpOnly cookie.

---

## I. Suggested Copy Improvements

- Overview metric: standardize on **"Agents discovered"** everywhere (drop "AI assets discovered" / "AI Assets").
- Platform Guide, add a one-liner: **"ObserveAgents reads OpenTelemetry traces from your agents. It never needs access to your source code."**
- Gateway Control Center header: **"Observe-only by default. ObserveAgents recommends controls; it enforces only for teams you explicitly switch to Enforce mode — and never silently."**
- API Keys page: keep the excellent "Never place OpenAI keys in customer code" note; add "This gateway key (`gk-…`) authenticates your traffic to ObserveAgents. It is not your OpenAI key."
- Rules & Alerts: label the section **"Detection Rules (preview)"** and group planned rules under a clearly separated "Coming soon" heading rather than dimmed inline rows.

---

## J. Final Verdict

**Ready for an internal / controlled demo now; not yet ready for an external paid pilot without the "should fix before pilot" items.**

In plain language: the product's story is clear and its core screens are strong and honest, and the most dangerous issue — non-admins being able to change governance state — is fixed. What still stands between it and a paying customer's trust is polish and consistency, not architecture: settle the naming, remove the abandoned pages, stand up CI, and finish or hide the half-built areas. Do those and this becomes a credible pilot product.

---

### Fixes applied in this pass (commit-ready)
- **Security — RBAC:** `require_admin` added to asset claim/registry-update, the five `/agents` lifecycle actions, and the two `/billing` mutations; dead import removed; regression test `tests/test_mutation_rbac.py` added.
- **Frontend — demo leak:** `demoMode` threaded into `ApiKeysPage` and `OnboardingPage` so demo builds use the demo gateway URL.
- **Credential hygiene:** `.env.example` placeholder commented out; `app/migrate_orgs.py` generates a random admin password (or uses `ADMIN_SEED_PASSWORD`) and no longer logs plaintext; `reset_admin.py` requires an explicit password via env/argv.
- **Error hygiene:** exception text replaced with generic client messages + server-side logging in `cost_intelligence.py` and `pricing_registry.py`.
- **Test infrastructure:** obsolete hardcoded paths and (where it fully recovered coverage) stale proxy mock targets corrected — 30/34 test files now green (was 25/34).

*Verification performed: live RBAC probe (viewer/analyst → 403, admin → unaffected), `make verify` green, full per-file test run, dashboard `npm run build` + `smoke_check.cjs` green, website build green, fresh-boot admin-password check (random password, no `Admin123!`).*
