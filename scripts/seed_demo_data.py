#!/usr/bin/env python3
"""
Demo seed data for the Enterprise AI Intelligence platform.

Seeds one demo organization ("Acme AI Operations") with five realistic AI
systems, observed via the real OTel ingestion path:

    OTLP JSON → parse_otlp_json() → normalize_spans() → derive_asset_intelligence()

so every derived record (otel_spans, otel_assets, asset_registry linkage,
agent_relationships, provenance_events, asset_capabilities, asset_findings)
is produced by the same code that handles production traffic — nothing is
hand-inserted into derived tables.

Systems seeded:
    support-agent          production   8.4s escalation trace (LLM/retrieval/Jira/CRM/Slack)
    finance-analyst-agent  production   11.2s analysis trace (docs/database/python tool)
    engineering-copilot    staging      6.2s suggestion trace (repo/MCP)
    hr-onboarding-bot      production   4.6s onboarding trace (KB/ServiceNow/Slack)
    research-agent         development  7.3s research trace with one ERROR span

All data is synthetic. No real prompts, responses, secrets, or PII —
span attributes carry only tool names, model names, token counts, and
synthetic .example URLs. Privacy scrubbing is NOT bypassed.

Idempotent: trace and span IDs are deterministic; traces already present are
skipped entirely (the ingestion path increments counters/provenance per call,
so re-ingesting the same payload is avoided rather than relied on). The
intelligence derivation is idempotent by design (application-level dedup).

Usage (from the repo root):
    python scripts/seed_demo_data.py
"""
from __future__ import annotations

import hashlib
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import engine, SessionLocal          # noqa: E402
from app.models import (                                # noqa: E402
    AssetCapability, AssetFinding, AssetRegistry, Base,
    Organization, OtelAsset, OtelSpan, User,
)

DEMO_ORG_NAME = "Acme AI Operations"
DEMO_ORG_SLUG = "acme-ai-ops"
DEMO_USER_EMAIL = "demo@observeagents.ai"
DEMO_USER_PASSWORD = "Demo123!"

_MS = 1_000_000  # nanoseconds per millisecond


def _trace_id(service: str) -> str:
    return hashlib.sha256(f"acme-demo-trace:{service}".encode()).hexdigest()[:32]


def _span_id(service: str, step: str) -> str:
    return hashlib.sha256(f"acme-demo-span:{service}:{step}".encode()).hexdigest()[:16]


# ── Demo system definitions ────────────────────────────────────────────────────
# Each step: (step_key, name, parent_step_key | None, offset_ms, duration_ms,
#             attrs, status | None)
# Offsets are relative to the trace start; all values are fixed and synthetic.

DEMO_SYSTEMS = [
    {
        "service": "support-agent",
        "environment": "production",
        "team": "customer-support",
        "steps": [
            ("root",      "support-agent customer escalation", None,   0,    8400, {}, None),
            ("plan",      "llm.planning",       "root", 0,    1200,
             {"gen_ai.system": "openai", "gen_ai.request.model": "gpt-4o",
              "gen_ai.usage.input_tokens": 640, "gen_ai.usage.output_tokens": 180}, None),
            ("retrieve",  "retrieval.kb_search", "root", 1200, 2800,
             {"tool.name": "vector_search"}, None),
            ("jira",      "jira.issue_search",  "root", 4000, 700,
             {"tool.name": "jira_issue_search"}, None),
            ("crm",       "crm.account_lookup", "root", 4700, 1900,
             {"tool.name": "crm_account_lookup"}, None),
            ("crm_http",  "crm.http_call",      "crm",  4800, 800,
             {"url.full": "https://api.acme-crm-demo.example/v1/accounts"}, None),
            ("slack",     "slack.notify",       "root", 6600, 600,
             {"tool.name": "slack_channel_update"}, None),
            ("final",     "llm.response",       "root", 7200, 1200,
             {"gen_ai.system": "openai", "gen_ai.request.model": "gpt-4o",
              "gen_ai.usage.input_tokens": 1220, "gen_ai.usage.output_tokens": 420}, None),
        ],
    },
    {
        "service": "finance-analyst-agent",
        "environment": "production",
        "team": "finance",
        "steps": [
            ("root",     "finance analysis request", None,   0,    11200, {}, None),
            ("plan",     "llm.planning",        "root", 0,    1800,
             {"gen_ai.system": "anthropic", "gen_ai.request.model": "claude-sonnet-4-6",
              "gen_ai.usage.input_tokens": 900, "gen_ai.usage.output_tokens": 260}, None),
            ("docs",     "document.retrieval",  "root", 1800, 2400,
             {"tool.name": "document_retrieval"}, None),
            ("db",       "database.query",      "root", 4200, 3600,
             {"db.system": "postgresql", "db.name": "finance-dw-demo"}, None),
            ("calc",     "tool.python_calc",    "root", 7800, 1700,
             {"tool.name": "python_calculator"}, None),
            ("summary",  "llm.final_summary",   "root", 9500, 1700,
             {"gen_ai.system": "anthropic", "gen_ai.request.model": "claude-sonnet-4-6",
              "gen_ai.usage.input_tokens": 2100, "gen_ai.usage.output_tokens": 640}, None),
        ],
    },
    {
        "service": "engineering-copilot",
        "environment": "staging",
        "team": "engineering",
        "steps": [
            ("root",     "engineering copilot request", None,   0,    6200,
             {"workflow.name": "copilot-code-review"}, None),
            ("plan",     "llm.planning",        "root", 0,    900,
             {"gen_ai.system": "openai", "gen_ai.request.model": "gpt-4o",
              "gen_ai.usage.input_tokens": 480, "gen_ai.usage.output_tokens": 120}, None),
            ("repo",     "repo.context_lookup", "root", 900,  1300,
             {"tool.name": "github_repo_context"}, None),
            ("audit",    "repo.dependency_audit", "root", 1000, 300,
             {"tool.name": "pip_audit_check"}, None),
            ("mcp",      "mcp.tool_call",       "root", 2200, 1600,
             {"tool.name": "mcp_code_search", "mcp.server": "acme-mcp-hub"}, None),
            ("suggest",  "llm.code_suggestion", "root", 3800, 2400,
             {"gen_ai.system": "openai", "gen_ai.request.model": "gpt-4o",
              "gen_ai.usage.input_tokens": 1850, "gen_ai.usage.output_tokens": 560}, None),
        ],
    },
    {
        "service": "hr-onboarding-bot",
        "environment": "production",
        "team": "people-ops",
        "steps": [
            ("root",     "onboarding request",  None,   0,    4600, {}, None),
            ("kb",       "knowledge.lookup",    "root", 0,    1200,
             {"tool.name": "kb_knowledge_search"}, None),
            ("policy",   "llm.policy_response", "root", 1200, 1400,
             {"gen_ai.system": "anthropic", "gen_ai.request.model": "claude-haiku-4-5",
              "gen_ai.usage.input_tokens": 520, "gen_ai.usage.output_tokens": 210}, None),
            ("workflow", "servicenow.workflow", "root", 2600, 1300,
             {"tool.name": "servicenow_workflow_trigger"}, None),
            ("wf_http",  "servicenow.http_call", "workflow", 2700, 900,
             {"url.full": "https://acme.servicenow-demo.example/api/now/workflow"}, None),
            ("slack",    "slack.message",       "root", 3900, 700,
             {"tool.name": "slack_message_post"}, None),
        ],
    },
    {
        "service": "research-agent",
        "environment": "development",
        "team": "research",
        "steps": [
            ("root",     "research request",    None,   0,    7300, {}, None),
            ("search",   "tool.web_search",     "root", 0,    1700,
             {"tool.name": "web_search"}, None),
            ("api",      "external.api_lookup", "root", 1700, 2100,
             {"url.full": "https://api.research-source-demo.example/v2/lookup"},
             {"code": 2, "message": "upstream timeout (synthetic)"}),
            ("llm",      "llm.summarization",   "root", 3800, 3500,
             {"gen_ai.system": "openai", "gen_ai.request.model": "gpt-4o-mini",
              "gen_ai.usage.input_tokens": 2600, "gen_ai.usage.output_tokens": 780}, None),
        ],
    },
]


def _build_otlp_payload(system: dict, base_nano: int) -> dict:
    """Build an OTLP/HTTP JSON envelope for one demo system's trace."""
    service = system["service"]
    tid = _trace_id(service)

    spans = []
    for step_key, name, parent_key, offset_ms, duration_ms, attrs, status in system["steps"]:
        span: dict = {
            "traceId": tid,
            "spanId": _span_id(service, step_key),
            "name": name,
            "kind": 3,
            "startTimeUnixNano": base_nano + offset_ms * _MS,
            "endTimeUnixNano": base_nano + (offset_ms + duration_ms) * _MS,
            "status": status or {},
            "attributes": [
                {
                    "key": k,
                    "value": ({"intValue": v} if isinstance(v, int) else {"stringValue": str(v)}),
                }
                for k, v in attrs.items()
            ],
        }
        if parent_key:
            span["parentSpanId"] = _span_id(service, parent_key)
        spans.append(span)

    return {
        "resourceSpans": [{
            "resource": {"attributes": [
                {"key": "service.name",           "value": {"stringValue": service}},
                {"key": "agent.name",             "value": {"stringValue": service}},
                {"key": "deployment.environment", "value": {"stringValue": system["environment"]}},
                {"key": "team",                   "value": {"stringValue": system["team"]}},
                {"key": "service.version",        "value": {"stringValue": "1.0.0-demo"}},
            ]},
            "scopeSpans": [{"spans": spans}],
        }]
    }


def _get_or_create_org(db) -> tuple[Organization, bool]:
    org = db.query(Organization).filter(Organization.slug == DEMO_ORG_SLUG).first()
    if org:
        return org, False
    org = Organization(name=DEMO_ORG_NAME, slug=DEMO_ORG_SLUG)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org, True


def _get_or_create_user(db, org_id: int) -> tuple[User, bool]:
    from app.auth import hash_password

    user = db.query(User).filter(User.email == DEMO_USER_EMAIL).first()
    if user:
        return user, False
    user = User(
        email=DEMO_USER_EMAIL,
        name="Acme Demo Admin",
        hashed_password=hash_password(DEMO_USER_PASSWORD),
        organization_id=org_id,
        role="admin",
        team="platform",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, True


def seed() -> dict:
    """Run the demo seed. Returns a summary dict (also used by tests)."""
    from app.otel_parser import parse_otlp_json
    from app.otel_normalizer import normalize_spans
    from app.asset_intelligence import derive_asset_intelligence
    from app.roles import seed_roles_for_org

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        org, org_created = _get_or_create_org(db)
        seed_roles_for_org(db, org.id)
        user, user_created = _get_or_create_user(db, org.id)

        # Fixed step offsets/durations relative to a recent base so the demo
        # looks fresh on first seed; reruns skip existing traces entirely.
        base_dt = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
        base_nano = int(base_dt.timestamp() * 1e9)

        traces_seeded = 0
        traces_skipped = 0
        spans_ingested = 0

        for system in DEMO_SYSTEMS:
            tid = _trace_id(system["service"])
            exists = (
                db.query(OtelSpan.id)
                .filter(OtelSpan.organization_id == org.id, OtelSpan.trace_id == tid)
                .first()
            )
            if exists:
                # Re-running normalize_spans on the same payload would inflate
                # span/trace counters and duplicate provenance rows — skip.
                traces_skipped += 1
                continue

            payload = _build_otlp_payload(system, base_nano)
            parsed = parse_otlp_json(payload)
            result = normalize_spans(db, org.id, parsed)
            spans_ingested += result["spans_ingested"]
            traces_seeded += 1

        intel = derive_asset_intelligence(db, org.id)

        service_names = [s["service"] for s in DEMO_SYSTEMS]
        registry_count = (
            db.query(AssetRegistry)
            .filter(
                AssetRegistry.organization_id == org.id,
                AssetRegistry.agent_id_raw.in_(service_names),
            )
            .count()
        )
        otel_asset_rows = (
            db.query(OtelAsset)
            .filter(OtelAsset.organization_id == org.id, OtelAsset.service_name.in_(service_names))
            .all()
        )
        linked = sum(1 for a in otel_asset_rows if a.ai_asset_id is not None)
        cap_total = db.query(AssetCapability).filter(AssetCapability.organization_id == org.id).count()
        find_total = db.query(AssetFinding).filter(AssetFinding.organization_id == org.id).count()

        return {
            "org_id": org.id,
            "org_name": org.name,
            "org_created": org_created,
            "user_email": user.email,
            "user_created": user_created,
            "traces_seeded": traces_seeded,
            "traces_skipped": traces_skipped,
            "spans_ingested": spans_ingested,
            "otel_assets": len(otel_asset_rows),
            "otel_assets_linked": linked,
            "registry_assets": registry_count,
            "capabilities_created": intel["capabilities_created"],
            "capabilities_updated": intel["capabilities_updated"],
            "capabilities_total": cap_total,
            "findings_created": intel["findings_created"],
            "findings_updated": intel["findings_updated"],
            "findings_total": find_total,
        }
    finally:
        db.close()


def main() -> None:
    s = seed()
    print(f"""
Acme AI Operations demo seed
────────────────────────────
organization : {s['org_name']} (id={s['org_id']}, {'created' if s['org_created'] else 'reused'})
demo user    : {s['user_email']} ({'created' if s['user_created'] else 'reused'}) — password: {DEMO_USER_PASSWORD}
traces       : {s['traces_seeded']} seeded, {s['traces_skipped']} already present
spans        : {s['spans_ingested']} ingested
otel assets  : {s['otel_assets']} ({s['otel_assets_linked']} linked to asset_registry)
registry     : {s['registry_assets']} canonical inventory rows
capabilities : {s['capabilities_created']} new, {s['capabilities_updated']} refreshed ({s['capabilities_total']} total)
findings     : {s['findings_created']} new, {s['findings_updated']} refreshed ({s['findings_total']} total)

Open the dashboard and log in as {DEMO_USER_EMAIL} / {DEMO_USER_PASSWORD}:
  • Runtime            — 5 traces incl. one with an error span
  • Asset Intelligence — discovered assets, capabilities, findings
  • Agents / Inventory — the 5 discovered AI systems
All data is synthetic; no real prompts, responses, secrets, or PII.
""")


if __name__ == "__main__":
    main()
