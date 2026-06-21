#!/usr/bin/env python3
"""
Generate realistic AI traffic telemetry for the synthetic enterprise orgs.

Simulates a real organization using AI tools over multiple days:
  • Normal daily traffic with business-hours bias
  • High-volume spikes (3-5× normal on random days)
  • Spiky bursts (many calls within a 30-minute window)
  • Failed / policy-blocked requests
  • Security findings (fake credentials and PII)
  • Budget threshold hits and hard blocks

Usage:
    python scripts/generate_synthetic_traffic.py --org acme --days 7
    python scripts/generate_synthetic_traffic.py --all --days 30
    python scripts/generate_synthetic_traffic.py --org globex --days 7 --breach
    python scripts/generate_synthetic_traffic.py --org acme --days 1 --spiky
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

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
from app.models import Base, Organization, Telemetry, AssetRegistry, calculate_cost
from app.scanner import scan
from scripts.synthetic_payloads import PAYLOADS, NORMAL_PROMPTS

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("gen_traffic")

random.seed()  # use true random so each run is unique


# ─── Model / agent / team definitions ────────────────────────────────────────

AGENTS = [
    # (agent_id_raw, team, env, preferred_models, base_calls_per_day, token_profile)
    ("claude-code",              "developer", "staging",    ["claude-sonnet-4-5", "gpt-4.1"],          (3, 8),    "medium"),
    ("ci-agent",                 "developer", "staging",    ["gpt-4.1-mini", "gpt-4o-mini"],           (10, 25),  "small"),
    ("soc-assistant",            "security",  "production", ["claude-opus-4-5", "claude-sonnet-4-5"],  (4, 10),   "large"),
    ("product-analyst",          "product",   "production", ["gpt-4o", "gpt-4.1"],                     (2, 6),    "medium"),
    ("customer-support-chatbot", "support",   "production", ["gpt-4o", "gpt-4o-mini"],                 (20, 60),  "medium"),
    ("rag-assistant",            "support",   "production", ["gpt-4o", "gpt-4.1"],                     (8, 20),   "large"),
    ("security-copilot",         "security",  "staging",    ["gpt-4o", "claude-sonnet-4-5"],           (1, 4),    "large"),
    ("mcp-server-agent",         "developer", "dev",        ["gpt-4.1-mini"],                          (0, 1),    "small"),
]

TOKEN_PROFILES = {
    "small":  {"prompt": (200,  800),  "completion": (100, 400)},
    "medium": {"prompt": (500,  2000), "completion": (200, 800)},
    "large":  {"prompt": (1500, 8000), "completion": (500, 3000)},
}

# Models not in preferred lists that appear during spikes or cross-team testing
EXTRA_MODELS = ["gemini-2.5-pro", "gemini-2.5-flash", "gpt-4.1-nano"]


# ─── Traffic pattern definitions ─────────────────────────────────────────────

def _pick_model(preferred: list[str], allow_extra: bool = False) -> str:
    if allow_extra and random.random() < 0.08:
        return random.choice(EXTRA_MODELS)
    return random.choice(preferred)


def _asset_key(org_id: int, agent_id_raw: str) -> str:
    return hashlib.sha256(f"{org_id}:{agent_id_raw}".encode()).hexdigest()


def _tokens(profile: str) -> tuple[int, int]:
    p = TOKEN_PROFILES[profile]
    return random.randint(*p["prompt"]), random.randint(*p["completion"])


def _business_hour() -> int:
    if random.random() < 0.80:
        return random.randint(8, 19)
    return random.choice([0, 1, 2, 3, 4, 5, 6, 7, 20, 21, 22, 23])


# ─── Single telemetry row builder ────────────────────────────────────────────

def _build_row(
    org_id: int,
    agent_id: str,
    team: str,
    env: str,
    model: str,
    ts: datetime,
    profile: str,
    *,
    blocked: bool = False,
    block_reason: str | None = None,
    prompt_text: str | None = None,
    response_text: str | None = None,
) -> Telemetry:
    pt, ct = _tokens(profile)
    if blocked:
        ct = 0
        cost = 0.0
        estimated = False
    else:
        cost, estimated = calculate_cost(model, pt, ct)

    prompt = prompt_text or f"[synthetic] {agent_id} req {ts.isoformat()}"
    response = "" if blocked else (response_text or f"[synthetic] {agent_id} resp")

    # Run scanner for sensitive content detection
    if prompt_text or response_text:
        sr = scan((prompt_text or "") + " " + (response_text or ""))
        is_sensitive = sr.is_sensitive
        findings_json = json.dumps(sr.to_dict()) if sr.is_sensitive else None
    else:
        is_sensitive = False
        findings_json = None

    return Telemetry(
        organization_id=org_id,
        team=team,
        agent=agent_id,
        model=model,
        prompt=prompt,
        response=response,
        prompt_tokens=pt,
        completion_tokens=ct,
        total_tokens=pt + ct,
        latency_ms=random.uniform(10, 50) if blocked else random.uniform(150, 4000),
        cost_usd=cost,
        pricing_estimated=estimated,
        sensitive=is_sensitive,
        sensitive_findings=findings_json,
        blocked=blocked,
        block_reason=block_reason,
        timestamp=ts,
        asset_key=_asset_key(org_id, agent_id),
        agent_id_raw=agent_id,
        agent_version="1.0.0",
        team_raw=team,
        environment_raw=env,
    )


# ─── Day patterns ─────────────────────────────────────────────────────────────

def _normal_day(org_id: int, day: datetime) -> list[Telemetry]:
    rows = []
    for agent_id, team, env, models, cpd_range, profile in AGENTS:
        n = random.randint(*cpd_range)
        for _ in range(n):
            ts = day.replace(
                hour=_business_hour(),
                minute=random.randint(0, 59),
                second=random.randint(0, 59),
                microsecond=0,
            )
            model = _pick_model(models)
            blocked = random.random() < 0.03
            reason = "policy_violation" if blocked else None
            prompt_text = response_text = None
            if not blocked and random.random() < 0.02:
                payload = random.choice(list(PAYLOADS.values()))
                prompt_text = payload["prompt"]
                response_text = payload["response"]
            rows.append(_build_row(
                org_id, agent_id, team, env, model, ts, profile,
                blocked=blocked, block_reason=reason,
                prompt_text=prompt_text, response_text=response_text,
            ))
    return rows


def _high_volume_day(org_id: int, day: datetime) -> list[Telemetry]:
    """3–5× normal volume. Represents a batch job or campaign day."""
    rows = []
    for agent_id, team, env, models, cpd_range, profile in AGENTS:
        multiplier = random.uniform(3, 5)
        n = int(random.randint(*cpd_range) * multiplier)
        for _ in range(n):
            ts = day.replace(
                hour=random.randint(0, 23),
                minute=random.randint(0, 59),
                second=random.randint(0, 59),
                microsecond=0,
            )
            rows.append(_build_row(
                org_id, agent_id, team, env, _pick_model(models, allow_extra=True), ts, profile,
            ))
    return rows


def _spiky_day(org_id: int, day: datetime) -> list[Telemetry]:
    """Normal all day but with 1–3 burst windows (many calls in 30 min)."""
    rows = _normal_day(org_id, day)

    burst_windows = random.randint(1, 3)
    for _ in range(burst_windows):
        burst_hour = random.randint(9, 17)
        burst_start = day.replace(hour=burst_hour, minute=random.randint(0, 29), microsecond=0)
        burst_agent, burst_team, burst_env, burst_models, _, burst_profile = random.choice(AGENTS[:5])
        burst_count = random.randint(30, 80)

        for i in range(burst_count):
            ts = burst_start + timedelta(seconds=random.randint(0, 1800))
            rows.append(_build_row(
                org_id, burst_agent, burst_team, burst_env,
                _pick_model(burst_models), ts, burst_profile,
            ))

    return rows


def _security_findings_day(org_id: int, day: datetime) -> list[Telemetry]:
    """Normal day with ~15% of soc-assistant + chatbot calls containing sensitive data."""
    rows = _normal_day(org_id, day)

    sensitive_agents = {"soc-assistant", "customer-support-chatbot",
                        "rag-assistant", "security-copilot"}

    extra_security_rows = []
    for payload_key, payload in PAYLOADS.items():
        # Each finding type gets 2–3 instances across security agents
        for _ in range(random.randint(2, 3)):
            agent_id, team, env, models, _, profile = random.choice(
                [a for a in AGENTS if a[0] in sensitive_agents]
            )
            hour = _business_hour()
            ts = day.replace(
                hour=hour, minute=random.randint(0, 59),
                second=random.randint(0, 59), microsecond=0,
            )
            extra_security_rows.append(_build_row(
                org_id, agent_id, team, env,
                _pick_model(models), ts, profile,
                prompt_text=payload["prompt"],
                response_text=payload["response"],
            ))

    rows.extend(extra_security_rows)
    return rows


def _budget_breach_day(org_id: int, day: datetime) -> list[Telemetry]:
    """Day where customer-support-chatbot exceeds its daily budget."""
    rows = _normal_day(org_id, day)

    # Massive spike on the chatbot — enough to blow through daily limits
    chatbot = next(a for a in AGENTS if a[0] == "customer-support-chatbot")
    agent_id, team, env, models, _, profile = chatbot

    spike_count = random.randint(120, 200)
    blocked_after = random.randint(80, 110)

    for i in range(spike_count):
        ts = day.replace(
            hour=random.randint(10, 20),
            minute=random.randint(0, 59),
            second=random.randint(0, 59),
            microsecond=0,
        )
        blocked = i >= blocked_after
        reason = "budget_exceeded" if blocked else None
        rows.append(_build_row(
            org_id, agent_id, team, env,
            _pick_model(models), ts, profile,
            blocked=blocked, block_reason=reason,
        ))

    return rows


def _failed_requests_day(org_id: int, day: datetime) -> list[Telemetry]:
    """Higher-than-normal failure rate (10–20%) for chaos/stress testing."""
    rows = _normal_day(org_id, day)
    fail_rate = random.uniform(0.10, 0.20)
    for row in rows:
        if random.random() < fail_rate and not row.blocked:
            row.blocked = True
            row.block_reason = random.choice(["policy_violation", "budget_exceeded", "model_not_allowed"])
            row.completion_tokens = 0
            row.total_tokens = row.prompt_tokens
            row.cost_usd = 0.0
            row.response = ""
    return rows


# ─── Onboarding journey ───────────────────────────────────────────────────────

def _generate_onboarding_journey(org_id: int, now: datetime, days: int) -> list[list[Telemetry]]:
    """
    Generates traffic following the 7-day customer onboarding journey:
    Day 1: Org created (no traffic yet)
    Day 2: SDK connects, first telemetry arrives
    Day 3: Multiple agents discovered
    Day 4: Admin claims discovered agents (traffic continues normally)
    Day 5: Security findings appear
    Day 6: Budget warning then hard block
    Day 7: Dashboard full of demo-ready data
    """
    total_days = min(days, 7)
    days_by_pattern: list[tuple[str, Any]] = []

    if total_days >= 7:
        days_by_pattern = [
            ("none",     None),
            ("low",      None),
            ("normal",   None),
            ("high",     None),
            ("security", None),
            ("breach",   None),
            ("spiky",    None),
        ]
    else:
        for i in range(total_days):
            if i == total_days - 1:
                days_by_pattern.append(("spiky", None))
            elif i == total_days - 2:
                days_by_pattern.append(("breach", None))
            elif i == total_days - 3:
                days_by_pattern.append(("security", None))
            else:
                days_by_pattern.append(("normal", None))

    result = []
    for day_offset, (pattern, _) in enumerate(reversed(days_by_pattern)):
        day = (now - timedelta(days=day_offset)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        if pattern == "none":
            rows = []
        elif pattern == "low":
            rows = [
                _build_row(org_id, agent_id, team, env, _pick_model(models), day, profile)
                for agent_id, team, env, models, _, profile in AGENTS
                if agent_id not in ("mcp-server-agent",)
            ]
        elif pattern == "normal":
            rows = _normal_day(org_id, day)
        elif pattern == "high":
            rows = _high_volume_day(org_id, day)
        elif pattern == "security":
            rows = _security_findings_day(org_id, day)
        elif pattern == "breach":
            rows = _budget_breach_day(org_id, day)
        elif pattern == "spiky":
            rows = _spiky_day(org_id, day)
        else:
            rows = _normal_day(org_id, day)

        result.append((day, pattern, rows))

    return result


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--org", metavar="SLUG",
                        help="Target org by slug (acme | globex | cybertech)")
    parser.add_argument("--all", dest="all_orgs", action="store_true",
                        help="Generate traffic for all synthetic enterprise orgs")
    parser.add_argument("--days", type=int, default=7,
                        help="Number of days of traffic to generate (default: 7)")
    parser.add_argument("--spiky", action="store_true",
                        help="Force all days to use the spiky traffic pattern")
    parser.add_argument("--breach", action="store_true",
                        help="Force the last day to trigger a budget breach")
    parser.add_argument("--journey", action="store_true",
                        help="Use the structured 7-day onboarding journey pattern")
    parser.add_argument("--clear", action="store_true",
                        help="Delete existing synthetic telemetry for the org before generating")
    args = parser.parse_args()

    if not args.org and not args.all_orgs:
        parser.error("Specify --org SLUG or --all")

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    now = datetime.now(timezone.utc)

    KNOWN_SLUGS = ["acme", "globex", "cybertech"]
    slugs = KNOWN_SLUGS if args.all_orgs else [args.org]

    try:
        for slug in slugs:
            org = db.query(Organization).filter(Organization.slug == slug).first()
            if not org:
                log.warning("Org '%s' not found — run seed_synthetic_enterprise.py first", slug)
                continue

            org_id = org.id
            log.info("Generating traffic for '%s' (id=%d) over %d days", org.name, org_id, args.days)

            if args.clear:
                deleted = db.query(Telemetry).filter(
                    Telemetry.organization_id == org_id,
                    Telemetry.prompt.like("[synthetic]%"),
                ).delete(synchronize_session=False)
                db.commit()
                log.info("  Cleared %d synthetic telemetry rows", deleted)

            total_rows = 0
            total_sensitive = 0
            total_blocked = 0

            if args.journey:
                day_batches = _generate_onboarding_journey(org_id, now, args.days)
                for day, pattern, rows in reversed(day_batches):
                    for row in rows:
                        db.add(row)
                    db.commit()
                    s = sum(1 for r in rows if r.sensitive)
                    b = sum(1 for r in rows if r.blocked)
                    total_rows += len(rows)
                    total_sensitive += s
                    total_blocked += b
                    log.info("  %s  pattern=%-10s  rows=%4d  sensitive=%d  blocked=%d",
                             day.strftime("%Y-%m-%d"), pattern, len(rows), s, b)

            else:
                for day_offset in range(args.days - 1, -1, -1):
                    day = (now - timedelta(days=day_offset)).replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )

                    is_breach = args.breach and day_offset == 0
                    is_spiky = args.spiky
                    is_security = (day_offset == 2)

                    # Determine pattern for this day
                    if is_breach:
                        rows = _budget_breach_day(org_id, day)
                        pattern = "breach"
                    elif is_spiky:
                        rows = _spiky_day(org_id, day)
                        pattern = "spiky"
                    elif is_security:
                        rows = _security_findings_day(org_id, day)
                        pattern = "security"
                    else:
                        # Randomly choose a day type for variety
                        roll = random.random()
                        if roll < 0.10:
                            rows = _high_volume_day(org_id, day)
                            pattern = "high_volume"
                        elif roll < 0.15:
                            rows = _failed_requests_day(org_id, day)
                            pattern = "failures"
                        elif roll < 0.25:
                            rows = _spiky_day(org_id, day)
                            pattern = "spiky"
                        else:
                            rows = _normal_day(org_id, day)
                            pattern = "normal"

                    for row in rows:
                        db.add(row)
                    db.commit()

                    s = sum(1 for r in rows if r.sensitive)
                    b = sum(1 for r in rows if r.blocked)
                    total_rows += len(rows)
                    total_sensitive += s
                    total_blocked += b
                    log.info("  %s  pattern=%-12s  rows=%4d  sensitive=%d  blocked=%d",
                             day.strftime("%Y-%m-%d"), pattern, len(rows), s, b)

            print(f"\n  ✓ {org.name}: {total_rows} rows generated "
                  f"({total_sensitive} sensitive, {total_blocked} blocked)\n")

    finally:
        db.close()


if __name__ == "__main__":
    main()
