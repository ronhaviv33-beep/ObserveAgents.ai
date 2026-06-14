#!/usr/bin/env python3
"""
Seed demo telemetry data for the AI Asset Management dashboard.
Creates realistic telemetry records for 25+ demo agents across multiple teams.

Usage:
    python scripts/seed_demo_data.py
    python scripts/seed_demo_data.py --clear   # clear existing demo data first
"""
import argparse
import os
import random
import sys
from datetime import datetime, timezone, timedelta

# Allow running from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import engine, SessionLocal
from app.models import Base, Telemetry, Organization, User

random.seed(42)

DEMO_TEAMS = [
    "platform-ai",
    "customer-support",
    "risk-analytics",
    "trading-research",
    "route-optimization",
    "data-engineering",
    "product-ml",
]

DEMO_AGENTS = [
    # (name, team, activity_profile)
    ("support-triage-v2",       "customer-support",    "active_high"),
    ("doc-summarizer",          "platform-ai",         "active_medium"),
    ("code-reviewer",           "platform-ai",         "active_medium"),
    ("risk-classifier",         "risk-analytics",      "active_high"),
    ("trade-narrator",          "trading-research",    "active_very_high"),
    ("route-planner",           "route-optimization",  "active_medium"),
    ("invoice-extractor",       "risk-analytics",      "active_high_pii"),
    ("kb-rag-search",           "customer-support",    "active_medium"),
    ("research-deepdive",       "trading-research",    "active_large_tokens"),
    ("qa-test-generator",       "platform-ai",         "active_failing"),
    ("contract-analyzer",       "risk-analytics",      "active_pii_heavy"),
    ("email-classifier",        "customer-support",    "active_low"),
    ("market-sentiment",        "trading-research",    "active_high"),
    ("pipeline-monitor",        "data-engineering",    "active_after_hours"),
    ("feature-extractor",       "data-engineering",    "active_loop"),
    ("user-intent-detector",    "product-ml",          "active_medium"),
    ("churn-predictor",         "product-ml",          "active_low"),
    ("compliance-scanner",      "risk-analytics",      "active_blocked"),
    ("alert-correlator",        "platform-ai",         "dormant"),
    ("batch-embedder",          "data-engineering",    "dormant"),
    ("legacy-classifier",       "risk-analytics",      "inactive"),
    ("old-chatbot-v1",          "customer-support",    "inactive"),
    ("prototype-agent-x",       "product-ml",          "inactive"),
    ("hedge-optimizer",         "trading-research",    "active_premium"),
    ("supply-chain-ai",         "route-optimization",  "active_medium"),
]

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


def cost_usd(model, prompt_tokens, completion_tokens):
    in_rate, out_rate = MODEL_COSTS.get(model, (0.002, 0.008))
    return (prompt_tokens / 1000) * in_rate + (completion_tokens / 1000) * out_rate


def make_calls(agent_name, team, profile, org_id, now):
    calls = []

    def call(ts_offset_hours, model=None, pt=None, ct=None,
             sensitive=False, blocked=False, block_reason=None):
        ts = now - timedelta(hours=ts_offset_hours)
        m  = model or random.choice(MODELS[:4])
        p  = pt or random.randint(200, 2000)
        c  = ct or random.randint(100, 800)
        cost = cost_usd(m, p, c) if not blocked else 0.0
        calls.append(Telemetry(
            organization_id=org_id,
            team=team,
            agent=agent_name,
            model=m,
            prompt=f"[demo] {agent_name} call at T-{ts_offset_hours}h",
            response="" if blocked else f"[demo response for {agent_name}]",
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
        ))

    if profile == "active_high":
        for h in range(0, 168, 4):   # every 4h over 7 days
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
        # Night-time batch (2am–5am)
        for day in range(7):
            for hour_offset in range(3):
                ts_h = day * 24 + (2 + hour_offset)
                call(ts_h)

    elif profile == "active_loop":
        # 5-min rapid-fire burst (loop pattern)
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
            call(h, model="claude-opus-4-5", pt=random.randint(500, 3000), ct=random.randint(200, 1500))

    elif profile == "dormant":
        # Last call 10–25 days ago
        for offset_days in range(10, 25, 5):
            call(offset_days * 24)

    elif profile == "inactive":
        # Last call 35–60 days ago
        for offset_days in range(35, 60, 10):
            call(offset_days * 24)

    return calls


def seed(clear=False):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # Find or create the first organization
        org = db.query(Organization).first()
        if not org:
            print("No organization found. Please start the server first to seed the admin org.")
            return

        org_id = org.id
        print(f"Seeding demo data for org_id={org_id} ({org.name})")

        if clear:
            deleted = db.query(Telemetry).filter(
                Telemetry.organization_id == org_id,
                Telemetry.prompt.like("[demo]%"),
            ).delete(synchronize_session=False)
            db.commit()
            print(f"Cleared {deleted} existing demo records.")

        now = datetime.now(timezone.utc)
        total = 0
        for agent_name, team, profile in DEMO_AGENTS:
            agent_calls = make_calls(agent_name, team, profile, org_id, now)
            for c in agent_calls:
                db.add(c)
            total += len(agent_calls)
            print(f"  {agent_name:<30} team={team:<20} profile={profile:<25} calls={len(agent_calls)}")

        db.commit()
        print(f"\nSeeded {total} telemetry records for {len(DEMO_AGENTS)} agents.")
        print("\nNext steps:")
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
