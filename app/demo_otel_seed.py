"""
OTel demo seeding — org-parameterized, reusable from the CLI seed script
(scripts/seed_demo_data.py) and the platform-admin populate endpoint
(POST /admin/organizations/{id}/populate).

Seeds five realistic AI systems through the real ingestion pipeline:

    OTLP JSON → parse_otlp_json() → normalize_spans() → derive_asset_intelligence()

so every derived record (otel_spans, otel_assets, asset_registry linkage,
agent_relationships, provenance_events, asset_capabilities, asset_findings)
comes from production code paths. Privacy scrubbing is not bypassed.

All data is synthetic — no prompts, responses, secrets, or PII. Span
attributes carry only tool names, model names, token counts, and reserved
`.example` URLs.

Idempotent: trace/span IDs are deterministic per service, and traces already
present are skipped entirely (normalize_spans increments counters and writes
provenance on every call, so re-ingesting the same payload is avoided rather
than relied on).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

_MS = 1_000_000  # nanoseconds per millisecond


def demo_trace_id(service: str) -> str:
    return hashlib.sha256(f"acme-demo-trace:{service}".encode()).hexdigest()[:32]


def demo_span_id(service: str, step: str) -> str:
    return hashlib.sha256(f"acme-demo-span:{service}:{step}".encode()).hexdigest()[:16]


def _demo_asset_key(org_id: int, service: str) -> str:
    return hashlib.sha256(f"{org_id}:{service}".encode()).hexdigest()[:64]


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

DEMO_SERVICE_NAMES = [s["service"] for s in DEMO_SYSTEMS]


def build_otlp_payload(system: dict, base_nano: int) -> dict:
    """Build an OTLP/HTTP JSON envelope for one demo system's trace."""
    service = system["service"]
    tid = demo_trace_id(service)

    spans = []
    for step_key, name, parent_key, offset_ms, duration_ms, attrs, status in system["steps"]:
        span: dict = {
            "traceId": tid,
            "spanId": demo_span_id(service, step_key),
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
            span["parentSpanId"] = demo_span_id(service, parent_key)
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


def seed_otel_demo(db: Session, org_id: int) -> dict:
    """
    Seed the five demo AI systems into an organization via the real ingestion
    pipeline, then derive capabilities/findings. Idempotent — traces already
    present are skipped, and derivation uses application-level dedup.
    """
    from app.otel_parser import parse_otlp_json
    from app.otel_normalizer import normalize_spans
    from app.asset_intelligence import derive_asset_intelligence
    from app.models import OtelSpan

    # Fixed step offsets/durations relative to a recent base so the demo looks
    # fresh on first seed; reruns skip existing traces so the anchor never moves.
    base_dt = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
    base_nano = int(base_dt.timestamp() * 1e9)

    traces_seeded = 0
    traces_skipped = 0
    spans_ingested = 0

    for system in DEMO_SYSTEMS:
        tid = demo_trace_id(system["service"])
        exists = (
            db.query(OtelSpan.id)
            .filter(OtelSpan.organization_id == org_id, OtelSpan.trace_id == tid)
            .first()
        )
        if exists:
            traces_skipped += 1
            continue

        payload = build_otlp_payload(system, base_nano)
        parsed = parse_otlp_json(payload)
        result = normalize_spans(db, org_id, parsed)
        spans_ingested += result["spans_ingested"]
        traces_seeded += 1

    intel = derive_asset_intelligence(db, org_id)

    return {
        "otel_traces_seeded": traces_seeded,
        "otel_traces_skipped": traces_skipped,
        "otel_spans_ingested": spans_ingested,
        "capabilities_created": intel["capabilities_created"],
        "capabilities_updated": intel["capabilities_updated"],
        "findings_created": intel["findings_created"],
        "findings_updated": intel["findings_updated"],
    }


def clear_otel_demo(db: Session, org_id: int) -> dict:
    """
    Remove the seeded OTel demo data from an organization: spans, provenance,
    OTel evidence rows, derived capabilities/findings, relationships, and the
    OTel-discovered registry rows for the five demo services. Only rows keyed
    by the deterministic demo identifiers are touched.
    """
    from app.models import (
        AgentRelationship, AssetCapability, AssetFinding, AssetRegistry,
        OtelAsset, OtelSpan, ProvenanceEvent,
    )

    trace_ids = [demo_trace_id(s) for s in DEMO_SERVICE_NAMES]
    asset_keys = [_demo_asset_key(org_id, s) for s in DEMO_SERVICE_NAMES]

    spans_deleted = db.query(OtelSpan).filter(
        OtelSpan.organization_id == org_id,
        OtelSpan.trace_id.in_(trace_ids),
    ).delete(synchronize_session=False)

    prov_deleted = db.query(ProvenanceEvent).filter(
        ProvenanceEvent.organization_id == org_id,
        ProvenanceEvent.trace_id.in_(trace_ids),
    ).delete(synchronize_session=False)

    otel_assets_deleted = db.query(OtelAsset).filter(
        OtelAsset.organization_id == org_id,
        OtelAsset.service_name.in_(DEMO_SERVICE_NAMES),
    ).delete(synchronize_session=False)

    caps_deleted = db.query(AssetCapability).filter(
        AssetCapability.organization_id == org_id,
        AssetCapability.asset_key.in_(asset_keys),
    ).delete(synchronize_session=False)

    findings_deleted = db.query(AssetFinding).filter(
        AssetFinding.organization_id == org_id,
        AssetFinding.asset_key.in_(asset_keys),
    ).delete(synchronize_session=False)

    rels_deleted = db.query(AgentRelationship).filter(
        AgentRelationship.organization_id == org_id,
        AgentRelationship.source_agent_name.in_(DEMO_SERVICE_NAMES),
    ).delete(synchronize_session=False)

    # Only OTel-discovered registry rows — never gateway-discovered assets that
    # happen to share a name.
    registry_deleted = db.query(AssetRegistry).filter(
        AssetRegistry.organization_id == org_id,
        AssetRegistry.asset_key.in_(asset_keys),
        AssetRegistry.discovery_source == "otel_trace",
    ).delete(synchronize_session=False)

    return {
        "otel_spans_deleted": spans_deleted,
        "provenance_deleted": prov_deleted,
        "otel_assets_deleted": otel_assets_deleted,
        "capabilities_deleted": caps_deleted,
        "findings_deleted": findings_deleted,
        "otel_relationships_deleted": rels_deleted,
        "otel_registry_deleted": registry_deleted,
    }
