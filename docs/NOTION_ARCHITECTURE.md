# AI Asset Management — Full Project Summary & Architecture

> Ready to paste into Notion. Copy the whole page as a Notion import or paste section by section.

---

## Overview

**AI Asset Management** is an internal platform that gives organizations full visibility and control over every AI agent running in their environment. It answers the questions: *What AI agents do we have? Who owns them? What do they cost? Are they safe?*

The platform works as a proxy gateway between your AI agents and external AI providers (OpenAI, Anthropic, Google, etc.). Every request through the gateway is logged, attributed to a team and agent, and surfaced on a unified dashboard.

---

## Problem Statement

As AI adoption grows, organizations face a common problem:
- Developers spin up AI agents without going through IT or security
- No one knows how many agents exist or who owns them
- AI spending is invisible until the cloud bill arrives
- Security risks (prompt injection, data leakage, policy violations) go undetected
- There is no process to approve, track, or retire agents

This platform solves all of these problems from a single place.

---

## Tech Stack

### Backend
| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Web Framework | FastAPI |
| ORM | SQLAlchemy |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Auth | JWT tokens + role-based access control |
| Package manager | pip / pyproject.toml |

### Frontend
| Layer | Technology |
|---|---|
| Framework | React 19 |
| Build tool | Vite |
| Styling | Inline styles with design token system (no CSS files) |
| Fonts | Geist (UI) + JetBrains Mono (code/data) |
| State | useState / useContext (no Redux) |
| API calls | Custom `authFetch` wrapper around `fetch()` |

### Deployment
- Single-repo monorepo: `/app` (backend) + `/dashboard` (frontend)
- Frontend is served as a static build
- Backend exposes a REST API on the same origin
- The AI gateway proxy runs as part of the backend

---

## Repository Structure

```
ai-asset-management/
├── app/                        # FastAPI backend
│   ├── main.py                 # App entry point, middleware, router registration
│   ├── auth.py                 # JWT auth, require_admin dependency
│   ├── database.py             # SQLAlchemy engine + session factory
│   ├── models.py               # SQLAlchemy ORM models
│   └── routes/
│       ├── agent_inventory.py  # GET/PATCH /agents endpoints
│       ├── discovery.py        # Discovery + claim/validate/reject endpoints
│       ├── governance.py       # Approval workflow endpoints
│       ├── security.py         # Security alert endpoints
│       ├── cost.py             # Cost/billing endpoints
│       ├── ecosystem.py        # Provider/ecosystem endpoints
│       ├── settings.py         # Org config (environments, etc.)
│       └── users.py            # User management endpoints
│
├── dashboard/                  # React frontend
│   ├── src/
│   │   ├── App.jsx             # Root component — auth, routing, nav, all page components
│   │   ├── api.js              # All API call functions
│   │   └── pages/              # Page-level components (one file per page)
│   │       ├── AgentInventory.jsx
│   │       ├── DiscoveryCenter.jsx
│   │       ├── GovernanceCenter.jsx
│   │       ├── CostIntelligence.jsx
│   │       ├── SecurityIntelligence.jsx
│   │       └── EcosystemDiscovery.jsx
│   ├── index.html
│   └── vite.config.js
│
└── docs/                       # Documentation (this file)
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    User's Browser                            │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              React 19 Dashboard (Vite)               │    │
│  │  App.jsx (routing + auth) → page components         │    │
│  │  api.js → authFetch → REST API calls                │    │
│  └───────────────────┬─────────────────────────────────┘    │
└──────────────────────┼──────────────────────────────────────┘
                       │ HTTPS
┌──────────────────────┼──────────────────────────────────────┐
│                      ▼  FastAPI Backend                      │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Auth middleware  →  JWT decode  →  RBAC check        │  │
│  └────────────────────────┬──────────────────────────────┘  │
│                           │                                  │
│  ┌────────────┐  ┌────────┴──────────┐  ┌────────────────┐  │
│  │  /agents   │  │  /discovery       │  │  /gateway/v1   │  │
│  │  /settings │  │  /governance      │  │  (AI proxy)    │  │
│  │  /users    │  │  /security        │  └───────┬────────┘  │
│  └─────┬──────┘  │  /cost /ecosystem │          │           │
│        │         └────────┬──────────┘          │           │
│        │                  │                      │           │
│  ┌─────▼──────────────────▼──────────────────┐  │           │
│  │          SQLAlchemy ORM                    │  │           │
│  │          SQLite / PostgreSQL               │  │           │
│  └────────────────────────────────────────────┘  │           │
└─────────────────────────────────────────────────┼───────────┘
                                                  │ HTTPS
                              ┌───────────────────▼──────────────┐
                              │  AI Providers                     │
                              │  OpenAI  /  Anthropic  /  Google  │
                              └──────────────────────────────────┘
```

---

## Data Model

### Core Tables

**`registry`** — The master agent table
| Column | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `org_id` | string | Organization that owns this agent |
| `asset_key` | string | SHA-256 of `"{org_id}:{agent_id_raw}"` — globally unique ID |
| `agent_name` | string | Human-readable name |
| `owner` | string | Individual owner (optional) |
| `team` | string | Team name |
| `environment` | string | production / staging / development |
| `criticality` | string | low / medium / high |
| `business_purpose` | text | Free text description |
| `status` | string | Lifecycle: unassigned / needs_validation / managed / retired |
| `discovery_status` | string | verified / potential |
| `first_seen` | datetime | When first discovered |
| `last_seen` | datetime | Most recent activity |
| `monthly_cost_usd` | float | Current month spend |
| `confidence_score` | float | 0–1, only for potential agents |

**`users`** — Platform users
| Column | Description |
|---|---|
| `id` | UUID |
| `email` | Login email |
| `role` | admin / analyst / viewer |
| `team` | Team scoping (analysts/viewers see only their team's data) |

---

## Authentication & Authorization

- **Login**: `POST /auth/login` → returns JWT
- **JWT**: stored in `localStorage`, attached as `Authorization: Bearer <token>` header on all API calls
- **RBAC** (Role-Based Access Control):
  - `admin` — full access, can edit agents, manage users, all admin pages
  - `analyst` — can view + claim/validate agents, team-scoped
  - `viewer` — read-only, team-scoped
- **`require_admin` dependency** (FastAPI): raises HTTP 403 if `user.role != "admin"` — used on PATCH /agents and user management endpoints
- **Team scoping**: analysts and viewers only see data for their team

---

## Key Features

### 1. Agent Inventory (4 tabs)
- **Verified Agents** — gateway-confirmed, high confidence
- **Needs Validation** — discovered but unconfirmed, redirects to Discovery Center
- **Managed** — officially approved and actively monitored
- **Retired** — decommissioned agents kept for history

All tabs support: column sorting, text search, claim/validate/reject actions, and (admin-only) inline edit.

### 2. Discovery Center
- **Verified tab** — agents confirmed by gateway telemetry
- **Potential Agents tab** — signals from platform scanning (30–80% confidence)
- Claim Agent modal: full ownership form (owner, team, environment, criticality, business purpose). Owner is optional — only team OR owner is required.
- Validate / Reject with confirmation dialogs before executing

### 3. Governance Center
- Approval queue for agents submitted by teams
- Unassigned agents list (no owner, no team)
- Sortable columns

### 4. Cost Intelligence
- Monthly spend per team and per agent
- Billing history table with sortable columns
- Reconciliation status per billing record

### 5. Security Intelligence
- Real-time alert feed (severity: critical / high / medium / low / info)
- Finding types: prompt injection, data leak, policy violation, anomaly
- Sortable by severity, type, agent, time

### 6. Ecosystem Discovery
- Provider cards showing agent count per AI provider (OpenAI, Anthropic, Google, etc.)
- Click any provider card to see a table of all agents using that provider
- Provider health indicators

### 7. Administration
- **Budgets** — team budget limits
- **Pricing Registry** — token pricing per model
- **Security & Audit** — audit log, IP allowlist, session management
- **Users** — invite, role management
- **API Keys** — generate gateway keys
- **Integrations** — step-by-step guide to connect an agent
- **Settings** — org config (environments, policies, provider keys)

---

## Frontend Design System

All styling is done with inline styles using a design token object `T`:

```js
const T = {
  bg:       "#0d0f14",   // page background
  panel:    "#141720",   // card/panel background
  panelHi:  "#1c2030",   // elevated panel
  border:   "#252b3b",   // border color
  text:     "#e8eaf0",   // primary text
  textDim:  "#8892a4",   // secondary text
  textMute: "#4a5468",   // muted/placeholder text
  accent:   "#4ade80",   // green — primary CTA color
  warn:     "#f59e0b",   // yellow — warning
  crit:     "#f87171",   // red — critical/error
  info:     "#60a5fa",   // blue — informational
  yellow:   "#fbbf24",   // yellow variant
  purple:   "#a78bfa",   // purple
};
```

Font constants:
- `FONT_UI` = `"Geist","Inter",sans-serif` — body text, buttons, labels
- `FONT_MONO` = `"JetBrains Mono","IBM Plex Mono",monospace` — code, IDs, numbers, tags

---

## Routing

The app uses a simple switch-case router inside `App.jsx` — no React Router. Navigation state is a single `page` string in `useState`. The sidebar calls `setPage(id)` on click.

```jsx
// App.jsx
const [page, setPage] = useState("dashboard");

const renderPage = () => {
  switch (page) {
    case "dashboard":      return <ExecutiveDashboard onNavigate={setPage} />;
    case "agent_inventory":return <AgentInventory isAdmin={...} onNavigate={...} />;
    case "discovery":      return <DiscoveryCenter initialTab={discoveryInitialTab} />;
    // ... etc
  }
};
```

Special case: clicking "Needs Validation" tab in Agent Inventory calls `onNavigate("discovery", { discoveryTab: "potential" })` which sets `discoveryInitialTab` state and switches to Discovery Center with the Potential Agents tab pre-selected.

---

## API Endpoints (Key Examples)

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/login` | Login, returns JWT |
| `GET` | `/agents` | List all agents (scoped to org) |
| `PATCH` | `/agents/{id}` | Edit agent (admin only) |
| `POST` | `/agents/{id}/claim` | Claim an agent with ownership info |
| `POST` | `/agents/{id}/validate` | Validate a potential agent (admin) |
| `POST` | `/agents/{id}/reject` | Reject a potential agent (admin) |
| `GET` | `/discovery/agents` | Discovery Center agent list |
| `GET` | `/cost/summary` | Cost breakdown by team/model |
| `GET` | `/security/alerts` | Security alert feed |
| `GET` | `/settings/config` | Org config (environments, etc.) |
| `GET` | `/users` | User list (admin only) |
| `POST` | `/apikeys` | Generate new gateway API key |
| `POST` | `/gateway/v1/chat/completions` | AI proxy — OpenAI compatible |

---

## How the Gateway Proxy Works

1. Developer changes `base_url` in their AI SDK from `https://api.openai.com` to `https://your-instance/v1`
2. Developer adds two headers: `X-Guard-Team` and `X-Guard-Agent`
3. Request arrives at the FastAPI gateway endpoint
4. Gateway authenticates the gateway API key
5. Gateway logs the request (team, agent, model, tokens, timestamp)
6. Gateway forwards the request to the real AI provider with the original API key
7. Response is returned to the developer's code unchanged
8. Agent appears in the inventory within seconds

---

## Development Setup

```bash
# Backend
cd app
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd dashboard
npm install
npm run dev   # runs on port 5173, proxies /api to :8000
```

---

## What Makes This Different from Other Tools

| Feature | This Platform | Typical API Gateway |
|---|---|---|
| Agent-level tracking | ✓ (team + agent headers) | ✗ |
| Automatic discovery of unknown agents | ✓ | ✗ |
| Ownership & governance workflow | ✓ | ✗ |
| Cost attribution per agent | ✓ | Sometimes |
| Security alerts & prompt injection detection | ✓ | Rarely |
| Admin-only editing with audit trail | ✓ | ✗ |
| Multi-provider support | ✓ | Sometimes |

---

## Glossary

| Term | Definition |
|---|---|
| **Agent** | Code that calls an AI provider API to perform a task |
| **Gateway** | The proxy server between agents and AI providers |
| **Asset Key** | SHA-256 unique ID for each agent: `hash("{org_id}:{agent_id_raw}")` |
| **Discovery** | Finding agents that exist but were not officially registered |
| **Claim** | An owner/team takes responsibility for a discovered agent |
| **Lifecycle Status** | `unassigned` → `needs_validation` → `managed` → `retired` |
| **Discovery Status** | `verified` (gateway telemetry) or `potential` (inferred signals) |
| **Confidence Score** | 0–1 probability that a potential agent is real (only for potential agents) |
| **Criticality** | Business impact: `low` / `medium` / `high` |
| **RBAC** | Role-Based Access Control — admin / analyst / viewer roles |
| **Team Scoping** | Analysts and viewers only see their own team's data |
