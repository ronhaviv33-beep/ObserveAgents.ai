# Synthetic Enterprise Environment

A complete demo environment that simulates realistic AI usage across three organizations, enabling end-to-end testing of onboarding, telemetry, agent discovery, governance, budgets, security detections, RBAC, and dashboards.

## Organizations

| Name | Slug | Profile |
|------|------|---------|
| Acme Corp | `acme` | SaaS product company — mixed AI usage across all teams |
| Globex | `globex` | Financial services — cost-conscious, strict model policies |
| CyberTech | `cybertech` | Cybersecurity company — security-first, Anthropic-only policy |

### Per-org structure

Each organization includes:

**Teams:** `developer`, `security`, `product`, `support`

**Users (password: `DemoPass123!`):**

| Role | Email pattern | Access |
|------|---------------|--------|
| Admin | `{slug}-admin@{slug}.example` | Full org access |
| Analyst (developer) | `alice@{slug}.example` | Developer team only |
| Analyst (security) | `bob@{slug}.example` | Security team only |
| Analyst (product) | `carol@{slug}.example` | Product team only |
| Analyst (support) | `dave@{slug}.example` | Support team only |
| Viewer | `eve@{slug}.example` | Developer team, read-only |

**Agents (8 per org):**

| Agent | Team | Status | Criticality | Environment |
|-------|------|--------|-------------|-------------|
| `claude-code` | developer | managed | medium | staging |
| `ci-agent` | developer | unassigned | low | staging |
| `soc-assistant` | security | managed | critical | production |
| `product-analyst` | product | managed | high | production |
| `customer-support-chatbot` | support | managed | high | production |
| `rag-assistant` | support | needs_validation | medium | production |
| `security-copilot` | security | needs_validation | high | staging |
| `mcp-server-agent` | developer | retired | low | dev |

## Quick Start

### 1. Seed synthetic organizations

```bash
# Seed all three orgs with 7 days of history
python scripts/seed_synthetic_enterprise.py

# Seed only one org
python scripts/seed_synthetic_enterprise.py --org acme

# Clear and re-seed
python scripts/seed_synthetic_enterprise.py --clear

# Specify number of historical days
python scripts/seed_synthetic_enterprise.py --days 30
```

This creates organizations, users, API keys, budgets, policies, guard modes, asset registry entries, and 7 days of realistic telemetry.

**Save the API keys printed at the end** — they are shown only once.

### 2. Generate additional traffic

```bash
# Normal 7-day traffic for Acme
python scripts/generate_synthetic_traffic.py --org acme --days 7

# Full month of traffic for all orgs (good for budget breach demos)
python scripts/generate_synthetic_traffic.py --all --days 30

# Force a budget breach on the last day
python scripts/generate_synthetic_traffic.py --org acme --days 7 --breach

# Spiky traffic (useful for load testing dashboards)
python scripts/generate_synthetic_traffic.py --org acme --days 1 --spiky

# Full onboarding journey (structured 7-day pattern)
python scripts/generate_synthetic_traffic.py --org acme --days 7 --journey
```

### 3. Run validation tests

```bash
# Multi-tenant isolation (verifies data never leaks between orgs)
python -m pytest tests/test_multitenant_isolation.py -v

# Agent discovery lifecycle (unassigned → managed → retired)
python -m pytest tests/test_agent_discovery_lifecycle.py -v

# All synthetic enterprise tests
python -m pytest tests/test_multitenant_isolation.py tests/test_agent_discovery_lifecycle.py -v

# Full test suite (does not break existing tests)
python -m pytest tests/ -v
```

## Traffic Patterns

The traffic generator supports several day patterns:

| Pattern | Description |
|---------|-------------|
| `normal` | Realistic business-hours traffic, 3% failure rate |
| `high_volume` | 3–5× normal volume (batch job / campaign day) |
| `spiky` | Normal all day + 1–3 burst windows of 30–80 calls in 30 min |
| `security` | Normal + injected sensitive payloads (12 finding types) |
| `breach` | Normal + chatbot spike that blows through daily budget |
| `failures` | 10–20% failure rate (chaos/stress testing) |

The `--journey` flag uses a structured 7-day onboarding sequence:
- Day 1: No traffic (org creation)
- Day 2: First telemetry (low volume)
- Day 3: Normal traffic, agent discovery
- Day 4: High-volume day
- Day 5: Security findings injected
- Day 6: Budget breach (chatbot spike)
- Day 7: Spiky traffic — dashboard ready for demo

## Security Findings

The seed and traffic generator inject fake sensitive payloads that trigger the PII/secrets scanner. All values are **obviously fake** and contain "FAKE" or "TEST" markers.

| Finding Type | Severity | Example Pattern |
|-------------|----------|-----------------|
| `openai_key` | critical | `sk-TESTFAKEOPENAIKEY0123456789ABCDE` |
| `anthropic_key` | critical | `sk-ant-TESTFAKEANTH0123456789012345` |
| `aws_key` | critical | `AKIAFAKEAPIKEY567890` |
| `google_key` | critical | `AIzaFAKETESTKEY123456789ABCDEFGHIJKLMNO` |
| `ssn` | critical | `123-45-6789` |
| `credit_card` | high | `4111 1111 1111 1111` |
| `email` | medium | `john.doe@internal.acmecorp.example` |
| `phone` | medium | `555-867-5309` |

Security payload templates are in `scripts/synthetic_payloads.py`.

## Budget Simulation

### Acme Corp budgets

| Scope | Limit | Period | Action |
|-------|-------|--------|--------|
| Org-wide | $200 | monthly | alert |
| Developer team | $60 | monthly | alert |
| Security team | $40 | monthly | alert |
| Product team | $30 | monthly | alert |
| Support team | $25 | monthly | block |
| `customer-support-chatbot` | $3 | daily | block |

To trigger a budget breach:
```bash
# Generate enough chatbot traffic to exceed the $3/day limit
python scripts/generate_synthetic_traffic.py --org acme --days 1 --breach
```

After running this, the dashboard shows:
- `customer-support-chatbot` daily budget: blocked at $3.00
- Support team monthly budget: approaching warning threshold
- Budget breach events in the audit log

## Agent Discovery Lifecycle

The seed script creates agents in mixed lifecycle states:

```
Unassigned → needs_validation → Managed → Retired
```

**Pre-seeded states per org:**
- 3 × `managed` (already claimed by admin)
- 2 × `unassigned` (gateway telemetry seen, not yet claimed)
- 2 × `needs_validation` (auto-detected, needs admin review)
- 1 × `retired` (old version, decommissioned)

To simulate the claim flow:
1. Login as `{slug}-admin@{slug}.example`
2. Go to Agent Inventory → Discovery Queue
3. Click "Claim" on an unassigned or needs_validation agent
4. Fill in owner, team, environment, criticality
5. Status changes to `managed` and canonical metadata is stored

## Multi-Tenant Isolation

The platform enforces strict org-level data isolation:

- Every telemetry row is filtered by `organization_id`
- Asset registry rows are scoped to their org
- Budget rules, guard modes, policies, users, and API keys are all org-scoped
- Team-scoped analyst roles see only their team's data within the org
- Org admins see all data within their org only

The isolation tests in `tests/test_multitenant_isolation.py` verify all of these guarantees automatically.

## File Reference

| File | Purpose |
|------|---------|
| `scripts/seed_synthetic_enterprise.py` | Creates orgs, users, agents, budgets, policies, 7-day history |
| `scripts/generate_synthetic_traffic.py` | Generates additional traffic with configurable patterns |
| `scripts/synthetic_payloads.py` | Fake security payload templates for scanner testing |
| `tests/test_multitenant_isolation.py` | Automated multi-tenant isolation verification |
| `tests/test_agent_discovery_lifecycle.py` | Agent discovery and lifecycle transition tests |

## Policy Configurations

### Acme Corp (permissive)
- Block: `gpt-4-turbo` (cost control)
- All other models allowed

### Globex (cost-focused)
- Block: `gpt-4-turbo`, `claude-opus-4-5`
- Security team allowlist: `claude-sonnet-4-5`, `gpt-4o`

### CyberTech (security-first)
- Block: `gpt-4o-mini`, `gpt-3.5-turbo`
- Security team allowlist: `claude-sonnet-4-5`, `claude-opus-4-5`

## Guard Mode Settings

Each org has team-level guard mode overrides:

| Org | Developer | Security | Product | Support |
|-----|-----------|----------|---------|---------|
| Acme | observe | enforce | alert | enforce |
| Globex | observe | enforce | observe | alert |
| CyberTech | alert | enforce | alert | enforce |

- `observe` — logs everything, never blocks
- `alert` — logs + fires alerts, never blocks
- `enforce` — logs + alerts + actually blocks violations
