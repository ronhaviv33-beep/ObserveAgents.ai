# AIFinOps Guard

**Observability, Security and FinOps for Enterprise AI Agents**

## Overview

AIFinOps Guard is an AI Runtime Intelligence platform designed to provide visibility, governance, security, and cost intelligence for enterprise AI applications and autonomous agents.

As organizations increasingly adopt AI Agents, LLMs, and AI-powered workflows, it becomes difficult to understand:

* Who is using AI
* Which models are being used
* How much AI operations cost
* Which agents are generating the most traffic
* Whether AI usage complies with security and governance policies

AIFinOps Guard acts as a central gateway between AI applications and LLM providers, collecting telemetry and enabling operational insights.

---

## Vision

Build the "Datadog + CrowdStrike for AI Runtime".

Provide organizations with:

* AI Observability
* AI FinOps
* AI Governance
* AI Security Monitoring
* Runtime Intelligence

---

## Architecture

```text
Agent / Application
        ↓
AIFinOps Gateway
        ↓
LLM Provider (OpenAI, Anthropic, etc.)
        ↓
Telemetry Collection
        ↓
Database
        ↓
Dashboard & Analytics
```

---

## Current MVP

### Backend

* Python
* FastAPI
* SQLAlchemy
* SQLite

### Features

* FastAPI Gateway
* Request Validation
* Telemetry Storage
* SQLite Database
* Telemetry Retrieval API
* Agent Tracking
* Team Tracking

### API Endpoints

#### Health Check

```http
GET /
```

Response:

```json
{
  "status": "AIFinOps Gateway Running"
}
```

---

#### Submit Agent Request

```http
POST /ask
```

Example:

```json
{
  "team": "SOC",
  "agent": "IR-Agent",
  "prompt": "Analyze this phishing email"
}
```

---

#### Retrieve Telemetry

```http
GET /telemetry
```

Returns all stored telemetry records.

---

## Roadmap

### Phase 1 – Gateway Foundation ✅

* FastAPI Gateway
* SQLite Storage
* Telemetry API

### Phase 2 – LLM Integration

* OpenAI Integration
* Anthropic Integration
* Real Token Tracking
* Latency Measurement

### Phase 3 – Cost Intelligence

* Cost Calculation
* Team Cost Breakdown
* Agent Cost Analysis
* Budget Monitoring

### Phase 4 – Runtime Intelligence

* Agent Activity Monitoring
* Workflow Tracking
* Tool Usage Analytics
* Runtime Health Metrics

### Phase 5 – Security & Governance

* Prompt Auditing
* Sensitive Data Detection
* Policy Enforcement
* Security Alerts
* Governance Dashboard

### Phase 6 – Frontend Dashboard

* React
* Tailwind CSS
* Recharts
* Executive Dashboard
* Cost Analytics
* Security Insights

---

## Future Capabilities

* Multi-Model Support
* AI Security Analytics
* Agent Inventory
* Runtime Anomaly Detection
* Cost Forecasting
* Compliance Reporting
* Enterprise Integrations

---

## Project Status

🚧 Active Development

This project is currently in MVP stage and focuses on building the core AI Runtime Intelligence platform.

---

## Author

Ron Haviv

SOC Analyst | Security Operations | AI Runtime Intelligence Research

Building the next generation of visibility, governance, security, and cost intelligence for enterprise AI.
