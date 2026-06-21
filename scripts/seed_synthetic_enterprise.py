#!/usr/bin/env python3
"""
Seed synthetic enterprise demo data for three organizations.

Creates per-org:
  • Teams: developer, security, product, support
  • Users: admin + 1 analyst/viewer per team
  • API keys: one per team
  • Agents: 8 agents across all teams (mixed lifecycle states)
  • Budget rules: team-level and agent-level
  • Policy rules: model allow/block lists (varies per org)
  • Guard mode overrides per team
  • 7-day historical telemetry including security findings

Usage:
    python scripts/seed_synthetic_enterprise.py
    python scripts/seed_synthetic_enterprise.py --clear
    python scripts/seed_synthetic_enterprise.py --org acme
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ── Bootstrap: load .env, set minimal env vars, add project root to path ──────
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

os.environ.setdefault("JWT_SECRET", "seed-enterprise-local-only-not-for-prod")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")

from app.database import engine, SessionLocal
from app.models import (
    Base, Organization, User, ApiKey, Team as TeamModel,
    Telemetry, AssetRegistry, BudgetRule, PolicyRule, GuardMode,
    Role as RoleModel, calculate_cost,
)
from app.auth import hash_password, generate_api_key
from app.scanner import scan

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("seed_enterprise")

random.seed(12345)

# ─── Org definitions ──────────────────────────────────────────────────────────

ORG_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "Acme Corp",
        "slug": "acme",
        "description": "SaaS product company — mixed AI usage across all teams",
        "users": [
            {"email": "acme-admin@acme.example",   "name": "Acme Admin",     "role": "admin",   "team": ""},
            {"email": "alice@acme.example",         "name": "Alice Dev",      "role": "analyst", "team": "developer"},
            {"email": "bob@acme.example",           "name": "Bob Security",   "role": "analyst", "team": "security"},
            {"email": "carol@acme.example",         "name": "Carol Product",  "role": "analyst", "team": "product"},
            {"email": "dave@acme.example",          "name": "Dave Support",   "role": "analyst", "team": "support"},
            {"email": "eve@acme.example",           "name": "Eve Viewer",     "role": "viewer",  "team": "developer"},
        ],
        "api_keys": [
            {"name": "acme-developer-key", "team": "developer"},
            {"name": "acme-security-key",  "team": "security"},
            {"name": "acme-product-key",   "team": "product"},
            {"name": "acme-support-key",   "team": "support"},
        ],
        "budgets": [
            {"team": "*",          "agent": None,                       "limit_usd": 200.0, "period": "monthly", "action": "alert"},
            {"team": "developer",  "agent": None,                       "limit_usd": 60.0,  "period": "monthly", "action": "alert"},
            {"team": "security",   "agent": None,                       "limit_usd": 40.0,  "period": "monthly", "action": "alert"},
            {"team": "product",    "agent": None,                       "limit_usd": 30.0,  "period": "monthly", "action": "alert"},
            {"team": "support",    "agent": None,                       "limit_usd": 25.0,  "period": "monthly", "action": "block"},
            {"team": "support",    "agent": "customer-support-chatbot", "limit_usd": 3.0,   "period": "daily",   "action": "block"},
        ],
        "policies": [
            {"team": "*", "rule_type": "block_model", "value": "gpt-4-turbo"},
        ],
        "guard_modes": [
            {"team": "developer", "mode": "observe"},
            {"team": "security",  "mode": "enforce"},
            {"team": "product",   "mode": "alert"},
            {"team": "support",   "mode": "enforce"},
        ],
    },
    {
        "name": "Globex",
        "slug": "globex",
        "description": "Financial services firm — cost-conscious, strict model allowlist",
        "users": [
            {"email": "globex-admin@globex.example",  "name": "Globex Admin",    "role": "admin",   "team": ""},
            {"email": "frank@globex.example",         "name": "Frank Dev",       "role": "analyst", "team": "developer"},
            {"email": "grace@globex.example",         "name": "Grace Security",  "role": "analyst", "team": "security"},
            {"email": "henry@globex.example",         "name": "Henry Product",   "role": "analyst", "team": "product"},
            {"email": "iris@globex.example",          "name": "Iris Support",    "role": "analyst", "team": "support"},
            {"email": "jack@globex.example",          "name": "Jack Viewer",     "role": "viewer",  "team": "security"},
        ],
        "api_keys": [
            {"name": "globex-developer-key", "team": "developer"},
            {"name": "globex-security-key",  "team": "security"},
            {"name": "globex-product-key",   "team": "product"},
            {"name": "globex-support-key",   "team": "support"},
        ],
        "budgets": [
            {"team": "*",         "agent": None,                       "limit_usd": 150.0, "period": "monthly", "action": "alert"},
            {"team": "developer", "agent": None,                       "limit_usd": 40.0,  "period": "monthly", "action": "alert"},
            {"team": "security",  "agent": None,                       "limit_usd": 30.0,  "period": "monthly", "action": "block"},
            {"team": "support",   "agent": "customer-support-chatbot", "limit_usd": 2.0,   "period": "daily",   "action": "block"},
        ],
        "policies": [
            {"team": "*",         "rule_type": "block_model", "value": "gpt-4-turbo"},
            {"team": "*",         "rule_type": "block_model", "value": "claude-opus-4-5"},
            {"team": "security",  "rule_type": "allow_model", "value": "claude-sonnet-4-5"},
            {"team": "security",  "rule_type": "allow_model", "value": "gpt-4o"},
        ],
        "guard_modes": [
            {"team": "developer", "mode": "observe"},
            {"team": "security",  "mode": "enforce"},
            {"team": "product",   "mode": "observe"},
            {"team": "support",   "mode": "alert"},
        ],
    },
    {
        "name": "CyberTech",
        "slug": "cybertech",
        "description": "Cybersecurity company — security-first, Anthropic-only policy",
        "users": [
            {"email": "cybertech-admin@cybertech.example", "name": "CyberTech Admin",  "role": "admin",   "team": ""},
            {"email": "kate@cybertech.example",            "name": "Kate Dev",         "role": "analyst", "team": "developer"},
            {"email": "leo@cybertech.example",             "name": "Leo Security",     "role": "analyst", "team": "security"},
            {"email": "mia@cybertech.example",             "name": "Mia Product",      "role": "analyst", "team": "product"},
            {"email": "noah@cybertech.example",            "name": "Noah Support",     "role": "analyst", "team": "support"},
            {"email": "olivia@cybertech.example",          "name": "Olivia Viewer",    "role": "viewer",  "team": "security"},
        ],
        "api_keys": [
            {"name": "cybertech-developer-key", "team": "developer"},
            {"name": "cybertech-security-key",  "team": "security"},
            {"name": "cybertech-product-key",   "team": "product"},
            {"name": "cybertech-support-key",   "team": "support"},
        ],
        "budgets": [
            {"team": "*",         "agent": None,              "limit_usd": 300.0, "period": "monthly", "action": "alert"},
            {"team": "security",  "agent": None,              "limit_usd": 100.0, "period": "monthly", "action": "alert"},
            {"team": "security",  "agent": "soc-assistant",   "limit_usd": 20.0,  "period": "daily",   "action": "alert"},
            {"team": "support",   "agent": "customer-support-chatbot", "limit_usd": 5.0, "period": "daily", "action": "block"},
        ],
        "policies": [
            {"team": "*",         "rule_type": "block_model", "value": "gpt-4o-mini"},
            {"team": "*",         "rule_type": "block_model", "value": "gpt-3.5-turbo"},
            {"team": "security",  "rule_type": "allow_model", "value": "claude-sonnet-4-5"},
            {"team": "security",  "rule_type": "allow_model", "value": "claude-opus-4-5"},
        ],
        "guard_modes": [
            {"team": "developer", "mode": "alert"},
            {"team": "security",  "mode": "enforce"},
            {"team": "product",   "mode": "alert"},
            {"team": "support",   "mode": "enforce"},
        ],
    },
]

# ─── Agent definitions (same set per org, varied lifecycle) ──────────────────

AGENT_TEMPLATES = [
    {
        "agent_id_raw": "claude-code",
        "team": "developer",
        "environment": "staging",
        "criticality": "medium",
        "status": "managed",
        "discovery_status": "verified",
        "confidence_score": 95.0,
        "business_purpose": "AI coding assistant integrated into developer IDEs via Claude Code CLI.",
        "preferred_models": ["claude-sonnet-4-5", "gpt-4.1"],
        "calls_per_day": (3, 8),
        "avg_prompt_tokens": (800, 2500),
        "avg_completion_tokens": (400, 1200),
    },
    {
        "agent_id_raw": "ci-agent",
        "team": "developer",
        "environment": "staging",
        "criticality": "low",
        "status": "unassigned",
        "discovery_status": "verified",
        "confidence_score": 75.0,
        "business_purpose": None,
        "preferred_models": ["gpt-4.1-mini", "gpt-4o-mini"],
        "calls_per_day": (10, 25),
        "avg_prompt_tokens": (500, 1500),
        "avg_completion_tokens": (200, 600),
    },
    {
        "agent_id_raw": "soc-assistant",
        "team": "security",
        "environment": "production",
        "criticality": "critical",
        "status": "managed",
        "discovery_status": "verified",
        "confidence_score": 95.0,
        "business_purpose": "Security Operations Center AI assistant for threat analysis and alert triage.",
        "preferred_models": ["claude-opus-4-5", "claude-sonnet-4-5"],
        "calls_per_day": (4, 10),
        "avg_prompt_tokens": (2000, 8000),
        "avg_completion_tokens": (800, 3000),
    },
    {
        "agent_id_raw": "product-analyst",
        "team": "product",
        "environment": "production",
        "criticality": "high",
        "status": "managed",
        "discovery_status": "verified",
        "confidence_score": 95.0,
        "business_purpose": "Analyzes product usage telemetry and generates insights for PM team.",
        "preferred_models": ["gpt-4o", "gpt-4.1"],
        "calls_per_day": (2, 6),
        "avg_prompt_tokens": (1000, 3000),
        "avg_completion_tokens": (500, 1500),
    },
    {
        "agent_id_raw": "customer-support-chatbot",
        "team": "support",
        "environment": "production",
        "criticality": "high",
        "status": "managed",
        "discovery_status": "verified",
        "confidence_score": 95.0,
        "business_purpose": "Customer-facing chatbot for tier-1 support deflection.",
        "preferred_models": ["gpt-4o", "gpt-4o-mini"],
        "calls_per_day": (20, 60),
        "avg_prompt_tokens": (400, 1200),
        "avg_completion_tokens": (200, 600),
    },
    {
        "agent_id_raw": "rag-assistant",
        "team": "support",
        "environment": "production",
        "criticality": "medium",
        "status": "needs_validation",
        "discovery_status": "verified",
        "confidence_score": 65.0,
        "business_purpose": None,
        "preferred_models": ["gpt-4o", "gpt-4.1"],
        "calls_per_day": (8, 20),
        "avg_prompt_tokens": (1500, 4000),
        "avg_completion_tokens": (600, 2000),
    },
    {
        "agent_id_raw": "security-copilot",
        "team": "security",
        "environment": "staging",
        "criticality": "high",
        "status": "needs_validation",
        "discovery_status": "verified",
        "confidence_score": 65.0,
        "business_purpose": None,
        "preferred_models": ["gpt-4o", "claude-sonnet-4-5"],
        "calls_per_day": (1, 4),
        "avg_prompt_tokens": (1000, 4000),
        "avg_completion_tokens": (400, 2000),
    },
    {
        "agent_id_raw": "mcp-server-agent",
        "team": "developer",
        "environment": "dev",
        "criticality": "low",
        "status": "retired",
        "discovery_status": "verified",
        "confidence_score": 95.0,
        "business_purpose": "Prototype MCP server agent — retired after proof-of-concept.",
        "preferred_models": ["gpt-4.1-mini"],
        "calls_per_day": (0, 1),
        "avg_prompt_tokens": (300, 800),
        "avg_completion_tokens": (100, 300),
    },
]

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _asset_key(org_id: int, agent_id_raw: str) -> str:
    return hashlib.sha256(f"{org_id}:{agent_id_raw}".encode()).hexdigest()


def _pick_model(preferred: list[str]) -> str:
    return random.choice(preferred)


def _jitter(base: int, spread: float = 0.3) -> int:
    delta = int(base * spread)
    return max(1, base + random.randint(-delta, delta))


def _ensure_tables():
    Base.metadata.create_all(bind=engine)


# ─── Seed roles (mirrors the logic in main.py) ────────────────────────────────

_SEED_ROLES = [
    {
        "name": "admin",
        "label": "Admin",
        "color": "#FF5C7A",
        "pages": json.dumps([
            "dashboard", "agent_inventory", "discovery", "governance",
            "cost", "security_intel", "ecosystem",
            "budgets", "pricing", "security", "users", "apikeys", "settings",
            "home", "chat", "assets", "overview", "agents", "models",
            "workflows", "alerts", "integrations", "onboarding",
        ]),
        "can": json.dumps(["view_all_sessions"]),
        "team_scoped": False,
    },
    {
        "name": "analyst",
        "label": "Analyst",
        "color": "#FFB547",
        "pages": json.dumps([
            "dashboard", "agent_inventory", "discovery", "governance",
            "cost", "security_intel", "ecosystem",
            "home", "chat", "assets", "overview", "agents", "models",
            "workflows", "alerts",
        ]),
        "can": json.dumps([]),
        "team_scoped": True,
    },
    {
        "name": "viewer",
        "label": "Viewer",
        "color": "#6FA8FF",
        "pages": json.dumps([
            "dashboard", "agent_inventory", "discovery", "governance",
            "cost", "security_intel", "ecosystem",
            "home", "assets", "overview", "agents", "models",
            "workflows", "alerts",
        ]),
        "can": json.dumps([]),
        "team_scoped": True,
    },
]


def _seed_roles_for_org(db, org_id: int) -> None:
    for r in _SEED_ROLES:
        existing = db.query(RoleModel).filter(
            RoleModel.organization_id == org_id,
            RoleModel.name == r["name"],
        ).first()
        if not existing:
            db.add(RoleModel(organization_id=org_id, **r))
    db.commit()


# ─── Telemetry generation ─────────────────────────────────────────────────────

def _make_telemetry_row(
    org_id: int,
    agent: dict,
    ts: datetime,
    *,
    sensitive: bool = False,
    blocked: bool = False,
    block_reason: str | None = None,
    prompt_override: str | None = None,
    response_override: str | None = None,
    findings_override: list[dict] | None = None,
) -> Telemetry:
    model = _pick_model(agent["preferred_models"])
    pt_min, pt_max = agent["avg_prompt_tokens"]
    ct_min, ct_max = agent["avg_completion_tokens"]
    prompt_tokens = random.randint(pt_min, pt_max)
    completion_tokens = 0 if blocked else random.randint(ct_min, ct_max)

    cost, estimated = calculate_cost(model, prompt_tokens, completion_tokens)
    if blocked:
        cost = 0.0

    prompt = prompt_override or f"[synthetic] {agent['agent_id_raw']} request at {ts.isoformat()}"
    response = "" if blocked else (response_override or f"[synthetic] {agent['agent_id_raw']} response")

    findings = findings_override
    if sensitive and not findings:
        result = scan(prompt + " " + response)
        findings = result.to_dict() if result.is_sensitive else []
        sensitive = result.is_sensitive

    key = _asset_key(org_id, agent["agent_id_raw"])
    return Telemetry(
        organization_id=org_id,
        team=agent["team"],
        agent=agent["agent_id_raw"],
        model=model,
        prompt=prompt,
        response=response,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        latency_ms=random.uniform(200, 3500) if not blocked else random.uniform(10, 50),
        cost_usd=cost,
        pricing_estimated=estimated,
        sensitive=sensitive,
        sensitive_findings=json.dumps(findings) if findings else None,
        blocked=blocked,
        block_reason=block_reason,
        timestamp=ts,
        asset_key=key,
        agent_id_raw=agent["agent_id_raw"],
        agent_version="1.0.0",
        team_raw=agent["team"],
        environment_raw=agent.get("environment"),
    )


def _generate_day_traffic(
    db,
    org_id: int,
    agents: list[dict],
    day: datetime,
    security_payload_day: bool = False,
    budget_breach_day: bool = False,
) -> int:
    """Generate all telemetry for one day. Returns the number of rows created."""
    from scripts.synthetic_payloads import PAYLOADS, NORMAL_PROMPTS

    rows = []
    day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)

    for agent in agents:
        if agent["status"] == "retired":
            if random.random() > 0.1:
                continue

        cpd_min, cpd_max = agent["calls_per_day"]
        if budget_breach_day and agent["agent_id_raw"] == "customer-support-chatbot":
            n_calls = cpd_max * 3  # spike: 3x normal volume
        else:
            n_calls = random.randint(cpd_min, cpd_max)

        for _ in range(n_calls):
            hour = _business_hour_sample()
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            ts = day_start + timedelta(hours=hour, minutes=minute, seconds=second)

            is_blocked = False
            block_reason = None
            is_sensitive = False
            prompt_text = None
            response_text = None
            findings = None

            # Budget breach day: some requests get blocked by budget rule
            if (budget_breach_day and agent["agent_id_raw"] == "customer-support-chatbot"
                    and random.random() < 0.35):
                is_blocked = True
                block_reason = "budget_exceeded"

            # Security payload day: inject sensitive content for specific agents
            elif (security_payload_day
                  and agent["agent_id_raw"] in ("soc-assistant", "customer-support-chatbot",
                                                "rag-assistant", "security-copilot")
                  and random.random() < 0.25):
                payload_key = random.choice(list(PAYLOADS.keys()))
                payload = PAYLOADS[payload_key]
                prompt_text = payload["prompt"]
                response_text = payload["response"]
                scan_result = scan(prompt_text + " " + response_text)
                is_sensitive = scan_result.is_sensitive
                findings = scan_result.to_dict() if scan_result.is_sensitive else []

            # Occasional failed/blocked request regardless of day
            elif random.random() < 0.03:
                is_blocked = True
                block_reason = "policy_violation"

            else:
                p = random.choice(NORMAL_PROMPTS)
                prompt_text = p["prompt"]
                response_text = p["response"]

            rows.append(_make_telemetry_row(
                org_id=org_id,
                agent=agent,
                ts=ts,
                sensitive=is_sensitive,
                blocked=is_blocked,
                block_reason=block_reason,
                prompt_override=prompt_text,
                response_override=response_text,
                findings_override=findings,
            ))

    for row in rows:
        db.add(row)

    return len(rows)


def _business_hour_sample() -> int:
    """Return an hour biased towards business hours (9-18) with off-hours tail."""
    if random.random() < 0.80:
        return random.randint(8, 19)
    return random.choice([0, 1, 2, 3, 4, 5, 6, 7, 20, 21, 22, 23])


# ─── Main seeding functions ───────────────────────────────────────────────────

def _get_or_create_org(db, name: str, slug: str) -> tuple[Organization, bool]:
    org = db.query(Organization).filter(Organization.slug == slug).first()
    if org:
        return org, False
    org = Organization(name=name, slug=slug, is_internal=False)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org, True


def seed_org(
    db,
    org_def: dict,
    *,
    days: int = 7,
    clear: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Create all synthetic data for one organization. Returns a summary dict."""

    if now is None:
        now = datetime.now(timezone.utc)

    name = org_def["name"]
    slug = org_def["slug"]

    org, created = _get_or_create_org(db, name, slug)
    org_id = org.id
    action = "created" if created else "found existing"
    log.info("Organization '%s' (id=%d): %s", name, org_id, action)

    if clear:
        dt = db.query(Telemetry).filter(
            Telemetry.organization_id == org_id,
            Telemetry.prompt.like("[synthetic]%"),
        ).delete(synchronize_session=False)
        dr = db.query(AssetRegistry).filter(
            AssetRegistry.organization_id == org_id,
        ).delete(synchronize_session=False)
        db.commit()
        log.info("  Cleared %d telemetry + %d registry rows", dt, dr)

    # ── Roles ─────────────────────────────────────────────────────────────────
    _seed_roles_for_org(db, org_id)
    log.info("  Roles seeded (admin, analyst, viewer)")

    # ── Teams ─────────────────────────────────────────────────────────────────
    teams = ["developer", "security", "product", "support"]
    for team_name in teams:
        existing = db.query(TeamModel).filter(
            TeamModel.organization_id == org_id,
            TeamModel.name == team_name,
        ).first()
        if not existing:
            db.add(TeamModel(organization_id=org_id, name=team_name))
    db.commit()
    log.info("  Teams: %s", ", ".join(teams))

    # ── Users ─────────────────────────────────────────────────────────────────
    created_users: list[str] = []
    users_map: dict[str, User] = {}
    for u in org_def["users"]:
        existing = db.query(User).filter(User.email == u["email"]).first()
        if not existing:
            user = User(
                email=u["email"],
                name=u["name"],
                hashed_password=hash_password("DemoPass123!"),
                role=u["role"],
                team=u["team"],
                organization_id=org_id,
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            created_users.append(u["email"])
            users_map[u["email"]] = user
        else:
            users_map[u["email"]] = existing
    log.info("  Users: %d created, %d already existed", len(created_users),
             len(org_def["users"]) - len(created_users))

    # ── API keys ──────────────────────────────────────────────────────────────
    issued_keys: list[dict] = []
    admin_user = next(
        (u for u in users_map.values() if u.role == "admin"),
        None,
    )
    for key_def in org_def["api_keys"]:
        existing = db.query(ApiKey).filter(
            ApiKey.name == key_def["name"],
            ApiKey.organization_id == org_id,
        ).first()
        if not existing:
            full_key, prefix, key_hash = generate_api_key()
            ak = ApiKey(
                name=key_def["name"],
                key_prefix=prefix,
                key_hash=key_hash,
                team=key_def["team"],
                organization_id=org_id,
                created_by_id=admin_user.id if admin_user else None,
                is_active=True,
            )
            db.add(ak)
            db.commit()
            issued_keys.append({
                "name": key_def["name"],
                "team": key_def["team"],
                "full_key": full_key,
                "prefix": prefix,
            })
    log.info("  API keys created: %d", len(issued_keys))

    # ── Budget rules ──────────────────────────────────────────────────────────
    for b in org_def["budgets"]:
        existing = db.query(BudgetRule).filter(
            BudgetRule.organization_id == org_id,
            BudgetRule.team == b["team"],
            BudgetRule.agent == b["agent"],
            BudgetRule.period == b["period"],
        ).first()
        if not existing:
            db.add(BudgetRule(
                organization_id=org_id,
                team=b["team"],
                agent=b["agent"],
                limit_usd=b["limit_usd"],
                period=b["period"],
                action=b["action"],
            ))
    db.commit()
    log.info("  Budget rules: %d", len(org_def["budgets"]))

    # ── Policy rules ──────────────────────────────────────────────────────────
    for p in org_def["policies"]:
        existing = db.query(PolicyRule).filter(
            PolicyRule.organization_id == org_id,
            PolicyRule.team == p["team"],
            PolicyRule.rule_type == p["rule_type"],
            PolicyRule.value == p["value"],
        ).first()
        if not existing:
            db.add(PolicyRule(
                organization_id=org_id,
                team=p["team"],
                rule_type=p["rule_type"],
                value=p["value"],
            ))
    db.commit()
    log.info("  Policy rules: %d", len(org_def["policies"]))

    # ── Guard modes ───────────────────────────────────────────────────────────
    for gm in org_def["guard_modes"]:
        existing = db.query(GuardMode).filter(
            GuardMode.organization_id == org_id,
            GuardMode.team == gm["team"],
        ).first()
        if existing:
            existing.mode = gm["mode"]
        else:
            db.add(GuardMode(
                organization_id=org_id,
                team=gm["team"],
                mode=gm["mode"],
                updated_by_id=admin_user.id if admin_user else None,
            ))
    db.commit()
    log.info("  Guard modes: %s", ", ".join(f"{g['team']}={g['mode']}" for g in org_def["guard_modes"]))

    # ── Asset registry ────────────────────────────────────────────────────────
    admin_email = next(
        (u["email"] for u in org_def["users"] if u["role"] == "admin"),
        None,
    )
    for agent_tmpl in AGENT_TEMPLATES:
        key = _asset_key(org_id, agent_tmpl["agent_id_raw"])
        existing = db.query(AssetRegistry).filter(
            AssetRegistry.organization_id == org_id,
            AssetRegistry.asset_key == key,
        ).first()

        days_ago = random.randint(15, 60)
        first_seen = now - timedelta(days=days_ago)
        claimed_at = None
        claimed_by = None
        owner = None
        if agent_tmpl["status"] == "managed":
            claimed_at = now - timedelta(days=random.randint(5, days_ago - 1))
            claimed_by = admin_email
            owner = admin_email

        if not existing:
            db.add(AssetRegistry(
                organization_id=org_id,
                asset_key=key,
                agent_id_raw=agent_tmpl["agent_id_raw"],
                agent_name=agent_tmpl["agent_id_raw"],
                owner=owner,
                team=agent_tmpl["team"] if agent_tmpl["status"] == "managed" else None,
                environment=agent_tmpl["environment"] if agent_tmpl["status"] == "managed" else None,
                criticality=agent_tmpl["criticality"] if agent_tmpl["status"] == "managed" else None,
                business_purpose=agent_tmpl.get("business_purpose"),
                status=agent_tmpl["status"],
                source="discovered",
                discovery_status=agent_tmpl["discovery_status"],
                discovery_source="gateway_telemetry",
                discovery_reason=f"Discovered via gateway telemetry on {first_seen.strftime('%Y-%m-%d')}",
                evidence=json.dumps({
                    "resolution_method": "explicit_headers",
                    "needs_admin_review": agent_tmpl["status"] == "needs_validation",
                    "evidence": [f"X-Guard-Agent: {agent_tmpl['agent_id_raw']}"],
                }),
                confidence_score=agent_tmpl["confidence_score"],
                claimed_by=claimed_by,
                claimed_at=claimed_at,
                first_seen_at=first_seen,
            ))
        else:
            log.debug("  Asset '%s' already exists, skipping", agent_tmpl["agent_id_raw"])

    db.commit()
    log.info("  Asset registry: %d agents", len(AGENT_TEMPLATES))

    # ── 7-day historical telemetry ────────────────────────────────────────────
    total_rows = 0
    active_agents = [a for a in AGENT_TEMPLATES if a["status"] != "retired"]

    for day_offset in range(days - 1, -1, -1):
        day = now - timedelta(days=day_offset)
        security_day = (day_offset == 2)
        breach_day = (day_offset <= 1)

        n = _generate_day_traffic(
            db, org_id, AGENT_TEMPLATES, day,
            security_payload_day=security_day,
            budget_breach_day=breach_day,
        )
        total_rows += n
        db.commit()

    log.info("  Telemetry: %d rows across %d days", total_rows, days)

    return {
        "org": name,
        "slug": slug,
        "org_id": org_id,
        "users": len(org_def["users"]),
        "api_keys_issued": issued_keys,
        "agents": len(AGENT_TEMPLATES),
        "telemetry_rows": total_rows,
    }


# ─── CLI entry point ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--clear", action="store_true",
                        help="Wipe existing synthetic telemetry/registry before re-seeding")
    parser.add_argument("--org", metavar="SLUG",
                        help="Seed only this org (acme | globex | cybertech)")
    parser.add_argument("--days", type=int, default=7,
                        help="Days of historical telemetry to generate (default: 7)")
    args = parser.parse_args()

    _ensure_tables()
    db = SessionLocal()

    try:
        orgs_to_seed = [
            o for o in ORG_DEFINITIONS
            if args.org is None or o["slug"] == args.org
        ]
        if not orgs_to_seed:
            log.error("No org found matching --org %r. Valid slugs: acme, globex, cybertech", args.org)
            sys.exit(1)

        print("\n" + "=" * 70)
        print("  AIFinOps Guard — Synthetic Enterprise Seed")
        print("=" * 70)

        results = []
        for org_def in orgs_to_seed:
            print(f"\n▶  Seeding {org_def['name']} ({org_def['slug']}) …")
            summary = seed_org(db, org_def, days=args.days, clear=args.clear)
            results.append(summary)

        # ── Print API key summary (keys shown once!) ───────────────────────────
        print("\n" + "=" * 70)
        print("  ISSUED API KEYS (shown once — save these!)")
        print("=" * 70)
        for r in results:
            if r["api_keys_issued"]:
                print(f"\n  {r['org']} ({r['slug']})")
                for k in r["api_keys_issued"]:
                    print(f"    [{k['team']:12s}]  {k['name']:30s}  {k['full_key']}")

        # ── Print summary table ────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("  SEED SUMMARY")
        print("=" * 70)
        print(f"  {'Org':<20}  {'ID':>4}  {'Users':>5}  {'Agents':>6}  {'Telemetry':>10}")
        print("  " + "-" * 58)
        for r in results:
            print(f"  {r['org']:<20}  {r['org_id']:>4}  {r['users']:>5}  "
                  f"{r['agents']:>6}  {r['telemetry_rows']:>10}")

        print(f"""
  Default password for all demo users: DemoPass123!
  Login as org admin (e.g. acme-admin@acme.example) to explore.

  Run traffic generator:
    python scripts/generate_synthetic_traffic.py --org acme --days 7
    python scripts/generate_synthetic_traffic.py --all --days 30

  Run tests:
    python -m pytest tests/test_multitenant_isolation.py -v
    python -m pytest tests/test_agent_discovery_lifecycle.py -v
""")

    finally:
        db.close()


if __name__ == "__main__":
    main()
