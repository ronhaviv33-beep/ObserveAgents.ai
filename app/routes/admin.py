import hashlib
import json
import random
import re as _re
import secrets as _sec
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    AgentRelationship, AssetRegistry, BudgetRule, GuardMode,
    Organization, PolicyRule, Team, Telemetry, User, calculate_cost,
)
from app.schemas import OrgCreate, OrgCreated
from app.auth import hash_password, require_platform_admin
from app.roles import seed_roles_for_org
from app.relationships import upsert_relationship
from app.relationship_resolver import ResolvedRelationship
from app.org_config import set_org_config

router = APIRouter(tags=["Admin — Platform"])


def _make_org_slug(name: str, db: Session) -> str:
    """Derive a unique URL-safe slug from an org name."""
    base = _re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:64] or "org"
    slug, n = base, 2
    while db.query(Organization).filter(Organization.slug == slug).first():
        slug = f"{base}-{n}"
        n += 1
    return slug


@router.get("/admin/organizations")
async def list_all_organizations(
    actor=Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """List all organizations on the platform. Platform admin only."""
    orgs = db.query(Organization).order_by(Organization.created_at).all()
    result = []
    for o in orgs:
        user_count = db.query(User).filter(User.organization_id == o.id).count()
        result.append({
            "id":          o.id,
            "name":        o.name,
            "slug":        o.slug,
            "is_internal": o.is_internal,
            "user_count":  user_count,
            "created_at":  o.created_at,
        })
    return result


@router.post("/admin/organizations", response_model=OrgCreated, status_code=201)
async def create_organization(
    req: OrgCreate,
    actor=Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """
    Create a new tenant organization. Platform admin only.

    Auto-seeds the three default roles (admin / analyst / viewer) and creates
    an org-level admin user. If `admin_password` is omitted a secure random
    password is generated; it is returned in `admin_temporary_password` **once**
    and also printed to the server boot log — store it immediately.
    """
    if db.query(Organization).filter(Organization.name == req.name).first():
        raise HTTPException(status_code=409, detail=f"Organization '{req.name}' already exists.")
    if db.query(User).filter(User.email == req.admin_email).first():
        raise HTTPException(status_code=409, detail=f"Email '{req.admin_email}' is already registered.")

    slug = _make_org_slug(req.name, db)
    org = Organization(name=req.name, slug=slug)
    db.add(org)
    db.flush()

    seed_roles_for_org(db, org.id)

    auto_generated = req.admin_password is None
    admin_pw = req.admin_password or _sec.token_urlsafe(20)

    admin_user = User(
        email=req.admin_email,
        name=req.admin_name,
        hashed_password=hash_password(admin_pw),
        role="admin",
        team="Platform",
        organization_id=org.id,
        is_platform_admin=False,
    )
    db.add(admin_user)
    db.commit()
    db.refresh(org)
    db.refresh(admin_user)

    if auto_generated:
        print(
            "\n"
            "╔══════════════════════════════════════════════════════════════╗\n"
            "║           NEW ORG ADMIN — TEMPORARY CREDENTIALS             ║\n"
            "║                                                              ║\n"
            f"║  org     : {org.name:<50} ║\n"
            f"║  email   : {req.admin_email:<50} ║\n"
            f"║  password: {admin_pw:<50} ║\n"
            "║                                                              ║\n"
            "║  Share with the org admin and ask them to change it.        ║\n"
            "╚══════════════════════════════════════════════════════════════╝\n",
            flush=True,
        )

    return OrgCreated(
        id=org.id,
        name=org.name,
        slug=org.slug,
        admin_email=req.admin_email,
        admin_user_id=admin_user.id,
        admin_temporary_password=admin_pw if auto_generated else None,
    )


# ─── Populate / clear demo data ───────────────────────────────────────────────

_DEMO_TEAMS = ["Sales", "Support", "Security", "Finance", "Engineering"]

_DEMO_AGENTS = [
    {
        "id": "sales-enrichment-agent",
        "team": "Sales",
        "model": "gpt-4o",
        "env": "production",
        "criticality": "high",
        "owner": "alice@acme.ai",
        "purpose": "Enrich CRM contacts with firmographic data and intent signals",
        "asset_type": "agent",
        "capabilities": ["inference", "tool_execution", "crm_write"],
    },
    {
        "id": "support-triage-agent",
        "team": "Support",
        "model": "gpt-4o-mini",
        "env": "production",
        "criticality": "medium",
        "owner": "bob@acme.ai",
        "purpose": "Route and prioritise incoming support tickets, draft initial responses",
        "asset_type": "agent",
        "capabilities": ["inference", "tool_execution", "ticket_routing"],
    },
    {
        "id": "soc-investigation-agent",
        "team": "Security",
        "model": "claude-sonnet-4-6",
        "env": "production",
        "criticality": "critical",
        "owner": "carol@acme.ai",
        "purpose": "Investigate security alerts, correlate SIEM events, draft incident reports",
        "asset_type": "agent",
        "capabilities": ["inference", "retrieval", "tool_execution", "siem_read"],
    },
    {
        "id": "finance-analyst-agent",
        "team": "Finance",
        "model": "gpt-4o",
        "env": "production",
        "criticality": "high",
        "owner": "dave@acme.ai",
        "purpose": "Analyse financial reports, generate variance summaries and forecasts",
        "asset_type": "agent",
        "capabilities": ["inference", "retrieval", "database_read"],
    },
    {
        "id": "release-assistant-agent",
        "team": "Engineering",
        "model": "claude-sonnet-4-6",
        "env": "staging",
        "criticality": "medium",
        "owner": "eve@acme.ai",
        "purpose": "Review PRs, summarise changelogs, create GitHub release notes",
        "asset_type": "agent",
        "capabilities": ["inference", "tool_execution", "code_review"],
    },
]

_DEMO_RELATIONSHIPS = [
    # Sales: HubSpot MCP tool + CRM write
    {"agent": "sales-enrichment-agent", "target_type": "mcp_tool", "target_name": "create_lead",
     "rel_type": "uses_tool", "evidence": "mcp_headers", "confidence": 0.92,
     "meta": {"mcp_server": "hubspot-mcp"}, "count": 47},
    {"agent": "sales-enrichment-agent", "target_type": "crm", "target_name": "hubspot-crm",
     "rel_type": "writes_to", "evidence": "headers", "confidence": 0.80,
     "meta": {}, "count": 22},
    # Support: Jira MCP tool
    {"agent": "support-triage-agent", "target_type": "mcp_tool", "target_name": "create_ticket",
     "rel_type": "uses_tool", "evidence": "mcp_headers", "confidence": 0.90,
     "meta": {"mcp_server": "jira-mcp"}, "count": 63},
    {"agent": "support-triage-agent", "target_type": "mcp_tool", "target_name": "send_message",
     "rel_type": "uses_tool", "evidence": "mcp_headers", "confidence": 0.85,
     "meta": {"mcp_server": "slack-mcp"}, "count": 31},
    # Security: Postgres MCP + SIEM API
    {"agent": "soc-investigation-agent", "target_type": "mcp_tool", "target_name": "query_events",
     "rel_type": "uses_tool", "evidence": "mcp_headers", "confidence": 0.88,
     "meta": {"mcp_server": "postgres-mcp"}, "count": 19},
    {"agent": "soc-investigation-agent", "target_type": "api", "target_name": "siem-api",
     "rel_type": "reads_from", "evidence": "headers", "confidence": 0.82,
     "meta": {}, "count": 34},
    # Engineering: GitHub MCP
    {"agent": "release-assistant-agent", "target_type": "mcp_tool", "target_name": "get_pull_request",
     "rel_type": "uses_tool", "evidence": "mcp_headers", "confidence": 0.91,
     "meta": {"mcp_server": "github-mcp"}, "count": 28},
    {"agent": "release-assistant-agent", "target_type": "mcp_tool", "target_name": "create_release",
     "rel_type": "uses_tool", "evidence": "mcp_headers", "confidence": 0.87,
     "meta": {"mcp_server": "github-mcp"}, "count": 11},
    # Finance: Postgres MCP read
    {"agent": "finance-analyst-agent", "target_type": "mcp_tool", "target_name": "run_query",
     "rel_type": "uses_tool", "evidence": "mcp_headers", "confidence": 0.89,
     "meta": {"mcp_server": "postgres-mcp"}, "count": 25},
    {"agent": "finance-analyst-agent", "target_type": "database", "target_name": "postgres-finance-db",
     "rel_type": "reads_from", "evidence": "headers", "confidence": 0.78,
     "meta": {}, "count": 14},
]

_DEMO_SAMPLE_PROMPTS = [
    "Summarise the key risks in this security alert.",
    "Draft a response to this support ticket.",
    "Enrich this contact with firmographic data.",
    "Generate a release note for the changes in this PR.",
    "Compare Q2 vs Q1 revenue by segment.",
    "What are the top 3 action items from this incident report?",
    "Create a ticket for the bug described in this thread.",
    "Identify intent signals for this account.",
    "Analyse the variance in this month's cost centre report.",
    "Review this pull request for security issues.",
]

_DEMO_SAMPLE_RESPONSES = [
    "Based on the available information, here is the analysis: ...",
    "I've identified the following key points: ...",
    "The recommended next steps are: ...",
    "After reviewing the provided context: ...",
    "Here is a summary of the findings: ...",
]


def _asset_key(org_id: int, agent_id: str) -> str:
    return hashlib.sha256(f"{org_id}:{agent_id}".encode()).hexdigest()


def _make_telemetry_rows(org_id: int, days: int = 30) -> list[Telemetry]:
    """Generate ~180 realistic telemetry rows spread over the last `days` days."""
    now = datetime.now(timezone.utc)
    rows: list[Telemetry] = []
    rng = random.Random(42)  # deterministic for idempotency on second populate
    for agent_cfg in _DEMO_AGENTS:
        agent_id = agent_cfg["id"]
        team = agent_cfg["team"]
        model = agent_cfg["model"]
        akey = _asset_key(org_id, agent_id)
        calls_per_day = rng.randint(4, 12)
        for day_offset in range(days):
            ts_base = now - timedelta(days=day_offset)
            n = rng.randint(max(1, calls_per_day - 3), calls_per_day + 3)
            for _ in range(n):
                hour = rng.randint(7, 21)
                minute = rng.randint(0, 59)
                ts = ts_base.replace(hour=hour, minute=minute, second=rng.randint(0, 59), microsecond=0)
                prompt_tokens = rng.randint(200, 2000)
                completion_tokens = rng.randint(80, 600)
                cost, estimated = calculate_cost(model, prompt_tokens, completion_tokens)
                rows.append(Telemetry(
                    organization_id=org_id,
                    team=team,
                    agent=agent_id,
                    model=model,
                    prompt=rng.choice(_DEMO_SAMPLE_PROMPTS),
                    response=rng.choice(_DEMO_SAMPLE_RESPONSES),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                    latency_ms=round(rng.uniform(250, 3500), 1),
                    cost_usd=cost,
                    pricing_estimated=estimated,
                    sensitive=False,
                    blocked=False,
                    timestamp=ts,
                    asset_key=akey,
                    agent_id_raw=agent_id,
                    environment_raw=agent_cfg["env"],
                    is_demo=True,
                ))
    return rows


def populate_demo_org(db: Session, org_id: int) -> dict:
    """
    Seed realistic enterprise runtime data into an existing organization.
    Creates teams, agents (asset registry + telemetry), relationships, budgets,
    and governance data.  All rows are tagged is_demo=True so they can be cleared
    with the companion DELETE endpoint without touching real customer data.
    Idempotent — safe to call more than once; existing demo rows are preserved
    (telemetry appends, asset/relationship rows upsert).

    Reusable from the HTTP endpoint and from the demo-service startup seeder.
    """
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization {org_id} not found")

    # ── 1. Teams ─────────────────────────────────────────────────────────────
    teams_created = 0
    for team_name in _DEMO_TEAMS:
        exists = db.query(Team).filter(
            Team.organization_id == org_id,
            Team.name == team_name,
        ).first()
        if not exists:
            db.add(Team(organization_id=org_id, name=team_name))
            teams_created += 1
    db.flush()

    # ── 2. Asset registry ─────────────────────────────────────────────────────
    assets_upserted = 0
    for cfg in _DEMO_AGENTS:
        akey = _asset_key(org_id, cfg["id"])
        existing = db.query(AssetRegistry).filter(
            AssetRegistry.organization_id == org_id,
            AssetRegistry.asset_key == akey,
        ).first()
        if not existing:
            db.add(AssetRegistry(
                organization_id=org_id,
                asset_key=akey,
                agent_id_raw=cfg["id"],
                agent_name=cfg["id"],
                owner=cfg["owner"],
                team=cfg["team"],
                environment=cfg["env"],
                criticality=cfg["criticality"],
                business_purpose=cfg["purpose"],
                status="managed",
                source="api",
                discovery_status="verified",
                discovery_source="gateway_telemetry",
                discovery_reason="Populated by platform admin",
                confidence_score=95.0,
                asset_type=cfg["asset_type"],
                capabilities=json.dumps(cfg["capabilities"]),
                is_demo=True,
            ))
            assets_upserted += 1
        else:
            # Update governance fields if already present but unassigned
            if not existing.owner:
                existing.owner = cfg["owner"]
            if not existing.team:
                existing.team = cfg["team"]
            if not existing.environment:
                existing.environment = cfg["env"]
            if existing.status == "unassigned":
                existing.status = "managed"
                existing.criticality = cfg["criticality"]
                existing.business_purpose = cfg["purpose"]
    db.flush()

    # ── 3. Telemetry ──────────────────────────────────────────────────────────
    rows = _make_telemetry_rows(org_id, days=30)
    for row in rows:
        db.add(row)
    db.flush()

    # ── 4. Relationships (through the standard upsert pipeline) ───────────────
    rels_created = 0
    for rel_cfg in _DEMO_RELATIONSHIPS:
        existing_rel = db.query(AgentRelationship).filter(
            AgentRelationship.organization_id == org_id,
            AgentRelationship.source_agent_name == rel_cfg["agent"],
            AgentRelationship.target_type == rel_cfg["target_type"],
            AgentRelationship.target_name == rel_cfg["target_name"],
            AgentRelationship.relationship_type == rel_cfg["rel_type"],
        ).first()
        if existing_rel:
            existing_rel.request_count += rel_cfg["count"]
            existing_rel.last_seen_at = datetime.now(timezone.utc)
        else:
            now = datetime.now(timezone.utc)
            meta_str = json.dumps(rel_cfg["meta"]) if rel_cfg["meta"] else None
            db.add(AgentRelationship(
                organization_id=org_id,
                source_agent_id=_asset_key(org_id, rel_cfg["agent"]),
                source_agent_name=rel_cfg["agent"],
                target_type=rel_cfg["target_type"],
                target_name=rel_cfg["target_name"],
                relationship_type=rel_cfg["rel_type"],
                evidence_source=rel_cfg["evidence"],
                confidence_score=rel_cfg["confidence"],
                first_seen_at=now - timedelta(days=29),
                last_seen_at=now,
                request_count=rel_cfg["count"],
                metadata_json=meta_str,
            ))
            rels_created += 1
    db.flush()

    # ── 5. Budget rules ───────────────────────────────────────────────────────
    _budget_defaults = [
        {"team": "Sales",    "limit_usd": 500.0,  "period": "monthly", "action": "alert"},
        {"team": "Security", "limit_usd": 300.0,  "period": "monthly", "action": "alert"},
        {"team": "Finance",  "limit_usd": 200.0,  "period": "monthly", "action": "block"},
        {"team": "Support",  "limit_usd": 150.0,  "period": "monthly", "action": "alert"},
    ]
    budgets_created = 0
    for b in _budget_defaults:
        exists = db.query(BudgetRule).filter(
            BudgetRule.organization_id == org_id,
            BudgetRule.team == b["team"],
            BudgetRule.period == b["period"],
        ).first()
        if not exists:
            db.add(BudgetRule(
                organization_id=org_id,
                team=b["team"],
                agent=None,
                limit_usd=b["limit_usd"],
                period=b["period"],
                action=b["action"],
            ))
            budgets_created += 1

    # ── 6. Policy rules ───────────────────────────────────────────────────────
    _policy_defaults = [
        {"team": "Finance",     "rule_type": "block_model", "value": "gpt-4-turbo"},
        {"team": "Finance",     "rule_type": "allow_model", "value": "gpt-4o-mini"},
        {"team": "Engineering", "rule_type": "allow_model", "value": "claude-sonnet-4-6"},
    ]
    policies_created = 0
    for p in _policy_defaults:
        exists = db.query(PolicyRule).filter(
            PolicyRule.organization_id == org_id,
            PolicyRule.team == p["team"],
            PolicyRule.rule_type == p["rule_type"],
            PolicyRule.value == p["value"],
        ).first()
        if not exists:
            db.add(PolicyRule(
                organization_id=org_id,
                team=p["team"],
                rule_type=p["rule_type"],
                value=p["value"],
            ))
            policies_created += 1

    # ── 7. Guard modes ────────────────────────────────────────────────────────
    _guard_defaults = [
        {"team": "Security", "mode": "alert"},
        {"team": "Finance",  "mode": "enforce"},
    ]
    for g in _guard_defaults:
        existing_gm = db.query(GuardMode).filter(
            GuardMode.organization_id == org_id,
            GuardMode.team == g["team"],
        ).first()
        if not existing_gm:
            db.add(GuardMode(
                organization_id=org_id,
                team=g["team"],
                mode=g["mode"],
            ))

    # Enable demo_mode so the dashboard shows is_demo=True rows immediately
    set_org_config(db, org_id, "demo_mode", True)

    db.commit()

    return {
        "org_id": org_id,
        "org_name": org.name,
        "teams_created": teams_created,
        "assets_upserted": assets_upserted,
        "telemetry_rows_added": len(rows),
        "relationships_created": rels_created,
        "budgets_created": budgets_created,
        "policies_created": policies_created,
        "agents": [a["id"] for a in _DEMO_AGENTS],
        "teams": _DEMO_TEAMS,
        "demo_mode_enabled": True,
    }


@router.post("/admin/organizations/{org_id}/populate", status_code=201)
async def populate_organization(
    org_id: int,
    actor=Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """Seed demo data into an org (platform admin only). Demo-specific tooling —
    only available when the service runs in demo or development mode."""
    from app.config import is_demo_mode, is_development
    if not (is_demo_mode() or is_development()):
        raise HTTPException(
            status_code=403,
            detail="Demo data seeding is disabled in production.",
        )
    return populate_demo_org(db, org_id)


@router.delete("/admin/organizations/{org_id}/demo-data", status_code=200)
async def clear_demo_data(
    org_id: int,
    actor=Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """
    Remove all demo data from an organization (rows tagged is_demo=True plus
    relationships and governance rules for the demo agent/team names).
    Real customer data (is_demo=False) is never touched.
    Demo-specific tooling — only available in demo or development mode.
    """
    from app.config import is_demo_mode, is_development
    if not (is_demo_mode() or is_development()):
        raise HTTPException(
            status_code=403,
            detail="Demo data clearing is disabled in production.",
        )
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization {org_id} not found")

    demo_agent_names = [a["id"] for a in _DEMO_AGENTS]

    # Telemetry — is_demo flag
    tel_deleted = db.query(Telemetry).filter(
        Telemetry.organization_id == org_id,
        Telemetry.is_demo == True,  # noqa: E712
    ).delete(synchronize_session=False)

    # Asset registry — is_demo flag
    asset_deleted = db.query(AssetRegistry).filter(
        AssetRegistry.organization_id == org_id,
        AssetRegistry.is_demo == True,  # noqa: E712
    ).delete(synchronize_session=False)

    # Relationships — keyed by demo agent names
    rel_deleted = db.query(AgentRelationship).filter(
        AgentRelationship.organization_id == org_id,
        AgentRelationship.source_agent_name.in_(demo_agent_names),
    ).delete(synchronize_session=False)

    # Budget rules — for demo teams only
    budget_deleted = db.query(BudgetRule).filter(
        BudgetRule.organization_id == org_id,
        BudgetRule.team.in_(_DEMO_TEAMS),
    ).delete(synchronize_session=False)

    # Policy rules — for demo teams only
    policy_deleted = db.query(PolicyRule).filter(
        PolicyRule.organization_id == org_id,
        PolicyRule.team.in_(_DEMO_TEAMS),
    ).delete(synchronize_session=False)

    # Guard modes — for demo teams
    db.query(GuardMode).filter(
        GuardMode.organization_id == org_id,
        GuardMode.team.in_(_DEMO_TEAMS),
    ).delete(synchronize_session=False)

    # Teams — only those in the demo set
    db.query(Team).filter(
        Team.organization_id == org_id,
        Team.name.in_(_DEMO_TEAMS),
    ).delete(synchronize_session=False)

    # Restore live mode — demo rows gone, switch back to real data view
    set_org_config(db, org_id, "demo_mode", False)

    db.commit()

    return {
        "org_id": org_id,
        "org_name": org.name,
        "telemetry_deleted": tel_deleted,
        "assets_deleted": asset_deleted,
        "relationships_deleted": rel_deleted,
        "budgets_deleted": budget_deleted,
        "policies_deleted": policy_deleted,
    }
