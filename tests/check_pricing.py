#!/usr/bin/env python3
"""
Pricing audit script — run manually to verify pricing integrity.

Usage:
    python tests/check_pricing.py              # audit only
    python tests/check_pricing.py --live       # also queries live telemetry DB for unknown models

What it checks:
  1. Every model in COST_PER_1M normalizes to itself (no keys are self-mangling)
  2. Known dated model strings normalize to a key that IS in the table
  3. The fallback is more expensive than the cheapest known model (conservative direction)
  4. PRICING_LAST_UPDATED is set and is a valid YYYY-MM-DD date
  5. calculate_cost returns (float, bool=False) for every known model
  6. calculate_cost returns (float, bool=True) for an unknown model
  7. If --live: scans the telemetry DB for model strings not in COST_PER_1M
"""
import os, sys, re, datetime, argparse

# ── env must be set before any app import ───────────────────────────────────
os.environ.setdefault("JWT_SECRET", "audit-check")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY",
                      "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
os.environ.setdefault("DATABASE_URL", os.environ.get("DATABASE_URL",
    "sqlite:////tmp/pricing_audit_scratch.db"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import (
    COST_PER_1M, _DEFAULT_PRICING, _normalize_model,
    calculate_cost, PRICING_LAST_UPDATED,
)

PASS  = "\033[32mPASS\033[0m"
FAIL  = "\033[31mFAIL\033[0m"
WARN  = "\033[33mWARN\033[0m"
INFO  = "\033[36mINFO\033[0m"

failures = []

def check(label, ok, detail=""):
    tag = PASS if ok else FAIL
    print(f"  [{tag}] {label}" + (f"  ({detail})" if detail else ""))
    if not ok:
        failures.append(label)


# ── 1. Every COST_PER_1M key is self-stable under normalization ─────────────
print("\n=== 1. Table key stability ===")
for key in COST_PER_1M:
    normalized = _normalize_model(key)
    check(
        f"Key {key!r} normalizes to itself",
        normalized == key,
        f"got {normalized!r}" if normalized != key else "",
    )

# ── 2. Known dated aliases resolve to a table entry ─────────────────────────
print("\n=== 2. Dated model string resolution ===")
DATED_ALIASES = [
    ("gpt-4o-mini-2024-07-18",    "gpt-4o-mini"),
    ("gpt-4o-2024-11-20",         "gpt-4o"),
    ("claude-haiku-4-5-20251001", "claude-haiku-4-5"),
    ("claude-sonnet-4-5-20251022","claude-sonnet-4-5"),
    ("o3-2025-04-16",             "o3"),
    ("gemini-1.5-pro-001",        None),   # non-date suffix — should NOT strip
]
for model_str, expected_base in DATED_ALIASES:
    normalized = _normalize_model(model_str)
    if expected_base is None:
        # should NOT have been stripped down to something unexpected
        in_table = normalized in COST_PER_1M or model_str in COST_PER_1M
        check(
            f"{model_str!r} → {normalized!r} (non-date suffix, lookup: {'hit' if in_table else 'miss'})",
            True,  # informational only
            "not in table — will use fallback" if not in_table else "in table",
        )
    else:
        check(
            f"{model_str!r} → {normalized!r} == {expected_base!r}",
            normalized == expected_base,
        )
        hit = normalized in COST_PER_1M
        check(
            f"  normalized key {normalized!r} is in COST_PER_1M",
            hit,
        )

# ── 3. Fallback is more expensive than the cheapest known model ─────────────
print("\n=== 3. Fallback direction ===")
cheapest_key   = min(COST_PER_1M, key=lambda k: COST_PER_1M[k]["prompt"])
cheapest_rate  = COST_PER_1M[cheapest_key]["prompt"]
fallback_rate  = _DEFAULT_PRICING["prompt"]
most_expensive_key  = max(COST_PER_1M, key=lambda k: COST_PER_1M[k]["completion"])
most_expensive_rate = COST_PER_1M[most_expensive_key]["completion"]
fallback_completion = _DEFAULT_PRICING["completion"]

check(
    f"Fallback prompt (${fallback_rate}) > cheapest table entry "
    f"{cheapest_key!r} (${cheapest_rate})",
    fallback_rate > cheapest_rate,
)
check(
    f"Fallback completion (${fallback_completion}) < most expensive table entry "
    f"{most_expensive_key!r} (${most_expensive_rate})",
    fallback_completion < most_expensive_rate,
    "EXPECTED — fallback underestimates frontier models; pricing_estimated flag mitigates",
)
print(f"  [{INFO}] Fallback is gpt-4o rates. "
      f"Models more expensive than fallback: ", end="")
above_fallback = [k for k, v in COST_PER_1M.items()
                  if v["completion"] > fallback_completion]
print(", ".join(above_fallback) if above_fallback else "none")

# ── 4. PRICING_LAST_UPDATED is valid ────────────────────────────────────────
print("\n=== 4. PRICING_LAST_UPDATED ===")
check("PRICING_LAST_UPDATED is non-empty", bool(PRICING_LAST_UPDATED))
try:
    dt = datetime.date.fromisoformat(PRICING_LAST_UPDATED)
    check(
        f"PRICING_LAST_UPDATED is valid YYYY-MM-DD ({PRICING_LAST_UPDATED})",
        True,
    )
    days_old = (datetime.date.today() - dt).days
    stale = days_old > 90
    check(
        f"Pricing table is {'STALE' if stale else 'current'} "
        f"(last updated {days_old} days ago)",
        not stale,
        f"Consider auditing provider pricing pages" if stale else "",
    )
except ValueError as e:
    check(f"PRICING_LAST_UPDATED parses as ISO date", False, str(e))

# ── 5. calculate_cost returns exact pricing for all known models ─────────────
print("\n=== 5. Known model cost calculation ===")
for model, rates in COST_PER_1M.items():
    cost, estimated = calculate_cost(model, 1_000_000, 1_000_000)
    expected = round(rates["prompt"] + rates["completion"], 8)
    check(
        f"{model}: cost={cost} estimated={estimated}",
        cost == expected and not estimated,
        f"expected cost={expected}" if cost != expected else "",
    )

# ── 6. Unknown model uses fallback and sets estimated=True ───────────────────
print("\n=== 6. Unknown model fallback ===")
unknown = "gpt-99-ultra-hypothetical"
cost, estimated = calculate_cost(unknown, 1_000_000, 1_000_000)
expected_fallback = round(_DEFAULT_PRICING["prompt"] + _DEFAULT_PRICING["completion"], 8)
check(f"Unknown model {unknown!r} → estimated=True", estimated)
check(f"Unknown model cost matches fallback rates (${expected_fallback})", cost == expected_fallback)

# ── 7. Live telemetry scan (optional) ───────────────────────────────────────
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--live", action="store_true")
args, _ = parser.parse_known_args()

if args.live:
    print("\n=== 7. Live telemetry — unknown model strings ===")
    try:
        from app.database import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT DISTINCT model, COUNT(*) as cnt FROM telemetry GROUP BY model ORDER BY cnt DESC")
            ).fetchall()
        if not rows:
            print(f"  [{INFO}] No telemetry rows found")
        else:
            print(f"  [{INFO}] {len(rows)} distinct model strings in telemetry:")
            for model_str, cnt in rows:
                normalized = _normalize_model(model_str)
                in_table = model_str in COST_PER_1M or normalized in COST_PER_1M
                tag = PASS if in_table else WARN
                label = "exact" if model_str in COST_PER_1M else (
                    f"via normalization ({normalized!r})" if in_table else "UNKNOWN — uses fallback"
                )
                print(f"    [{tag}] {model_str!r}  ({cnt} requests)  → {label}")
    except Exception as e:
        print(f"  [{WARN}] Could not query telemetry: {e}")
        print(f"         Set DATABASE_URL to your live DB and retry with --live")
else:
    print(f"\n  [{INFO}] Skipping live telemetry scan. "
          f"Run with --live to check actual model strings in your DB.")

# ── Summary ─────────────────────────────────────────────────────────────────
print()
print(f"{'='*55}")
table_count = len(COST_PER_1M)
if failures:
    print(f"\033[31m{len(failures)} check(s) FAILED:\033[0m")
    for f in failures:
        print(f"  - {f}")
else:
    print(f"\033[32mAll checks passed.\033[0m "
          f"({table_count} models in pricing table, "
          f"last updated {PRICING_LAST_UPDATED})")
print(f"{'='*55}\n")
sys.exit(1 if failures else 0)
