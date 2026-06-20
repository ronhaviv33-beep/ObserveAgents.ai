#!/usr/bin/env python3
"""
Seed demo telemetry data for the AI Asset Management dashboard.
Creates realistic telemetry records for 25 demo agents across multiple teams,
plus Phase 2 asset_registry rows with a realistic mix of lifecycle states.

Usage:
    python scripts/seed_demo_data.py
    python scripts/seed_demo_data.py --clear   # clear existing demo data first
"""
import argparse
import hashlib
import os
import random
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import engine, SessionLocal
from app.models import Base, Telemetry, AssetRegistry, Organization, User

random.seed(42)


def _ensure_phase2_columns():
    """Idempotent: add Phase 2 asset identity columns to telemetry if absent.
    Mirrors the migration in app/main.py so the seed script is self-contained."""
    from sqlalchemy import inspect as _inspect, text as _text
    with engine.connect() as conn:
        cols = {c["name"] for c in _inspect(engine).get_columns("telemetry")}
        for col_name, col_def in [
            ("asset_key",       "VARCHAR(64)"),
            ("agent_id_raw",    "VARCHAR(256)"),
            ("agent_version",   "VARCHAR(128)"),
            ("team_raw",        "VARCHAR(128)"),
            ("environment_raw", "VARCHAR(64)"),
        ]:
            if col_name not in cols:
                conn.execute(_text(f"ALTER TABLE telemetry ADD COLUMN {col_name} {col_def}"))
        conn.commit()

DEMO_TEAMS = [
    "platform-ai",
    "customer-support",
    "risk-analytics",
    "trading-research",
    "route-optimization",
    "data-engineering",
    "product-ml",
]

# (agent_id_raw, team_raw, profile, agent_version, environment_raw)
# team_raw / environment_raw = runtime hints from X-Guard-* headers (may differ from canonical)
DEMO_AGENTS = [
    ("support-triage-v2",    "customer-support",   "active_high",         "2.3.1",  "prod"),
    ("doc-summarizer",       "platform-ai",        "active_medium",       "1.5.0",  "prod"),
    ("code-reviewer",        "platform-ai",        "active_medium",       "3.0.2",  "prod"),
    ("risk-classifier",      "risk-analytics",     "active_high",         "1.4.0",  "prod"),
    ("trade-narrator",       "trading-research",   "active_very_high",    "3.1.2",  "prod"),
    ("route-planner",        "route-optimization", "active_medium",       "1.2.0",  "prod"),
    ("invoice-extractor",    "risk-analytics",     "active_high_pii",     "2.1.0",  "prod"),
    ("kb-rag-search",        "customer-support",   "active_medium",       "1.0.3",  "prod"),
    ("research-deepdive",    "trading-research",   "active_large_tokens", "1.1.0",  "staging"),
    ("qa-test-generator",    "platform-ai",        "active_failing",      "0.9.1",  "staging"),
    ("contract-analyzer",    "risk-analytics",     "active_pii_heavy",    "2.0.0",  "prod"),
    ("email-classifier",     "customer-support",   "active_low",          "1.3.0",  "prod"),
    ("market-sentiment",     "trading-research",   "active_high",         "2.2.0",  "prod"),
    # team_raw="data-eng" — a shortened alias; canonical registry team is "data-engineering"
    ("pipeline-monitor",     "data-eng",           "active_after_hours",  "1.0.0",  "prod"),
    ("feature-extractor",    "data-engineering",   "active_loop",         "0.8.0",  "staging"),
    ("user-intent-detector", "product-ml",         "active_medium",       "2.0.1",  "prod"),
    ("churn-predictor",      "product-ml",         "active_low",          "1.1.0",  "staging"),
    ("compliance-scanner",   "risk-analytics",     "active_blocked",      "1.2.5",  "prod"),
    ("alert-correlator",     "platform-ai",        "dormant",             "1.0.0",  "staging"),
    ("batch-embedder",       "data-engineering",   "dormant",             "2.3.0",  "staging"),
    ("legacy-classifier",    "risk-analytics",     "inactive",            "0.5.0",  "dev"),
    ("old-chatbot-v1",       "customer-support",   "inactive",            "1.0.0",  "dev"),
    ("prototype-agent-x",    "product-ml",         "inactive",            "0.1.0",  "dev"),
    ("hedge-optimizer",      "trading-research",   "active_premium",      "4.0.0",  "prod"),
    ("supply-chain-ai",      "route-optimization", "active_medium",       "1.8.0",  "prod"),
]

# Registry metadata per agent.
# lifecycle: "managed" | "unassigned" | "retired"
# registry_team overrides team_raw for canonical ownership (used for RBAC, display, filters).
# Unassigned / retired agents without owner/team show the discovery queue in action.
AGENT_REGISTRY = {
    "support-triage-v2": {
        "lifecycle": "managed",
        "owner": "alice@acme.ai",
        "registry_team": "customer-support",
        "environment": "prod",
        "criticality": "high",
        "business_purpose": "Routes incoming customer tickets to the correct support tier using intent classification.",
        "claimed_by": "alice@acme.ai",
        "claimed_days_ago": 45,
    },
    "doc-summarizer": {
        "lifecycle": "managed",
        "owner": "bob@acme.ai",
        "registry_team": "platform-ai",
        "environment": "prod",
        "criticality": "medium",
        "business_purpose": "Generates concise summaries of internal documentation and meeting notes.",
        "claimed_by": "bob@acme.ai",
        "claimed_days_ago": 30,
    },
    "code-reviewer": {
        "lifecycle": "managed",
        "owner": "bob@acme.ai",
        "registry_team": "platform-ai",
        "environment": "prod",
        "criticality": "medium",
        "business_purpose": "Performs automated code review for pull requests in the CI pipeline.",
        "claimed_by": "bob@acme.ai",
        "claimed_days_ago": 20,
    },
    "risk-classifier": {
        "lifecycle": "managed",
        "owner": "carol@acme.ai",
        "registry_team": "risk-analytics",
        "environment": "prod",
        "criticality": "critical",
        "business_purpose": "Classifies transaction risk in real-time for the fraud detection pipeline.",
        "claimed_by": "carol@acme.ai",
        "claimed_days_ago": 60,
    },
    "trade-narrator": {
        "lifecycle": "managed",
        "owner": "dave@acme.ai",
        "registry_team": "trading-research",
        "environment": "prod",
        "criticality": "high",
        "business_purpose": "Generates natural-language explanations of algorithmic trading decisions for compliance audit trails.",
        "claimed_by": "dave@acme.ai",
        "claimed_days_ago": 35,
    },
    "route-planner": {
        "lifecycle": "managed",
        "owner": "eve@acme.ai",
        "registry_team": "route-optimization",
        "environment": "prod",
        "criticality": "high",
        "business_purpose": "Optimizes last-mile delivery routes based on real-time traffic and capacity constraints.",
        "claimed_by": "eve@acme.ai",
        "claimed_days_ago": 25,
    },
    "invoice-extractor": {
        "lifecycle": "managed",
        "owner": "carol@acme.ai",
        "registry_team": "risk-analytics",
        "environment": "prod",
        "criticality": "critical",
        "business_purpose": "Extracts structured data from vendor invoices. Handles PII under active DPA; access restricted to risk-analytics.",
        "claimed_by": "carol@acme.ai",
        "claimed_days_ago": 50,
    },
    "kb-rag-search": {
        "lifecycle": "managed",
        "owner": "alice@acme.ai",
        "registry_team": "customer-support",
        "environment": "prod",
        "criticality": "medium",
        "business_purpose": "Retrieval-augmented search over the knowledge base, surfacing answers directly to support agents.",
        "claimed_by": "alice@acme.ai",
        "claimed_days_ago": 22,
    },
    "research-deepdive": {
        "lifecycle": "managed",
        "owner": "dave@acme.ai",
        "registry_team": "trading-research",
        "environment": "staging",
        "criticality": "high",
        "business_purpose": "Deep-research synthesis for market opportunity analysis; uses long-context frontier model.",
        "claimed_by": "dave@acme.ai",
        "claimed_days_ago": 15,
    },
    # qa-test-generator: discovered but not yet claimed — appears in unassigned queue
    "qa-test-generator": {
        "lifecycle": "unassigned",
    },
    "contract-analyzer": {
        "lifecycle": "managed",
        "owner": "carol@acme.ai",
        "registry_team": "risk-analytics",
        "environment": "prod",
        "criticality": "critical",
        "business_purpose": "Scans legal contracts for compliance violations and risk clauses. PII redacted before storage.",
        "claimed_by": "carol@acme.ai",
        "claimed_days_ago": 40,
    },
    "email-classifier": {
        "lifecycle": "managed",
        "owner": "alice@acme.ai",
        "registry_team": "customer-support",
        "environment": "prod",
        "criticality": "low",
        "business_purpose": "Classifies inbound customer emails by intent for automated queue routing.",
        "claimed_by": "alice@acme.ai",
        "claimed_days_ago": 18,
    },
    "market-sentiment": {
        "lifecycle": "managed",
        "owner": "dave@acme.ai",
        "registry_team": "trading-research",
        "environment": "prod",
        "criticality": "high",
        "business_purpose": "Aggregates and scores market sentiment from financial news and social signals.",
        "claimed_by": "dave@acme.ai",
        "claimed_days_ago": 28,
    },
    # pipeline-monitor: team_raw="data-eng" in telemetry headers, but canonical team corrected on claim
    "pipeline-monitor": {
        "lifecycle": "unassigned",
    },
    # feature-extractor: loop pattern detected — pending review in unassigned queue
    "feature-extractor": {
        "lifecycle": "unassigned",
    },
    "user-intent-detector": {
        "lifecycle": "managed",
        "owner": "frank@acme.ai",
        "registry_team": "product-ml",
        "environment": "prod",
        "criticality": "medium",
        "business_purpose": "Detects user intent signals from product interactions for personalization and feature flagging.",
        "claimed_by": "frank@acme.ai",
        "claimed_days_ago": 12,
    },
    # churn-predictor: low-activity staging agent, not yet claimed
    "churn-predictor": {
        "lifecycle": "unassigned",
    },
    "compliance-scanner": {
        "lifecycle": "managed",
        "owner": "carol@acme.ai",
        "registry_team": "risk-analytics",
        "environment": "prod",
        "criticality": "critical",
        "business_purpose": "Scans outbound communications in real-time for regulatory compliance violations (FINRA, SEC).",
        "claimed_by": "carol@acme.ai",
        "claimed_days_ago": 55,
    },
    # alert-correlator: dormant — discovered, not yet reviewed
    "alert-correlator": {
        "lifecycle": "unassigned",
    },
    # batch-embedder: dormant — in unassigned queue
    "batch-embedder": {
        "lifecycle": "unassigned",
    },
    # Retired agents — inactive, governance recorded for audit history
    "legacy-classifier": {
        "lifecycle": "retired",
        "owner": "carol@acme.ai",
        "registry_team": "risk-analytics",
        "environment": "dev",
        "criticality": "low",
        "business_purpose": "Legacy risk classifier replaced by risk-classifier v1.4. Retained for audit history.",
        "claimed_by": "carol@acme.ai",
        "claimed_days_ago": 90,
    },
    "old-chatbot-v1": {
        "lifecycle": "retired",
        "owner": "alice@acme.ai",
        "registry_team": "customer-support",
        "environment": "dev",
        "criticality": "low",
        "business_purpose": "First-generation customer support chatbot; superseded by support-triage-v2.",
        "claimed_by": "alice@acme.ai",
        "claimed_days_ago": 80,
    },
    "prototype-agent-x": {
        "lifecycle": "retired",
        "owner": "frank@acme.ai",
        "registry_team": "product-ml",
        "environment": "dev",
        "criticality": "low",
        "business_purpose": "Experimental prototype from the Q1 hackathon; never promoted to production.",
        "claimed_by": "frank@acme.ai",
        "claimed_days_ago": 70,
    },
    "hedge-optimizer": {
        "lifecycle": "managed",
        "owner": "dave@acme.ai",
        "registry_team": "trading-research",
        "environment": "prod",
        "criticality": "critical",
        "business_purpose": "Generates hedge ratios and portfolio rebalancing recommendations for the quant desk.",
        "claimed_by": "dave@acme.ai",
        "claimed_days_ago": 42,
    },
    "supply-chain-ai": {
        "lifecycle": "managed",
        "owner": "eve@acme.ai",
        "registry_team": "route-optimization",
        "environment": "prod",
        "criticality": "high",
        "business_purpose": "Predicts supply chain disruptions using lead-time signals and recommends mitigation actions.",
        "claimed_by": "eve@acme.ai",
        "claimed_days_ago": 33,
    },
}

MODELS = [
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4o",
    "claude-sonnet-4-5",
    "claude-haiku-4-5",
    "claude-opus-4-5",
    "gpt-4o-mini",
]

MODEL_COSTS = {
    "gpt-4.1":           (0.002,   0.008),
    "gpt-4.1-mini":      (0.0004,  0.0016),
    "gpt-4o":            (0.0025,  0.01),
    "claude-sonnet-4-5": (0.003,   0.015),
    "claude-haiku-4-5":  (0.0008,  0.004),
    "claude-opus-4-5":   (0.015,   0.075),
    "gpt-4o-mini":       (0.00015, 0.0006),
}


def _asset_key(org_id: int, agent_id_raw: str) -> str:
    return hashlib.sha256(f"{org_id}:{agent_id_raw}".encode()).hexdigest()


def cost_usd(model, prompt_tokens, completion_tokens):
    in_rate, out_rate = MODEL_COSTS.get(model, (0.002, 0.008))
    return (prompt_tokens / 1000) * in_rate + (completion_tokens / 1000) * out_rate


def make_calls(agent_id_raw, team_raw, profile, org_id, now,
               agent_version=None, environment_raw=None):
    calls = []
    key = _asset_key(org_id, agent_id_raw)

    def call(ts_offset_hours, model=None, pt=None, ct=None,
             sensitive=False, blocked=False, block_reason=None):
        ts = now - timedelta(hours=ts_offset_hours)
        m  = model or random.choice(MODELS[:4])
        p  = pt or random.randint(200, 2000)
        c  = ct or random.randint(100, 800)
        cost = cost_usd(m, p, c) if not blocked else 0.0
        calls.append(Telemetry(
            organization_id=org_id,
            team=team_raw,
            agent=agent_id_raw,
            model=m,
            prompt=f"[demo] {agent_id_raw} call at T-{ts_offset_hours}h",
            response="" if blocked else f"[demo response for {agent_id_raw}]",
            prompt_tokens=p,
            completion_tokens=c,
            total_tokens=p + c,
            latency_ms=random.uniform(300, 2500),
            cost_usd=cost,
            pricing_estimated=False,
            sensitive=sensitive,
            blocked=blocked,
            block_reason=block_reason,
            timestamp=ts,
            # Phase 2 identity fields
            asset_key=key,
            agent_id_raw=agent_id_raw,
            agent_version=agent_version,
            team_raw=team_raw,
            environment_raw=environment_raw,
        ))

    if profile == "active_high":
        for h in range(0, 168, 4):
            call(h + random.uniform(0, 3))

    elif profile == "active_very_high":
        for h in range(0, 168, 2):
            call(h, model="claude-opus-4-5", pt=3000, ct=1500)

    elif profile == "active_medium":
        for h in range(0, 120, 12):
            call(h + random.uniform(0, 8))

    elif profile == "active_low":
        for h in range(0, 72, 24):
            call(h)

    elif profile == "active_high_pii":
        for h in range(0, 120, 6):
            call(h, sensitive=random.random() < 0.3)

    elif profile == "active_large_tokens":
        for h in range(0, 72, 8):
            call(h, model="claude-opus-4-5", pt=45000, ct=3000)

    elif profile == "active_failing":
        for h in range(0, 48, 3):
            blocked_flag = random.random() < 0.4
            call(h, blocked=blocked_flag, block_reason="policy_violation" if blocked_flag else None)

    elif profile == "active_pii_heavy":
        for h in range(0, 96, 4):
            call(h, sensitive=True)

    elif profile == "active_after_hours":
        for day in range(7):
            for hour_offset in range(3):
                ts_h = day * 24 + (2 + hour_offset)
                call(ts_h)

    elif profile == "active_loop":
        # Rapid-fire burst triggering loop detection (5+ calls in a 5-min window)
        for i in range(20):
            call(random.uniform(1, 2), model="gpt-4.1-mini", pt=500, ct=200)
        for h in range(3, 96, 12):
            call(h)

    elif profile == "active_blocked":
        for h in range(0, 72, 6):
            is_blocked = random.random() < 0.5
            call(h, blocked=is_blocked, block_reason="budget_exceeded" if is_blocked else None)

    elif profile == "active_premium":
        for h in range(0, 48, 3):
            call(h, model="claude-opus-4-5",
                 pt=random.randint(500, 3000), ct=random.randint(200, 1500))

    elif profile == "dormant":
        for offset_days in range(10, 25, 5):
            call(offset_days * 24)

    elif profile == "inactive":
        for offset_days in range(35, 60, 10):
            call(offset_days * 24)

    return calls


def seed_registry(db, org_id, now):
    """Upsert AssetRegistry rows for every demo agent."""
    created = 0
    for agent_id_raw, team_raw, _profile, agent_version, environment_raw in DEMO_AGENTS:
        meta = AGENT_REGISTRY.get(agent_id_raw, {"lifecycle": "unassigned"})
        key  = _asset_key(org_id, agent_id_raw)

        existing = db.query(AssetRegistry).filter(
            AssetRegistry.organization_id == org_id,
            AssetRegistry.asset_key == key,
        ).first()

        lifecycle    = meta["lifecycle"]
        claimed_at   = None
        if meta.get("claimed_days_ago") is not None:
            claimed_at = now - timedelta(days=meta["claimed_days_ago"])

        if existing:
            # Refresh governance fields so re-seeding is idempotent
            existing.agent_id_raw      = agent_id_raw
            existing.agent_name        = agent_id_raw
            existing.status            = lifecycle
            existing.source            = "claimed" if lifecycle in ("managed", "retired") else "discovered"
            existing.owner             = meta.get("owner")
            existing.team              = meta.get("registry_team")
            existing.environment       = meta.get("environment")
            existing.criticality       = meta.get("criticality")
            existing.business_purpose  = meta.get("business_purpose")
            existing.claimed_by        = meta.get("claimed_by")
            existing.claimed_at        = claimed_at
        else:
            reg = AssetRegistry(
                organization_id=org_id,
                asset_key=key,
                agent_id_raw=agent_id_raw,
                agent_name=agent_id_raw,
                status=lifecycle,
                source="claimed" if lifecycle in ("managed", "retired") else "discovered",
                owner=meta.get("owner"),
                team=meta.get("registry_team"),
                environment=meta.get("environment"),
                criticality=meta.get("criticality"),
                business_purpose=meta.get("business_purpose"),
                claimed_by=meta.get("claimed_by"),
                claimed_at=claimed_at,
                first_seen_at=now - timedelta(days=90),
            )
            db.add(reg)
            created += 1

    db.commit()
    return created


def seed(clear=False):
    Base.metadata.create_all(bind=engine)
    _ensure_phase2_columns()
    db = SessionLocal()

    try:
        org = db.query(Organization).first()
        if not org:
            print("No organization found. Please start the server first to seed the admin org.")
            return

        org_id = org.id
        print(f"Seeding demo data for org_id={org_id} ({org.name})")

        if clear:
            deleted_t = db.query(Telemetry).filter(
                Telemetry.organization_id == org_id,
                Telemetry.prompt.like("[demo]%"),
            ).delete(synchronize_session=False)
            deleted_r = db.query(AssetRegistry).filter(
                AssetRegistry.organization_id == org_id,
            ).delete(synchronize_session=False)
            db.commit()
            print(f"Cleared {deleted_t} telemetry records and {deleted_r} registry rows.")

        now   = datetime.now(timezone.utc)
        total = 0

        managed_count    = 0
        unassigned_count = 0
        retired_count    = 0

        for agent_id_raw, team_raw, profile, agent_version, environment_raw in DEMO_AGENTS:
            agent_calls = make_calls(
                agent_id_raw, team_raw, profile, org_id, now,
                agent_version=agent_version,
                environment_raw=environment_raw,
            )
            for c in agent_calls:
                db.add(c)
            total += len(agent_calls)

            meta      = AGENT_REGISTRY.get(agent_id_raw, {"lifecycle": "unassigned"})
            lifecycle = meta["lifecycle"]
            if lifecycle == "managed":
                managed_count += 1
            elif lifecycle == "retired":
                retired_count += 1
            else:
                unassigned_count += 1

            registry_team = meta.get("registry_team", team_raw)
            print(
                f"  {agent_id_raw:<30} team_raw={team_raw:<20} "
                f"canonical={registry_team:<20} lifecycle={lifecycle:<10} "
                f"profile={profile:<25} calls={len(agent_calls)}"
            )

        db.commit()

        # Seed asset_registry
        created = seed_registry(db, org_id, now)
        print(
            f"\nSeeded {total} telemetry records for {len(DEMO_AGENTS)} agents.\n"
            f"Asset registry: {managed_count} managed, "
            f"{unassigned_count} unassigned, "
            f"{retired_count} retired "
            f"({created} new rows inserted).\n"
        )
        print("Lifecycle highlights:")
        print("  Managed (16): full governance metadata with owner, team, environment, criticality")
        print("  Unassigned (6): discovery queue — qa-test-generator, pipeline-monitor,")
        print("                  feature-extractor (loop detected), churn-predictor,")
        print("                  alert-correlator (dormant), batch-embedder (dormant)")
        print("  Retired (3): legacy-classifier, old-chatbot-v1, prototype-agent-x")
        print()
        print("Canonical override demo:")
        print("  pipeline-monitor  team_raw='data-eng' → registry team='data-engineering' (once claimed)")
        print("  research-deepdive environment_raw='staging' → registry environment='staging' (matched)")
        print()
        print("Next steps:")
        print("  python -m uvicorn app.main:app --reload")
        print("  cd dashboard && npm start")
        print("  http://localhost:5173  (or 3000)")

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo telemetry data")
    parser.add_argument("--clear", action="store_true", help="Clear existing demo data before seeding")
    args = parser.parse_args()
    seed(clear=args.clear)
