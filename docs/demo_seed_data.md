# Demo Seed Data

One command populates a local/dev database with a realistic ObserveAgents demo: five AI systems observed via OpenTelemetry, with execution traces, discovered assets, derived capabilities, and findings across all five intelligence categories.

**This is synthetic demo data for local/dev use — not production data.**

---

## Run it

From the repo root, with the same environment variables the backend uses (`DATABASE_URL`, `JWT_SECRET`, `CREDENTIAL_ENCRYPTION_KEY`):

```bash
python scripts/seed_demo_data.py
```

Safe to run multiple times — traces already present are skipped, and capability/finding derivation is idempotent. A second run reports `0 seeded, 5 already present`.

### Alternative: the "Populate Organization" button

Platform admins (demo/dev environments only) can seed the same five AI systems into **any organization** from the dashboard: pick the org in the sidebar's **Platform View** switcher and click **Populate Organization**. This seeds the gateway demo data *and* the OTel runtime intelligence demo into the selected org — Runtime and Asset Intelligence fill immediately. **Clear Demo Data** removes both. Note: the Runtime and Asset Intelligence pages always show the organization you are currently viewing, so make sure the Platform View selection matches where you seeded.

## Demo login

| | |
|---|---|
| Organization | Acme AI Operations (`acme-ai-ops`) |
| Email | `demo@observeagents.ai` |
| Password | `Demo123!` |
| Role | admin |

The user and organization are created on first run and reused afterwards.

---

## What gets created

Everything flows through the **real ingestion pipeline** — OTLP JSON payloads are passed through `parse_otlp_json()` → `normalize_spans()` → `derive_asset_intelligence()`, the same code that handles live traffic. Nothing is hand-inserted into derived tables, and privacy scrubbing is not bypassed.

### Five AI systems

| Service | Environment | Trace | Notable |
|---|---|---|---|
| `support-agent` | production | 8.4s customer escalation | LLM planning, retrieval, Jira, CRM (with nested HTTP hop), Slack, final LLM |
| `finance-analyst-agent` | production | 11.2s finance analysis | Document retrieval, PostgreSQL query, Python tool |
| `engineering-copilot` | staging | 6.2s code suggestion | GitHub repo context, MCP tool call via `acme-mcp-hub` |
| `hr-onboarding-bot` | production | 4.6s onboarding | Knowledge base, ServiceNow workflow (nested HTTP hop), Slack |
| `research-agent` | development | 7.3s research request | Web search, **one ERROR span** (synthetic upstream timeout), LLM summarization |

### Derived data (typical first run)

- 5 traces / 30 spans (`otel_spans`)
- 5 OTel evidence rows (`otel_assets`), all linked to `asset_registry`
- 5 canonical inventory rows (`asset_registry`, `discovery_source="otel_trace"`)
- ~32 capabilities across types: provider, model, retrieval, crm, messaging, mcp, database, external_api, source_control, runtime
- ~22 findings across all five categories:
  - **security** — `database_access`, `mcp_enabled`, `sensitive_system_access`
  - **performance** — `slow_runtime_step`
  - **operations** — `production_runtime`, `runtime_error`, `unmanaged_runtime`
  - **dependency** — `external_api_access`, `broad_tool_access`
  - **inventory** — `new_ai_system_detected`

---

## Where to look after seeding

Log in as the demo user and open:

1. **Runtime** — five traces across three environments; click `support-agent customer escalation` for the trace waterfall (note the nested `crm.http_call` hop), and the research-agent trace for the error span.
2. **Asset Intelligence** — Discovered Assets / Capabilities / Findings tabs; try the category and severity filters, expand a finding for its evidence, and use Resolve/Dismiss.
3. **Agents / Inventory** — the five discovered AI systems, all `potential` status awaiting review.

---

## Resetting / re-running

Re-running is always safe and changes nothing once seeded. To start fresh:

- **Dev SQLite:** delete the database file pointed to by `DATABASE_URL` and restart the server (migrations + seed run again), or
- **Targeted reset:** delete the Acme org's rows from `otel_spans`, `otel_assets`, `provenance_events`, `agent_relationships`, `asset_capabilities`, `asset_findings`, and `asset_registry`, then re-run the script.

Trace IDs are deterministic (`sha256("acme-demo-trace:<service>")`), so re-seeding after a reset produces identical traces.

---

## Privacy

All seeded data is synthetic:

- No real prompts or responses — LLM spans carry only model names, provider names, and token counts.
- No secrets, API keys, or credentials.
- No customer PII — URLs use reserved `.example` domains.
- The sensitive-attribute scrubber runs exactly as in production (there is simply nothing sensitive to scrub).
