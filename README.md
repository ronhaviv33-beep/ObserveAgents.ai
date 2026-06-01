# AIFinOps Guard

**Observability, Security and FinOps for Enterprise AI Agents**

> "Datadog + CrowdStrike for AI Runtime" — visibility, governance, security, and cost intelligence for enterprise AI.

---

## Overview

AIFinOps Guard is an AI Runtime Intelligence platform that sits between AI agents and LLM providers. It collects telemetry, enforces budgets, detects anomalies, and provides a full observability dashboard across all AI activity.

**Problems it solves:**

- Who is using AI, which models, and how much is it costing?
- Which agents are looping, spiking in cost, or using unapproved models?
- Is sensitive data being sent to external LLMs?
- How do we enforce budget limits before tokens are consumed?

---

## Architecture

```text
Agent / Application
        ↓
AIFinOps Gateway  ←─ Budget enforcement, policy checks
        ↓
LLM Provider (OpenAI · Anthropic · Google · Local)
        ↓
Telemetry Collection  ←─ tokens, cost, latency, model
        ↓
SQLite Database
        ↓
React Dashboard  ←─ live observability, alerts, budgets
```

---

## Tech Stack

### Backend
| Layer | Technology |
|---|---|
| Runtime | Python 3.14 |
| API Framework | FastAPI |
| ORM | SQLAlchemy |
| Database | SQLite |
| Server | Uvicorn |

### Frontend
| Layer | Technology |
|---|---|
| Framework | React + Vite |
| Styling | Tailwind CSS v4 |
| Charts | Recharts |
| Icons | Lucide React |

---

## Features

### ✅ AI Gateway
- Single `/ask` endpoint routes to any supported LLM provider
- Provider auto-detected from model name (no config changes needed)
- Full request/response telemetry stored on every call

### ✅ Multi-Provider Support (15 models)
| Provider | Models |
|---|---|
| OpenAI | `gpt-4o`, `gpt-4o-mini`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-4-turbo`, `o3`, `o4-mini` |
| Anthropic | `claude-opus-4`, `claude-sonnet-4`, `claude-haiku-4` |
| Google | `gemini-2.0-pro`, `gemini-2.0-flash`, `gemini-1.5-pro` |
| Local | `llama-3.1-70b-local`, `llama-3.1-8b-local` |

### ✅ Cost Intelligence
- Per-request cost calculation using real per-1M-token pricing
- Cost breakdown by team, agent, model, workflow
- Savings estimator (premium model right-sizing, loop detection, failed workflows)

### ✅ Budget Enforcement
- Budget rules per team and/or agent (daily or monthly)
- **`action=alert`** — request proceeds, warning returned in response
- **`action=block`** — request rejected (HTTP 429) before any tokens are consumed
- 80% threshold warning before limits are hit
- Full CRUD API for budget rules

### ✅ Runtime Intelligence
- Agent activity monitoring (requests, cost, latency, errors)
- Workflow health tracking with failure rate badges
- Runtime Chain — end-to-end trace per agent (tool → model → cost → risk)
- AI Runtime Risk Score (0–100 composite across 6 factors)

### ✅ Security & Governance
- 8 automated detection rules:
  - Agent cost spike
  - Unusually large prompt
  - Workflow failure spike
  - Premium model on trivial prompts
  - After-hours activity
  - Agent loop detection
  - Unapproved model usage
  - Sensitive data in requests
- Each alert includes expandable "Why this fired" explanation with root causes and recommended action
- Governance allowlist — Google models flagged as unapproved by default

### ✅ Observability Dashboard
- **Home** — Risk score ring, savings card, executive summary, critical signals
- **Overview** — KPI stats, cost trend chart, top agents by cost
- **Cost Intelligence** — Cost by team (bar), by model (pie), expensive workflows table
- **Agent Activity** — All agents with live metrics
- **Model Usage** — Performance, spend, governance posture per model
- **Workflow Health** — Failure rates with health status badges
- **Alerts** — All active alerts with full explanation panels
- **Budgets** — Budget rules management, live progress bars per team
- Auto-refresh every 30 seconds
- **Live mode** (real API data) / **Demo mode** (6,000 synthetic events) — switches automatically

---

## API Reference

### Gateway

```http
POST /ask
```
```json
{
  "team": "SOC",
  "agent": "IR-Agent",
  "prompt": "Analyze this phishing email",
  "model": "gpt-4o-mini",
  "system_prompt": "You are a security analyst."
}
```

Response includes `response`, `model`, `prompt_tokens`, `completion_tokens`,
`total_tokens`, `latency_ms`, `cost_usd`, `telemetry_id`, `budget_warnings`.

---

### Telemetry

```http
GET /telemetry?skip=0&limit=100
GET /telemetry/summary
```

---

### Budgets

```http
POST   /budgets              # create a rule
GET    /budgets              # list all rules
DELETE /budgets/{id}         # delete a rule
GET    /budgets/status       # live spend vs limit for every rule
```

Example rule:
```json
{
  "team": "SOC",
  "agent": "IR-Agent",
  "limit_usd": 5.00,
  "period": "daily",
  "action": "block"
}
```

---

## Quick Start

### Prerequisites
- Python 3.12+
- Node.js 18+

### Backend

```bash
# 1. Clone and enter the repo
git clone https://github.com/ronhaviv33-beep/aifinops-guard.git
cd aifinops-guard
git checkout claude/kind-faraday-yoNJq

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\Activate.ps1       # Windows PowerShell

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure API keys (.env file in project root)
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# GOOGLE_API_KEY=AIza...
# LOCAL_LLM_URL=http://localhost:11434/v1

# 5. Start the gateway
uvicorn app.main:app
# → http://localhost:8000/docs
```

### Frontend Dashboard

```bash
cd dashboard
npm install
npm run dev
# → http://localhost:5173
```

> The dashboard auto-connects to the backend via the Vite dev proxy.
> Empty database = demo mode. Send a real `/ask` request to switch to live mode.

---

## Roadmap

### Phase 1 – Gateway Foundation ✅
- FastAPI Gateway
- SQLite Storage
- Telemetry API

### Phase 2 – LLM Integration ✅
- OpenAI Integration
- Anthropic Integration
- Real Token Tracking
- Latency Measurement

### Phase 3 – Cost Intelligence ✅
- Cost Calculation (15 models, 4 providers)
- Team & Agent Cost Breakdown
- Budget Monitoring with Enforcement

### Phase 4 – Runtime Intelligence ✅
- Agent Activity Monitoring
- Workflow Tracking
- Runtime Health Metrics
- AI Risk Scoring

### Phase 5 – Security & Governance ✅
- Prompt Auditing ✅
- Security Alerts (8 detection rules) ✅
- Governance Dashboard ✅
- Sensitive Data Detection ✅ (10 pattern types: PII, credentials, API keys)
- Policy Enforcement ✅ (model allowlist/blocklist per team)

### Phase 6 – Frontend Dashboard ✅
- React + Vite + Tailwind CSS + Recharts
- 8-page observability dashboard
- Executive Summary
- Live / Demo mode

### Future Capabilities
- PII / sensitive data ML scanner
- Cost forecasting
- Compliance reporting (SOC 2, GDPR)
- Multi-tenant org isolation
- Slack / PagerDuty alert integrations
- Agent inventory & approval workflow
- Enterprise SSO

---

## Project Status

🟢 **Active Development** — core platform complete, advancing governance and security features.

---

## Author

**Ron Haviv**
SOC Analyst | Security Operations | AI Runtime Intelligence

Building the next generation of visibility, governance, security, and cost intelligence for enterprise AI.
